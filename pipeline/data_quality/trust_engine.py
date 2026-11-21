"""
HealthGuard 360: Data Trust Score & Observability Engine.

Computes transparent 4-pillar Data Trust Scores:
  1. Completeness: % non-null values across mandatory attributes.
  2. Validity: % records conforming to domain constraints and business rules.
  3. Uniqueness: % unique primary/composite key identifiers.
  4. Referential Integrity: % valid foreign key references against dimensions.

Also monitors data freshness, detects schema drift, and tracks quarantine trends.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TrustStatus(str, Enum):
    """Data Trust health classification."""
    PRISTINE = "PRISTINE"    # >= 95.0%
    GOOD = "GOOD"            # 85.0% - 94.9%
    DEGRADED = "DEGRADED"    # 70.0% - 84.9%
    CRITICAL = "CRITICAL"    # < 70.0%


class FreshnessStatus(str, Enum):
    """Data Freshness classification."""
    FRESH = "FRESH"
    STALE = "STALE"
    CRITICAL_LAG = "CRITICAL_LAG"


@dataclass(frozen=True)
class PillarScores:
    """Individual scores (0.0 to 100.0) for the 4 data quality pillars."""
    completeness: float
    validity: float
    uniqueness: float
    referential_integrity: float


@dataclass(frozen=True)
class DataFreshnessReport:
    """Audit report of data arrival latency and SLA compliance."""
    latest_timestamp: Optional[datetime]
    lag_minutes: float
    sla_hours: float
    sla_breached: bool
    status: FreshnessStatus


@dataclass(frozen=True)
class SchemaDriftReport:
    """Report detailing drift between expected schema and actual structure."""
    has_drift: bool
    missing_columns: List[str] = field(default_factory=list)
    added_columns: List[str] = field(default_factory=list)
    type_mismatches: Dict[str, Dict[str, str]] = field(default_factory=dict)


@dataclass(frozen=True)
class DataTrustReport:
    """Comprehensive Data Trust & Observability audit manifest."""
    batch_id: str
    evaluated_at: str
    total_records: int
    pillars: PillarScores
    overall_trust_score: float
    status: TrustStatus
    freshness: Optional[DataFreshnessReport] = None
    schema_drift: Optional[SchemaDriftReport] = None
    quarantine_rate_pct: float = 0.0
    violation_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to JSON-serializable dictionary."""
        d = {
            "batch_id": self.batch_id,
            "evaluated_at": self.evaluated_at,
            "total_records": self.total_records,
            "overall_trust_score": self.overall_trust_score,
            "status": self.status.value,
            "quarantine_rate_pct": self.quarantine_rate_pct,
            "pillars": asdict(self.pillars),
            "violation_counts": dict(self.violation_counts),
        }
        if self.freshness:
            d["freshness"] = {
                "latest_timestamp": self.freshness.latest_timestamp.isoformat() if self.freshness.latest_timestamp else None,
                "lag_minutes": self.freshness.lag_minutes,
                "sla_hours": self.freshness.sla_hours,
                "sla_breached": self.freshness.sla_breached,
                "status": self.freshness.status.value,
            }
        if self.schema_drift:
            d["schema_drift"] = {
                "has_drift": self.schema_drift.has_drift,
                "missing_columns": list(self.schema_drift.missing_columns),
                "added_columns": list(self.schema_drift.added_columns),
                "type_mismatches": dict(self.schema_drift.type_mismatches),
            }
        return d

    def to_markdown(self) -> str:
        """Render standard audit markdown summary."""
        status_badge = {
            TrustStatus.PRISTINE: "🟢 Pristine",
            TrustStatus.GOOD: "🔵 Good",
            TrustStatus.DEGRADED: "🟠 Degraded",
            TrustStatus.CRITICAL: "🔴 Critical",
        }.get(self.status, str(self.status.value))

        lines = [
            f"# HealthGuard 360 — Data Trust & Observability Report",
            f"**Batch ID**: `{self.batch_id}`  ",
            f"**Evaluation Timestamp**: `{self.evaluated_at}`  ",
            f"**Records Evaluated**: `{self.total_records:,}`  ",
            f"",
            f"## 🛡️ Overall Data Trust Score: **{self.overall_trust_score:.1f}%** ({status_badge})",
            f"",
            f"### 📊 4-Pillar Quality Matrix",
            f"| Pillar Dimension | Score | Production Threshold | Health Status |",
            f"|---|---|---|---|",
            f"| **Validity** | {self.pillars.validity:.1f}% | ≥ 98.0% | {'✅ Pass' if self.pillars.validity >= 98 else '⚠️ Attention'} |",
            f"| **Completeness** | {self.pillars.completeness:.1f}% | ≥ 95.0% | {'✅ Pass' if self.pillars.completeness >= 95 else '⚠️ Attention'} |",
            f"| **Uniqueness** | {self.pillars.uniqueness:.1f}% | ≥ 99.0% | {'✅ Pass' if self.pillars.uniqueness >= 99 else '⚠️ Attention'} |",
            f"| **Referential Integrity** | {self.pillars.referential_integrity:.1f}% | 100.0% | {'✅ Pass' if self.pillars.referential_integrity == 100 else '⚠️ Attention'} |",
            f"",
        ]

        if self.freshness:
            lines.extend([
                f"### ⏱️ Data Freshness & SLA",
                f"- **Current Lag**: `{self.freshness.lag_minutes:.1f} minutes`",
                f"- **SLA Window**: `{self.freshness.sla_hours} hours`",
                f"- **Status**: `{'✅ Fresh' if not self.freshness.sla_breached else '🚨 SLA Breached (' + self.freshness.status.value + ')'}`",
                f"",
            ])

        if self.schema_drift:
            lines.extend([
                f"### 📐 Schema Drift Status",
                f"- **Drift Detected**: `{'Yes' if self.schema_drift.has_drift else 'No'}`",
                f"- **Missing Columns**: `{', '.join(self.schema_drift.missing_columns) if self.schema_drift.missing_columns else 'None'}`",
                f"- **Added Columns**: `{', '.join(self.schema_drift.added_columns) if self.schema_drift.added_columns else 'None'}`",
                f"",
            ])

        return "\n".join(lines)


class DataTrustEngine:
    """
    Engine to measure, score, and monitor healthcare data trustworthiness.
    """

    DEFAULT_WEIGHTS: Dict[str, float] = {
        "validity": 0.35,
        "completeness": 0.25,
        "uniqueness": 0.20,
        "referential_integrity": 0.20,
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None) -> None:
        self.weights = weights or dict(self.DEFAULT_WEIGHTS)
        weight_sum = sum(self.weights.values())
        if abs(weight_sum - 1.0) > 1e-4:
            raise ValueError(f"Weights must sum to 1.0; got {weight_sum:.4f}")

    # ------------------------------------------------------------------
    # Core Evaluation
    # ------------------------------------------------------------------
    def evaluate(
        self,
        df: pd.DataFrame,
        primary_key: Optional[str] = None,
        mandatory_columns: Optional[List[str]] = None,
        validation_rules: Optional[Dict[str, Callable[[pd.Series], pd.Series]]] = None,
        foreign_keys: Optional[Dict[str, Set[Any]]] = None,
        batch_id: Optional[str] = None,
    ) -> DataTrustReport:
        """
        Evaluate a dataframe across all 4 pillars and produce a DataTrustReport.
        """
        total = len(df)
        if total == 0:
            pillars = PillarScores(100.0, 100.0, 100.0, 100.0)
            return DataTrustReport(
                batch_id=batch_id or f"batch_{int(datetime.now().timestamp())}",
                evaluated_at=datetime.now(timezone.utc).isoformat(),
                total_records=0,
                pillars=pillars,
                overall_trust_score=100.0,
                status=TrustStatus.PRISTINE,
            )

        # 1. Completeness Score
        completeness = self._calculate_completeness(df, mandatory_columns)

        # 2. Validity Score
        validity = self._calculate_validity(df, validation_rules)

        # 3. Uniqueness Score
        uniqueness = self._calculate_uniqueness(df, primary_key)

        # 4. Referential Integrity Score
        ref_integrity = self._calculate_referential_integrity(df, foreign_keys)

        pillars = PillarScores(
            completeness=completeness,
            validity=validity,
            uniqueness=uniqueness,
            referential_integrity=ref_integrity,
        )

        overall = self.calculate_overall_score(pillars)
        status = self.classify_trust_score(overall)

        return DataTrustReport(
            batch_id=batch_id or f"batch_{int(datetime.now().timestamp())}",
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            total_records=total,
            pillars=pillars,
            overall_trust_score=overall,
            status=status,
        )

    # ------------------------------------------------------------------
    # Pillar Calculations
    # ------------------------------------------------------------------
    def _calculate_completeness(
        self, df: pd.DataFrame, mandatory_columns: Optional[List[str]]
    ) -> float:
        cols = mandatory_columns or list(df.columns)
        if not cols:
            return 100.0
        total_cells = len(df) * len(cols)
        non_null_cells = int(df[cols].notna().sum().sum())
        return round((non_null_cells / total_cells) * 100.0, 2)

    def _calculate_validity(
        self,
        df: pd.DataFrame,
        validation_rules: Optional[Dict[str, Callable[[pd.Series], pd.Series]]],
    ) -> float:
        if not validation_rules:
            return 100.0

        valid_mask = pd.Series(True, index=df.index)
        for col, rule_fn in validation_rules.items():
            if col in df.columns:
                try:
                    rule_res = rule_fn(df[col])
                    valid_mask = valid_mask & rule_res.fillna(False)
                except Exception as e:
                    logger.warning("Validation rule on '%s' failed: %s", col, e)
                    valid_mask = pd.Series(False, index=df.index)

        valid_count = int(valid_mask.sum())
        return round((valid_count / len(df)) * 100.0, 2)

    def _calculate_uniqueness(
        self, df: pd.DataFrame, primary_key: Optional[str]
    ) -> float:
        if not primary_key or primary_key not in df.columns:
            # Check entire row uniqueness
            unique_count = int(df.drop_duplicates().shape[0])
        else:
            unique_count = int(df[primary_key].nunique(dropna=False))
        return round((unique_count / len(df)) * 100.0, 2)

    def _calculate_referential_integrity(
        self, df: pd.DataFrame, foreign_keys: Optional[Dict[str, Set[Any]]]
    ) -> float:
        if not foreign_keys:
            return 100.0

        matches: List[float] = []
        for col, valid_set in foreign_keys.items():
            if col in df.columns:
                in_set = df[col].isin(valid_set)
                matches.append(float(in_set.mean() * 100.0))

        if not matches:
            return 100.0
        return round(float(np.mean(matches)), 2)

    # ------------------------------------------------------------------
    # Scoring & Classification
    # ------------------------------------------------------------------
    def calculate_overall_score(self, pillars: PillarScores) -> float:
        """Weighted sum of 4 pillar scores."""
        score = (
            (pillars.validity * self.weights["validity"])
            + (pillars.completeness * self.weights["completeness"])
            + (pillars.uniqueness * self.weights["uniqueness"])
            + (pillars.referential_integrity * self.weights["referential_integrity"])
        )
        return round(score, 2)

    def classify_trust_score(self, score: float) -> TrustStatus:
        """Determine trust tier status."""
        if score >= 95.0:
            return TrustStatus.PRISTINE
        if score >= 85.0:
            return TrustStatus.GOOD
        if score >= 70.0:
            return TrustStatus.DEGRADED
        return TrustStatus.CRITICAL

    # ------------------------------------------------------------------
    # Observability: Freshness, Schema Drift, Quarantine Trends
    # ------------------------------------------------------------------
    def check_freshness(
        self,
        latest_timestamp: Optional[datetime],
        sla_hours: float = 24.0,
        now: Optional[datetime] = None,
    ) -> DataFreshnessReport:
        """Measure data arrival freshness against SLA."""
        curr_time = now or datetime.now(timezone.utc)
        if latest_timestamp is None:
            return DataFreshnessReport(
                latest_timestamp=None,
                lag_minutes=float("inf"),
                sla_hours=sla_hours,
                sla_breached=True,
                status=FreshnessStatus.CRITICAL_LAG,
            )

        # Normalize timezones
        ts = latest_timestamp if latest_timestamp.tzinfo else latest_timestamp.replace(tzinfo=timezone.utc)
        ct = curr_time if curr_time.tzinfo else curr_time.replace(tzinfo=timezone.utc)

        lag_seconds = max((ct - ts).total_seconds(), 0.0)
        lag_minutes = lag_seconds / 60.0
        sla_seconds = sla_hours * 3600.0
        breached = lag_seconds > sla_seconds

        if lag_seconds <= 3600.0 and not breached:
            status = FreshnessStatus.FRESH
        elif breached and lag_seconds > (sla_seconds * 2.0):
            status = FreshnessStatus.CRITICAL_LAG
        else:
            status = FreshnessStatus.STALE

        return DataFreshnessReport(
            latest_timestamp=ts,
            lag_minutes=round(lag_minutes, 2),
            sla_hours=sla_hours,
            sla_breached=breached,
            status=status,
        )

    def check_schema_drift(
        self,
        expected_schema: Dict[str, str],
        actual_schema: Dict[str, str],
    ) -> SchemaDriftReport:
        """Detect missing columns, new columns, or type mismatches."""
        expected_cols = set(expected_schema.keys())
        actual_cols = set(actual_schema.keys())

        missing = sorted(list(expected_cols - actual_cols))
        added = sorted(list(actual_cols - expected_cols))

        type_mismatches: Dict[str, Dict[str, str]] = {}
        for col in expected_cols.intersection(actual_cols):
            exp_type = expected_schema[col].lower()
            act_type = actual_schema[col].lower()
            if exp_type != act_type:
                type_mismatches[col] = {"expected": exp_type, "actual": act_type}

        has_drift = bool(missing or added or type_mismatches)
        return SchemaDriftReport(
            has_drift=has_drift,
            missing_columns=missing,
            added_columns=added,
            type_mismatches=type_mismatches,
        )

    def analyze_quarantine_trends(
        self, batches: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Aggregate quarantine history across micro-batches."""
        if not batches:
            return {
                "total_records": 0,
                "total_quarantined": 0,
                "quarantine_rate_pct": 0.0,
                "top_violations": {},
            }

        total_rec = sum(b.get("total", 0) for b in batches)
        total_quar = sum(b.get("quarantined", 0) for b in batches)
        quar_rate = (total_quar / total_rec * 100.0) if total_rec > 0 else 0.0

        violations: Dict[str, int] = {}
        for b in batches:
            for rule, count in b.get("violations", {}).items():
                violations[rule] = violations.get(rule, 0) + count

        sorted_violations = dict(sorted(violations.items(), key=lambda x: x[1], reverse=True))

        return {
            "total_records": total_rec,
            "total_quarantined": total_quar,
            "quarantine_rate_pct": round(quar_rate, 2),
            "top_violations": sorted_violations,
        }
