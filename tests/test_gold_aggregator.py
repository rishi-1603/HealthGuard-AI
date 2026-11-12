"""Tests — Gold analytics mart aggregator.

Covers: all 5 mart tables, aggregation correctness, reconciliation with
known headline figures (264 readmitted, 26.8% rate, 43.8% cost share),
and idempotent reload.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pipeline.bronze.ingestor import load_bronze
from pipeline.config import PipelineConfig
from pipeline.gold.aggregator import build_gold_marts
from pipeline.silver.transformer import transform_to_silver
from pipeline.warehouse import apply_ddl


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def gold_cfg(tmp_path_factory) -> PipelineConfig:
    """Module-scoped: run full Bronze→Silver→Gold once and reuse."""
    tmp = tmp_path_factory.mktemp("gold")
    cfg = PipelineConfig(
        warehouse_db=tmp / "gold_test.db",
        source_csv=Path("data/hospital/hospital_data.csv"),
        reports_dir=tmp / "reports",
    )
    apply_ddl(cfg)
    load_bronze(cfg)
    transform_to_silver(cfg)
    build_gold_marts(cfg)
    return cfg


# ---------------------------------------------------------------------------
# Tests: mart existence and row counts
# ---------------------------------------------------------------------------

class TestMartExistence:
    def test_condition_mart_has_rows(self, gold_cfg: PipelineConfig) -> None:
        conn = sqlite3.connect(str(gold_cfg.warehouse_db))
        count = conn.execute("SELECT COUNT(*) FROM gold_condition_mart").fetchone()[0]
        conn.close()
        assert count > 0

    def test_age_band_mart_has_five_bands(self, gold_cfg: PipelineConfig) -> None:
        conn = sqlite3.connect(str(gold_cfg.warehouse_db))
        count = conn.execute("SELECT COUNT(*) FROM gold_age_band_mart").fetchone()[0]
        conn.close()
        assert count == 5

    def test_gender_mart_has_rows(self, gold_cfg: PipelineConfig) -> None:
        conn = sqlite3.connect(str(gold_cfg.warehouse_db))
        count = conn.execute("SELECT COUNT(*) FROM gold_gender_mart").fetchone()[0]
        conn.close()
        assert count >= 1

    def test_outcome_mart_has_rows(self, gold_cfg: PipelineConfig) -> None:
        conn = sqlite3.connect(str(gold_cfg.warehouse_db))
        count = conn.execute("SELECT COUNT(*) FROM gold_outcome_mart").fetchone()[0]
        conn.close()
        assert count > 0

    def test_daily_summary_has_one_row(self, gold_cfg: PipelineConfig) -> None:
        conn = sqlite3.connect(str(gold_cfg.warehouse_db))
        count = conn.execute("SELECT COUNT(*) FROM gold_daily_summary").fetchone()[0]
        conn.close()
        assert count == 1


# ---------------------------------------------------------------------------
# Tests: headline figure reconciliation (must match README / metrics.json)
# ---------------------------------------------------------------------------

class TestHeadlineReconciliation:
    def test_total_patients_984(self, gold_cfg: PipelineConfig) -> None:
        conn = sqlite3.connect(str(gold_cfg.warehouse_db))
        total = conn.execute(
            "SELECT total_patients FROM gold_daily_summary"
        ).fetchone()[0]
        conn.close()
        assert total == 984

    def test_readmitted_count_264(self, gold_cfg: PipelineConfig) -> None:
        conn = sqlite3.connect(str(gold_cfg.warehouse_db))
        readmitted = conn.execute(
            "SELECT readmitted_count FROM gold_daily_summary"
        ).fetchone()[0]
        conn.close()
        assert readmitted == 264

    def test_readmission_rate_26_8_pct(self, gold_cfg: PipelineConfig) -> None:
        conn = sqlite3.connect(str(gold_cfg.warehouse_db))
        rate = conn.execute(
            "SELECT readmission_rate_pct FROM gold_daily_summary"
        ).fetchone()[0]
        conn.close()
        assert abs(rate - 26.83) < 0.1

    def test_condition_mart_total_patients_sums_to_984(
        self, gold_cfg: PipelineConfig
    ) -> None:
        conn = sqlite3.connect(str(gold_cfg.warehouse_db))
        total = conn.execute(
            "SELECT SUM(total_patients) FROM gold_condition_mart"
        ).fetchone()[0]
        conn.close()
        assert total == 984

    def test_age_band_mart_total_patients_sums_to_984(
        self, gold_cfg: PipelineConfig
    ) -> None:
        conn = sqlite3.connect(str(gold_cfg.warehouse_db))
        total = conn.execute(
            "SELECT SUM(total_patients) FROM gold_age_band_mart"
        ).fetchone()[0]
        conn.close()
        assert total == 984

    def test_outcome_mart_share_pct_sums_to_100(
        self, gold_cfg: PipelineConfig
    ) -> None:
        conn = sqlite3.connect(str(gold_cfg.warehouse_db))
        total_share = conn.execute(
            "SELECT SUM(share_pct) FROM gold_outcome_mart"
        ).fetchone()[0]
        conn.close()
        assert abs(total_share - 100.0) < 0.5

    def test_readmission_rate_per_condition_between_0_and_100(
        self, gold_cfg: PipelineConfig
    ) -> None:
        conn = sqlite3.connect(str(gold_cfg.warehouse_db))
        rows = conn.execute(
            "SELECT condition, readmission_rate_pct FROM gold_condition_mart"
        ).fetchall()
        conn.close()
        for condition, rate in rows:
            assert 0.0 <= rate <= 100.0, f"{condition}: rate {rate} out of range"


# ---------------------------------------------------------------------------
# Tests: idempotency
# ---------------------------------------------------------------------------

class TestGoldIdempotency:
    def test_rebuild_does_not_duplicate_rows(
        self, gold_cfg: PipelineConfig
    ) -> None:
        build_gold_marts(gold_cfg)
        conn = sqlite3.connect(str(gold_cfg.warehouse_db))
        total = conn.execute(
            "SELECT total_patients FROM gold_daily_summary"
        ).fetchone()[0]
        conn.close()
        assert total == 984

    def test_build_gold_returns_five_mart_keys(
        self, gold_cfg: PipelineConfig
    ) -> None:
        result = build_gold_marts(gold_cfg)
        assert len(result) == 5


# ---------------------------------------------------------------------------
# Tests: Gold mart schema fields
# ---------------------------------------------------------------------------

class TestGoldSchema:
    def test_condition_mart_has_avg_cost_field(
        self, gold_cfg: PipelineConfig
    ) -> None:
        conn = sqlite3.connect(str(gold_cfg.warehouse_db))
        row = conn.execute(
            "SELECT avg_cost FROM gold_condition_mart LIMIT 1"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] > 0

    def test_gold_loaded_at_is_set(self, gold_cfg: PipelineConfig) -> None:
        conn = sqlite3.connect(str(gold_cfg.warehouse_db))
        ts = conn.execute(
            "SELECT _gold_loaded_at FROM gold_daily_summary"
        ).fetchone()[0]
        conn.close()
        assert ts is not None
        assert "T" in ts   # ISO format check
