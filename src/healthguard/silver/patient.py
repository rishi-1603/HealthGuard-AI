"""
Patient Transformer — Bronze → Silver for Patient resources.

Extracts structured fields from raw FHIR Patient payload, resolves references,
applies normalization, validates, and quarantines invalid records.
"""

import logging
import json
from pathlib import Path
from typing import Optional

import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd

from src.healthguard.silver.references import build_patient_lookup, resolve_references_in_record, load_contract
from src.healthguard.ingestion.source_validator import validate_resource, normalize_resource
from src.healthguard.silver.quarantine import QuarantineEngine, QuarantineReason
from src.healthguard.silver.quality import DQEngine
from src.healthguard.silver.reconciliation import ReconciliationEngine, ReconciliationReport

logger = logging.getLogger(__name__)


PATIENT_PK = "patient_id"


def extract_patient_fields(resource: dict) -> dict:
    """Extract and flatten Patient fields from FHIR resource."""
    extracted = {}

    # Direct fields
    extracted["patient_id"] = resource.get("id")
    extracted["gender"] = resource.get("gender")
    extracted["birth_date"] = resource.get("birthDate")
    extracted["deceased_boolean"] = resource.get("deceasedBoolean")
    extracted["deceased_datetime"] = resource.get("deceasedDateTime")
    extracted["marital_status"] = json.dumps(resource.get("maritalStatus")) if resource.get("maritalStatus") else None
    extracted["multiple_birth_boolean"] = resource.get("multipleBirthBoolean")
    extracted["multiple_birth_integer"] = resource.get("multipleBirthInteger")

    # Complex nested fields - store as JSON
    if resource.get("identifier"):
        extracted["identifiers"] = json.dumps(resource["identifier"])
    if resource.get("name"):
        extracted["names"] = json.dumps(resource["name"])
    if resource.get("address"):
        extracted["addresses"] = json.dumps(resource["address"])
    if resource.get("telecom"):
        extracted["telecoms"] = json.dumps(resource["telecom"])
    if resource.get("contact"):
        extracted["contacts"] = json.dumps(resource["contact"])
    if resource.get("communication"):
        extracted["communications"] = json.dumps(resource["communication"])
    if resource.get("generalPractitioner"):
        extracted["general_practitioners"] = json.dumps(resource["generalPractitioner"])
    if resource.get("managingOrganization"):
        extracted["managing_organization"] = json.dumps(resource["managingOrganization"])
    if resource.get("link"):
        extracted["links"] = json.dumps(resource["link"])
    if resource.get("photo"):
        extracted["photos"] = json.dumps(resource["photo"])

    return extracted


def transform_patient_batch(
    bronze_root: Path,
    silver_root: Path,
    quarantine_root: Path,
    report_root: Path,
    batch_id: str,
    ingestion_date: str,
) -> dict:
    """
    Transform Bronze Patient records to Silver.

    Args:
        bronze_root: Root of Bronze Parquet files
        silver_root: Root for Silver output
        quarantine_root: Root for Quarantine output
        report_root: Root for DQ/Reconciliation reports
        batch_id: Current batch ID
        ingestion_date: Ingestion date (YYYY-MM-DD)

    Returns:
        Dict with transformation statistics
    """
    # Paths
    bronze_path = bronze_root / f"resource_type=Patient" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet"
    silver_dir = silver_root / f"resource_type=Patient" / f"ingestion_date={ingestion_date}"
    silver_dir.mkdir(parents=True, exist_ok=True)
    silver_file = silver_dir / f"batch_{batch_id}.parquet"

    # Load Bronze
    if not bronze_path.exists():
        logger.warning(f"Bronze file not found: {bronze_path}")
        return {"status": "SKIPPED", "reason": "Bronze file not found"}

    bronze_table = pq.read_table(str(bronze_path))
    bronze_df = bronze_table.to_pandas()

    # Load all Patient records for reference resolution (self-lookup)
    patient_lookup = build_patient_lookup(bronze_df.to_dict("records"))

    # Initialize engines
    quarantine = QuarantineEngine(quarantine_root / "silver" / "Patient")
    dq_engine = DQEngine(quarantine)
    recon = ReconciliationEngine()

    # Contract
    contract = load_contract("Patient")
    required_fields = contract.get_required_fields()
    enum_fields = {
        f["target"]: f.get("enum", [])
        for f in contract.fields
        if f.get("enum")
    }
    reference_fields = {
        k: v for k, v in contract.reference_resolution.items()
    }

    # Process records
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

        # Parse raw payload
        try:
            resource = json.loads(raw_payload)
        except json.JSONDecodeError:
            quarantine.quarantine_from_bronze(
                row.to_dict(), batch_id, QuarantineReason.MALFORMED_JSON,
                "Failed to parse raw_payload as JSON"
            )
            stats["quarantined"] += 1
            continue

        # Validate
        validation = validate_resource(resource, "Patient")
        if not validation.is_valid:
            for error in validation.errors:
                reason = _map_error_to_reason(error)
                quarantine.quarantine_from_bronze(
                    row.to_dict(), batch_id, reason, error
                )
                stats["quarantined"] += 1
            continue

        # Check duplicate
        if resource_id in seen_ids:
            quarantine.quarantine_from_bronze(
                row.to_dict(), batch_id, QuarantineReason.DUPLICATE_SUPPRESSED,
                f"Duplicate patient_id: {resource_id}"
            )
            stats["duplicates"] += 1
            stats["quarantined"] += 1
            continue

        # Normalize
        normalized = normalize_resource(resource, "Patient")

        # Extract fields
        extracted = extract_patient_fields(normalized)

        # Build Silver record
        silver_record = {
            "batch_id": batch_id,
            "source_system": "SYNTHEA_FHIR",
            "source_line": source_line,
            "ingested_at": row["ingested_at"],
            "parse_status": "VALID",
            **extracted,
        }

        # Resolve references (Patient has no external references in core fields)
        silver_record = resolve_references_in_record(
            silver_record, "Patient", patient_lookup, {}
        )

        silver_records.append(silver_record)
        seen_ids.add(resource_id)
        stats["accepted"] += 1

    # Write Silver Parquet
    if silver_records:
        silver_df = pd.DataFrame(silver_records)
        table = pa.Table.from_pandas(silver_df)
        temp_file = silver_dir / f".temp_batch_{batch_id}.parquet"
        pq.write_table(table, str(temp_file))
        temp_file.rename(silver_file)
        logger.info(f"Wrote {len(silver_records)} Silver Patient records to {silver_file}")

    # Run DQ assessment
    if silver_records:
        dq_report = dq_engine.assess_table(
            table_path=silver_file,
            resource_type="Patient",
            batch_id=batch_id,
            primary_key=PATIENT_PK,
            required_fields=required_fields,
            enum_fields=enum_fields,
            reference_fields=reference_fields,
        )
        dq_engine.save_report(dq_report, report_root / "dq" / "Patient" / f"batch_{batch_id}")

    # Reconciliation
    bronze_manifest_path = bronze_root / "manifests" / f"manifest_{batch_id}.json"
    recon_report = recon.reconcile_batch(
        batch_id=batch_id,
        resource_type="Patient",
        bronze_manifest_path=bronze_manifest_path,
        silver_table_path=silver_file,
        quarantine_root=quarantine_root / "silver" / "Patient",
    )
    recon.save_report(recon_report, report_root / "reconciliation" / "Patient" / f"batch_{batch_id}")

    # Close quarantine
    quarantine.close()

    stats["status"] = "COMPLETED"
    return stats


def _map_error_to_reason(error: str) -> QuarantineReason:
    """Map validation error to quarantine reason."""
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
        return QuarantineReason.INVALID_REFERENCE
    return QuarantineReason.INVALID_DATA_TYPE


# CLI entry point
if __name__ == "__main__":
    import argparse
    from datetime import datetime, timezone

    parser = argparse.ArgumentParser(description="Transform Bronze Patient → Silver")
    parser.add_argument("--batch-id", required=True, help="Batch ID")
    parser.add_argument("--bronze-root", default="data/lakehouse/bronze", help="Bronze root path")
    parser.add_argument("--silver-root", default="data/lakehouse/silver", help="Silver root path")
    parser.add_argument("--quarantine-root", default="data/lakehouse/quarantine", help="Quarantine root path")
    parser.add_argument("--report-root", default="data/lakehouse/reports", help="Report root path")
    parser.add_argument("--ingestion-date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    result = transform_patient_batch(
        bronze_root=Path(args.bronze_root),
        silver_root=Path(args.silver_root),
        quarantine_root=Path(args.quarantine_root),
        report_root=Path(args.report_root),
        batch_id=args.batch_id,
        ingestion_date=args.ingestion_date,
    )

    print(json.dumps(result, indent=2))