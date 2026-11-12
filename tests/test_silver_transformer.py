"""Tests — Silver transformation layer.

Covers: type coercion, age-band derivation, readmission_flag, cost_per_day,
DQ checks (nulls, duplicates, ranges, categoricals), quality gate enforcement,
and Silver warehouse write.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from pipeline.bronze.ingestor import load_bronze
from pipeline.config import PipelineConfig
from pipeline.silver.quality import (
    QualityReport,
    Severity,
    check_categorical_values,
    check_duplicate_patients,
    check_minimum_rows,
    check_null_rate,
    check_numeric_ranges,
    run_quality_checks,
)
from pipeline.silver.transformer import (
    _assign_age_band,
    _coerce_types,
    _add_derived_columns,
    transform_to_silver,
)
from pipeline.warehouse import apply_ddl


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def primed_cfg(tmp_path: Path) -> PipelineConfig:
    """Config with Bronze loaded — ready for Silver transform."""
    cfg = PipelineConfig(
        warehouse_db=tmp_path / "test.db",
        source_csv=Path("data/hospital/hospital_data.csv"),
        reports_dir=tmp_path / "reports",
    )
    apply_ddl(cfg)
    load_bronze(cfg)
    return cfg


@pytest.fixture()
def valid_df() -> pd.DataFrame:
    """A minimal valid DataFrame matching Silver input expectations."""
    return pd.DataFrame(
        {
            "Patient_ID": [1, 2, 3, 4, 5],
            "Age": [25, 40, 55, 70, 80],
            "Gender": ["Male", "Female", "Male", "Female", "Male"],
            "Condition": ["Diabetes"] * 5,
            "Procedure": ["Insulin Therapy"] * 5,
            "Cost": [5000, 8000, 3000, 12000, 7000],
            "Length_of_Stay": [3, 5, 2, 7, 4],
            "Readmission": ["No", "Yes", "No", "Yes", "No"],
            "Outcome": ["Recovered"] * 5,
            "Satisfaction": [8, 7, 9, 6, 8],
        }
    )


# ---------------------------------------------------------------------------
# Tests: age-band derivation
# ---------------------------------------------------------------------------

class TestAgeBand:
    @pytest.mark.parametrize("age,expected", [
        (18, "18-30"), (30, "18-30"),
        (31, "31-45"), (45, "31-45"),
        (46, "46-60"), (60, "46-60"),
        (61, "61-75"), (75, "61-75"),
        (76, "76+"), (100, "76+"),
    ])
    def test_band_boundaries(self, age: int, expected: str) -> None:
        assert _assign_age_band(age) == expected


# ---------------------------------------------------------------------------
# Tests: type coercion
# ---------------------------------------------------------------------------

class TestTypeCoercion:
    def test_int_columns_become_numeric(self, valid_df: pd.DataFrame) -> None:
        # start with everything as str (simulating Bronze)
        str_df = valid_df.astype(str)
        result = _coerce_types(str_df)
        assert pd.api.types.is_numeric_dtype(result["Age"])
        assert pd.api.types.is_numeric_dtype(result["Cost"])
        assert pd.api.types.is_numeric_dtype(result["Satisfaction"])

    def test_coerce_does_not_mutate_input(self, valid_df: pd.DataFrame) -> None:
        original_dtype = valid_df["Age"].dtype
        _ = _coerce_types(valid_df.astype(str))
        assert valid_df["Age"].dtype == original_dtype


# ---------------------------------------------------------------------------
# Tests: derived columns
# ---------------------------------------------------------------------------

class TestDerivedColumns:
    def test_readmission_flag_yes(self, valid_df: pd.DataFrame) -> None:
        result = _add_derived_columns(valid_df)
        assert result.loc[result["Readmission"] == "Yes", "readmission_flag"].iloc[0] == 1

    def test_readmission_flag_no(self, valid_df: pd.DataFrame) -> None:
        result = _add_derived_columns(valid_df)
        assert result.loc[result["Readmission"] == "No", "readmission_flag"].iloc[0] == 0

    def test_cost_per_day_computed(self, valid_df: pd.DataFrame) -> None:
        result = _add_derived_columns(valid_df)
        row = result.iloc[0]
        expected = round(row["Cost"] / row["Length_of_Stay"], 4)
        assert abs(result.iloc[0]["cost_per_day"] - expected) < 0.01

    def test_cost_per_day_zero_los_is_none(self) -> None:
        df = pd.DataFrame(
            {
                "Patient_ID": [99], "Age": [40], "Gender": ["Male"],
                "Condition": ["X"], "Procedure": ["Y"],
                "Cost": [5000], "Length_of_Stay": [0],
                "Readmission": ["No"], "Outcome": ["Recovered"],
                "Satisfaction": [5],
            }
        )
        result = _add_derived_columns(df)
        assert result.iloc[0]["cost_per_day"] is None

    def test_age_band_column_added(self, valid_df: pd.DataFrame) -> None:
        result = _add_derived_columns(valid_df)
        assert "age_band" in result.columns
        assert result.iloc[0]["age_band"] == "18-30"

    def test_no_mutation_of_input(self, valid_df: pd.DataFrame) -> None:
        original_cols = set(valid_df.columns)
        _ = _add_derived_columns(valid_df)
        assert set(valid_df.columns) == original_cols


# ---------------------------------------------------------------------------
# Tests: data quality checks
# ---------------------------------------------------------------------------

class TestNullCheck:
    def test_no_nulls_passes(self, valid_df: pd.DataFrame) -> None:
        cfg = PipelineConfig()
        results = check_null_rate(valid_df, cfg)
        assert all(r.passed for r in results)

    def test_high_null_rate_fails(self, valid_df: pd.DataFrame) -> None:
        cfg = PipelineConfig(max_null_pct=0.0)
        df = valid_df.copy()
        df.loc[0, "Age"] = None
        results = check_null_rate(df, cfg)
        age_result = next(r for r in results if "Age" in r.check_name)
        assert not age_result.passed


class TestDuplicateCheck:
    def test_no_duplicates_passes(self, valid_df: pd.DataFrame) -> None:
        result = check_duplicate_patients(valid_df, PipelineConfig())
        assert result.passed

    def test_duplicates_fail(self, valid_df: pd.DataFrame) -> None:
        df = pd.concat([valid_df, valid_df]).reset_index(drop=True)
        result = check_duplicate_patients(df, PipelineConfig(max_duplicate_pct=0.0))
        assert not result.passed


class TestCategoricalCheck:
    def test_valid_categories_pass(self, valid_df: pd.DataFrame) -> None:
        results = check_categorical_values(valid_df)
        assert all(r.passed for r in results)

    def test_invalid_readmission_fails(self, valid_df: pd.DataFrame) -> None:
        df = valid_df.copy()
        df.loc[0, "Readmission"] = "Maybe"
        results = check_categorical_values(df)
        readmit = next(r for r in results if "Readmission" in r.check_name)
        assert not readmit.passed


class TestRangeCheck:
    def test_in_range_passes(self, valid_df: pd.DataFrame) -> None:
        results = check_numeric_ranges(valid_df)
        assert all(r.passed for r in results)

    def test_negative_cost_fails(self, valid_df: pd.DataFrame) -> None:
        df = valid_df.copy()
        df.loc[0, "Cost"] = -1
        results = check_numeric_ranges(df)
        cost = next(r for r in results if "Cost" in r.check_name)
        assert not cost.passed


class TestMinRowCheck:
    def test_enough_rows_passes(self, valid_df: pd.DataFrame) -> None:
        cfg = PipelineConfig(min_row_count=3)
        result = check_minimum_rows(valid_df, cfg)
        assert result.passed

    def test_too_few_rows_fails(self, valid_df: pd.DataFrame) -> None:
        cfg = PipelineConfig(min_row_count=1000)
        result = check_minimum_rows(valid_df, cfg)
        assert not result.passed


class TestQualityReport:
    def test_all_pass_gate_passes(self, valid_df: pd.DataFrame) -> None:
        cfg = PipelineConfig(min_row_count=1)
        report = run_quality_checks(valid_df, cfg)
        assert report.passed

    def test_summary_has_required_keys(self, valid_df: pd.DataFrame) -> None:
        report = run_quality_checks(valid_df, PipelineConfig(min_row_count=1))
        summary = report.summary()
        assert "total_checks" in summary
        assert "gate_passed" in summary
        assert "details" in summary


# ---------------------------------------------------------------------------
# Tests: Silver warehouse write
# ---------------------------------------------------------------------------

class TestTransformToSilver:
    def test_silver_row_count_matches_bronze(self, primed_cfg: PipelineConfig) -> None:
        rows, _ = transform_to_silver(primed_cfg)
        assert rows == 984

    def test_silver_has_derived_columns(self, primed_cfg: PipelineConfig) -> None:
        transform_to_silver(primed_cfg)
        conn = sqlite3.connect(str(primed_cfg.warehouse_db))
        row = conn.execute(
            "SELECT age_band, readmission_flag, cost_per_day FROM silver_encounters LIMIT 1"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] in {"18-30", "31-45", "46-60", "61-75", "76+"}
        assert row[1] in (0, 1)

    def test_silver_idempotent(self, primed_cfg: PipelineConfig) -> None:
        transform_to_silver(primed_cfg)
        rows2, _ = transform_to_silver(primed_cfg)
        assert rows2 == 984

    def test_readmission_flag_sum_matches_yes_count(
        self, primed_cfg: PipelineConfig
    ) -> None:
        transform_to_silver(primed_cfg)
        conn = sqlite3.connect(str(primed_cfg.warehouse_db))
        flag_sum = conn.execute(
            "SELECT SUM(readmission_flag) FROM silver_encounters"
        ).fetchone()[0]
        conn.close()
        # From the README: 264 / 984 readmitted
        assert flag_sum == 264
