"""
Unit tests for Patient Silver transformer.
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd

from src.healthguard.silver.patient import transform_patient_batch, extract_patient_fields
from src.healthguard.silver.references import build_patient_lookup, resolve_patient_ref
from src.healthguard.silver.quarantine import QuarantineEngine, QuarantineReason, QuarantineRecord
from src.healthguard.silver.quality import DQEngine, QualityReport
from src.healthguard.silver.reconciliation import ReconciliationEngine, ReconciliationReport


@pytest.fixture
def sample_patient_resource():
    """Valid Patient FHIR resource."""
    return {
        "resourceType": "Patient",
        "id": "PAT001",
        "identifier": [{"system": "http://hospital.org/mrn", "value": "MRN12345"}],
        "name": [{"use": "official", "family": "Smith", "given": ["John"]}],
        "gender": "male",
        "birthDate": "1980-05-15",
        "deceasedBoolean": False,
        "address": [{"use": "home", "city": "Boston", "state": "MA"}],
        "telecom": [{"system": "phone", "value": "555-1234"}],
    }


@pytest.fixture
def sample_patient_invalid():
    """Patient missing required id field."""
    return {
        "resourceType": "Patient",
        "gender": "female",
        "birthDate": "1990-01-01",
    }


@pytest.fixture
def sample_patient_duplicate():
    """Duplicate Patient with same ID."""
    return {
        "resourceType": "Patient",
        "id": "PAT002",
        "gender": "female",
        "birthDate": "1990-01-01",
    }


@pytest.fixture
def bronze_root(tmp_path):
    """Create temporary Bronze root with test data."""
    root = tmp_path / "bronze"
    root.mkdir()
    return root


@pytest.fixture
def silver_root(tmp_path):
    """Create temporary Silver root."""
    root = tmp_path / "silver"
    root.mkdir()
    return root


@pytest.fixture
def quarantine_root(tmp_path):
    """Create temporary Quarantine root."""
    root = tmp_path / "quarantine"
    root.mkdir()
    return root


@pytest.fixture
def report_root(tmp_path):
    """Create temporary Report root."""
    root = tmp_path / "reports"
    root.mkdir()
    return root


@pytest.fixture
def batch_id():
    return "testbatch123"


@pytest.fixture
def ingestion_date():
    return "2026-01-15"


def create_bronze_patient_file(
    bronze_root: Path,
    ingestion_date: str,
    batch_id: str,
    resources: list[dict],
) -> Path:
    """Create a Bronze Patient Parquet file for testing."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    bronze_dir = bronze_root / f"resource_type=Patient" / f"ingestion_date={ingestion_date}"
    bronze_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for i, res in enumerate(resources):
        records.append({
            "batch_id": batch_id,
            "source_system": "SYNTHEA_FHIR",
            "source_file": "Patient.ndjson",
            "source_line": i + 1,
            "resource_type": "Patient",
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

    # Create manifest
    manifest_dir = bronze_root / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "batch_id": batch_id,
        "resource_counts": {"Patient": len(records)},
        "total_records": len(records),
    }
    with open(manifest_dir / f"manifest_{batch_id}.json", "w") as f:
        json.dump(manifest, f)

    return output_file


class TestPatientTransformer:
    """Tests for transform_patient_batch function."""

    def test_valid_patient_accepted(
        self, bronze_root, silver_root, quarantine_root, report_root, batch_id, ingestion_date, sample_patient_resource
    ):
        """Valid Patient resource should be accepted into Silver."""
        create_bronze_patient_file(bronze_root, ingestion_date, batch_id, [sample_patient_resource])

        result = transform_patient_batch(
            bronze_root=bronze_root,
            silver_root=silver_root,
            quarantine_root=quarantine_root,
            report_root=report_root,
            batch_id=batch_id,
            ingestion_date=ingestion_date,
        )

        assert result["status"] == "COMPLETED"
        assert result["accepted"] == 1
        assert result["quarantined"] == 0
        assert result["duplicates"] == 0

        # Verify Silver file exists and has correct data
        silver_file = silver_root / f"resource_type=Patient" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet"
        assert silver_file.exists()

        table = pq.read_table(str(silver_file))
        df = table.to_pandas()
        assert len(df) == 1
        assert df.iloc[0]["patient_id"] == "PAT001"
        assert df.iloc[0]["gender"] == "male"
        assert df.iloc[0]["birth_date"] == "1980-05-15"

    def test_missing_id_quarantined(
        self, bronze_root, silver_root, quarantine_root, report_root, batch_id, ingestion_date, sample_patient_invalid
    ):
        """Patient missing required id should be quarantined."""
        create_bronze_patient_file(bronze_root, ingestion_date, batch_id, [sample_patient_invalid])

        result = transform_patient_batch(
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

    def test_duplicate_suppressed(
        self, bronze_root, silver_root, quarantine_root, report_root, batch_id, ingestion_date, sample_patient_duplicate
    ):
        """Duplicate Patient ID should be suppressed (second one quarantined)."""
        resources = [sample_patient_duplicate, sample_patient_duplicate.copy()]
        create_bronze_patient_file(bronze_root, ingestion_date, batch_id, resources)

        result = transform_patient_batch(
            bronze_root=bronze_root,
            silver_root=silver_root,
            quarantine_root=quarantine_root,
            report_root=report_root,
            batch_id=batch_id,
            ingestion_date=ingestion_date,
        )

        assert result["status"] == "COMPLETED"
        assert result["accepted"] == 1
        assert result["duplicates"] == 1
        assert result["quarantined"] == 1

    def test_malformed_json_quarantined(
        self, bronze_root, silver_root, quarantine_root, report_root, batch_id, ingestion_date
    ):
        """Malformed JSON in raw_payload should be quarantined."""
        # Create Bronze with invalid JSON
        bronze_dir = bronze_root / f"resource_type=Patient" / f"ingestion_date={ingestion_date}"
        bronze_dir.mkdir(parents=True, exist_ok=True)

        records = [{
            "batch_id": batch_id,
            "source_system": "SYNTHEA_FHIR",
            "source_file": "Patient.ndjson",
            "source_line": 1,
            "resource_type": "Patient",
            "resource_id": "PAT003",
            "resource_version": "1",
            "source_last_updated": "2026-01-15T10:00:00Z",
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "raw_payload": "{ invalid json }",
            "parse_status": "VALID",
        }]

        import pyarrow as pa
        import pyarrow.parquet as pq
        table = pa.Table.from_pylist(records)
        output_file = bronze_dir / f"batch_{batch_id}.parquet"
        pq.write_table(table, str(output_file))

        result = transform_patient_batch(
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


class TestReferenceResolution:
    """Tests for reference resolution functions."""

    def test_resolve_patient_ref_valid(self):
        """Valid Patient reference resolves correctly."""
        lookup = {"PAT001": "SYNTHEA_FHIR:PAT001", "PAT002": "SYNTHEA_FHIR:PAT002"}
        assert resolve_patient_ref("Patient/PAT001", lookup) == "SYNTHEA_FHIR:PAT001"
        assert resolve_patient_ref("Patient/PAT002/_history/1", lookup) == "SYNTHEA_FHIR:PAT002"

    def test_resolve_patient_ref_not_found(self):
        """Missing reference returns None."""
        lookup = {"PAT001": "SYNTHEA_FHIR:PAT001"}
        assert resolve_patient_ref("Patient/PAT999", lookup) is None

    def test_resolve_patient_ref_invalid_format(self):
        """Invalid reference format returns None."""
        lookup = {"PAT001": "SYNTHEA_FHIR:PAT001"}
        assert resolve_patient_ref("Patient/", lookup) is None
        assert resolve_patient_ref("Encounter/PAT001", lookup) is None
        assert resolve_patient_ref(None, lookup) is None

    def test_build_patient_lookup(self):
        """Build lookup from Bronze records."""
        records = [
            {"resource_id": "PAT001"},
            {"resource_id": "PAT002"},
            {"resource_id": None},
        ]
        lookup = build_patient_lookup(records)
        assert lookup == {"PAT001": "SYNTHEA_FHIR:PAT001", "PAT002": "SYNTHEA_FHIR:PAT002"}


class TestQuarantineEngine:
    """Tests for QuarantineEngine."""

    def test_quarantine_and_flush(self, quarantine_root):
        """Records added to quarantine can be flushed to Parquet."""
        engine = QuarantineEngine(quarantine_root / "test", batch_size=2)

        record = QuarantineRecord(
            batch_id="batch1",
            resource_type="Patient",
            resource_id="PAT001",
            source_line=1,
            raw_payload='{"id": "PAT001"}',
            reason=QuarantineReason.MISSING_REQUIRED_FIELD,
            reason_detail="Missing id field",
        )
        engine.quarantine(record)
        engine.flush()

        # Verify file created
        parquet_files = list((quarantine_root / "test").rglob("*.parquet"))
        assert len(parquet_files) == 1

        # Verify content
        import pyarrow.parquet as pq
        table = pq.read_table(str(parquet_files[0]))
        assert len(table) == 1
        assert table.column("reason")[0].as_py() == "MISSING_REQUIRED_FIELD"

    def test_quarantine_summary(self, quarantine_root):
        """Get summary of quarantined records."""
        engine = QuarantineEngine(quarantine_root / "test2")

        engine.quarantine(QuarantineRecord(
            batch_id="b1", resource_type="Patient", resource_id="1", source_line=1,
            raw_payload="{}", reason=QuarantineReason.MISSING_REQUIRED_FIELD, reason_detail="test"
        ))
        engine.quarantine(QuarantineRecord(
            batch_id="b1", resource_type="Patient", resource_id="2", source_line=2,
            raw_payload="{}", reason=QuarantineReason.INVALID_REFERENCE, reason_detail="test"
        ))

        summary = engine.get_summary()
        assert summary["total_quarantined"] == 2
        assert summary["by_reason"]["MISSING_REQUIRED_FIELD"] == 1
        assert summary["by_reason"]["INVALID_REFERENCE"] == 1


class TestDQEngine:
    """Tests for Data Quality Engine."""

    def test_completeness_check(self, tmp_path, silver_root):
        """Completeness pillar checks required fields."""
        # Create Silver file with all required fields
        silver_dir = silver_root / "resource_type=Patient" / "ingestion_date=2026-01-15"
        silver_dir.mkdir(parents=True, exist_ok=True)
        silver_file = silver_dir / "batch_test.parquet"

        df = pd.DataFrame([{
            "patient_id": "PAT001",
            "gender": "male",
            "birth_date": "1980-01-01",
        }])
        import pyarrow as pa
        import pyarrow.parquet as pq
        pq.write_table(pa.Table.from_pandas(df), str(silver_file))

        engine = DQEngine()
        report = engine.assess_table(
            table_path=silver_file,
            resource_type="Patient",
            batch_id="test",
            primary_key="patient_id",
            required_fields=["patient_id", "gender", "birth_date"],
            enum_fields={"gender": ["male", "female", "other", "unknown"]},
            reference_fields={},
        )

        assert report.pillars[0].pillar == "Completeness"
        assert report.pillars[0].score == 1.0

    def test_uniqueness_check(self, silver_root):
        """Uniqueness pillar detects duplicate primary keys."""
        silver_dir = silver_root / "resource_type=Patient" / "ingestion_date=2026-01-15"
        silver_dir.mkdir(parents=True, exist_ok=True)
        silver_file = silver_dir / "batch_test2.parquet"

        df = pd.DataFrame([{
            "patient_id": "PAT001",
            "gender": "male",
        }, {
            "patient_id": "PAT001",  # Duplicate
            "gender": "female",
        }])
        import pyarrow as pa
        import pyarrow.parquet as pq
        pq.write_table(pa.Table.from_pandas(df), str(silver_file))

        engine = DQEngine()
        report = engine.assess_table(
            table_path=silver_file,
            resource_type="Patient",
            batch_id="test",
            primary_key="patient_id",
            required_fields=["patient_id"],
            enum_fields={},
            reference_fields={},
        )

        uniqueness = [p for p in report.pillars if p.pillar == "Uniqueness"][0]
        assert uniqueness.score < 1.0
        assert uniqueness.details["duplicate_count"] == 1


class TestReconciliationEngine:
    """Tests for ReconciliationEngine."""

    def test_reconciliation_balances(self, bronze_root, silver_root, quarantine_root, batch_id, ingestion_date, sample_patient_resource):
        """Reconciliation balances when all records accounted for."""
        create_bronze_patient_file(bronze_root, ingestion_date, batch_id, [sample_patient_resource])

        # Run transform to create Silver and Quarantine
        from src.healthguard.silver.patient import transform_patient_batch
        transform_patient_batch(
            bronze_root=bronze_root,
            silver_root=silver_root,
            quarantine_root=quarantine_root,
            report_root=bronze_root.parent / "reports",
            batch_id=batch_id,
            ingestion_date=ingestion_date,
        )

        # Check reconciliation
        recon = ReconciliationEngine()
        report = recon.reconcile_batch(
            batch_id=batch_id,
            resource_type="Patient",
            bronze_manifest_path=bronze_root / "manifests" / f"manifest_{batch_id}.json",
            silver_table_path=silver_root / f"resource_type=Patient" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet",
            quarantine_root=quarantine_root / "silver" / "Patient",
        )

        assert report.balances()
        assert report.discrepancy() == 0


def test_extract_patient_fields(sample_patient_resource):
    """Test field extraction from Patient resource."""
    extracted = extract_patient_fields(sample_patient_resource)
    assert extracted["patient_id"] == "PAT001"
    assert extracted["gender"] == "male"
    assert extracted["birth_date"] == "1980-05-15"
    assert extracted["deceased_boolean"] is False
    assert "identifiers" in extracted
    assert "names" in extracted