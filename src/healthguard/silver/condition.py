"""
Condition Transformer — Bronze → Silver for Condition resources.

Extracts structured fields, resolves Patient and Encounter references, validates, quarantines.
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


CONDITION_PK = "condition_id"


def extract_condition_fields(resource: dict) -> dict:
    """Extract and flatten Condition fields from FHIR resource."""
    extracted = {}

    extracted["condition_id"] = resource.get("id")
    extracted["clinical_status"] = json.dumps(resource.get("clinicalStatus")) if resource.get("clinicalStatus") else None
    extracted["verification_status"] = json.dumps(resource.get("verificationStatus")) if resource.get("verificationStatus") else None
    extracted["categories"] = json.dumps(resource.get("category")) if resource.get("category") else None
    extracted["severity"] = json.dumps(resource.get("severity")) if resource.get("severity") else None
    extracted["code"] = json.dumps(resource.get("code")) if resource.get("code") else None
    extracted["body_sites"] = json.dumps(resource.get("bodySite")) if resource.get("bodySite") else None

    # Subject (Patient reference)
    extracted["subject"] = json.dumps(resource.get("subject")) if resource.get("subject") else None

    # Encounter reference (optional)
    extracted["encounter"] = json.dumps(resource.get("encounter")) if resource.get("encounter") else None

    # Onset
    extracted["onset_datetime"] = resource.get("onsetDateTime")
    extracted["onset_age"] = json.dumps(resource.get("onsetAge")) if resource.get("onsetAge") else None
    extracted["onset_period"] = json.dumps(resource.get("onsetPeriod")) if resource.get("onsetPeriod") else None
    extracted["onset_range"] = json.dumps(resource.get("onsetRange")) if resource.get("onsetRange") else None
    extracted["onset_string"] = resource.get("onsetString")

    # Abatement
    extracted["abatement_datetime"] = resource.get("abatementDateTime")
    extracted["abatement_age"] = json.dumps(resource.get("abatementAge")) if resource.get("abatementAge") else None
    extracted["abatement_period"] = json.dumps(resource.get("abatementPeriod")) if resource.get("abatementPeriod") else None
    extracted["abatement_range"] = json.dumps(resource.get("abatementRange")) if resource.get("abatementRange") else None
    extracted["abatement_string"] = resource.get("abatementString")

    extracted["recorded_date"] = resource.get("recordedDate")
    extracted["recorder"] = json.dumps(resource.get("recorder")) if resource.get("recorder") else None
    extracted["asserter"] = json.dumps(resource.get("asserter")) if resource.get("asserter") else None
    extracted["stages"] = json.dumps(resource.get("stage")) if resource.get("stage") else None
    extracted["evidence"] = json.dumps(resource.get("evidence")) if resource.get("evidence") else None
    extracted["notes"] = json.dumps(resource.get("note")) if resource.get("note") else None

    if resource.get("identifier"):
        extracted["identifiers"] = json.dumps(resource["identifier"])

    return extracted


def transform_condition_batch(
    bronze_root: Path,
    silver_root: Path,
    quarantine_root: Path,
    report_root: Path,
    batch_id: str,
    ingestion_date: str,
) -> dict:
    """Transform Bronze Condition records to Silver."""
    bronze_path = bronze_root / f"resource_type=Condition" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet"
    silver_dir = silver_root / f"resource_type=Condition" / f"ingestion_date={ingestion_date}"
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

    quarantine = QuarantineEngine(quarantine_root / "silver" / "Condition")
    dq_engine = DQEngine(quarantine)
    recon = ReconciliationEngine()

    contract = load_contract("Condition")
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

        validation = validate_resource(resource, "Condition")
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
                f"Duplicate condition_id: {resource_id}"
            )
            stats["duplicates"] += 1
            stats["quarantined"] += 1
            continue

        normalized = normalize_resource(resource, "Condition")
        extracted = extract_condition_fields(normalized)

        silver_record = {
            "batch_id": batch_id,
            "source_system": "SYNTHEA_FHIR",
            "source_line": source_line,
            "ingested_at": row["ingested_at"],
            "parse_status": "VALID",
            **extracted,
        }

        # Resolve references (subject -> Patient, encounter -> Encounter)
        silver_record = resolve_references_in_record(
            silver_record, "Condition", patient_lookup, encounter_lookup
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
        logger.info(f"Wrote {len(silver_records)} Silver Condition records to {silver_file}")

    if silver_records:
        dq_report = dq_engine.assess_table(
            table_path=silver_file,
            resource_type="Condition",
            batch_id=batch_id,
            primary_key=CONDITION_PK,
            required_fields=required_fields,
            enum_fields=enum_fields,
            reference_fields=reference_fields,
            parent_tables={
                "Patient": silver_root / f"resource_type=Patient" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet",
                "Encounter": silver_root / f"resource_type=Encounter" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet",
            },
        )
        dq_engine.save_report(dq_report, report_root / "dq" / "Condition" / f"batch_{batch_id}")

    bronze_manifest_path = bronze_root / "manifests" / f"manifest_{batch_id}.json"
    recon_report = recon.reconcile_batch(
        batch_id=batch_id,
        resource_type="Condition",
        bronze_manifest_path=bronze_manifest_path,
        silver_table_path=silver_file,
        quarantine_root=quarantine_root / "silver" / "Condition",
    )
    recon.save_report(recon_report, report_root / "reconciliation" / "Condition" / f"batch_{batch_id}")

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

    parser = argparse.ArgumentParser(description="Transform Bronze Condition → Silver")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--bronze-root", default="data/lakehouse/bronze")
    parser.add_argument("--silver-root", default="data/lakehouse/silver")
    parser.add_argument("--quarantine-root", default="data/lakehouse/quarantine")
    parser.add_argument("--report-root", default="data/lakehouse/reports")
    parser.add_argument("--ingestion-date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    result = transform_condition_batch(
        bronze_root=Path(args.bronze_root),
        silver_root=Path(args.silver_root),
        quarantine_root=Path(args.quarantine_root),
        report_root=Path(args.report_root),
        batch_id=args.batch_id,
        ingestion_date=args.ingestion_date,
    )

    print(json.dumps(result, indent=2))