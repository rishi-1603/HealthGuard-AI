"""Pipeline orchestrator — DAG-style runner.

Executes Bronze → Silver → Gold in order, records lineage,
and writes a run manifest.  Any stage failure stops the pipeline
and records the error without leaving the warehouse in a corrupt state.

Usage:
    from pipeline.orchestrator import run_pipeline
    result = run_pipeline()
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

from pipeline.audit.lineage import fail_run, finish_run, start_run, write_manifest
from pipeline.bronze.ingestor import load_bronze
from pipeline.config import PipelineConfig
from pipeline.gold.aggregator import build_gold_marts
from pipeline.silver.transformer import transform_to_silver
from pipeline.warehouse import apply_ddl

logger = logging.getLogger(__name__)


def _configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

def _stage_bronze(cfg: PipelineConfig) -> dict:
    run_id = start_run("bronze", cfg)
    try:
        result = load_bronze(cfg)
        finish_run(
            run_id, "bronze", cfg,
            rows_in=result["rows_in"],
            rows_out=result["rows_loaded"],
            metadata={"source_hash": result["source_hash"]},
        )
        return result
    except Exception as exc:
        fail_run(run_id, cfg, str(exc))
        raise


def _stage_silver(cfg: PipelineConfig, bronze_rows: int) -> dict:
    run_id = start_run("silver", cfg)
    try:
        rows_written, dq_report = transform_to_silver(cfg)
        finish_run(
            run_id, "silver", cfg,
            rows_in=bronze_rows,
            rows_out=rows_written,
            rows_rejected=bronze_rows - rows_written,
            metadata=dq_report.summary(),
        )
        return {"rows_written": rows_written, "dq_report": dq_report.summary()}
    except Exception as exc:
        fail_run(run_id, cfg, str(exc))
        raise


def _stage_gold(cfg: PipelineConfig, silver_rows: int) -> dict:
    run_id = start_run("gold", cfg)
    try:
        mart_rows = build_gold_marts(cfg)
        finish_run(
            run_id, "gold", cfg,
            rows_in=silver_rows,
            rows_out=sum(mart_rows.values()),
            metadata=mart_rows,
        )
        return mart_rows
    except Exception as exc:
        fail_run(run_id, cfg, str(exc))
        raise


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_pipeline(cfg: PipelineConfig | None = None, verbose: bool = False) -> dict:
    """Execute the full Bronze → Silver → Gold pipeline.

    Returns a manifest dict suitable for JSON serialisation.
    Raises on any stage failure.
    """
    _configure_logging(logging.DEBUG if verbose else logging.INFO)
    cfg = cfg or PipelineConfig()

    started_at = datetime.now(timezone.utc).isoformat()
    logger.info("=" * 60)
    logger.info("HealthGuard AI — Data Pipeline starting")
    logger.info("Warehouse: %s", cfg.warehouse_db)
    logger.info("=" * 60)

    # Always ensure schema exists before any stage runs
    apply_ddl(cfg)

    try:
        # Stage 1: Bronze
        logger.info("[1/3] Bronze — raw ingestion")
        bronze_result = _stage_bronze(cfg)

        # Stage 2: Silver
        logger.info("[2/3] Silver — transform + quality gate")
        silver_result = _stage_silver(cfg, bronze_result["rows_loaded"])

        # Stage 3: Gold
        logger.info("[3/3] Gold — analytics mart aggregation")
        gold_result = _stage_gold(cfg, silver_result["rows_written"])

        finished_at = datetime.now(timezone.utc).isoformat()
        manifest = {
            "status": "success",
            "started_at": started_at,
            "finished_at": finished_at,
            "bronze": bronze_result,
            "silver": silver_result,
            "gold": gold_result,
        }
        # Remove non-serialisable objects before writing manifest
        manifest["silver"] = {
            "rows_written": silver_result["rows_written"],
            "dq_report": silver_result["dq_report"],
        }

        manifest_path = write_manifest(manifest, cfg)
        manifest["manifest_path"] = str(manifest_path)

        logger.info("=" * 60)
        logger.info("Pipeline COMPLETE — Bronze:%d  Silver:%d  Gold marts:%d",
                    bronze_result["rows_loaded"],
                    silver_result["rows_written"],
                    len(gold_result))
        logger.info("=" * 60)
        return manifest

    except Exception as exc:
        logger.error("Pipeline FAILED: %s", exc, exc_info=True)
        raise
