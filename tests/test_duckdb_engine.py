"""Unit and integration tests for Day 3 (DE-003): Scalable Analytical Processing Engine.

Tests cover:
- DuckDB OLAP engine initialization, context management, and query execution.
- Analytical aggregations (Condition, Age Band, Cost percentiles) matching headline figures.
- Columnar partitioned Parquet export and partition-pruned querying.
- SHA-256 row-level incremental delta detection (inserts, updates, unchanged).
- PySpark engine router and graceful fallback when Spark runtime is not installed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pandas as pd
import pytest

from pipeline.config import PipelineConfig, RAW_HOSPITAL_CSV
from pipeline.bronze.ingestor import load_bronze
from pipeline.silver.transformer import transform_to_silver
from pipeline.warehouse import apply_ddl, managed_connection

from pipeline.engine.duckdb_runner import DuckDBEngine
from pipeline.engine.parquet_exporter import export_partitioned_parquet, read_partitioned_parquet
from pipeline.engine.delta import compute_row_hashes, detect_deltas, DeltaReport
from pipeline.engine.spark_session import (
    is_spark_available,
    get_spark_session,
    SparkNotAvailableError,
    get_processing_engine,
)


@pytest.fixture(scope="module")
def silver_sample_df(tmp_path_factory) -> pd.DataFrame:
    """Provide a validated Silver dataset for testing engine features."""
    tmp = tmp_path_factory.mktemp("engine_test")
    cfg = PipelineConfig(
        warehouse_db=tmp / "test.db",
        source_csv=RAW_HOSPITAL_CSV,
        reports_dir=tmp / "reports",
    )
    apply_ddl(cfg)
    load_bronze(cfg)
    transform_to_silver(cfg)
    with managed_connection(cfg.warehouse_db) as conn:
        df = pd.read_sql_query("SELECT * FROM silver_encounters", conn)
    return df


# ---------------------------------------------------------------------------
# 1. DuckDB OLAP Engine Tests
# ---------------------------------------------------------------------------
class TestDuckDBEngine:
    def test_in_memory_connection(self):
        engine = DuckDBEngine()
        df = engine.execute_query("SELECT 1 AS val")
        assert df["val"].iloc[0] == 1
        engine.close()

    def test_context_manager_lifecycle(self, tmp_path: Path):
        db_file = tmp_path / "test_olap.duckdb"
        with DuckDBEngine(db_file) as engine:
            engine.execute_query("CREATE TABLE t (id INT, name VARCHAR)")
            engine.execute_query("INSERT INTO t VALUES (1, 'HealthGuard')")
            res = engine.query_scalar("SELECT name FROM t WHERE id = 1")
            assert res == "HealthGuard"
        assert db_file.exists()

    def test_parameterized_query_safety(self):
        with DuckDBEngine() as engine:
            query = "SELECT ? + ? AS sum_val"
            df = engine.execute_query(query, params=[10, 32])
            assert df["sum_val"].iloc[0] == 42

    def test_register_and_query_dataframe(self, silver_sample_df: pd.DataFrame):
        with DuckDBEngine() as engine:
            engine.register_df("patients", silver_sample_df)
            count = engine.query_scalar("SELECT count(*) FROM patients")
            assert count == len(silver_sample_df)

    def test_condition_metrics_reconciliation(self, silver_sample_df: pd.DataFrame):
        with DuckDBEngine() as engine:
            engine.register_df("silver", silver_sample_df)
            metrics = engine.compute_condition_metrics("silver")
            
            assert "Condition" in metrics.columns
            assert "patient_count" in metrics.columns
            assert "readmission_rate_pct" in metrics.columns
            assert "avg_cost" in metrics.columns
            assert metrics["patient_count"].sum() == 984

    def test_cost_percentiles(self, silver_sample_df: pd.DataFrame):
        with DuckDBEngine() as engine:
            engine.register_df("silver", silver_sample_df)
            pcts = engine.compute_cost_percentiles("silver")
            
            assert "p25" in pcts
            assert "p50" in pcts
            assert "p75" in pcts
            assert "p90" in pcts
            assert pcts["p25"] <= pcts["p50"] <= pcts["p75"] <= pcts["p90"]


# ---------------------------------------------------------------------------
# 2. Partitioned Parquet Storage Tests
# ---------------------------------------------------------------------------
class TestParquetPartitioning:
    def test_export_partitioned_parquet(self, silver_sample_df: pd.DataFrame, tmp_path: Path):
        parquet_dir = tmp_path / "parquet_marts"
        out_path = export_partitioned_parquet(
            df=silver_sample_df,
            base_dir=parquet_dir,
            partition_cols=["condition", "age_band"],
        )
        assert out_path.exists()
        
        # Verify partition subdirectories exist
        subdirs = [p.name for p in out_path.iterdir() if p.is_dir()]
        assert any("condition=" in d for d in subdirs)

    def test_partition_pruned_query(self, silver_sample_df: pd.DataFrame, tmp_path: Path):
        parquet_dir = tmp_path / "parquet_prune"
        export_partitioned_parquet(
            df=silver_sample_df,
            base_dir=parquet_dir,
            partition_cols=["condition", "age_band"],
        )
        
        with DuckDBEngine() as engine:
            # Query only Diabetes condition
            parquet_glob = str(parquet_dir / "**/*.parquet")
            query = f"""
                SELECT count(*) FROM read_parquet('{parquet_glob}', hive_partitioning=true)
                WHERE condition = 'Diabetes'
            """
            count = engine.query_scalar(query)
            expected = int((silver_sample_df["condition"] == "Diabetes").sum())
            assert count == expected

    def test_round_trip_preserves_row_count(self, silver_sample_df: pd.DataFrame, tmp_path: Path):
        parquet_dir = tmp_path / "parquet_roundtrip"
        export_partitioned_parquet(silver_sample_df, parquet_dir, partition_cols=["condition"])
        df_read = read_partitioned_parquet(parquet_dir)
        assert len(df_read) == len(silver_sample_df)
        assert set(df_read["patient_id"]) == set(silver_sample_df["patient_id"])


# ---------------------------------------------------------------------------
# 3. Incremental Delta Engine Tests
# ---------------------------------------------------------------------------
class TestIncrementalDeltaEngine:
    def test_compute_row_hashes_deterministic(self, silver_sample_df: pd.DataFrame):
        hashes1 = compute_row_hashes(silver_sample_df)
        hashes2 = compute_row_hashes(silver_sample_df)
        assert (hashes1 == hashes2).all()
        assert len(hashes1) == len(silver_sample_df)

    def test_detect_deltas_identical_datasets(self, silver_sample_df: pd.DataFrame):
        delta_df, report = detect_deltas(
            existing_df=silver_sample_df,
            incoming_df=silver_sample_df,
            key_col="patient_id",
        )
        assert report.new_rows == 0
        assert report.updated_rows == 0
        assert report.unchanged_rows == len(silver_sample_df)
        assert len(delta_df) == 0

    def test_detect_deltas_with_inserts_and_updates(self, silver_sample_df: pd.DataFrame):
        base_df = silver_sample_df.iloc[:500].copy()
        
        # Modify row 0 cost
        incoming_df = base_df.copy()
        incoming_df.loc[0, "cost"] = incoming_df.loc[0, "cost"] + 1000
        
        # Add new row from original dataset
        new_row = silver_sample_df.iloc[[501]].copy()
        incoming_df = pd.concat([incoming_df, new_row], ignore_index=True)
        
        delta_df, report = detect_deltas(
            existing_df=base_df,
            incoming_df=incoming_df,
            key_col="patient_id",
        )
        
        assert report.new_rows == 1
        assert report.updated_rows == 1
        assert report.unchanged_rows == 499
        assert len(delta_df) == 2


# ---------------------------------------------------------------------------
# 4. Engine Router and PySpark Fallback Tests
# ---------------------------------------------------------------------------
class TestEngineRouterAndSparkFallback:
    def test_is_spark_available_boolean(self):
        avail = is_spark_available()
        assert isinstance(avail, bool)

    def test_spark_session_fallback_behavior(self):
        if not is_spark_available():
            with pytest.raises(SparkNotAvailableError):
                get_spark_session(fallback_to_duckdb=False)
        else:
            session = get_spark_session()
            assert session is not None

    def test_processing_engine_router_duckdb(self):
        engine = get_processing_engine(prefer="duckdb")
        assert isinstance(engine, DuckDBEngine)
        engine.close()

    def test_processing_engine_router_spark_falls_back_gracefully(self):
        # If spark not available, routing to prefer="spark" should return DuckDBEngine with fallback
        engine = get_processing_engine(prefer="spark", fallback=True)
        assert engine is not None
        engine.close()
