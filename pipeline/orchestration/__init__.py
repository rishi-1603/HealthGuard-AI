"""
HealthGuard 360 Orchestration Package.

Exports Airflow DAG definitions and execution engine abstractions.
"""
from pipeline.orchestration.airflow_compat import (
    DAG,
    BaseOperator,
    BaseSensorOperator,
    EmptyOperator,
    ExternalTaskSensor,
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

__all__ = [
    "DAG",
    "BaseOperator",
    "PythonOperator",
    "EmptyOperator",
    "BaseSensorOperator",
    "FileSensor",
    "ExternalTaskSensor",
    "TaskState",
    "TaskResult",
    "AirflowExecutionEngine",
    "AirflowDAGValidationError",
    "DagRunResult",
    "BackfillResult",
]
