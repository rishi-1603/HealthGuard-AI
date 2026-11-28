"""
Data Quality Engine — 4-Pillar DQ: Completeness, Validity, Uniqueness, Referential Integrity.

Produces JSON + Markdown scorecards for each Silver table and batch.
"""

import logging
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict
from collections import defaultdict

import pyarrow.parquet as pq
import pyarrow as pa

logger = logging.getLogger(__name__)


@dataclass
class PillarScore:
    """Score for one DQ pillar."""
    pillar: str
    score: float  # 0.0 - 1.0
    total_checks: int
    passed_checks: int
    failed_checks: int
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class QualityReport:
    """Complete DQ report for a Silver table."""
    table_name: str
    batch_id: str
    generated_at: str
    overall_score: float
    pillars: list[PillarScore]
    record_count: int
    quarantined_count: int = 0

    def to_dict(self) -> dict:
        return {
            "table_name": self.table_name,
            "batch_id": self.batch_id,
            "generated_at": self.generated_at,
            "overall_score": self.overall_score,
            "pillars": [p.to_dict() for p in self.pillars],
            "record_count": self.record_count,
            "quarantined_count": self.quarantined_count,
        }

    def to_markdown(self) -> str:
        """Generate Markdown report."""
        lines = [
            f"# Data Quality Report: {self.table_name}",
            f"**Batch ID:** {self.batch_id}  ",
            f"**Generated:** {self.generated_at}  ",
            f"**Records:** {self.record_count:,}  ",
            f"**Quarantined:** {self.quarantined_count:,}  ",
            f"**Overall Score:** {self.overall_score:.2%}",
            "",
            "## Pillar Scores",
            "",
            "| Pillar | Score | Passed / Total |",
            "|--------|-------|----------------|",
        ]
        for p in self.pillars:
            lines.append(f"| {p.pillar} | {p.score:.2%} | {p.passed_checks} / {p.total_checks} |")

        lines.append("")
        return "\n".join(lines)


class DQEngine:
    """
    4-Pillar Data Quality Engine.

    Pillars:
    1. Completeness — Required fields present, non-null
    2. Validity — Values conform to types, enums, formats
    3. Uniqueness — No duplicate primary keys
    4. Referential Integrity — Foreign keys resolve to valid parents
    """

    def __init__(self, quarantine_engine=None):
        self.quarantine_engine = quarantine_engine

    def assess_table(
        self,
        table_path: Path,
        resource_type: str,
        batch_id: str,
        primary_key: str,
        required_fields: list[str],
        enum_fields: dict[str, list],
        reference_fields: dict[str, dict],
        parent_tables: dict[str, Path] = None,
    ) -> QualityReport:
        """
        Run full DQ assessment on a Silver table.

        Args:
            table_path: Path to Silver Parquet file(s)
            resource_type: FHIR resource type
            batch_id: Current batch ID
            primary_key: Primary key column name
            required_fields: List of required field names
            enum_fields: {field_name: [allowed_values]}
            reference_fields: {field_name: {"parent_table": "table", "parent_key": "col", "required": bool}}
            parent_tables: {parent_name: Path to parent Silver table}

        Returns:
            QualityReport with all pillar scores
        """
        # Load table
        table = pq.read_table(str(table_path))
        df = table.to_pandas()

        record_count = len(df)
        pillars = []

        # Pillar 1: Completeness
        completeness = self._check_completeness(df, required_fields, primary_key)
        pillars.append(completeness)

        # Pillar 2: Validity
        validity = self._check_validity(df, enum_fields, primary_key)
        pillars.append(validity)

        # Pillar 3: Uniqueness
        uniqueness = self._check_uniqueness(df, primary_key)
        pillars.append(uniqueness)

        # Pillar 4: Referential Integrity
        referential = self._check_referential_integrity(
            df, reference_fields, parent_tables, primary_key
        )
        pillars.append(referential)

        # Overall score (weighted average)
        weights = {"Completeness": 0.25, "Validity": 0.25, "Uniqueness": 0.25, "Referential Integrity": 0.25}
        overall = sum(p.score * weights.get(p.pillar, 0.25) for p in pillars)

        return QualityReport(
            table_name=resource_type.lower(),
            batch_id=batch_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            overall_score=overall,
            pillars=pillars,
            record_count=record_count,
        )

    def _check_completeness(self, df, required_fields: list[str], pk: str) -> PillarScore:
        """Check required fields are present and non-null."""
        checks = []
        details = {"field_results": {}}

        # Primary key
        pk_null = int(df[pk].isna().sum()) if pk in df.columns else len(df)
        pk_passed = bool(pk_null == 0)
        checks.append(("Primary key non-null", pk_passed))
        details["field_results"][pk] = {"null_count": pk_null, "pass": pk_passed}

        for field in required_fields:
            if field == pk:
                continue
            if field in df.columns:
                null_count = int(df[field].isna().sum())
                passed = bool(null_count == 0)
            else:
                null_count = len(df)
                passed = False
            checks.append((f"Required field '{field}' non-null", passed))
            details["field_results"][field] = {"null_count": null_count, "pass": passed}

        passed = sum(1 for _, p in checks if p)
        return PillarScore(
            pillar="Completeness",
            score=passed / len(checks) if checks else 1.0,
            total_checks=len(checks),
            passed_checks=passed,
            failed_checks=len(checks) - passed,
            details=details,
        )

    def _check_validity(self, df, enum_fields: dict[str, list], pk: str) -> PillarScore:
        """Check enum values and basic type validity."""
        checks = []
        details = {"field_results": {}}

        for field, allowed_values in enum_fields.items():
            if field not in df.columns:
                checks.append((f"Enum field '{field}' exists", False))
                details["field_results"][field] = {"error": "field_missing"}
                continue

            # Check each non-null value
            mask = df[field].notna()
            if mask.any():
                invalid = ~df.loc[mask, field].isin(allowed_values)
                invalid_count = int(invalid.sum())
                passed = bool(invalid_count == 0)
                checks.append((f"Enum field '{field}' valid", passed))
                details["field_results"][field] = {
                    "allowed": allowed_values,
                    "invalid_count": invalid_count,
                    "pass": passed,
                }
            else:
                checks.append((f"Enum field '{field}' valid (all null)", True))
                details["field_results"][field] = {"pass": True, "note": "all_null"}

        passed = sum(1 for _, p in checks if p)
        return PillarScore(
            pillar="Validity",
            score=passed / len(checks) if checks else 1.0,
            total_checks=len(checks),
            passed_checks=passed,
            failed_checks=len(checks) - passed,
            details=details,
        )

    def _check_uniqueness(self, df, pk: str) -> PillarScore:
        """Check primary key uniqueness."""
        if pk not in df.columns:
            return PillarScore(
                pillar="Uniqueness",
                score=0.0,
                total_checks=1,
                passed_checks=0,
                failed_checks=1,
                details={"error": f"Primary key '{pk}' not in table"},
            )

        total = len(df)
        unique = df[pk].nunique()
        dup_count = total - unique
        passed = dup_count == 0

        return PillarScore(
            pillar="Uniqueness",
            score=1.0 if passed else unique / total,
            total_checks=1,
            passed_checks=1 if passed else 0,
            failed_checks=0 if passed else 1,
            details={
                "total_rows": total,
                "unique_keys": int(unique),
                "duplicate_count": int(dup_count),
            },
        )

    def _check_referential_integrity(
        self,
        df,
        reference_fields: dict[str, dict],
        parent_tables: dict[str, Path],
        pk: str,
    ) -> PillarScore:
        """Check foreign keys resolve to parent tables."""
        checks = []
        details = {"reference_results": {}}

        for ref_field, spec in reference_fields.items():
            parent_name = spec.get("parent_table")
            parent_key = spec.get("parent_key")
            required = spec.get("required", False)

            if ref_field not in df.columns:
                checks.append((f"Ref field '{ref_field}' exists", False))
                details["reference_results"][ref_field] = {"error": "field_missing"}
                continue

            # Get non-null values
            child_values = df[ref_field].dropna().unique()
            total_refs = int(len(child_values))

            if total_refs == 0:
                passed = bool(not required)
                checks.append((f"Referential integrity '{ref_field}'", passed))
                details["reference_results"][ref_field] = {"total_refs": 0, "pass": passed}
                continue

            # Load parent table
            if parent_name and parent_name in parent_tables:
                parent_table = pq.read_table(str(parent_tables[parent_name]))
                parent_df = parent_table.to_pandas()
                parent_keys = set(parent_df[parent_key].dropna().unique())
                child_keys = set(child_values)

                orphaned = child_keys - parent_keys
                orphan_count = int(len(orphaned))
                passed = bool(orphan_count == 0)

                checks.append((f"Referential integrity '{ref_field}' -> {parent_name}", passed))
                details["reference_results"][ref_field] = {
                    "parent_table": parent_name,
                    "total_refs": total_refs,
                    "orphaned_count": orphan_count,
                    "pass": passed,
                }
            else:
                # No parent table available - soft check
                passed = True
                checks.append((f"Referential integrity '{ref_field}' (no parent table)", passed))
                details["reference_results"][ref_field] = {"note": "parent_not_available", "pass": True}

        passed = sum(1 for _, p in checks if p)
        return PillarScore(
            pillar="Referential Integrity",
            score=passed / len(checks) if checks else 1.0,
            total_checks=len(checks),
            passed_checks=passed,
            failed_checks=len(checks) - passed,
            details=details,
        )

    def save_report(self, report: QualityReport, output_dir: Path) -> tuple[Path, Path]:
        """Save QualityReport as JSON and Markdown."""
        output_dir.mkdir(parents=True, exist_ok=True)

        json_file = output_dir / f"dq_report_{report.table_name}_{report.batch_id}.json"
        md_file = output_dir / f"dq_report_{report.table_name}_{report.batch_id}.md"

        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)

        with open(md_file, "w", encoding="utf-8") as f:
            f.write(report.to_markdown())

        logger.info(f"Saved DQ report: {json_file}, {md_file}")
        return json_file, md_file