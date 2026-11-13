"""Scalable analytical processing engine layer (DuckDB OLAP, Parquet, and Spark integration)."""

from pipeline.engine.duckdb_runner import DuckDBEngine
from pipeline.engine.parquet_exporter import export_partitioned_parquet, read_partitioned_parquet
from pipeline.engine.delta import compute_row_hashes, detect_deltas, DeltaReport
from pipeline.engine.spark_session import (
    is_spark_available,
    get_spark_session,
    SparkNotAvailableError,
    get_processing_engine,
)

__all__ = [
    "DuckDBEngine",
    "export_partitioned_parquet",
    "read_partitioned_parquet",
    "compute_row_hashes",
    "detect_deltas",
    "DeltaReport",
    "is_spark_available",
    "get_spark_session",
    "SparkNotAvailableError",
    "get_processing_engine",
]
