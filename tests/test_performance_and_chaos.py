"""
Unit and integration tests for Day 15 (DE-015):
Synthetic Load Benchmarks, Chaos Fault Injection, and Enterprise Documentation Integrity.
"""

from pathlib import Path
from typing import Any, Dict
import pytest

from pipeline.benchmarks.load_benchmark import SyntheticLoadBenchmark, BenchmarkResult
from pipeline.benchmarks.chaos_engine import LakehouseChaosEngine, ChaosExperimentResult

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestSyntheticLoadBenchmark:
    """Verifies synthetic workload generation, ingestion throughput, and OLAP query latencies."""

    @pytest.fixture
    def benchmark_engine(self) -> SyntheticLoadBenchmark:
        return SyntheticLoadBenchmark(seed=42)

    def test_synthetic_batch_generation(self, benchmark_engine: SyntheticLoadBenchmark) -> None:
        """T01: Synthetic batch generates expected schema and row counts."""
        df = benchmark_engine.generate_synthetic_batch(500)
        assert len(df) == 500
        expected_cols = [
            "patient_id",
            "encounter_id",
            "age",
            "gender",
            "condition",
            "cost",
            "length_of_stay",
            "readmitted",
            "outcome",
            "satisfaction",
        ]
        for col in expected_cols:
            assert col in df.columns, f"Missing expected column '{col}' in synthetic batch"
        assert (df["cost"] > 0).all(), "All generated costs must be positive"

    def test_load_benchmark_execution(self, benchmark_engine: SyntheticLoadBenchmark) -> None:
        """T02: Benchmarking engine measures throughput, memory, and query percentiles."""
        res: BenchmarkResult = benchmark_engine.run_benchmark(n_records=5000, query_iterations=20)
        assert res.scale_records == 5000
        assert res.ingestion_throughput_rps > 1000.0, "Throughput should exceed 1,000 records/sec"
        assert res.p50_query_latency_ms > 0.0
        assert res.p95_query_latency_ms >= res.p50_query_latency_ms
        assert res.peak_memory_mb > 0.0

        d = res.to_dict()
        assert d["metrics_summary"]["status"] == "PASS"


class TestLakehouseChaosEngine:
    """Verifies resilience against broker pause, corrupt batch poisoning, and crash recovery."""

    def test_kafka_broker_pause_and_recovery(self) -> None:
        """T03: Chaos test recovers 100% of buffered events after broker network partition."""
        res: ChaosExperimentResult = LakehouseChaosEngine.test_broker_pause_and_resume(
            num_events=50, pause_duration_sec=0.01
        )
        assert res.passed is True
        assert res.recovery_time_ms > 0.0
        assert res.details["consumed_events"] == 50
        assert res.details["buffered_during_pause"] == 20

    def test_corrupt_batch_quarantine_isolation(self) -> None:
        """T04: Poison pill records are quarantined while valid records reach Silver."""
        res: ChaosExperimentResult = LakehouseChaosEngine.test_corrupt_batch_quarantine_isolation(
            total_records=100, corrupt_count=15
        )
        assert res.passed is True
        assert res.details["quarantine_records"] == 15
        assert res.details["silver_records"] == 85

    def test_worker_crash_and_idempotent_retry(self) -> None:
        """T05: Worker killed mid-transaction produces zero duplicate rows on idempotent retry."""
        res: ChaosExperimentResult = LakehouseChaosEngine.test_task_crash_and_idempotent_retry()
        assert res.passed is True
        assert res.details["interrupted_row_count"] == 2
        assert res.details["final_row_count"] == 3


class TestDocumentationIntegrity:
    """Verifies all enterprise documentation artifacts are present and comprehensive."""

    def test_architecture_doc_present_and_valid(self) -> None:
        """T06: ARCHITECTURE.md contains system design, Medallion tiers, and Mermaid diagram."""
        p = REPO_ROOT / "docs" / "ARCHITECTURE.md"
        assert p.exists(), "docs/ARCHITECTURE.md must exist"
        content = p.read_text(encoding="utf-8")
        assert "```mermaid" in content
        assert "Medallion Storage Tiers" in content
        assert "Bronze Tier" in content
        assert "Silver Tier" in content
        assert "Gold Tier" in content

    def test_data_dictionary_doc_present_and_valid(self) -> None:
        """T07: DATA_DICTIONARY.md defines all Bronze, Silver, and Gold dimensional tables."""
        p = REPO_ROOT / "docs" / "DATA_DICTIONARY.md"
        assert p.exists(), "docs/DATA_DICTIONARY.md must exist"
        content = p.read_text(encoding="utf-8")
        assert "bronze_encounters" in content
        assert "silver_encounters" in content
        assert "dim_patient" in content
        assert "fact_encounter" in content
        assert "gold_condition_mart" in content

    def test_data_governance_doc_present_and_valid(self) -> None:
        """T08: DATA_GOVERNANCE.md details 4-pillar trust scoring and AST guardrails."""
        p = REPO_ROOT / "docs" / "DATA_GOVERNANCE.md"
        assert p.exists(), "docs/DATA_GOVERNANCE.md must exist"
        content = p.read_text(encoding="utf-8")
        assert "4-Pillar Data Trust Scoring Framework" in content
        assert "Validity" in content
        assert "Completeness" in content
        assert "Uniqueness" in content
        assert "Referential Integrity" in content
        assert "SQLGlot" in content

    def test_runbook_doc_present_and_valid(self) -> None:
        """T09: RUNBOOK.md details disaster recovery, startup, and incident playbooks."""
        p = REPO_ROOT / "docs" / "RUNBOOK.md"
        assert p.exists(), "docs/RUNBOOK.md must exist"
        content = p.read_text(encoding="utf-8")
        assert "Quickstart & Service Startup" in content
        assert "Incident Response Playbooks" in content
        assert "Disaster Recovery & Backup" in content

    def test_readme_references_healthguard_360(self) -> None:
        """T10: README.md highlights HealthGuard 360, quickstart, and test commands."""
        p = REPO_ROOT / "README.md"
        assert p.exists(), "README.md must exist"
        content = p.read_text(encoding="utf-8")
        assert "HealthGuard 360" in content
        assert "Architecture" in content
        assert "Quickstart" in content
