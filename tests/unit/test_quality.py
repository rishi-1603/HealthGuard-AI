"""
Unit tests for Data Quality Engine.
"""

import pytest
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.healthguard.silver.quality import DQEngine, QualityReport, PillarScore


@pytest.fixture
def silver_root(tmp_path):
    root = tmp_path / "silver"
    root.mkdir()
    return root


def create_silver_table(silver_root: Path, table_name: str, df: pd.DataFrame, batch_id: str = "test"):
    """Create a Silver Parquet table for testing."""
    table_dir = silver_root / f"resource_type={table_name}" / "ingestion_date=2026-01-15"
    table_dir.mkdir(parents=True, exist_ok=True)
    table_file = table_dir / f"batch_{batch_id}.parquet"
    pq.write_table(pa.Table.from_pandas(df), str(table_file))
    return table_file


class TestDQEngine:
    """Tests for DQEngine."""

    def test_completeness_all_required_present(self, silver_root):
        """Completeness pillar passes when all required fields present."""
        df = pd.DataFrame([{
            "patient_id": "PAT001",
            "gender": "male",
            "birth_date": "1980-01-01",
        }])
        table_file = create_silver_table(silver_root, "Patient", df)

        engine = DQEngine()
        report = engine.assess_table(
            table_path=table_file,
            resource_type="Patient",
            batch_id="test",
            primary_key="patient_id",
            required_fields=["patient_id", "gender", "birth_date"],
            enum_fields={"gender": ["male", "female", "other", "unknown"]},
            reference_fields={},
        )

        completeness = next(p for p in report.pillars if p.pillar == "Completeness")
        assert completeness.score == 1.0
        assert completeness.passed_checks == completeness.total_checks

    def test_completeness_missing_required_field(self, silver_root):
        """Completeness fails when required field missing."""
        df = pd.DataFrame([{
            "patient_id": "PAT001",
            # gender missing
            "birth_date": "1980-01-01",
        }])
        table_file = create_silver_table(silver_root, "Patient", df)

        engine = DQEngine()
        report = engine.assess_table(
            table_path=table_file,
            resource_type="Patient",
            batch_id="test",
            primary_key="patient_id",
            required_fields=["patient_id", "gender", "birth_date"],
            enum_fields={},
            reference_fields={},
        )

        completeness = next(p for p in report.pillars if p.pillar == "Completeness")
        assert completeness.score < 1.0

    def test_validity_enum_values(self, silver_root):
        """Validity pillar checks enum values."""
        df = pd.DataFrame([{
            "patient_id": "PAT001",
            "gender": "male",  # Valid enum
        }])
        table_file = create_silver_table(silver_root, "Patient", df)

        engine = DQEngine()
        report = engine.assess_table(
            table_path=table_file,
            resource_type="Patient",
            batch_id="test",
            primary_key="patient_id",
            required_fields=["patient_id"],
            enum_fields={"gender": ["male", "female", "other", "unknown"]},
            reference_fields={},
        )

        validity = next(p for p in report.pillars if p.pillar == "Validity")
        assert validity.score == 1.0

    def test_validity_invalid_enum(self, silver_root):
        """Validity fails on invalid enum value."""
        df = pd.DataFrame([{
            "patient_id": "PAT001",
            "gender": "invalid_gender",  # Not in enum
        }])
        table_file = create_silver_table(silver_root, "Patient", df)

        engine = DQEngine()
        report = engine.assess_table(
            table_path=table_file,
            resource_type="Patient",
            batch_id="test",
            primary_key="patient_id",
            required_fields=["patient_id"],
            enum_fields={"gender": ["male", "female", "other", "unknown"]},
            reference_fields={},
        )

        validity = next(p for p in report.pillars if p.pillar == "Validity")
        assert validity.score < 1.0

    def test_uniqueness_no_duplicates(self, silver_root):
        """Uniqueness passes with no duplicate PKs."""
        df = pd.DataFrame([{
            "patient_id": "PAT001",
            "gender": "male",
        }, {
            "patient_id": "PAT002",
            "gender": "female",
        }])
        table_file = create_silver_table(silver_root, "Patient", df)

        engine = DQEngine()
        report = engine.assess_table(
            table_path=table_file,
            resource_type="Patient",
            batch_id="test",
            primary_key="patient_id",
            required_fields=["patient_id"],
            enum_fields={},
            reference_fields={},
        )

        uniqueness = next(p for p in report.pillars if p.pillar == "Uniqueness")
        assert uniqueness.score == 1.0
        assert uniqueness.details["duplicate_count"] == 0

    def test_uniqueness_with_duplicates(self, silver_root):
        """Uniqueness fails with duplicate PKs."""
        df = pd.DataFrame([{
            "patient_id": "PAT001",
            "gender": "male",
        }, {
            "patient_id": "PAT001",  # Duplicate
            "gender": "female",
        }])
        table_file = create_silver_table(silver_root, "Patient", df)

        engine = DQEngine()
        report = engine.assess_table(
            table_path=table_file,
            resource_type="Patient",
            batch_id="test",
            primary_key="patient_id",
            required_fields=["patient_id"],
            enum_fields={},
            reference_fields={},
        )

        uniqueness = next(p for p in report.pillars if p.pillar == "Uniqueness")
        assert uniqueness.score < 1.0
        assert uniqueness.details["duplicate_count"] == 1

    def test_referential_integrity_valid(self, silver_root):
        """Referential integrity passes when all FKs resolve."""
        # Child table: Encounter with subject_id
        child_df = pd.DataFrame([{
            "encounter_id": "ENC001",
            "subject_id": "SYNTHEA_FHIR:PAT001",
            "status": "finished",
        }])
        child_file = create_silver_table(silver_root, "Encounter", child_df)

        # Parent table: Patient
        parent_df = pd.DataFrame([{
            "patient_id": "SYNTHEA_FHIR:PAT001",
            "gender": "male",
        }])
        parent_file = create_silver_table(silver_root, "Patient", parent_df)

        engine = DQEngine()
        report = engine.assess_table(
            table_path=child_file,
            resource_type="Encounter",
            batch_id="test",
            primary_key="encounter_id",
            required_fields=["encounter_id", "subject_id"],
            enum_fields={"status": ["planned", "arrived", "finished"]},
            reference_fields={
                "subject_id": {"parent_table": "Patient", "parent_key": "patient_id", "required": True}
            },
            parent_tables={"Patient": parent_file},
        )

        referential = next(p for p in report.pillars if p.pillar == "Referential Integrity")
        assert referential.score == 1.0

    def test_referential_integrity_orphaned(self, silver_root):
        """Referential integrity fails on orphaned FK."""
        child_df = pd.DataFrame([{
            "encounter_id": "ENC001",
            "subject_id": "SYNTHEA_FHIR:PAT999",  # Doesn't exist in parent
            "status": "finished",
        }])
        child_file = create_silver_table(silver_root, "Encounter", child_df)

        parent_df = pd.DataFrame([{
            "patient_id": "SYNTHEA_FHIR:PAT001",
            "gender": "male",
        }])
        parent_file = create_silver_table(silver_root, "Patient", parent_df)

        engine = DQEngine()
        report = engine.assess_table(
            table_path=child_file,
            resource_type="Encounter",
            batch_id="test",
            primary_key="encounter_id",
            required_fields=["encounter_id", "subject_id"],
            enum_fields={},
            reference_fields={
                "subject_id": {"parent_table": "Patient", "parent_key": "patient_id", "required": True}
            },
            parent_tables={"Patient": parent_file},
        )

        referential = next(p for p in report.pillars if p.pillar == "Referential Integrity")
        assert referential.score < 1.0
        assert referential.details["reference_results"]["subject_id"]["orphaned_count"] == 1

    def test_report_generation(self, silver_root, tmp_path):
        """QualityReport can be saved as JSON and Markdown."""
        df = pd.DataFrame([{"patient_id": "PAT001", "gender": "male"}])
        table_file = create_silver_table(silver_root, "Patient", df)

        engine = DQEngine()
        report = engine.assess_table(
            table_path=table_file,
            resource_type="Patient",
            batch_id="test",
            primary_key="patient_id",
            required_fields=["patient_id"],
            enum_fields={},
            reference_fields={},
        )

        json_file, md_file = engine.save_report(report, tmp_path / "dq_reports")

        assert json_file.exists()
        assert md_file.exists()

        # Verify JSON content
        import json
        with open(json_file) as f:
            data = json.load(f)
        assert data["table_name"] == "patient"
        assert data["batch_id"] == "test"

        # Verify Markdown content
        md_content = md_file.read_text()
        assert "Data Quality Report" in md_content
        assert "Completeness" in md_content


class TestQualityReport:
    """Tests for QualityReport dataclass."""

    def test_overall_score_calculation(self):
        """Overall score is weighted average of pillars."""
        pillars = [
            PillarScore("Completeness", 1.0, 3, 3, 0),
            PillarScore("Validity", 1.0, 2, 2, 0),
            PillarScore("Uniqueness", 0.5, 1, 0, 1),
            PillarScore("Referential Integrity", 1.0, 1, 1, 0),
        ]
        report = QualityReport(
            table_name="Patient",
            batch_id="test",
            generated_at="2026-01-15T10:00:00Z",
            overall_score=0.875,  # (1.0 + 1.0 + 0.5 + 1.0) / 4
            pillars=pillars,
            record_count=100,
        )

        # Default equal weights: 0.25 each
        expected = (1.0 + 1.0 + 0.5 + 1.0) / 4
        assert abs(report.overall_score - expected) < 0.01

    def test_to_markdown(self):
        """Markdown output contains all sections."""
        pillars = [
            PillarScore("Completeness", 1.0, 1, 1, 0),
            PillarScore("Validity", 0.8, 5, 4, 1),
        ]
        report = QualityReport(
            table_name="Patient",
            batch_id="test",
            generated_at="2026-01-15T10:00:00Z",
            overall_score=0.9,
            pillars=pillars,
            record_count=100,
        )

        md = report.to_markdown()
        assert "Data Quality Report: Patient" in md
        assert "Completeness" in md
        assert "Validity" in md
        assert "100" in md