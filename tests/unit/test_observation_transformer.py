"""
Unit tests for Observation Silver transformer.
"""

import pytest
import json
from pathlib import Path
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd

from src.healthguard.silver.observation import transform_observation_batch


@pytest.fixture
def sample_patient_resource():
    return {
        "resourceType": "Patient",
        "id": "PAT001",
        "gender": "female",
        "birthDate": "1985-03-20",
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
def sample_observation_vital():
    """Observation with valueQuantity (vital sign)."""
    return {
        "resourceType": "Observation",
        "id": "OBS001",
        "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4", "display": "Heart rate"}]},
        "subject": {"reference": "Patient/PAT001"},
        "encounter": {"reference": "Encounter/ENC001"},
        "effectiveDateTime": "2026-01-15T10:00:00Z",
        "valueQuantity": {"value": 72, "unit": "beats/min", "system": "http://unitsofmeasure.org", "code": "/min"},
    }


@pytest.fixture
def sample_observation_lab():
    """Observation with valueQuantity (lab result)."""
    return {
        "resourceType": "Observation",
        "id": "OBS002",
        "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "2345-7", "display": "Glucose [Mass/volume] in Serum"}]},
        "subject": {"reference": "Patient/PAT001"},
        "effectiveDateTime": "2026-01-15T08:00:00Z",
        "valueQuantity": {"value": 95, "unit": "mg/dL", "system": "http://unitsofmeasure.org", "code": "mg/dL"},
    }


@pytest.fixture
def sample_observation_categorical():
    """Observation with valueCodeableConcept."""
    return {
        "resourceType": "Observation",
        "id": "OBS003",
        "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "72166-2", "display": "Tobacco smoking status"}]},
        "subject": {"reference": "Patient/PAT001"},
        "valueCodeableConcept": {"coding": [{"system": "http://snomed.info/sct", "code": "266919005", "display": "Never smoked"}]},
    }


@pytest.fixture
def sample_observation_missing_subject():
    return {
        "resourceType": "Observation",
        "id": "OBS004",
        "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4", "display": "Heart rate"}]},
        "valueQuantity": {"value": 80, "unit": "beats/min"},
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
    return "testbatch999"


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


class TestObservationTransformer:
    """Tests for transform_observation_batch."""

    def test_multiple_value_types_accepted(
        self, bronze_root, silver_root, quarantine_root, report_root, batch_id, ingestion_date,
        sample_patient_resource, sample_encounter_resource,
        sample_observation_vital, sample_observation_lab, sample_observation_categorical
    ):
        """Observations with different value[x] types should all be accepted."""
        create_bronze_file(bronze_root, "Patient", ingestion_date, batch_id, [sample_patient_resource])
        create_bronze_file(bronze_root, "Encounter", ingestion_date, batch_id, [sample_encounter_resource])
        create_bronze_file(bronze_root, "Observation", ingestion_date, batch_id, [
            sample_observation_vital, sample_observation_lab, sample_observation_categorical
        ])

        from src.healthguard.silver.observation import transform_observation_batch
        result = transform_observation_batch(
            bronze_root=bronze_root,
            silver_root=silver_root,
            quarantine_root=quarantine_root,
            report_root=report_root,
            batch_id=batch_id,
            ingestion_date=ingestion_date,
        )

        assert result["status"] == "COMPLETED"
        assert result["accepted"] == 3

        # Verify all value types preserved
        silver_file = silver_root / f"resource_type=Observation" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet"
        table = pq.read_table(str(silver_file))
        df = table.to_pandas()
        assert len(df) == 3
        # Check vital signs
        vital = df[df["observation_id"] == "OBS001"].iloc[0]
        assert vital["value_quantity"] is not None
        # Check lab
        lab = df[df["observation_id"] == "OBS002"].iloc[0]
        assert lab["value_quantity"] is not None
        # Check categorical
        cat = df[df["observation_id"] == "OBS003"].iloc[0]
        assert cat["value_codeable_concept"] is not None

    def test_optional_encounter_reference(
        self, bronze_root, silver_root, quarantine_root, report_root, batch_id, ingestion_date,
        sample_patient_resource, sample_observation_vital
    ):
        """Observation without Encounter reference should be accepted (optional)."""
        # Remove encounter reference
        obs = sample_observation_vital.copy()
        obs.pop("encounter", None)

        create_bronze_file(bronze_root, "Patient", ingestion_date, batch_id, [sample_patient_resource])
        create_bronze_file(bronze_root, "Observation", ingestion_date, batch_id, [obs])

        from src.healthguard.silver.observation import transform_observation_batch
        result = transform_observation_batch(
            bronze_root=bronze_root,
            silver_root=silver_root,
            quarantine_root=quarantine_root,
            report_root=report_root,
            batch_id=batch_id,
            ingestion_date=ingestion_date,
        )

        assert result["status"] == "COMPLETED"
        assert result["accepted"] == 1

    def test_missing_subject_quarantined(
        self, bronze_root, silver_root, quarantine_root, report_root, batch_id, ingestion_date,
        sample_patient_resource, sample_observation_missing_subject
    ):
        """Observation missing required subject should be quarantined."""
        create_bronze_file(bronze_root, "Patient", ingestion_date, batch_id, [sample_patient_resource])
        create_bronze_file(bronze_root, "Observation", ingestion_date, batch_id, [sample_observation_missing_subject])

        from src.healthguard.silver.observation import transform_observation_batch
        result = transform_observation_batch(
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