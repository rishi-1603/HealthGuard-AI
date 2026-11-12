"""Pipeline audit — lineage and run manifest writer."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pipeline.config import PipelineConfig
from pipeline.warehouse import managed_connection

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def start_run(stage: str, cfg: PipelineConfig) -> str:
    """Record a pipeline run start and return the run_id."""
    run_id = str(uuid.uuid4())
    with managed_connection(cfg.warehouse_db) as conn:
        conn.execute(
            """INSERT INTO pipeline_runs
               (run_id, stage, status, started_at)
               VALUES (?, ?, 'running', ?)""",
            (run_id, stage, _now()),
        )
    return run_id


def finish_run(
    run_id: str,
    stage: str,
    cfg: PipelineConfig,
    rows_in: int = 0,
    rows_out: int = 0,
    rows_rejected: int = 0,
    metadata: dict | None = None,
) -> None:
    """Mark a pipeline run as successful."""
    with managed_connection(cfg.warehouse_db) as conn:
        conn.execute(
            """UPDATE pipeline_runs
               SET status='success', rows_in=?, rows_out=?, rows_rejected=?,
                   finished_at=?, metadata_json=?
               WHERE run_id=?""",
            (
                rows_in,
                rows_out,
                rows_rejected,
                _now(),
                json.dumps(metadata or {}),
                run_id,
            ),
        )
    logger.info("Run %s [%s] finished OK", run_id[:8], stage)


def fail_run(run_id: str, cfg: PipelineConfig, error: str) -> None:
    """Mark a pipeline run as failed."""
    with managed_connection(cfg.warehouse_db) as conn:
        conn.execute(
            """UPDATE pipeline_runs
               SET status='failed', finished_at=?, error_message=?
               WHERE run_id=?""",
            (_now(), error[:2000], run_id),
        )
    logger.error("Run %s FAILED: %s", run_id[:8], error)


def write_manifest(result: dict, cfg: PipelineConfig) -> Path:
    """Write a JSON pipeline manifest to reports/pipeline/."""
    cfg.reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = cfg.reports_dir / f"pipeline_run_{stamp}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info("Manifest written to %s", path)
    return path
