"""
DE-012 Test Suite: HealthGuard Data Trust Score & Observability Engine.

Verifies:
  T1  - Engine initialization with default and custom pillar weights
  T2  - Pristine dataset produces 100% on all 4 pillars and overall trust score >= 99.0%
  T3  - Missing values in mandatory attributes strictly degrade Completeness score
  T4  - Out-of-bounds and invalid enum values degrade Validity score
  T5  - Duplicate primary keys degrade Uniqueness score
  T6  - Orphaned foreign keys degrade Referential Integrity score
  T7  - Pillar weights validation: weights must sum to 1.0
  T8  - Overall Trust Score calculation respects configured pillar weights
  T9  - Trust status rating thresholds (PRISTINE, GOOD, DEGRADED, CRITICAL)
  T10 - Data Freshness monitoring: accurately calculates lag and freshness status
  T11 - Freshness SLA breach detection (STALE / CRITICAL_LAG)
  T12 - Schema Drift: detects missing expected columns
  T13 - Schema Drift: detects unexpected added columns
  T14 - Schema Drift: detects data type mismatches
  T15 - Quarantine trend analysis: calculates violation frequencies and quarantine rate
  T16 - JSON report serialization is complete and deterministic
  T17 - Markdown report generation produces standard audit document
  T18 - Live warehouse evaluation against silver_encounters table
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pandas as pd
import pytest

from pipeline.data_quality.trust_engine import (
    DataFreshnessReport,
    DataTrustEngine,
    DataTrustReport,
    FreshnessStatus,
    PillarScores,
    SchemaDriftReport,
    TrustStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def clean_patient_df() -> pd.DataFrame:
    """Perfect pristine dataset with zero flaws."""
    return pd.DataFrame({
        "patient_id": [f"PAT-{i:04d}" for i in range(1, 101)],
        "age": [20 + (i % 60) for i in range(1, 101)],
        "gender": ["Male" if i % 2 == 0 else "Female" for i in range(1, 101)],
        "admission_type": ["Emergency" if i % 3 == 0 else "Elective" for i in range(1, 101)],
        "diagnosis_code": ["J44.1" if i % 2 == 0 else "E11.9" for i in range(1, 101)],
        "billing_amount": [1500.0 + (i * 10.0) for i in range(1, 101)],
        "facility_id": ["FAC-01" for _ in range(100)],
    })


@pytest.fixture
def reference_facilities() -> set[str]:
    return {"FAC-01", "FAC-02", "FAC-03"}


# ---------------------------------------------------------------------------
# T1-T2 — Initialization & Pristine Dataset
# ---------------------------------------------------------------------------
class TestDataTrustEngineBasics:
    def test_engine_initialization_defaults(self) -> None:
        """T1: Default weights sum to 1.0."""
        engine = DataTrustEngine()
        assert sum(engine.weights.values()) == pytest.approx(1.0)
        assert engine.weights["validity"] == 0.35
        assert engine.weights["completeness"] == 0.25
        assert engine.weights["uniqueness"] == 0.20
        assert engine.weights["referential_integrity"] == 0.20

    def test_custom_weights_validation(self) -> None:
        """T7: Custom weights not summing to 1.0 raise ValueError."""
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            DataTrustEngine(weights={"validity": 0.5, "completeness": 0.2})

    def test_pristine_dataset_scores_100(
        self, clean_patient_df: pd.DataFrame, reference_facilities: set[str]
    ) -> None:
        """T2: Clean data produces 100% across all pillars."""
        engine = DataTrustEngine()
        report = engine.evaluate(
            df=clean_patient_df,
            primary_key="patient_id",
            mandatory_columns=["patient_id", "age", "gender", "billing_amount"],
            validation_rules={
                "age": lambda s: s.between(0, 120),
                "billing_amount": lambda s: s > 0,
            },
            foreign_keys={"facility_id": reference_facilities},
        )
        assert report.pillars.completeness == 100.0
        assert report.pillars.validity == 100.0
        assert report.pillars.uniqueness == 100.0
        assert report.pillars.referential_integrity == 100.0
        assert report.overall_trust_score == 100.0
        assert report.status == TrustStatus.PRISTINE


# ---------------------------------------------------------------------------
# T3-T6 — Known Corrupted Datasets
# ---------------------------------------------------------------------------
class TestCorruptedDatasets:
    def test_completeness_degradation(self, clean_patient_df: pd.DataFrame) -> None:
        """T3: 20 nulls in mandatory column reduce Completeness score."""
        df = clean_patient_df.copy()
        # Introduce 20 nulls in mandatory column 'age'
        df.loc[:19, "age"] = None

        engine = DataTrustEngine()
        report = engine.evaluate(
            df=df,
            primary_key="patient_id",
            mandatory_columns=["patient_id", "age", "gender", "billing_amount"],
        )
        # 20 missing out of (4 * 100) = 380/400 = 95.0% completeness
        assert report.pillars.completeness == pytest.approx(95.0, abs=0.1)
        assert report.overall_trust_score < 100.0

    def test_validity_degradation(self, clean_patient_df: pd.DataFrame) -> None:
        """T4: Negative billing amounts and impossible ages degrade Validity."""
        df = clean_patient_df.copy()
        # 10 negative billing amounts
        df.loc[:9, "billing_amount"] = -500.0
        # 10 ages over 150
        df.loc[10:19, "age"] = 180

        engine = DataTrustEngine()
        report = engine.evaluate(
            df=df,
            primary_key="patient_id",
            validation_rules={
                "age": lambda s: s.between(0, 120),
                "billing_amount": lambda s: s > 0,
            },
        )
        # 20 invalid records out of 100 = 80.0% validity
        assert report.pillars.validity == pytest.approx(80.0, abs=0.5)

    def test_uniqueness_degradation(self, clean_patient_df: pd.DataFrame) -> None:
        """T5: Duplicate primary keys degrade Uniqueness score."""
        df = clean_patient_df.copy()
        # Duplicate first 10 IDs
        df.loc[10:19, "patient_id"] = df.loc[:9, "patient_id"].values

        engine = DataTrustEngine()
        report = engine.evaluate(df=df, primary_key="patient_id")
        # 90 unique out of 100 = 90.0% uniqueness
        assert report.pillars.uniqueness == pytest.approx(90.0, abs=0.1)

    def test_referential_integrity_degradation(
        self, clean_patient_df: pd.DataFrame, reference_facilities: set[str]
    ) -> None:
        """T6: Orphaned foreign keys degrade Referential Integrity."""
        df = clean_patient_df.copy()
        # Assign 25 records to non-existent facility
        df.loc[:24, "facility_id"] = "UNKNOWN_FAC_99"

        engine = DataTrustEngine()
        report = engine.evaluate(
            df=df,
            primary_key="patient_id",
            foreign_keys={"facility_id": reference_facilities},
        )
        # 75 matching out of 100 = 75.0% referential integrity
        assert report.pillars.referential_integrity == pytest.approx(75.0, abs=0.1)


# ---------------------------------------------------------------------------
# T8-T9 — Weighted Score & Trust Status Thresholds
# ---------------------------------------------------------------------------
class TestTrustStatusThresholds:
    def test_status_ratings(self) -> None:
        """T9: Rating classifications."""
        engine = DataTrustEngine()
        assert engine.classify_trust_score(98.5) == TrustStatus.PRISTINE
        assert engine.classify_trust_score(90.0) == TrustStatus.GOOD
        assert engine.classify_trust_score(78.0) == TrustStatus.DEGRADED
        assert engine.classify_trust_score(60.0) == TrustStatus.CRITICAL

    def test_weighted_overall_calculation(self) -> None:
        """T8: Overall trust score matches exact weighted combination."""
        engine = DataTrustEngine(
            weights={"validity": 0.4, "completeness": 0.3, "uniqueness": 0.2, "referential_integrity": 0.1}
        )
        pillars = PillarScores(
            completeness=90.0,
            validity=80.0,
            uniqueness=100.0,
            referential_integrity=70.0,
        )
        # Expected: (80*0.4) + (90*0.3) + (100*0.2) + (70*0.1) = 32 + 27 + 20 + 7 = 86.0
        score = engine.calculate_overall_score(pillars)
        assert score == pytest.approx(86.0, abs=0.01)


# ---------------------------------------------------------------------------
# T10-T11 — Data Freshness Monitoring
# ---------------------------------------------------------------------------
class TestDataFreshness:
    def test_fresh_data_detection(self) -> None:
        """T10: Recent timestamp within SLA is marked FRESH."""
        engine = DataTrustEngine()
        now = datetime.now(timezone.utc)
        latest_ts = now - timedelta(minutes=15)

        freshness: DataFreshnessReport = engine.check_freshness(
            latest_timestamp=latest_ts,
            sla_hours=1.0,
            now=now,
        )
        assert freshness.status == FreshnessStatus.FRESH
        assert freshness.lag_minutes == pytest.approx(15.0, abs=0.5)

    def test_stale_data_detection(self) -> None:
        """T11: Timestamp exceeding SLA (between 1x and 2x) is marked STALE."""
        engine = DataTrustEngine()
        now = datetime.now(timezone.utc)
        latest_ts = now - timedelta(hours=3)

        freshness: DataFreshnessReport = engine.check_freshness(
            latest_timestamp=latest_ts,
            sla_hours=2.0,
            now=now,
        )
        assert freshness.status == FreshnessStatus.STALE
        assert freshness.sla_breached is True

    def test_critical_lag_detection(self) -> None:
        """Timestamp exceeding 2x SLA is marked CRITICAL_LAG."""
        engine = DataTrustEngine()
        now = datetime.now(timezone.utc)
        latest_ts = now - timedelta(hours=10)

        freshness = engine.check_freshness(
            latest_timestamp=latest_ts,
            sla_hours=2.0,
            now=now,
        )
        assert freshness.status == FreshnessStatus.CRITICAL_LAG
        assert freshness.sla_breached is True


# ---------------------------------------------------------------------------
# T12-T14 — Schema Drift Monitoring
# ---------------------------------------------------------------------------
class TestSchemaDrift:
    def test_detect_missing_columns(self) -> None:
        """T12: Missing expected column flagged in SchemaDriftReport."""
        engine = DataTrustEngine()
        expected = {"id": "int", "name": "str", "age": "int"}
        actual = {"id": "int", "name": "str"}  # 'age' missing

        drift: SchemaDriftReport = engine.check_schema_drift(expected, actual)
        assert drift.has_drift is True
        assert "age" in drift.missing_columns

    def test_detect_added_columns(self) -> None:
        """T13: Unexpected new column flagged in SchemaDriftReport."""
        engine = DataTrustEngine()
        expected = {"id": "int"}
        actual = {"id": "int", "secret_token": "str"}

        drift = engine.check_schema_drift(expected, actual)
        assert drift.has_drift is True
        assert "secret_token" in drift.added_columns

    def test_detect_type_mismatch(self) -> None:
        """T14: Type mismatch flagged in SchemaDriftReport."""
        engine = DataTrustEngine()
        expected = {"cost": "float"}
        actual = {"cost": "str"}

        drift = engine.check_schema_drift(expected, actual)
        assert drift.has_drift is True
        assert "cost" in drift.type_mismatches


# ---------------------------------------------------------------------------
# T15-T18 — Quarantine Trends & Report Generation
# ---------------------------------------------------------------------------
class TestReportingAndTrends:
    def test_quarantine_trends_summary(self) -> None:
        """T15: Quarantine logs aggregation into trends."""
        engine = DataTrustEngine()
        batches = [
            {"batch_id": "B1", "total": 100, "quarantined": 5, "violations": {"NULL_AGE": 3, "INVALID_COST": 2}},
            {"batch_id": "B2", "total": 100, "quarantined": 10, "violations": {"NULL_AGE": 6, "INVALID_COST": 4}},
        ]
        trend = engine.analyze_quarantine_trends(batches)
        assert trend["total_records"] == 200
        assert trend["total_quarantined"] == 15
        assert trend["quarantine_rate_pct"] == 7.5
        assert trend["top_violations"]["NULL_AGE"] == 9

    def test_report_json_and_markdown(self, clean_patient_df: pd.DataFrame) -> None:
        """T16/T17: Report serializes cleanly to JSON and Markdown string."""
        engine = DataTrustEngine()
        report = engine.evaluate(df=clean_patient_df, primary_key="patient_id")

        # JSON dictionary
        d = report.to_dict()
        assert "overall_trust_score" in d
        assert "pillars" in d
        assert d["status"] == "PRISTINE"

        # Markdown format
        md = report.to_markdown()
        assert "# HealthGuard 360" in md
        assert "Data Trust Score" in md
        assert "Completeness" in md

    def test_live_warehouse_evaluation(self) -> None:
        """T18: Evaluates live silver_encounters table in warehouse database."""
        from pipeline.config import PipelineConfig
        from pipeline.warehouse import managed_connection
        cfg = PipelineConfig()

        with managed_connection(cfg.warehouse_db) as conn:
            df = pd.read_sql("SELECT * FROM silver_encounters LIMIT 50", conn)

        engine = DataTrustEngine()
        report = engine.evaluate(
            df=df,
            primary_key="patient_id",
            mandatory_columns=["patient_id", "condition", "cost", "readmission_flag"],
        )
        assert report.total_records > 0
        assert report.overall_trust_score >= 80.0

    def test_empty_dataframe_evaluation(self) -> None:
        """T19: Empty dataframe returns zero records without divide-by-zero error."""
        engine = DataTrustEngine()
        empty_df = pd.DataFrame(columns=["patient_id", "age", "cost"])
        report = engine.evaluate(df=empty_df, primary_key="patient_id")

        assert report.total_records == 0
        assert report.overall_trust_score == 100.0
        assert report.status == TrustStatus.PRISTINE

    def test_console_table_evaluation_helper(self, clean_patient_df: pd.DataFrame) -> None:
        """T20: Console _evaluate_table helper returns valid DataTrustReport."""
        from app.dashboard.utils.data_trust_console import _evaluate_table
        engine = DataTrustEngine()
        report = _evaluate_table(engine, clean_patient_df, "test_table")

        assert report.total_records == 100
        assert report.batch_id == "test_table_live"
        assert report.pillars.validity == 100.0
