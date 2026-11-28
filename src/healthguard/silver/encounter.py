"""
Encounter Transformer — Bronze → Silver for Encounter resources.

Extracts structured fields, resolves Patient reference, validates, quarantines.
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


ENCOUNTER_PK = "encounter_id"


def extract_encounter_fields(resource: dict) -> dict:
    """Extract and flatten Encounter fields from FHIR resource."""
    extracted = {}

    extracted["encounter_id"] = resource.get("id")
    extracted["status"] = resource.get("status")
    extracted["class"] = json.dumps(resource.get("class")) if resource.get("class") else None
    extracted["class_history"] = json.dumps(resource.get("classHistory")) if resource.get("classHistory") else None
    extracted["types"] = json.dumps(resource.get("type")) if resource.get("type") else None
    extracted["service_type"] = json.dumps(resource.get("serviceType")) if resource.get("serviceType") else None
    extracted["priority"] = json.dumps(resource.get("priority")) if resource.get("priority") else None

    # Subject (Patient reference) - handled by reference resolution
    extracted["subject"] = json.dumps(resource.get("subject")) if resource.get("subject") else None

    extracted["episode_of_care"] = json.dumps(resource.get("episodeOfCare")) if resource.get("episodeOfCare") else None
    extracted["based_on"] = json.dumps(resource.get("basedOn")) if resource.get("basedOn") else None
    extracted["participants"] = json.dumps(resource.get("participant")) if resource.get("participant") else None
    extracted["appointment"] = json.dumps(resource.get("appointment")) if resource.get("appointment") else None

    # Period
    period = resource.get("period", {})
    extracted["period_start"] = period.get("start")
    extracted["period_end"] = period.get("end")

    extracted["length"] = json.dumps(resource.get("length")) if resource.get("length") else None
    extracted["reason_codes"] = json.dumps(resource.get("reasonCode")) if resource.get("reasonCode") else None
    extracted["reason_references"] = json.dumps(resource.get("reasonReference")) if resource.get("reasonReference") else None
    extracted["diagnoses"] = json.dumps(resource.get("diagnosis")) if resource.get("diagnosis") else None
    extracted["accounts"] = json.dumps(resource.get("account")) if resource.get("account") else None
    extracted["hospitalization"] = json.dumps(resource.get("hospitalization")) if resource.get("hospitalization") else None
    extracted["locations"] = json.dumps(resource.get("location")) if resource.get("location") else None
    extracted["service_provider"] = json.dumps(resource.get("serviceProvider")) if resource.get("serviceProvider") else None
    extracted["part_of"] = json.dumps(resource.get("partOf")) if resource.get("partOf") else None

    # Identifiers
    if resource.get("identifier"):
        extracted["identifiers"] = json.dumps(resource["identifier"])

    return extracted


def transform_encounter_batch(
    bronze_root: Path,
    silver_root: Path,
    quarantine_root: Path,
    report_root: Path,
    batch_id: str,
    ingestion_date: str,
) -> dict:
    """
    Transform Bronze Encounter records to Silver.

    Requires Patient lookup for subject reference resolution.
    """
    bronze_path = bronze_root / f"resource_type=Encounter" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet"
    silver_dir = silver_root / f"resource_type=Encounter" / f"ingestion_date={ingestion_date}"
    silver_dir.mkdir(parents=True, exist_ok=True)
    silver_file = silver_dir / f"batch_{batch_id}.parquet"

    if not bronze_path.exists():
        logger.warning(f"Bronze file not found: {bronze_path}")
        return {"status": "SKIPPED", "reason": "Bronze file not found"}

    bronze_table = pq.read_table(str(bronze_path))
    bronze_df = bronze_table.to_pandas()

    # Build Patient lookup (need Bronze Patient from same batch)
    patient_bronze_path = bronze_root / f"resource_type=Patient" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet"
    patient_lookup = {}
    if patient_bronze_path.exists():
        patient_table = pq.read_table(str(patient_bronze_path))
        patient_df = patient_table.to_pandas()
        patient_lookup = build_patient_lookup(patient_df.to_dict("records"))

    # Build Encounter lookup for self-references (partOf)
    encounter_lookup = build_encounter_lookup(bronze_df.to_dict("records"))

    quarantine = QuarantineEngine(quarantine_root / "silver" / "Encounter")
    dq_engine = DQEngine(quarantine)
    recon = ReconciliationEngine()

    contract = load_contract("Encounter")
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

        validation = validate_resource(resource, "Encounter")
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
                f"Duplicate encounter_id: {resource_id}"
            )
            stats["duplicates"] += 1
            stats["quarantined"] += 1
            continue

        normalized = normalize_resource(resource, "Encounter")
        extracted = extract_encounter_fields(normalized)

        silver_record = {
            "batch_id": batch_id,
            "source_system": "SYNTHEA_FHIR",
            "source_line": source_line,
            "ingested_at": row["ingested_at"],
            "parse_status": "VALID",
            **extracted,
        }

        # Resolve references (subject -> Patient)
        silver_record = resolve_references_in_record(
            silver_record, "Encounter", patient_lookup, encounter_lookup
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
        logger.info(f"Wrote {len(silver_records)} Silver Encounter records to {silver_file}")

    if silver_records:
        dq_report = dq_engine.assess_table(
            table_path=silver_file,
            resource_type="Encounter",
            batch_id=batch_id,
            primary_key=ENCOUNTER_PK,
            required_fields=required_fields,
            enum_fields=enum_fields,
            reference_fields=reference_fields,
            parent_tables={
                "Patient": silver_root / f"resource_type=Patient" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet"
            },
        )
        dq_engine.save_report(dq_report, report_root / "dq" / "Encounter" / f"batch_{batch_id}")

    bronze_manifest_path = bronze_root / "manifests" / f"manifest_{batch_id}.json"
    recon_report = recon.reconcile_batch(
        batch_id=batch_id,
        resource_type="Encounter",
        bronze_manifest_path=bronze_manifest_path,
        silver_table_path=silver_file,
        quarantine_root=quarantine_root / "silver" / "Encounter",
    )
    recon.save_report(recon_report, report_root / "reconciliation" / "Encounter" / f"batch_{batch_id}")

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
        if "status" in error_lower:
            return QuarantineReason.MISSING_STATUS
        return QuarantineReason.MISSING_REQUIRED_FIELD
    if "reference" in error_lower:
        if "subject" in error_lower and "patient" in error_lower:
            return QuarantineReason.SUBJECT_NOT_PATIENT
        return QuarantineReason.INVALID_REFERENCE
    return QuarantineReason.INVALID_DATA_TYPE


if __name__ == "__main__":
    import argparse
    from datetime import datetime, timezone

    parser = argparse.ArgumentParser(description="Transform Bronze Encounter → Silver")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--bronze-root", default="data/lakehouse/bronze")
    parser.add_argument("--silver-root", default="data/lakehouse/silver")
    parser.add_argument("--quarantine-root", default="data/lakehouse/quarantine")
    parser.add_argument("--report-root", default="data/lakehouse/reports")
    parser.add_argument("--ingestion-date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    result = transform_encounter_batch(
        bronze_root=Path(args.bronze_root),
        silver_root=Path(args.silver_root),
        quarantine_root=Path(args.quarantine_root),
        report_root=Path(args.report_root),
        batch_id=args.batch_id,
        ingestion_date=args.ingestion_date,
    )

    print(json.dumps(result, indent=2))