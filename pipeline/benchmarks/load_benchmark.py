"""
Synthetic Load and Performance Benchmarking Engine for HealthGuard 360 Lakehouse.
Measures ingestion throughput, stage latencies, memory footprint, and OLAP query percentiles.
"""

from dataclasses import dataclass, field
import gc
import time
from typing import Any, Dict, List, Optional
import duckdb
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BenchmarkResult:
    """Immutable record of load and query performance benchmark execution."""
    scale_records: int
    generation_time_sec: float
    ingestion_time_sec: float
    ingestion_throughput_rps: float
    transformation_time_sec: float
    p50_query_latency_ms: float
    p95_query_latency_ms: float
    p99_query_latency_ms: float
    peak_memory_mb: float
    metrics_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scale_records": self.scale_records,
            "generation_time_sec": round(self.generation_time_sec, 3),
            "ingestion_time_sec": round(self.ingestion_time_sec, 3),
            "ingestion_throughput_rps": round(self.ingestion_throughput_rps, 1),
            "transformation_time_sec": round(self.transformation_time_sec, 3),
            "p50_query_latency_ms": round(self.p50_query_latency_ms, 2),
            "p95_query_latency_ms": round(self.p95_query_latency_ms, 2),
            "p99_query_latency_ms": round(self.p99_query_latency_ms, 2),
            "peak_memory_mb": round(self.peak_memory_mb, 2),
            "metrics_summary": dict(self.metrics_summary),
        }


class SyntheticLoadBenchmark:
    """
    Generates high-volume synthetic clinical workloads and benchmarks
    the lakehouse ingestion and analytical query engine.
    """

    CONDITIONS = ["Diabetes", "Hypertension", "Heart Disease", "Asthma", "Sepsis"]
    GENDERS = ["M", "F", "Other"]
    OUTCOMES = ["Discharged", "Transferred", "Expired", "AMA"]

    def __init__(self, seed: int = 42) -> None:
        self.rng = np.random.default_rng(seed)

    def generate_synthetic_batch(self, n_records: int) -> pd.DataFrame:
        """Generate high-fidelity synthetic clinical records at scale."""
        patient_ids = [f"PT-{i:07d}" for i in self.rng.integers(1, n_records // 3 + 2, size=n_records)]
        encounter_ids = [f"ENC-{i:08d}" for i in range(1, n_records + 1)]
        ages = self.rng.integers(18, 90, size=n_records)
        genders = self.rng.choice(self.GENDERS, size=n_records)
        conditions = self.rng.choice(self.CONDITIONS, size=n_records)
        costs = np.round(self.rng.uniform(500.0, 50000.0, size=n_records), 2)
        los = self.rng.integers(1, 21, size=n_records)
        readmitted = self.rng.choice([0, 1], p=[0.75, 0.25], size=n_records)
        outcomes = self.rng.choice(self.OUTCOMES, p=[0.85, 0.08, 0.05, 0.02], size=n_records)
        satisfaction = self.rng.integers(1, 6, size=n_records)

        return pd.DataFrame({
            "patient_id": patient_ids,
            "encounter_id": encounter_ids,
            "age": ages,
            "gender": genders,
            "condition": conditions,
            "cost": costs,
            "length_of_stay": los,
            "readmitted": readmitted,
            "outcome": outcomes,
            "satisfaction": satisfaction,
        })

    def run_benchmark(self, n_records: int, query_iterations: int = 50) -> BenchmarkResult:
        """
        Execute an end-to-end load benchmark:
        1. Synthetic data generation
        2. High-speed DuckDB memory ingestion & partitioning
        3. Gold-mart aggregation transformations
        4. Multi-iteration analytical query latency measurements
        """
        gc.collect()

        # Step 1: Data Generation
        t0 = time.perf_counter()
        df = self.generate_synthetic_batch(n_records)
        gen_time = time.perf_counter() - t0

        # Estimate memory
        mem_mb = df.memory_usage(deep=True).sum() / (1024 * 1024)

        # Step 2: DuckDB Ingestion
        con = duckdb.connect(database=":memory:")
        t1 = time.perf_counter()
        con.execute("CREATE TABLE bronze_raw AS SELECT * FROM df")
        ingest_time = time.perf_counter() - t1
        throughput_rps = n_records / max(ingest_time, 0.0001)

        # Step 3: Transformation / Mart Aggregation
        t2 = time.perf_counter()
        con.execute("""
            CREATE TABLE gold_condition_mart AS
            SELECT
                condition,
                COUNT(*) AS total_patients,
                SUM(readmitted) AS readmitted_count,
                ROUND(AVG(readmitted) * 100.0, 2) AS readmission_rate_pct,
                ROUND(SUM(cost), 2) AS total_cost,
                ROUND(AVG(cost), 2) AS avg_cost,
                ROUND(AVG(length_of_stay), 2) AS avg_los,
                ROUND(AVG(satisfaction), 2) AS avg_satisfaction
            FROM bronze_raw
            GROUP BY condition
        """)
        transform_time = time.perf_counter() - t2

        # Step 4: Analytical Query Latency Benchmarking
        query_latencies_ms: List[float] = []
        queries = [
            "SELECT * FROM gold_condition_mart ORDER BY total_cost DESC",
            "SELECT condition, avg_cost, readmission_rate_pct FROM gold_condition_mart WHERE total_patients > 10",
            "SELECT SUM(total_cost) AS total_spend, AVG(avg_satisfaction) AS overall_sat FROM gold_condition_mart",
            "SELECT condition, readmission_rate_pct FROM gold_condition_mart ORDER BY readmission_rate_pct DESC LIMIT 3",
        ]

        for i in range(query_iterations):
            q = queries[i % len(queries)]
            qt0 = time.perf_counter()
            con.execute(q).fetchall()
            lat_ms = (time.perf_counter() - qt0) * 1000.0
            query_latencies_ms.append(lat_ms)

        con.close()
        gc.collect()

        query_latencies_ms.sort()
        p50 = float(np.percentile(query_latencies_ms, 50))
        p95 = float(np.percentile(query_latencies_ms, 95))
        p99 = float(np.percentile(query_latencies_ms, 99))

        return BenchmarkResult(
            scale_records=n_records,
            generation_time_sec=gen_time,
            ingestion_time_sec=ingest_time,
            ingestion_throughput_rps=throughput_rps,
            transformation_time_sec=transform_time,
            p50_query_latency_ms=p50,
            p95_query_latency_ms=p95,
            p99_query_latency_ms=p99,
            peak_memory_mb=mem_mb,
            metrics_summary={
                "status": "PASS",
                "scale_label": f"{n_records // 1000}k" if n_records >= 1000 else str(n_records),
                "total_queries_executed": query_iterations,
            },
        )
