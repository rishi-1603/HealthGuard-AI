"""Tests — End-to-end pipeline integration.

Covers: full pipeline run, manifest generation, audit log entries,
pipeline_runs table, error propagation, and re-run idempotency.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from pipeline.config import PipelineConfig
from pipeline.orchestrator import run_pipeline
from pipeline.warehouse import apply_ddl


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def e2e_cfg(tmp_path: Path) -> PipelineConfig:
    return PipelineConfig(
        warehouse_db=tmp_path / "e2e.db",
        source_csv=Path("data/hospital/hospital_data.csv"),
        reports_dir=tmp_path / "reports",
    )


# ---------------------------------------------------------------------------
# Tests: happy path
# ---------------------------------------------------------------------------

class TestPipelineHappyPath:
    def test_pipeline_returns_success_status(
        self, e2e_cfg: PipelineConfig
    ) -> None:
        result = run_pipeline(cfg=e2e_cfg)
        assert result["status"] == "success"

    def test_bronze_rows_reported_correctly(
        self, e2e_cfg: PipelineConfig
    ) -> None:
        result = run_pipeline(cfg=e2e_cfg)
        assert result["bronze"]["rows_loaded"] == 984

    def test_silver_rows_reported_correctly(
        self, e2e_cfg: PipelineConfig
    ) -> None:
        result = run_pipeline(cfg=e2e_cfg)
        assert result["silver"]["rows_written"] == 984

    def test_gold_has_five_marts(self, e2e_cfg: PipelineConfig) -> None:
        result = run_pipeline(cfg=e2e_cfg)
        assert len(result["gold"]) == 5

    def test_manifest_file_written(self, e2e_cfg: PipelineConfig) -> None:
        result = run_pipeline(cfg=e2e_cfg)
        manifest_path = Path(result["manifest_path"])
        assert manifest_path.exists()

    def test_manifest_is_valid_json(self, e2e_cfg: PipelineConfig) -> None:
        result = run_pipeline(cfg=e2e_cfg)
        content = Path(result["manifest_path"]).read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert parsed["status"] == "success"

    def test_started_and_finished_timestamps_present(
        self, e2e_cfg: PipelineConfig
    ) -> None:
        result = run_pipeline(cfg=e2e_cfg)
        assert "started_at" in result
        assert "finished_at" in result


# ---------------------------------------------------------------------------
# Tests: audit log
# ---------------------------------------------------------------------------

class TestAuditLog:
    def test_three_pipeline_run_records_created(
        self, e2e_cfg: PipelineConfig
    ) -> None:
        run_pipeline(cfg=e2e_cfg)
        conn = sqlite3.connect(str(e2e_cfg.warehouse_db))
        count = conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0]
        conn.close()
        assert count == 3  # bronze + silver + gold

    def test_all_runs_have_success_status(
        self, e2e_cfg: PipelineConfig
    ) -> None:
        run_pipeline(cfg=e2e_cfg)
        conn = sqlite3.connect(str(e2e_cfg.warehouse_db))
        statuses = [
            r[0]
            for r in conn.execute("SELECT status FROM pipeline_runs").fetchall()
        ]
        conn.close()
        assert all(s == "success" for s in statuses)

    def test_run_records_have_row_counts(
        self, e2e_cfg: PipelineConfig
    ) -> None:
        run_pipeline(cfg=e2e_cfg)
        conn = sqlite3.connect(str(e2e_cfg.warehouse_db))
        rows = conn.execute(
            "SELECT stage, rows_out FROM pipeline_runs ORDER BY started_at"
        ).fetchall()
        conn.close()
        stage_map = {stage: rows_out for stage, rows_out in rows}
        assert stage_map["bronze"] == 984
        assert stage_map["silver"] == 984

    def test_gold_run_records_mart_metadata(
        self, e2e_cfg: PipelineConfig
    ) -> None:
        run_pipeline(cfg=e2e_cfg)
        conn = sqlite3.connect(str(e2e_cfg.warehouse_db))
        meta_json = conn.execute(
            "SELECT metadata_json FROM pipeline_runs WHERE stage='gold'"
        ).fetchone()[0]
        conn.close()
        meta = json.loads(meta_json)
        assert "gold_condition_mart" in meta


# ---------------------------------------------------------------------------
# Tests: idempotency
# ---------------------------------------------------------------------------

class TestPipelineIdempotency:
    def test_second_run_does_not_corrupt_warehouse(
        self, e2e_cfg: PipelineConfig
    ) -> None:
        run_pipeline(cfg=e2e_cfg)
        result2 = run_pipeline(cfg=e2e_cfg)
        assert result2["silver"]["rows_written"] == 984

    def test_second_run_appends_audit_records(
        self, e2e_cfg: PipelineConfig
    ) -> None:
        run_pipeline(cfg=e2e_cfg)
        run_pipeline(cfg=e2e_cfg)
        conn = sqlite3.connect(str(e2e_cfg.warehouse_db))
        count = conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0]
        conn.close()
        assert count == 6  # 3 stages × 2 runs


# ---------------------------------------------------------------------------
# Tests: error propagation
# ---------------------------------------------------------------------------

class TestPipelineErrorHandling:
    def test_missing_source_raises(self, tmp_path: Path) -> None:
        cfg = PipelineConfig(
            warehouse_db=tmp_path / "err.db",
            source_csv=tmp_path / "nonexistent.csv",
            reports_dir=tmp_path / "r",
        )
        with pytest.raises(FileNotFoundError):
            run_pipeline(cfg=cfg)

    def test_failed_run_recorded_in_audit(self, tmp_path: Path) -> None:
        cfg = PipelineConfig(
            warehouse_db=tmp_path / "fail.db",
            source_csv=tmp_path / "missing.csv",
            reports_dir=tmp_path / "r",
        )
        apply_ddl(cfg)
        with pytest.raises(FileNotFoundError):
            run_pipeline(cfg=cfg)
        conn = sqlite3.connect(str(cfg.warehouse_db))
        failed = conn.execute(
            "SELECT COUNT(*) FROM pipeline_runs WHERE status='failed'"
        ).fetchone()[0]
        conn.close()
        assert failed >= 1
