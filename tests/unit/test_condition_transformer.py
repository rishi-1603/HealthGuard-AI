"""
Unit tests for Condition Silver transformer.
"""

import pytest
import json
from pathlib import Path
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd

from src.healthguard.silver.condition import transform_condition_batch


@pytest.fixture
def sample_patient_resource():
    return {
        "resourceType": "Patient",
        "id": "PAT001",
        "gender": "male",
        "birthDate": "1980-05-15",
    }


@pytest.fixture
def sample_encounter_resource():
    return {
        "resourceType": "Encounter",
        "id": "ENC001",
        "status": "finished",
        "subject": {"reference": "Patient/PAT001"},
    }


@pytest.fixture
def sample_condition_resource():
    return {
        "resourceType": "Condition",
        "id": "COND001",
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
        "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"}]},
        "code": {"coding": [{"system": "http://snomed.info/sct", "code": "44054006", "display": "Type 2 diabetes mellitus"}]},
        "subject": {"reference": "Patient/PAT001"},
        "encounter": {"reference": "Encounter/ENC001"},
    }


@pytest.fixture
def sample_condition_missing_code():
    return {
        "resourceType": "Condition",
        "id": "COND002",
        "subject": {"reference": "Patient/PAT001"},
    }


@pytest.fixture
def bronze_root(tmp_path):
    root = tmp_path / "bronze"
    root.mkdir()
    return root


@pytest.fixture
def silver_root(tmp_path):
    root = tmp_path / "silver"
    root.mkdir()
    return root


@pytest.fixture
def quarantine_root(tmp_path):
    root = tmp_path / "quarantine"
    root.mkdir()
    return root


@pytest.fixture
def report_root(tmp_path):
    root = tmp_path / "reports"
    root.mkdir()
    return root


@pytest.fixture
def batch_id():
    return "testbatch789"


@pytest.fixture
def ingestion_date():
    return "2026-01-15"


def create_bronze_file(bronze_root: Path, resource_type: str, ingestion_date: str, batch_id: str, resources: list[dict]):
    bronze_dir = bronze_root / f"resource_type={resource_type}" / f"ingestion_date={ingestion_date}"
    bronze_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for i, res in enumerate(resources):
        records.append({
            "batch_id": batch_id,
            "source_system": "SYNTHEA_FHIR",
            "source_file": f"{resource_type}.ndjson",
            "source_line": i + 1,
            "resource_type": resource_type,
            "resource_id": res.get("id"),
            "resource_version": "1",
            "source_last_updated": "2026-01-15T10:00:00Z",
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "raw_payload": json.dumps(res),
            "parse_status": "VALID",
        })

    table = pa.Table.from_pylist(records)
    output_file = bronze_dir / f"batch_{batch_id}.parquet"
    pq.write_table(table, str(output_file))

    manifest_dir = bronze_root / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "batch_id": batch_id,
        "resource_counts": {resource_type: len(records)},
        "total_records": len(records),
    }
    with open(manifest_dir / f"manifest_{batch_id}.json", "w") as f:
        json.dump(manifest, f)

    return output_file


class TestConditionTransformer:
    """Tests for transform_condition_batch."""

    def test_valid_condition_with_references(
        self, bronze_root, silver_root, quarantine_root, report_root, batch_id, ingestion_date,
        sample_patient_resource, sample_encounter_resource, sample_condition_resource
    ):
        """Condition with valid Patient and Encounter references should be accepted."""
        create_bronze_file(bronze_root, "Patient", ingestion_date, batch_id, [sample_patient_resource])
        create_bronze_file(bronze_root, "Encounter", ingestion_date, batch_id, [sample_encounter_resource])
        create_bronze_file(bronze_root, "Condition", ingestion_date, batch_id, [sample_condition_resource])

        from src.healthguard.silver.condition import transform_condition_batch
        result = transform_condition_batch(
            bronze_root=bronze_root,
            silver_root=silver_root,
            quarantine_root=quarantine_root,
            report_root=report_root,
            batch_id=batch_id,
            ingestion_date=ingestion_date,
        )

        assert result["status"] == "COMPLETED"
        assert result["accepted"] == 1

        # Verify references resolved
        silver_file = silver_root / f"resource_type=Condition" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet"
        table = pq.read_table(str(silver_file))
        df = table.to_pandas()
        assert df.iloc[0]["subject_id"] == "SYNTHEA_FHIR:PAT001"
        assert df.iloc[0]["encounter_id"] == "SYNTHEA_FHIR:ENC001"

    def test_missing_code_quarantined(
        self, bronze_root, silver_root, quarantine_root, report_root, batch_id, ingestion_date,
        sample_patient_resource, sample_condition_missing_code
    ):
        """Condition missing required code should be quarantined."""
        create_bronze_file(bronze_root, "Patient", ingestion_date, batch_id, [sample_patient_resource])
        create_bronze_file(bronze_root, "Condition", ingestion_date, batch_id, [sample_condition_missing_code])

        from src.healthguard.silver.condition import transform_condition_batch
        result = transform_condition_batch(
            bronze_root=bronze_root,
            silver_root=silver_root,
            quarantine_root=quarantine_root,
            report_root=report_root,
            batch_id=batch_id,
            ingestion_date=ingestion_date,
        )

        assert result["status"] == "COMPLETED"
        assert result["accepted"] == 0
        assert result["quarantined"] == 1

    def test_optional_encounter_reference(
        self, bronze_root, silver_root, quarantine_root, report_root, batch_id, ingestion_date,
        sample_patient_resource, sample_condition_resource
    ):
        """Condition without Encounter reference should still be accepted (optional)."""
        # Remove encounter reference
        cond = sample_condition_resource.copy()
        cond.pop("encounter", None)

        create_bronze_file(bronze_root, "Patient", ingestion_date, batch_id, [sample_patient_resource])
        create_bronze_file(bronze_root, "Condition", ingestion_date, batch_id, [cond])

        from src.healthguard.silver.condition import transform_condition_batch
        result = transform_condition_batch(
            bronze_root=bronze_root,
            silver_root=silver_root,
            quarantine_root=quarantine_root,
            report_root=report_root,
            batch_id=batch_id,
            ingestion_date=ingestion_date,
        )

        assert result["status"] == "COMPLETED"
        assert result["accepted"] == 1
        silver_file = silver_root / f"resource_type=Condition" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet"
        table = pq.read_table(str(silver_file))
        df = table.to_pandas()
        assert df.iloc[0]["encounter_id"] is None