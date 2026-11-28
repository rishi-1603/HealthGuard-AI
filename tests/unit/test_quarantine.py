"""
Unit tests for Quarantine Engine.
"""

import pytest
from pathlib import Path
from src.healthguard.silver.quarantine import (
    QuarantineEngine,
    QuarantineRecord,
    QuarantineReason,
    load_quarantine_records,
)


@pytest.fixture
def quarantine_root(tmp_path):
    root = tmp_path / "quarantine"
    root.mkdir()
    return root


class TestQuarantineRecord:
    """Tests for QuarantineRecord dataclass."""

    def test_create_from_bronze_record(self):
        """Create quarantine record from Bronze record."""
        bronze = {
            "batch_id": "batch1",
            "resource_type": "Patient",
            "resource_id": "PAT001",
            "source_line": 42,
            "raw_payload": '{"id": "PAT001"}',
            "ingested_at": "2026-01-15T10:00:00Z",
        }

        record = QuarantineRecord.from_bronze_record(
            bronze, "batch1", QuarantineReason.MISSING_REQUIRED_FIELD, "Missing id field"
        )

        assert record.batch_id == "batch1"
        assert record.resource_type == "Patient"
        assert record.resource_id == "PAT001"
        assert record.source_line == 42
        assert record.reason == QuarantineReason.MISSING_REQUIRED_FIELD
        assert record.reason_detail == "Missing id field"
        assert record.severity == "ERROR"

    def test_to_dict(self):
        """Convert to dictionary."""
        record = QuarantineRecord(
            batch_id="batch1",
            resource_type="Patient",
            resource_id="PAT001",
            source_line=1,
            raw_payload="{}",
            reason=QuarantineReason.INVALID_REFERENCE,
            reason_detail="test",
        )
        d = record.to_dict()
        assert d["batch_id"] == "batch1"
        assert d["reason"] == "INVALID_REFERENCE"


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

    def test_quarantine_from_bronze(self, quarantine_root):
        """Convenience method quarantines from Bronze record."""
        engine = QuarantineEngine(quarantine_root / "test2", batch_size=10)

        bronze = {
            "batch_id": "batch1",
            "resource_type": "Encounter",
            "resource_id": "ENC001",
            "source_line": 5,
            "raw_payload": '{"id": "ENC001"}',
        }

        engine.quarantine_from_bronze(
            bronze, "batch1", QuarantineReason.INVALID_REFERENCE, "Subject not Patient"
        )
        engine.flush()

        import pyarrow.parquet as pq
        table = pq.read_table(str(list((quarantine_root / "test2").rglob("*.parquet"))[0]))
        assert len(table) == 1
        assert table.column("resource_type")[0].as_py() == "Encounter"

    def test_quarantine_summary(self, quarantine_root):
        """Get summary of quarantined records by reason."""
        engine = QuarantineEngine(quarantine_root / "test3")

        for reason in [QuarantineReason.MISSING_REQUIRED_FIELD, QuarantineReason.INVALID_REFERENCE, QuarantineReason.MISSING_REQUIRED_FIELD]:
            engine.quarantine(QuarantineRecord(
                batch_id="b1", resource_type="Patient", resource_id="1", source_line=1,
                raw_payload="{}", reason=reason, reason_detail="test"
            ))

        summary = engine.get_summary()
        assert summary["total_quarantined"] == 3
        assert summary["by_reason"]["MISSING_REQUIRED_FIELD"] == 2
        assert summary["by_reason"]["INVALID_REFERENCE"] == 1

    def test_partitioned_output(self, quarantine_root):
        """Quarantine output is partitioned by reason and date."""
        engine = QuarantineEngine(quarantine_root / "test4", batch_size=1)

        for i in range(3):
            engine.quarantine(QuarantineRecord(
                batch_id=f"b{i}", resource_type="Patient", resource_id=str(i), source_line=i,
                raw_payload="{}", reason=QuarantineReason.MISSING_REQUIRED_FIELD, reason_detail="test"
            ))
            engine.flush()

        # Should have 3 files (one per flush due to batch_size=1)
        parquet_files = list((quarantine_root / "test4").rglob("*.parquet"))
        assert len(parquet_files) == 3

    def test_close_flushes_remaining(self, quarantine_root):
        """close() flushes any remaining buffered records."""
        engine = QuarantineEngine(quarantine_root / "test5", batch_size=100)

        engine.quarantine(QuarantineRecord(
            batch_id="b1", resource_type="Patient", resource_id="1", source_line=1,
            raw_payload="{}", reason=QuarantineReason.MISSING_REQUIRED_FIELD, reason_detail="test"
        ))
        # Don't flush, just close
        engine.close()

        parquet_files = list((quarantine_root / "test5").rglob("*.parquet"))
        assert len(parquet_files) == 1


class TestLoadQuarantineRecords:
    """Tests for load_quarantine_records function."""

    def test_load_multiple_files(self, quarantine_root):
        """Load records from multiple Parquet files."""
        engine = QuarantineEngine(quarantine_root / "load_test", batch_size=2)

        for i in range(4):
            engine.quarantine(QuarantineRecord(
                batch_id=f"b{i}", resource_type="Patient", resource_id=str(i), source_line=i,
                raw_payload="{}", reason=QuarantineReason.MISSING_REQUIRED_FIELD, reason_detail="test"
            ))
        engine.close()

        records = load_quarantine_records(quarantine_root / "load_test")
        assert len(records) == 4
        assert all(r["resource_type"] == "Patient" for r in records)