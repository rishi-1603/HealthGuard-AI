"""
Unit tests for Encounter Silver transformer.
"""

import pytest
import json
from pathlib import Path
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd

from src.healthguard.silver.encounter import transform_encounter_batch
from src.healthguard.silver.references import build_patient_lookup, resolve_encounter_ref


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
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP", "display": "inpatient"},
        "subject": {"reference": "Patient/PAT001"},
        "period": {"start": "2026-01-15T08:00:00Z", "end": "2026-01-15T12:00:00Z"},
    }


@pytest.fixture
def sample_encounter_missing_subject():
    return {
        "resourceType": "Encounter",
        "id": "ENC002",
        "status": "finished",
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
    return "testbatch456"


@pytest.fixture
def ingestion_date():
    return "2026-01-15"


def create_bronze_file(bronze_root: Path, resource_type: str, ingestion_date: str, batch_id: str, resources: list[dict]):
    """Create Bronze Parquet file for any resource type."""
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

    # Manifest
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


class TestEncounterTransformer:
    """Tests for transform_encounter_batch."""

    def test_valid_encounter_with_patient_ref(
        self, bronze_root, silver_root, quarantine_root, report_root, batch_id, ingestion_date,
        sample_patient_resource, sample_encounter_resource
    ):
        """Encounter with valid Patient reference should be accepted."""
        create_bronze_file(bronze_root, "Patient", ingestion_date, batch_id, [sample_patient_resource])
        create_bronze_file(bronze_root, "Encounter", ingestion_date, batch_id, [sample_encounter_resource])

        from src.healthguard.silver.encounter import transform_encounter_batch
        result = transform_encounter_batch(
            bronze_root=bronze_root,
            silver_root=silver_root,
            quarantine_root=quarantine_root,
            report_root=report_root,
            batch_id=batch_id,
            ingestion_date=ingestion_date,
        )

        assert result["status"] == "COMPLETED"
        assert result["accepted"] == 1

        # Verify subject reference resolved
        silver_file = silver_root / f"resource_type=Encounter" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet"
        table = pq.read_table(str(silver_file))
        df = table.to_pandas()
        assert df.iloc[0]["subject_id"] == "SYNTHEA_FHIR:PAT001"

    def test_missing_subject_quarantined(
        self, bronze_root, silver_root, quarantine_root, report_root, batch_id, ingestion_date,
        sample_patient_resource, sample_encounter_missing_subject
    ):
        """Encounter missing subject should be quarantined."""
        create_bronze_file(bronze_root, "Patient", ingestion_date, batch_id, [sample_patient_resource])
        create_bronze_file(bronze_root, "Encounter", ingestion_date, batch_id, [sample_encounter_missing_subject])

        from src.healthguard.silver.encounter import transform_encounter_batch
        result = transform_encounter_batch(
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

    def test_duplicate_encounter_suppressed(
        self, bronze_root, silver_root, quarantine_root, report_root, batch_id, ingestion_date,
        sample_patient_resource, sample_encounter_resource
    ):
        """Duplicate Encounter ID should be suppressed."""
        create_bronze_file(bronze_root, "Patient", ingestion_date, batch_id, [sample_patient_resource])
        create_bronze_file(bronze_root, "Encounter", ingestion_date, batch_id, [sample_encounter_resource, sample_encounter_resource.copy()])

        from src.healthguard.silver.encounter import transform_encounter_batch
        result = transform_encounter_batch(
            bronze_root=bronze_root,
            silver_root=silver_root,
            quarantine_root=quarantine_root,
            report_root=report_root,
            batch_id=batch_id,
            ingestion_date=ingestion_date,
        )

        assert result["accepted"] == 1
        assert result["duplicates"] == 1


class TestEncounterReferenceResolution:
    """Tests for Encounter reference resolution."""

    def test_resolve_encounter_ref_valid(self):
        """Valid Encounter reference resolves correctly."""
        lookup = {"ENC001": "SYNTHEA_FHIR:ENC001", "ENC002": "SYNTHEA_FHIR:ENC002"}
        from src.healthguard.silver.references import resolve_encounter_ref
        assert resolve_encounter_ref("Encounter/ENC001", lookup) == "SYNTHEA_FHIR:ENC001"

    def test_build_encounter_lookup(self):
        """Build lookup from Bronze Encounter records."""
        from src.healthguard.silver.references import build_encounter_lookup
        records = [{"resource_id": "ENC001"}, {"resource_id": "ENC002"}]
        lookup = build_encounter_lookup(records)
        assert lookup == {"ENC001": "SYNTHEA_FHIR:ENC001", "ENC002": "SYNTHEA_FHIR:ENC002"}