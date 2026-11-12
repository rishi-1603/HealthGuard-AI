"""Silver layer — data quality checks.

Each check returns a DataQualityResult.  The Silver transformer runs all
checks and fails if any CRITICAL check fails (WARNING checks are logged
but do not stop the pipeline).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

from pipeline.config import (
    ALLOWED_GENDER,
    ALLOWED_OUTCOMES,
    ALLOWED_READMISSION,
    CONSTRAINTS,
    PipelineConfig,
)

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class DQResult:
    check_name: str
    severity: Severity
    passed: bool
    detail: str = ""
    affected_rows: int = 0


# ---------------------------------------------------------------------------
# Individual DQ checks (pure functions — take a DataFrame, return DQResult)
# ---------------------------------------------------------------------------

def check_null_rate(df: pd.DataFrame, cfg: PipelineConfig) -> list[DQResult]:
    """Flag any column with null rate > cfg.max_null_pct."""
    results: list[DQResult] = []
    for col in df.columns:
        null_pct = df[col].isna().mean()
        passed = null_pct <= cfg.max_null_pct
        results.append(
            DQResult(
                check_name=f"null_rate:{col}",
                severity=Severity.CRITICAL,
                passed=passed,
                detail=f"{null_pct:.1%} null (threshold {cfg.max_null_pct:.0%})",
                affected_rows=int(df[col].isna().sum()),
            )
        )
    return results


def check_duplicate_patients(df: pd.DataFrame, cfg: PipelineConfig) -> DQResult:
    """Fail if duplicate Patient_IDs exceed cfg.max_duplicate_pct."""
    total = len(df)
    dupes = total - df["Patient_ID"].nunique()
    pct = dupes / total if total > 0 else 0.0
    return DQResult(
        check_name="duplicate_patient_ids",
        severity=Severity.CRITICAL,
        passed=pct <= cfg.max_duplicate_pct,
        detail=f"{dupes} duplicates ({pct:.2%})",
        affected_rows=dupes,
    )


def check_categorical_values(df: pd.DataFrame) -> list[DQResult]:
    """Reject rows with invalid categorical values."""
    results: list[DQResult] = []

    checks = [
        ("Readmission", ALLOWED_READMISSION),
        ("Gender", ALLOWED_GENDER),
        ("Outcome", ALLOWED_OUTCOMES),
    ]

    for col, allowed in checks:
        if col not in df.columns:
            continue
        invalid_mask = ~df[col].isin(allowed)
        affected = int(invalid_mask.sum())
        results.append(
            DQResult(
                check_name=f"categorical:{col}",
                severity=Severity.CRITICAL,
                passed=affected == 0,
                detail=(
                    f"{affected} rows with values outside {sorted(allowed)}"
                    if affected
                    else "all values valid"
                ),
                affected_rows=affected,
            )
        )
    return results


def check_numeric_ranges(df: pd.DataFrame) -> list[DQResult]:
    """Validate numeric columns are within defined CONSTRAINTS."""
    results: list[DQResult] = []
    for col, (lo, hi) in CONSTRAINTS.items():
        if col not in df.columns:
            continue
        series = pd.to_numeric(df[col], errors="coerce")
        out_of_range = ((series < lo) | (series > hi)).sum()
        results.append(
            DQResult(
                check_name=f"range:{col}",
                severity=Severity.CRITICAL,
                passed=int(out_of_range) == 0,
                detail=f"{out_of_range} rows outside [{lo}, {hi}]",
                affected_rows=int(out_of_range),
            )
        )
    return results


def check_minimum_rows(df: pd.DataFrame, cfg: PipelineConfig) -> DQResult:
    """Fail if the Silver dataset is too small to be meaningful."""
    return DQResult(
        check_name="minimum_row_count",
        severity=Severity.CRITICAL,
        passed=len(df) >= cfg.min_row_count,
        detail=f"{len(df)} rows (minimum {cfg.min_row_count})",
        affected_rows=0,
    )


# ---------------------------------------------------------------------------
# Quality gate orchestrator
# ---------------------------------------------------------------------------

@dataclass
class QualityReport:
    results: list[DQResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results if r.severity == Severity.CRITICAL)

    @property
    def critical_failures(self) -> list[DQResult]:
        return [r for r in self.results if not r.passed and r.severity == Severity.CRITICAL]

    def summary(self) -> dict:
        return {
            "total_checks": len(self.results),
            "passed": sum(1 for r in self.results if r.passed),
            "failed_critical": len(self.critical_failures),
            "gate_passed": int(self.passed),   # bool→int for JSON compat
            "details": [
                {
                    "check": r.check_name,
                    "severity": str(r.severity),
                    "passed": int(r.passed),   # bool→int for JSON compat
                    "detail": r.detail,
                    "affected_rows": r.affected_rows,
                }
                for r in self.results
            ],
        }


def run_quality_checks(df: pd.DataFrame, cfg: PipelineConfig) -> QualityReport:
    """Execute all DQ checks and return a consolidated QualityReport."""
    report = QualityReport()
    report.results.extend(check_null_rate(df, cfg))
    report.results.append(check_duplicate_patients(df, cfg))
    report.results.extend(check_categorical_values(df))
    report.results.extend(check_numeric_ranges(df))
    report.results.append(check_minimum_rows(df, cfg))

    failures = report.critical_failures
    if failures:
        logger.warning("DQ gate FAILED — %d critical issue(s)", len(failures))
        for f in failures:
            logger.warning("  FAIL %s: %s", f.check_name, f.detail)
    else:
        logger.info("DQ gate PASSED — all %d checks green", len(report.results))

    return report
