"""PySpark session manager and multi-engine analytical router.

Supports distributed processing via PySpark when runtime is available, with
automatic high-speed fallback to DuckDB in local or serverless environments.
"""

from __future__ import annotations

import logging
from typing import Any
from pipeline.engine.duckdb_runner import DuckDBEngine

logger = logging.getLogger(__name__)


class SparkNotAvailableError(ImportError):
    """Raised when PySpark operations are attempted without pyspark installed."""
    pass


def is_spark_available() -> bool:
    """Check if PySpark is installed and importable."""
    try:
        import pyspark  # noqa: F401
        return True
    except (ImportError, ModuleNotFoundError):
        return False


def get_spark_session(
    app_name: str = "HealthGuardAnalytics",
    fallback_to_duckdb: bool = False,
) -> Any:
    """Retrieve or create a SparkSession, with optional DuckDB fallback.
    
    Args:
        app_name: Spark application name.
        fallback_to_duckdb: If True and PySpark is absent, returns DuckDBEngine instead.
    
    Returns:
        SparkSession or DuckDBEngine.
    """
    if not is_spark_available():
        if fallback_to_duckdb:
            logger.warning("PySpark unavailable; routing execution to DuckDB engine.")
            return DuckDBEngine()
        raise SparkNotAvailableError(
            "PySpark is not installed. Run 'pip install pyspark' or use DuckDBEngine."
        )

    from pyspark.sql import SparkSession  # type: ignore

    session = (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.driver.memory", "2g")
        .getOrCreate()
    )
    return session


def get_processing_engine(
    prefer: str = "duckdb",
    fallback: bool = True,
) -> Any:
    """Factory router returning the optimal available analytical engine."""
    if prefer.lower() == "spark":
        if is_spark_available():
            return get_spark_session()
        elif fallback:
            logger.info("Preferred engine 'spark' unavailable; falling back to DuckDB.")
            return DuckDBEngine()
        else:
            raise SparkNotAvailableError("PySpark is unavailable and fallback=False.")
            
    return DuckDBEngine()
