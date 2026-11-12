"""Tests — Bronze ingestion layer.

Covers: file hash, schema validation, CSV loading, metadata columns,
idempotent reload, missing-file error.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from pipeline.bronze.ingestor import (
    compute_file_hash,
    load_bronze,
    read_raw_csv,
    validate_schema,
)
from pipeline.config import BRONZE_COLUMNS, PipelineConfig
from pipeline.warehouse import apply_ddl


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_cfg(tmp_path: Path) -> PipelineConfig:
    """PipelineConfig pointing at a temporary warehouse and real source CSV."""
    return PipelineConfig(
        warehouse_db=tmp_path / "test_warehouse.db",
        source_csv=Path("data/hospital/hospital_data.csv"),
        reports_dir=tmp_path / "reports",
    )


@pytest.fixture()
def ready_cfg(tmp_cfg: PipelineConfig) -> PipelineConfig:
    """Config with DDL already applied (tables exist)."""
    apply_ddl(tmp_cfg)
    return tmp_cfg


@pytest.fixture()
def minimal_csv(tmp_path: Path) -> Path:
    """Write a minimal valid CSV and return its path."""
    df = pd.DataFrame(
        {
            "Patient_ID": [1, 2, 3],
            "Age": [30, 45, 60],
            "Gender": ["Male", "Female", "Male"],
            "Condition": ["Diabetes", "Hypertension", "Asthma"],
            "Procedure": ["Insulin Therapy", "Blood Pressure Medication", "Inhaler"],
            "Cost": [5000, 8000, 3000],
            "Length_of_Stay": [3, 5, 2],
            "Readmission": ["No", "Yes", "No"],
            "Outcome": ["Recovered", "Stable", "Recovered"],
            "Satisfaction": [8, 7, 9],
        }
    )
    p = tmp_path / "minimal.csv"
    df.to_csv(p, index=False)
    return p


# ---------------------------------------------------------------------------
# Tests: file hash
# ---------------------------------------------------------------------------

class TestFileHash:
    def test_hash_is_hex_string(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("hello")
        h = compute_file_hash(f)
        assert isinstance(h, str)
        assert len(h) == 64

    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("data")
        b.write_text("data")
        assert compute_file_hash(a) == compute_file_hash(b)

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("data1")
        b.write_text("data2")
        assert compute_file_hash(a) != compute_file_hash(b)


# ---------------------------------------------------------------------------
# Tests: CSV reader
# ---------------------------------------------------------------------------

class TestReadRawCsv:
    def test_reads_expected_shape(self) -> None:
        df = read_raw_csv(Path("data/hospital/hospital_data.csv"))
        assert df.shape == (984, 10)

    def test_all_dtypes_are_object_at_bronze(self) -> None:
        """Bronze reads everything as str — no premature coercion."""
        df = read_raw_csv(Path("data/hospital/hospital_data.csv"))
        for col in df.columns:
            # Accept both pandas object, string[python], and str dtypes
            dtype_str = str(df[col].dtype)
            assert dtype_str in ("object", "string[python]", "str"), (
                f"Column {col} has unexpected dtype {dtype_str}"
            )

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            read_raw_csv(tmp_path / "nonexistent.csv")


# ---------------------------------------------------------------------------
# Tests: schema validation
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    def test_valid_schema_returns_no_issues(self) -> None:
        df = pd.DataFrame(columns=BRONZE_COLUMNS)
        assert validate_schema(df) == []

    def test_missing_column_detected(self) -> None:
        df = pd.DataFrame(columns=[c for c in BRONZE_COLUMNS if c != "Age"])
        issues = validate_schema(df)
        assert any("Age" in i for i in issues)

    def test_extra_column_detected(self) -> None:
        df = pd.DataFrame(columns=BRONZE_COLUMNS + ["ExtraCol"])
        issues = validate_schema(df)
        assert any("ExtraCol" in i for i in issues)

    def test_correct_columns_pass(self) -> None:
        df = read_raw_csv(Path("data/hospital/hospital_data.csv"))
        assert validate_schema(df) == []


# ---------------------------------------------------------------------------
# Tests: load_bronze end-to-end
# ---------------------------------------------------------------------------

class TestLoadBronze:
    def test_loads_all_rows(self, ready_cfg: PipelineConfig) -> None:
        result = load_bronze(ready_cfg)
        assert result["rows_in"] == 984
        assert result["rows_loaded"] == 984

    def test_metadata_columns_present(self, ready_cfg: PipelineConfig) -> None:
        load_bronze(ready_cfg)
        conn = sqlite3.connect(str(ready_cfg.warehouse_db))
        row = conn.execute(
            "SELECT _ingested_at, _source_file, _source_hash FROM bronze_encounters LIMIT 1"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[1] == "hospital_data.csv"
        assert len(row[2]) == 64  # SHA-256 hex

    def test_idempotent_reload(self, ready_cfg: PipelineConfig) -> None:
        """Running load_bronze twice should not double the row count."""
        load_bronze(ready_cfg)
        load_bronze(ready_cfg)
        conn = sqlite3.connect(str(ready_cfg.warehouse_db))
        count = conn.execute("SELECT COUNT(*) FROM bronze_encounters").fetchone()[0]
        conn.close()
        assert count == 984

    def test_source_hash_is_64_chars(self, ready_cfg: PipelineConfig) -> None:
        result = load_bronze(ready_cfg)
        assert len(result["source_hash"]) == 64

    def test_bad_schema_raises_value_error(
        self, tmp_path: Path, ready_cfg: PipelineConfig
    ) -> None:
        bad_csv = tmp_path / "bad.csv"
        pd.DataFrame({"wrong_col": [1, 2]}).to_csv(bad_csv, index=False)
        ready_cfg.source_csv = bad_csv
        with pytest.raises(ValueError, match="schema validation failed"):
            load_bronze(ready_cfg)

    def test_minimal_csv_loads(
        self, minimal_csv: Path, tmp_path: Path
    ) -> None:
        cfg = PipelineConfig(
            source_csv=minimal_csv,
            warehouse_db=tmp_path / "mini.db",
            reports_dir=tmp_path / "r",
        )
        apply_ddl(cfg)
        result = load_bronze(cfg)
        assert result["rows_loaded"] == 3
