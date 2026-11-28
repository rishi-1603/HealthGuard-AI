"""
Unit tests for Reconciliation Engine.
"""

import pytest
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import json

from src.healthguard.silver.reconciliation import ReconciliationEngine, ReconciliationReport
from src.healthguard.silver.quarantine import QuarantineEngine, QuarantineRecord, QuarantineReason


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
def batch_id():
    return "recon_test_batch"


@pytest.fixture
def ingestion_date():
    return "2026-01-15"


def create_bronze_manifest(bronze_root: Path, batch_id: str, resource_counts: dict):
    """Create Bronze manifest file."""
    manifest_dir = bronze_root / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "batch_id": batch_id,
        "resource_counts": resource_counts,
        "total_records": sum(resource_counts.values()),
    }
    manifest_path = manifest_dir / f"manifest_{batch_id}.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f)
    return manifest_path


def create_silver_table(silver_root: Path, resource_type: str, ingestion_date: str, batch_id: str, records: list[dict]):
    """Create Silver Parquet table."""
    table_dir = silver_root / f"resource_type={resource_type}" / f"ingestion_date={ingestion_date}"
    table_dir.mkdir(parents=True, exist_ok=True)
    table_file = table_dir / f"batch_{batch_id}.parquet"
    df = pd.DataFrame(records)
    pq.write_table(pa.Table.from_pandas(df), str(table_file))
    return table_file


def create_quarantine_records(quarantine_root: Path, resource_type: str, batch_id: str, records: list[dict]):
    """Create quarantine Parquet files."""
    engine = QuarantineEngine(quarantine_root / "silver" / resource_type, batch_size=10)
    for r in records:
        engine.quarantine(QuarantineRecord(**r))
    engine.close()


class TestReconciliationReport:
    """Tests for ReconciliationReport dataclass."""

    def test_balances_when_accounted(self):
        """Balances when accounted equals source valid."""
        report = ReconciliationReport(
            batch_id="test",
            resource_type="Patient",
            generated_at="2026-01-15T10:00:00Z",
            source_valid=100,
            silver_accepted=90,
            silver_duplicates_suppressed=5,
            quarantined_total=5,
        )
        assert report.balances()
        assert report.discrepancy() == 0

    def test_discrepancy_when_missing(self):
        """Discrepancy when records unaccounted for."""
        report = ReconciliationReport(
            batch_id="test",
            resource_type="Patient",
            generated_at="2026-01-15T10:00:00Z",
            source_valid=100,
            silver_accepted=90,
            silver_duplicates_suppressed=0,
            quarantined_total=5,
        )
        assert not report.balances()
        assert report.discrepancy() == 5

    def test_to_markdown(self):
        """Markdown output contains all sections."""
        report = ReconciliationReport(
            batch_id="test",
            resource_type="Patient",
            generated_at="2026-01-15T10:00:00Z",
            source_valid=100,
            silver_accepted=95,
            silver_duplicates_suppressed=3,
            quarantined_total=2,
            quarantined_by_reason={"MISSING_REQUIRED_FIELD": 2},
        )
        md = report.to_markdown()
        assert "Reconciliation Report: Patient" in md
        assert "95" in md
        assert "MISSING_REQUIRED_FIELD" in md
        assert "BALANCED" in md or "✅" in md


class TestReconciliationEngine:
    """Tests for ReconciliationEngine."""

    def test_reconcile_batch_balances(
        self, bronze_root, silver_root, quarantine_root, batch_id, ingestion_date
    ):
        """Reconciliation balances when all records accounted."""
        # Bronze manifest
        create_bronze_manifest(bronze_root, batch_id, {"Patient": 10})

        # Silver: 8 accepted
        silver_records = [{"patient_id": f"PAT{i:03d}", "gender": "male"} for i in range(8)]
        create_silver_table(silver_root, "Patient", ingestion_date, batch_id, silver_records)

        # Quarantine: 2 records
        quarantine_records = [
            {"batch_id": batch_id, "resource_type": "Patient", "resource_id": "PAT001", "source_line": 1,
             "raw_payload": "{}", "reason": QuarantineReason.MISSING_REQUIRED_FIELD, "reason_detail": "test"},
            {"batch_id": batch_id, "resource_type": "Patient", "resource_id": "PAT002", "source_line": 2,
             "raw_payload": "{}", "reason": QuarantineReason.INVALID_REFERENCE, "reason_detail": "test"},
        ]
        create_quarantine_records(quarantine_root, "Patient", batch_id, quarantine_records)

        recon = ReconciliationEngine()
        report = recon.reconcile_batch(
            batch_id=batch_id,
            resource_type="Patient",
            bronze_manifest_path=bronze_root / "manifests" / f"manifest_{batch_id}.json",
            silver_table_path=silver_root / f"resource_type=Patient" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet",
            quarantine_root=quarantine_root / "silver" / "Patient",
        )

        assert report.balances()
        assert report.source_valid == 10
        assert report.silver_accepted == 8
        assert report.quarantined_total == 2

    def test_reconcile_with_duplicates(
        self, bronze_root, silver_root, quarantine_root, batch_id, ingestion_date
    ):
        """Duplicates in Silver are counted separately."""
        create_bronze_manifest(bronze_root, batch_id, {"Patient": 10})

        # Silver: 7 unique + 2 duplicates = 9 total rows
        silver_records = [{"patient_id": f"PAT{i:03d}", "gender": "male"} for i in range(7)]
        silver_records.append({"patient_id": "PAT001", "gender": "female"})  # Duplicate
        silver_records.append({"patient_id": "PAT002", "gender": "female"})  # Duplicate
        create_silver_table(silver_root, "Patient", ingestion_date, batch_id, silver_records)

        # Quarantine: 1 record
        quarantine_records = [
            {"batch_id": batch_id, "resource_type": "Patient", "resource_id": "PAT003", "source_line": 3,
             "raw_payload": "{}", "reason": QuarantineReason.MISSING_REQUIRED_FIELD, "reason_detail": "test"},
        ]
        create_quarantine_records(quarantine_root, "Patient", batch_id, quarantine_records)

        recon = ReconciliationEngine()
        report = recon.reconcile_batch(
            batch_id=batch_id,
            resource_type="Patient",
            bronze_manifest_path=bronze_root / "manifests" / f"manifest_{batch_id}.json",
            silver_table_path=silver_root / f"resource_type=Patient" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet",
            quarantine_root=quarantine_root / "silver" / "Patient",
        )

        assert report.silver_accepted == 7  # Unique count
        assert report.silver_duplicates_suppressed == 2
        assert report.quarantined_total == 1
        assert report.balances()

    def test_report_generation(self, bronze_root, silver_root, quarantine_root, batch_id, ingestion_date, tmp_path):
        """ReconciliationReport can be saved as JSON and Markdown."""
        create_bronze_manifest(bronze_root, batch_id, {"Patient": 5})
        create_silver_table(silver_root, "Patient", ingestion_date, batch_id, [{"patient_id": f"PAT{i:03d}"} for i in range(5)])

        recon = ReconciliationEngine()
        report = recon.reconcile_batch(
            batch_id=batch_id,
            resource_type="Patient",
            bronze_manifest_path=bronze_root / "manifests" / f"manifest_{batch_id}.json",
            silver_table_path=silver_root / f"resource_type=Patient" / f"ingestion_date={ingestion_date}" / f"batch_{batch_id}.parquet",
            quarantine_root=quarantine_root / "silver" / "Patient",
        )

        json_file, md_file = recon.save_report(report, tmp_path / "recon_reports")

        assert json_file.exists()
        assert md_file.exists()

        import json
        with open(json_file) as f:
            data = json.load(f)
        assert data["batch_id"] == batch_id
        assert data["resource_type"] == "Patient"