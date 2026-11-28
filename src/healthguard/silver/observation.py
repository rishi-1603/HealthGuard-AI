"""
Observation Transformer — Bronze → Silver for Observation resources.

Extracts structured fields including all value[x] types, resolves Patient/Encounter references,
validates, quarantines.
"""

import logging
import json
from pathlib import Path
from typing import Optional

import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd

from src.healthguard.silver.references import build_patient_lookup, build_encounter_lookup, resolve_references_in_record, load_contract
from src.healthguard.ingestion.source_validator import validate_resource, normalize_resource
from src.healthguard.silver.quarantine import QuarantineEngine, QuarantineReason
from src.healthguard.silver.quality import DQEngine
from src.healthguard.silver.reconciliation import ReconciliationEngine

logger = logging.getLogger(__name__)


OBSERVATION_PK = "observation_id"


def extract_observation_fields(resource: dict) -> dict:
    """Extract and flatten Observation fields from FHIR resource, including all value[x] types."""
    extracted = {}

    extracted["observation_id"] = resource.get("id")
    extracted["status"] = resource.get("status")
    extracted["categories"] = json.dumps(resource.get("category")) if resource.get("category") else None
    extracted["code"] = json.dumps(resource.get("code")) if resource.get("code") else None

    # Subject (Patient reference)
    extracted["subject"] = json.dumps(resource.get("subject")) if resource.get("subject") else None

    # Encounter reference (optional)
    extracted["encounter"] = json.dumps(resource.get("encounter")) if resource.get("encounter") else None

    # Time
    extracted["effective_datetime"] = resource.get("effectiveDateTime")
    extracted["effective_period"] = json.dumps(resource.get("effectivePeriod")) if resource.get("effectivePeriod") else None
    extracted["effective_timing"] = json.dumps(resource.get("effectiveTiming")) if resource.get("effectiveTiming") else None
    extracted["issued"] = resource.get("issued")

    # Performers
    extracted["performers"] = json.dumps(resource.get("performer")) if resource.get("performer") else None

    # All value[x] representations - FHIR supports multiple
    extracted["value_quantity"] = json.dumps(resource.get("valueQuantity")) if resource.get("valueQuantity") else None
    extracted["value_codeable_concept"] = json.dumps(resource.get("valueCodeableConcept")) if resource.get("valueCodeableConcept") else None
    extracted["value_string"] = resource.get("valueString")
    extracted["value_boolean"] = resource.get("valueBoolean")
    extracted["value_integer"] = resource.get("valueInteger")
    extracted["value_range"] = json.dumps(resource.get("valueRange")) if resource.get("valueRange") else None
    extracted["value_ratio"] = json.dumps(resource.get("valueRatio")) if resource.get("valueRatio") else None
    extracted["value_sampled_data"] = json.dumps(resource.get("valueSampledData")) if resource.get("valueSampledData") else None
    extracted["value_time"] = resource.get("valueTime")
    extracted["value_datetime"] = resource.get("valueDateTime")
    extracted["value_period"] = json.dumps(resource.get("valuePeriod")) if resource.get("valuePeriod") else None
    extracted["data_absent_reason"] = json.dumps(resource.get("dataAbsentReason")) if resource.get("dataAbsentReason") else None

    extracted["interpretations"] = json.dumps(resource.get("interpretation")) if resource.get("interpretation") else None
    extracted["notes"] = json.dumps(resource.get("note")) if resource.get("note") else None
    extracted["body_site"] = json.dumps(resource.get("bodySite")) if resource.get("bodySite") else None
    extracted["method"] = json.dumps(resource.get("method")) if resource.get("method") else None
    extracted["specimen"] = json.dumps(resource.get("specimen")) if resource.get("specimen") else None
    extracted["device"] = json.dumps(resource.get("device")) if resource.get("device") else None
    extracted["reference_ranges"] = json.dumps(resource.get("referenceRange")) if resource.get("referenceRange") else None
    extracted["has_member"] = json.dumps(resource.get("hasMember")) if resource.get("hasMember") else None
    extracted["derived_from"] = json.dumps(resource.get("derivedFrom")) if resource.get("derivedFrom") else None
    extracted["components"] = json.dumps(resource.get("component")) if resource.get("component") else None

    if resource.get("identifier"):
        extracted["identifiers"] = json.dumps(resource["identifier"])
    if resource.get("basedOn"):
        extracted["based_on"] = json.dumps(resource["basedOn"])
    if resource.get("partOf"):
        extracted["part_of"] = json.dumps(resource["partOf"])
    if resource.get("focus"):
        extracted["focus"] = json.dumps(resource["focus"])

    return extracted


def transform_observation_batch(
    bronze_root: Path,
    silver_root: Path,
    quarantine_root: Path,
    report_root: Path,
    batch_id: str,
    ingestion_date: str,
) -> dict:
    """Transform Bronze Observation records to Silver."""
    bronze_path = bronze_root / f"resource_type=Observation" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet"
    silver_dir = silver_root / f"resource_type=Observation" / f"ingestion_date={ingestion_date}"
    silver_dir.mkdir(parents=True, exist_ok=True)
    silver_file = silver_dir / f"batch_{batch_id}.parquet"

    if not bronze_path.exists():
        logger.warning(f"Bronze file not found: {bronze_path}")
        return {"status": "SKIPPED", "reason": "Bronze file not found"}

    bronze_table = pq.read_table(str(bronze_path))
    bronze_df = bronze_table.to_pandas()

    # Build Patient lookup
    patient_bronze_path = bronze_root / f"resource_type=Patient" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet"
    patient_lookup = {}
    if patient_bronze_path.exists():
        patient_table = pq.read_table(str(patient_bronze_path))
        patient_df = patient_table.to_pandas()
        patient_lookup = build_patient_lookup(patient_df.to_dict("records"))

    # Build Encounter lookup
    encounter_bronze_path = bronze_root / f"resource_type=Encounter" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet"
    encounter_lookup = {}
    if encounter_bronze_path.exists():
        encounter_table = pq.read_table(str(encounter_bronze_path))
        encounter_df = encounter_table.to_pandas()
        encounter_lookup = build_encounter_lookup(encounter_df.to_dict("records"))

    quarantine = QuarantineEngine(quarantine_root / "silver" / "Observation")
    dq_engine = DQEngine(quarantine)
    recon = ReconciliationEngine()

    contract = load_contract("Observation")
    required_fields = contract.get_required_fields()
    enum_fields = {
        f["target"]: f.get("enum", [])
        for f in contract.fields
        if f.get("enum")
    }
    reference_fields = contract.reference_resolution

    silver_records = []
    seen_ids = set()
    stats = {
        "total_bronze": len(bronze_df),
        "accepted": 0,
        "quarantined": 0,
        "duplicates": 0,
    }

    for _, row in bronze_df.iterrows():
        raw_payload = row["raw_payload"]
        resource_id = row["resource_id"]
        source_line = row["source_line"]

        try:
            resource = json.loads(raw_payload)
        except json.JSONDecodeError:
            quarantine.quarantine_from_bronze(
                row.to_dict(), batch_id, QuarantineReason.MALFORMED_JSON,
                "Failed to parse raw_payload as JSON"
            )
            stats["quarantined"] += 1
            continue

        validation = validate_resource(resource, "Observation")
        if not validation.is_valid:
            for error in validation.errors:
                reason = _map_error_to_reason(error)
                quarantine.quarantine_from_bronze(
                    row.to_dict(), batch_id, reason, error
                )
                stats["quarantined"] += 1
            continue

        if resource_id in seen_ids:
            quarantine.quarantine_from_bronze(
                row.to_dict(), batch_id, QuarantineReason.DUPLICATE_SUPPRESSED,
                f"Duplicate observation_id: {resource_id}"
            )
            stats["duplicates"] += 1
            stats["quarantined"] += 1
            continue

        normalized = normalize_resource(resource, "Observation")
        extracted = extract_observation_fields(normalized)

        silver_record = {
            "batch_id": batch_id,
            "source_system": "SYNTHEA_FHIR",
            "source_line": source_line,
            "ingested_at": row["ingested_at"],
            "parse_status": "VALID",
            **extracted,
        }

        # Resolve references (subject -> Patient, encounter -> Encounter, performer -> Practitioner, device -> Device)
        silver_record = resolve_references_in_record(
            silver_record, "Observation", patient_lookup, encounter_lookup
        )

        silver_records.append(silver_record)
        seen_ids.add(resource_id)
        stats["accepted"] += 1

    if silver_records:
        silver_df = pd.DataFrame(silver_records)
        table = pa.Table.from_pandas(silver_df)
        temp_file = silver_dir / f".temp_batch_{batch_id}.parquet"
        pq.write_table(table, str(temp_file))
        temp_file.rename(silver_file)
        logger.info(f"Wrote {len(silver_records)} Silver Observation records to {silver_file}")

    if silver_records:
        dq_report = dq_engine.assess_table(
            table_path=silver_file,
            resource_type="Observation",
            batch_id=batch_id,
            primary_key=OBSERVATION_PK,
            required_fields=required_fields,
            enum_fields=enum_fields,
            reference_fields=reference_fields,
            parent_tables={
                "Patient": silver_root / f"resource_type=Patient" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet",
                "Encounter": silver_root / f"resource_type=Encounter" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet",
            },
        )
        dq_engine.save_report(dq_report, report_root / "dq" / "Observation" / f"batch_{batch_id}")

    bronze_manifest_path = bronze_root / "manifests" / f"manifest_{batch_id}.json"
    recon_report = recon.reconcile_batch(
        batch_id=batch_id,
        resource_type="Observation",
        bronze_manifest_path=bronze_manifest_path,
        silver_table_path=silver_file,
        quarantine_root=quarantine_root / "silver" / "Observation",
    )
    recon.save_report(recon_report, report_root / "reconciliation" / "Observation" / f"batch_{batch_id}")

    quarantine.close()
    stats["status"] = "COMPLETED"
    return stats


def _map_error_to_reason(error: str) -> QuarantineReason:
    error_lower = error.lower()
    if "missing required field" in error_lower:
        if "id" in error_lower:
            return QuarantineReason.MISSING_REQUIRED_FIELD
        if "subject" in error_lower:
            return QuarantineReason.MISSING_SUBJECT
        if "code" in error_lower:
            return QuarantineReason.MISSING_CODE
        if "status" in error_lower:
            return QuarantineReason.MISSING_STATUS
        return QuarantineReason.MISSING_REQUIRED_FIELD
    if "reference" in error_lower:
        if "subject" in error_lower and "patient" in error_lower:
            return QuarantineReason.SUBJECT_NOT_PATIENT
        if "encounter" in error_lower:
            return QuarantineReason.ENCOUNTER_NOT_ENCOUNTER
        return QuarantineReason.INVALID_REFERENCE
    return QuarantineReason.INVALID_DATA_TYPE


if __name__ == "__main__":
    import argparse
    from datetime import datetime, timezone

    parser = argparse.ArgumentParser(description="Transform Bronze Observation → Silver")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--bronze-root", default="data/lakehouse/bronze")
    parser.add_argument("--silver-root", default="data/lakehouse/silver")
    parser.add_argument("--quarantine-root", default="data/lakehouse/quarantine")
    parser.add_argument("--report-root", default="data/lakehouse/reports")
    parser.add_argument("--ingestion-date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    result = transform_observation_batch(
        bronze_root=Path(args.bronze_root),
        silver_root=Path(args.silver_root),
        quarantine_root=Path(args.quarantine_root),
        report_root=Path(args.report_root),
        batch_id=args.batch_id,
        ingestion_date=args.ingestion_date,
    )

    print(json.dumps(result, indent=2))