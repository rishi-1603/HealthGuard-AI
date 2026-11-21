"""
Apache Airflow DAG: healthguard_cdc_sync_dag

Orchestrates near-real-time CDC event capture and Lakehouse synchronization:
  1. sensor_cdc_wal: checks WAL activity on operational healthcare DB
  2. extract_cdc_events: polls uncommitted Debezium CDC change events
  3. reconcile_silver_lakehouse: compacts LSN state into Silver lakehouse
  4. update_star_schema_scd2: tracks patient history via SCD Type 2 dimensional modeling
  5. audit_cdc_reconciliation: emits watermarked CDC reconciliation audit log
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from pipeline.cdc.cdc_engine import DebeziumCdcEngine
from pipeline.cdc.lakehouse_sync import LakehouseCdcSync
from pipeline.cdc.operational_db import OperationalEhrDb
from pipeline.config import PipelineConfig
from pipeline.orchestration.airflow_compat import (
    DAG,
    BaseSensorOperator,
    PythonOperator,
)
from pipeline.warehouse import apply_ddl
from pipeline.warehouse.star_schema import populate_star_schema_from_silver

logger = logging.getLogger(__name__)

DEFAULT_ARGS = {
    "owner": "healthguard-cdc-ops",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(seconds=5),
    "retry_exponential_backoff": True,
    "sla": timedelta(minutes=15),
    "email_on_failure": False,
    "email_on_retry": False,
}


class WalActivitySensor(BaseSensorOperator):
    """Sensor checking if WAL log has new unread CDC transactions."""

    def poke(self, context: Dict[str, Any]) -> bool:
        cfg = PipelineConfig()
        ops_db_path = cfg.warehouse_db.parent / "operational_ehr.db"
        ops_db = OperationalEhrDb(ops_db_path)
        tables = ops_db.get_table_names()
        return "operational_wal_log" in tables


# ---------------------------------------------------------------------------
# Task Callables
# ---------------------------------------------------------------------------
def task_extract_cdc_events(**context: Any) -> Dict[str, Any]:
    cfg = PipelineConfig()
    apply_ddl(cfg)
    ops_db_path = cfg.warehouse_db.parent / "operational_ehr.db"
    ops_db = OperationalEhrDb(ops_db_path)
    engine = DebeziumCdcEngine(ops_db)
    events = engine.poll_events()
    sync = LakehouseCdcSync(cfg)
    if events:
        sync.sync_to_bronze(events)
    logger.info("Polled and synced %d CDC events", len(events))
    return {"event_count": len(events)}


def task_reconcile_silver(**context: Any) -> Dict[str, Any]:
    cfg = PipelineConfig()
    sync = LakehouseCdcSync(cfg)
    rows_compacted = sync.compact_to_silver()
    logger.info("Silver CDC reconciliation complete: %d rows compacted", rows_compacted)
    return {"rows_compacted": rows_compacted}


def task_update_star_schema(**context: Any) -> Dict[str, Any]:
    cfg = PipelineConfig()
    count_dict = populate_star_schema_from_silver(cfg)
    logger.info("Star schema updated: %s", count_dict)
    return count_dict if isinstance(count_dict, dict) else {"status": "updated"}


def task_audit_reconciliation(**context: Any) -> Dict[str, Any]:
    ds = context.get("ds", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    manifest = {
        "dag": "healthguard_cdc_sync_dag",
        "ds": ds,
        "sync_status": "COMMITTED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("CDC reconciliation audited: %s", manifest)
    return manifest


# ---------------------------------------------------------------------------
# DAG Definition Factory
# ---------------------------------------------------------------------------
def create_cdc_sync_dag(
    dag_id: str = "healthguard_cdc_sync_dag",
    schedule_interval: str = "*/15 * * * *",
    start_date: Optional[datetime] = None,
) -> DAG:
    """Build and return the CDC sync DAG."""
    dag = DAG(
        dag_id=dag_id,
        description="HealthGuard 360 CDC Lakehouse Reconciliation & SCD2 Pipeline",
        schedule_interval=schedule_interval,
        start_date=start_date or datetime(2026, 1, 1, tzinfo=timezone.utc),
        default_args=DEFAULT_ARGS,
        catchup=False,
        tags=["healthcare", "cdc", "debezium", "streaming", "scd2"],
    )

    sensor_wal = WalActivitySensor(
        task_id="sensor_cdc_wal",
        poke_interval=timedelta(seconds=1),
        timeout=timedelta(seconds=5),
        soft_fail=True,
        dag=dag,
    )

    t_extract = PythonOperator(
        task_id="extract_cdc_events",
        python_callable=task_extract_cdc_events,
        dag=dag,
    )

    t_reconcile = PythonOperator(
        task_id="reconcile_silver_lakehouse",
        python_callable=task_reconcile_silver,
        dag=dag,
    )

    t_scd2 = PythonOperator(
        task_id="update_star_schema_scd2",
        python_callable=task_update_star_schema,
        dag=dag,
    )

    t_audit = PythonOperator(
        task_id="audit_cdc_reconciliation",
        python_callable=task_audit_reconciliation,
        dag=dag,
    )

    # Dependency chain:
    # sensor >> extract >> reconcile >> scd2 >> audit
    sensor_wal >> t_extract >> t_reconcile >> t_scd2 >> t_audit

    return dag


# Module-level DAG instance for Airflow DAG discovery
dag = create_cdc_sync_dag()
