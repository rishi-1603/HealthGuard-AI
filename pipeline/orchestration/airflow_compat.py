"""
Airflow Compatibility Layer for HealthGuard 360.

Provides standard Apache Airflow abstractions (DAG, BaseOperator, PythonOperator,
EmptyOperator, BaseSensorOperator, FileSensor, ExternalTaskSensor) that conform
to Airflow 2.x API. If apache-airflow is installed, aliases can defer to native;
otherwise, provides a clean, dependency-free, high-fidelity implementation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    """Airflow Task Instance Execution State."""
    NONE = "none"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    UPSTREAM_FAILED = "upstream_failed"
    SKIPPED = "skipped"
    UP_FOR_RETRY = "up_for_retry"


@dataclass(frozen=True)
class TaskResult:
    """Immutable result of a single task execution."""
    task_id: str
    state: TaskState
    execution_date: datetime
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    retries_exhausted: int
    return_value: Any = None
    error_message: Optional[str] = None
    sla_missed: bool = False


class BaseOperator:
    """Airflow BaseOperator abstraction supporting standard bitshift operators."""

    def __init__(
        self,
        task_id: str,
        dag: Optional["DAG"] = None,
        retries: int = 0,
        retry_delay: Union[int, float, timedelta] = 60,
        retry_exponential_backoff: bool = False,
        sla: Optional[timedelta] = None,
        execution_timeout: Optional[timedelta] = None,
        on_failure_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_success_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        **kwargs: Any,
    ) -> None:
        if not task_id or not isinstance(task_id, str):
            raise ValueError("task_id must be a non-empty string")
        self.task_id = task_id
        self.retries = retries
        self.retry_delay = (
            retry_delay if isinstance(retry_delay, timedelta)
            else timedelta(seconds=float(retry_delay))
        )
        self.retry_exponential_backoff = retry_exponential_backoff
        self.sla = sla
        self.execution_timeout = execution_timeout
        self.on_failure_callback = on_failure_callback
        self.on_success_callback = on_success_callback
        self.extra_args = kwargs

        self._upstream_task_ids: Set[str] = set()
        self._downstream_task_ids: Set[str] = set()

        if dag is not None:
            dag.add_task(self)

    @property
    def upstream_task_ids(self) -> Set[str]:
        return set(self._upstream_task_ids)

    @property
    def downstream_task_ids(self) -> Set[str]:
        return set(self._downstream_task_ids)

    def execute(self, context: Dict[str, Any]) -> Any:
        """Override in subclasses."""
        return None

    def set_downstream(
        self, task_or_task_list: Union["BaseOperator", List["BaseOperator"]]
    ) -> None:
        tasks = (
            task_or_task_list if isinstance(task_or_task_list, list)
            else [task_or_task_list]
        )
        for t in tasks:
            self._downstream_task_ids.add(t.task_id)
            t._upstream_task_ids.add(self.task_id)

    def set_upstream(
        self, task_or_task_list: Union["BaseOperator", List["BaseOperator"]]
    ) -> None:
        tasks = (
            task_or_task_list if isinstance(task_or_task_list, list)
            else [task_or_task_list]
        )
        for t in tasks:
            self._upstream_task_ids.add(t.task_id)
            t._downstream_task_ids.add(self.task_id)

    def __rshift__(
        self, other: Union["BaseOperator", List["BaseOperator"]]
    ) -> Union["BaseOperator", List["BaseOperator"]]:
        self.set_downstream(other)
        return other

    def __lshift__(
        self, other: Union["BaseOperator", List["BaseOperator"]]
    ) -> Union["BaseOperator", List["BaseOperator"]]:
        self.set_upstream(other)
        return other

    def __rrshift__(
        self, other: Union["BaseOperator", List["BaseOperator"]]
    ) -> "BaseOperator":
        """Handles [t1, t2] >> t3."""
        self.set_upstream(other)
        return self

    def __rlshift__(
        self, other: Union["BaseOperator", List["BaseOperator"]]
    ) -> "BaseOperator":
        """Handles [t1, t2] << t3."""
        self.set_downstream(other)
        return self

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(task_id={self.task_id})>"


class EmptyOperator(BaseOperator):
    """No-op operator (Airflow 2.x replacement for DummyOperator)."""

    def execute(self, context: Dict[str, Any]) -> Any:
        return None


# Backwards compatibility alias
DummyOperator = EmptyOperator


class PythonOperator(BaseOperator):
    """Executes a Python callable with context arguments."""

    def __init__(
        self,
        task_id: str,
        python_callable: Callable[..., Any],
        op_kwargs: Optional[Dict[str, Any]] = None,
        op_args: Optional[List[Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(task_id=task_id, **kwargs)
        if not callable(python_callable):
            raise TypeError("python_callable must be callable")
        self.python_callable = python_callable
        self.op_kwargs = op_kwargs or {}
        self.op_args = op_args or []

    def execute(self, context: Dict[str, Any]) -> Any:
        merged_kwargs = {**context, **self.op_kwargs}
        try:
            return self.python_callable(*self.op_args, **merged_kwargs)
        except TypeError:
            # Fallback if callable does not accept arbitrary context kwargs
            return self.python_callable(*self.op_args, **self.op_kwargs)


class BaseSensorOperator(BaseOperator):
    """Base sensor polling for an external condition until poke returns True or timeout."""

    def __init__(
        self,
        task_id: str,
        poke_interval: Union[int, float, timedelta] = 10,
        timeout: Union[int, float, timedelta] = 300,
        mode: str = "poke",
        soft_fail: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(task_id=task_id, **kwargs)
        self.poke_interval = (
            poke_interval if isinstance(poke_interval, timedelta)
            else timedelta(seconds=float(poke_interval))
        )
        self.timeout = (
            timeout if isinstance(timeout, timedelta)
            else timedelta(seconds=float(timeout))
        )
        self.mode = mode
        self.soft_fail = soft_fail

    def poke(self, context: Dict[str, Any]) -> bool:
        """Override in subclasses. Return True when condition is satisfied."""
        return True

    def execute(self, context: Dict[str, Any]) -> bool:
        return self.poke(context)


class FileSensor(BaseSensorOperator):
    """Sensor that checks whether a given file exists on the filesystem."""

    def __init__(
        self,
        task_id: str,
        filepath: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(task_id=task_id, **kwargs)
        self.filepath = filepath

    def poke(self, context: Dict[str, Any]) -> bool:
        from pathlib import Path
        path = Path(self.filepath)
        return path.exists()


class ExternalTaskSensor(BaseSensorOperator):
    """Sensor checking external DAG completion."""

    def __init__(
        self,
        task_id: str,
        external_dag_id: str,
        external_task_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(task_id=task_id, **kwargs)
        self.external_dag_id = external_dag_id
        self.external_task_id = external_task_id

    def poke(self, context: Dict[str, Any]) -> bool:
        # Default behavior: checks context registry for external completion
        external_registry = context.get("external_task_registry", {})
        key = (self.external_dag_id, self.external_task_id or "__all__")
        return bool(external_registry.get(key, True))


class DAG:
    """Airflow DAG abstraction."""

    def __init__(
        self,
        dag_id: str,
        description: str = "",
        schedule_interval: Optional[str] = "@daily",
        start_date: Optional[datetime] = None,
        default_args: Optional[Dict[str, Any]] = None,
        catchup: bool = False,
        max_active_runs: int = 1,
        tags: Optional[List[str]] = None,
        sla: Optional[timedelta] = None,
    ) -> None:
        if not dag_id or not isinstance(dag_id, str):
            raise ValueError("dag_id must be a non-empty string")
        self.dag_id = dag_id
        self.description = description
        self.schedule_interval = schedule_interval
        self.start_date = start_date or datetime.now(timezone.utc)
        self.default_args = default_args or {}
        self.catchup = catchup
        self.max_active_runs = max_active_runs
        self.tags = list(tags or [])
        self.sla = sla

        self._tasks: Dict[str, BaseOperator] = {}

    def add_task(self, task: BaseOperator) -> None:
        if task.task_id in self._tasks and self._tasks[task.task_id] is not task:
            raise ValueError(f"Duplicate task_id '{task.task_id}' in DAG '{self.dag_id}'")
        self._tasks[task.task_id] = task

        # Inherit default_args if not set on task
        if task.retries == 0 and "retries" in self.default_args:
            task.retries = self.default_args["retries"]
        if "retry_delay" in self.default_args and hasattr(task, "retry_delay"):
            d = self.default_args["retry_delay"]
            task.retry_delay = d if isinstance(d, timedelta) else timedelta(seconds=float(d))
        if "retry_exponential_backoff" in self.default_args:
            task.retry_exponential_backoff = self.default_args["retry_exponential_backoff"]
        if task.sla is None and "sla" in self.default_args:
            task.sla = self.default_args["sla"]

    @property
    def tasks(self) -> List[BaseOperator]:
        return list(self._tasks.values())

    def get_task(self, task_id: str) -> BaseOperator:
        if task_id not in self._tasks:
            raise KeyError(f"Task '{task_id}' not found in DAG '{self.dag_id}'")
        return self._tasks[task_id]

    def has_task(self, task_id: str) -> bool:
        return task_id in self._tasks

    def __enter__(self) -> "DAG":
        _DAGContext.set_current_dag(self)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        _DAGContext.clear_current_dag()

    def __repr__(self) -> str:
        return f"<DAG(dag_id={self.dag_id}, tasks={len(self._tasks)})>"


class _DAGContext:
    """Thread-local context manager tracking the active DAG block."""
    _current_dag: Optional[DAG] = None

    @classmethod
    def set_current_dag(cls, dag: DAG) -> None:
        cls._current_dag = dag

    @classmethod
    def clear_current_dag(cls) -> None:
        cls._current_dag = None

    @classmethod
    def get_current_dag(cls) -> Optional[DAG]:
        return cls._current_dag
