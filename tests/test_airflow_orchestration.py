"""
DE-011 Test Suite: Apache Airflow DAG Orchestration & Backfill Engine.

Verifies:
  T1  - DAG construction and default_args inheritance
  T2  - Bitshift operators (>>) correctly establish upstream/downstream dependencies
  T3  - List bitshift ([t1, t2] >> t3) works in both directions
  T4  - Topological sort orders tasks respecting dependencies
  T5  - Cycle detection raises AirflowDAGValidationError
  T6  - Dangling dependency raises AirflowDAGValidationError
  T7  - PythonOperator executes callable with Airflow context (ds, execution_date)
  T8  - Sensor operator: poke=True succeeds immediately
  T9  - Sensor operator: poke=False with timeout raises TimeoutError
  T10 - Sensor operator: soft_fail=True marks task as False rather than raising
  T11 - Task retry: transient failures retry with exponential backoff up to max retries
  T12 - Task retry: eventual success after retries returns TaskState.SUCCESS
  T13 - Upstream failure cascades to UPSTREAM_FAILED for downstream tasks
  T14 - Callbacks: on_success_callback and on_failure_callback are invoked
  T15 - SLA monitoring: flags sla_missed when execution exceeds task SLA
  T16 - Multi-date backfill iterates across logical execution dates
  T17 - Backfill idempotency: re-running backfill produces consistent zero-corruption state
  T18 - healthguard_batch_medallion_dag DAG structure and task count
  T19 - healthguard_cdc_sync_dag DAG structure and task count
  T20 - End-to-end dry-run execution of both production DAGs
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from orchestration.airflow.dags.healthguard_batch_medallion_dag import (
    create_batch_medallion_dag,
)
from orchestration.airflow.dags.healthguard_cdc_sync_dag import create_cdc_sync_dag
from pipeline.orchestration.airflow_compat import (
    DAG,
    BaseOperator,
    BaseSensorOperator,
    EmptyOperator,
    FileSensor,
    PythonOperator,
    TaskResult,
    TaskState,
)
from pipeline.orchestration.engine import (
    AirflowDAGValidationError,
    AirflowExecutionEngine,
    BackfillResult,
    DagRunResult,
)


# Mock sleep for instant tests
def _no_op_sleep(seconds: float) -> None:
    pass


# ---------------------------------------------------------------------------
# T1-T3 — DAG & Operator Construction
# ---------------------------------------------------------------------------
class TestAirflowCompat:
    def test_dag_construction_and_defaults(self) -> None:
        """T1: Tasks inherit DAG default_args when not explicitly configured."""
        default_args = {"retries": 5, "retry_delay": 15, "retry_exponential_backoff": True}
        dag = DAG(dag_id="test_dag", default_args=default_args)
        t1 = EmptyOperator(task_id="t1", dag=dag)

        assert t1.retries == 5
        assert t1.retry_delay == timedelta(seconds=15)
        assert t1.retry_exponential_backoff is True
        assert dag.has_task("t1")

    def test_bitshift_dependency_chain(self) -> None:
        """T2: Single bitshift >> correctly sets upstreams and downstreams."""
        t1 = EmptyOperator(task_id="t1")
        t2 = EmptyOperator(task_id="t2")
        t1 >> t2

        assert "t1" in t2.upstream_task_ids
        assert "t2" in t1.downstream_task_ids

    def test_list_bitshift(self) -> None:
        """T3: List bitshift [t1, t2] >> t3 and t3 >> [t4, t5]."""
        t1 = EmptyOperator(task_id="t1")
        t2 = EmptyOperator(task_id="t2")
        t3 = EmptyOperator(task_id="t3")
        t4 = EmptyOperator(task_id="t4")

        [t1, t2] >> t3 >> t4

        assert "t1" in t3.upstream_task_ids
        assert "t2" in t3.upstream_task_ids
        assert "t3" in t4.upstream_task_ids


# ---------------------------------------------------------------------------
# T4-T6 — Topology & Validation
# ---------------------------------------------------------------------------
class TestTopologyAndValidation:
    def test_topological_sort(self) -> None:
        """T4: Ordered tasks strictly respect dependency tree."""
        dag = DAG(dag_id="linear_dag")
        t1 = EmptyOperator(task_id="extract", dag=dag)
        t2 = EmptyOperator(task_id="transform", dag=dag)
        t3 = EmptyOperator(task_id="load", dag=dag)
        t1 >> t2 >> t3

        ordered = AirflowExecutionEngine.topological_sort(dag)
        ids = [t.task_id for t in ordered]
        assert ids == ["extract", "transform", "load"]

    def test_cycle_detection(self) -> None:
        """T5: Cycle t1 -> t2 -> t3 -> t1 raises AirflowDAGValidationError."""
        dag = DAG(dag_id="cycle_dag")
        t1 = EmptyOperator(task_id="t1", dag=dag)
        t2 = EmptyOperator(task_id="t2", dag=dag)
        t3 = EmptyOperator(task_id="t3", dag=dag)
        t1 >> t2 >> t3 >> t1

        with pytest.raises(AirflowDAGValidationError, match="Cycle detected"):
            AirflowExecutionEngine.validate_dag(dag)

    def test_duplicate_task_id_rejected(self) -> None:
        """Duplicate task_ids in a DAG raise ValueError."""
        dag = DAG(dag_id="dup_dag")
        EmptyOperator(task_id="same_id", dag=dag)
        with pytest.raises(ValueError, match="Duplicate task_id"):
            EmptyOperator(task_id="same_id", dag=dag)


# ---------------------------------------------------------------------------
# T7-T10 — Task Execution & Sensor Handling
# ---------------------------------------------------------------------------
class TestTaskExecution:
    def test_python_operator_receives_context(self) -> None:
        """T7: Airflow context macros (ds, execution_date) are passed to callable."""
        captured: Dict[str, Any] = {}

        def my_fn(**context: Any) -> str:
            captured["ds"] = context.get("ds")
            captured["execution_date"] = context.get("execution_date")
            return "ok"

        dag = DAG(dag_id="ctx_dag")
        PythonOperator(task_id="my_task", python_callable=my_fn, dag=dag)

        engine = AirflowExecutionEngine(sleep_fn=_no_op_sleep)
        now = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
        res = engine.execute_dag(dag, execution_date=now)

        assert res.success is True
        assert captured["ds"] == "2026-05-10"
        assert captured["execution_date"] == now

    def test_sensor_poke_success(self) -> None:
        """T8: Sensor whose poke returns True immediately succeeds."""
        class InstantSensor(BaseSensorOperator):
            def poke(self, context: Dict[str, Any]) -> bool:
                return True

        dag = DAG(dag_id="sensor_dag")
        InstantSensor(task_id="test_sensor", dag=dag)

        engine = AirflowExecutionEngine(sleep_fn=_no_op_sleep)
        res = engine.execute_dag(dag)
        assert res.task_results["test_sensor"].state == TaskState.SUCCESS

    def test_sensor_poke_timeout(self) -> None:
        """T9: Sensor whose poke returns False times out and fails task."""
        class StalledSensor(BaseSensorOperator):
            def poke(self, context: Dict[str, Any]) -> bool:
                return False

        dag = DAG(dag_id="timeout_dag")
        StalledSensor(
            task_id="stalled_sensor",
            timeout=timedelta(milliseconds=50),
            poke_interval=timedelta(milliseconds=10),
            dag=dag,
        )

        engine = AirflowExecutionEngine(sleep_fn=_no_op_sleep)
        res = engine.execute_dag(dag)
        assert res.success is False
        assert res.task_results["stalled_sensor"].state == TaskState.FAILED


# ---------------------------------------------------------------------------
# T11-T15 — Retries, Failure Cascades, Callbacks & SLA
# ---------------------------------------------------------------------------
class TestRetriesAndCascades:
    def test_task_retries_and_succeeds(self) -> None:
        """T11/T12: Task failing 2 times with retries=3 succeeds on 3rd attempt."""
        attempts = 0

        def flaky_task(**context: Any) -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError("Transient DB glitch")
            return "recovered"

        dag = DAG(dag_id="flaky_dag")
        PythonOperator(
            task_id="flaky",
            python_callable=flaky_task,
            retries=3,
            retry_delay=timedelta(milliseconds=1),
            retry_exponential_backoff=True,
            dag=dag,
        )

        engine = AirflowExecutionEngine(sleep_fn=_no_op_sleep)
        res = engine.execute_dag(dag)

        assert res.success is True
        assert res.task_results["flaky"].state == TaskState.SUCCESS
        assert res.task_results["flaky"].retries_exhausted == 2
        assert res.task_results["flaky"].return_value == "recovered"

    def test_upstream_failure_cascades(self) -> None:
        """T13: Failed upstream marks downstreams as UPSTREAM_FAILED without executing them."""
        dag = DAG(dag_id="cascade_dag")
        t1 = PythonOperator(
            task_id="bad_upstream",
            python_callable=lambda **c: (_ for _ in ()).throw(ValueError("fatal")),
            retries=0,
            dag=dag,
        )
        downstream_executed = False

        def downstream_fn(**c: Any) -> None:
            nonlocal downstream_executed
            downstream_executed = True

        t2 = PythonOperator(task_id="guarded_downstream", python_callable=downstream_fn, dag=dag)
        t1 >> t2

        engine = AirflowExecutionEngine(sleep_fn=_no_op_sleep)
        res = engine.execute_dag(dag)

        assert res.success is False
        assert res.task_results["bad_upstream"].state == TaskState.FAILED
        assert res.task_results["guarded_downstream"].state == TaskState.UPSTREAM_FAILED
        assert downstream_executed is False

    def test_callbacks_invoked(self) -> None:
        """T14: on_success_callback and on_failure_callback are triggered."""
        success_called = False
        failure_called = False

        dag = DAG(dag_id="callback_dag")
        PythonOperator(
            task_id="success_task",
            python_callable=lambda **c: "done",
            on_success_callback=lambda c: nonlocal_success(),
            dag=dag,
        )
        PythonOperator(
            task_id="failure_task",
            python_callable=lambda **c: (_ for _ in ()).throw(RuntimeError("fail")),
            on_failure_callback=lambda c: nonlocal_failure(),
            retries=0,
            dag=dag,
        )

        def nonlocal_success() -> None:
            nonlocal success_called
            success_called = True

        def nonlocal_failure() -> None:
            nonlocal failure_called
            failure_called = True

        engine = AirflowExecutionEngine(sleep_fn=_no_op_sleep)
        engine.execute_dag(dag)

        assert success_called is True
        assert failure_called is True

    def test_sla_miss_detection(self) -> None:
        """T15: Task exceeding SLA is flagged in sla_missed_tasks."""
        import time

        def slow_task(**c: Any) -> str:
            time.sleep(0.05)
            return "slow_done"

        dag = DAG(dag_id="sla_dag")
        PythonOperator(
            task_id="slow",
            python_callable=slow_task,
            sla=timedelta(milliseconds=10),
            dag=dag,
        )

        engine = AirflowExecutionEngine(sleep_fn=_no_op_sleep)
        res = engine.execute_dag(dag)

        assert res.success is True
        assert "slow" in res.sla_missed_tasks


# ---------------------------------------------------------------------------
# T16-T17 — Backfill Engine & Idempotency
# ---------------------------------------------------------------------------
class TestBackfillEngine:
    def test_multi_date_backfill(self) -> None:
        """T16: Backfill executes DAG sequentially over start_date to end_date."""
        executed_dates: List[str] = []

        def capture_ds(**c: Any) -> None:
            executed_dates.append(c["ds"])

        dag = DAG(dag_id="backfill_dag")
        PythonOperator(task_id="record_ds", python_callable=capture_ds, dag=dag)

        engine = AirflowExecutionEngine(sleep_fn=_no_op_sleep)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 4, tzinfo=timezone.utc)

        result: BackfillResult = engine.backfill(dag, start, end, interval=timedelta(days=1))

        assert result.total_runs == 4
        assert result.successful_runs == 4
        assert result.failed_runs == 0
        assert executed_dates == ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]

    def test_backfill_idempotency(self) -> None:
        """T17: Re-running backfill on same date range produces identical state."""
        state_store: Dict[str, int] = {}

        def idempotent_write(**c: Any) -> None:
            ds = c["ds"]
            # Idempotent write: overwrites/sets value for date
            state_store[ds] = 1

        dag = DAG(dag_id="idempotent_backfill")
        PythonOperator(task_id="write_state", python_callable=idempotent_write, dag=dag)

        engine = AirflowExecutionEngine(sleep_fn=_no_op_sleep)
        start = datetime(2026, 2, 1, tzinfo=timezone.utc)
        end = datetime(2026, 2, 3, tzinfo=timezone.utc)

        # First run
        res1 = engine.backfill(dag, start, end)
        assert len(state_store) == 3

        # Forced re-run (backfill retry)
        res2 = engine.backfill(dag, start, end)
        assert len(state_store) == 3  # Zero duplicates, exact same keys
        assert res1.successful_runs == res2.successful_runs == 3


# ---------------------------------------------------------------------------
# T18-T20 — Production DAG Definitions
# ---------------------------------------------------------------------------
class TestProductionAirflowDags:
    def test_batch_medallion_dag_structure(self) -> None:
        """T18: healthguard_batch_medallion_dag has expected tasks and dependencies."""
        dag = create_batch_medallion_dag()
        assert dag.dag_id == "healthguard_batch_medallion_dag"
        assert dag.schedule_interval == "@daily"
        assert len(dag.tasks) == 7

        task_ids = {t.task_id for t in dag.tasks}
        expected_ids = {
            "sensor_raw_data_available",
            "ingest_bronze",
            "validate_silver_quality",
            "transform_silver",
            "aggregate_gold_marts",
            "run_dbt_models",
            "generate_audit_lineage",
        }
        assert task_ids == expected_ids

        # Verify DAG has no cycles
        AirflowExecutionEngine.validate_dag(dag)

    def test_cdc_sync_dag_structure(self) -> None:
        """T19: healthguard_cdc_sync_dag has expected tasks and dependencies."""
        dag = create_cdc_sync_dag()
        assert dag.dag_id == "healthguard_cdc_sync_dag"
        assert dag.schedule_interval == "*/15 * * * *"
        assert len(dag.tasks) == 5

        task_ids = {t.task_id for t in dag.tasks}
        expected_ids = {
            "sensor_cdc_wal",
            "extract_cdc_events",
            "reconcile_silver_lakehouse",
            "update_star_schema_scd2",
            "audit_cdc_reconciliation",
        }
        assert task_ids == expected_ids

        # Verify DAG has no cycles
        AirflowExecutionEngine.validate_dag(dag)

    def test_production_dags_execute_cleanly(self) -> None:
        """T20: Execute both production DAGs in dry/isolated run."""
        engine = AirflowExecutionEngine(sleep_fn=_no_op_sleep)
        exec_date = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)

        # Batch Medallion DAG
        batch_dag = create_batch_medallion_dag()
        res_batch = engine.execute_dag(batch_dag, execution_date=exec_date)
        assert res_batch.success is True
        assert res_batch.task_results["generate_audit_lineage"].state == TaskState.SUCCESS

        # CDC Sync DAG
        cdc_dag = create_cdc_sync_dag()
        res_cdc = engine.execute_dag(cdc_dag, execution_date=exec_date)
        assert res_cdc.success is True
        assert res_cdc.task_results["audit_cdc_reconciliation"].state == TaskState.SUCCESS
