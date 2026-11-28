"""
Reconciliation Engine — Source → Silver accounting.

Ensures every Bronze record is accounted for:
Source = Accepted + Quarantined + Duplicates + Explicitly_Excluded
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict

import pyarrow.parquet as pq

logger = logging.getLogger(__name__)


@dataclass
class ReconciliationReport:
    """Complete reconciliation report for a batch."""
    batch_id: str
    resource_type: str
    generated_at: str

    # Source counts
    source_total: int = 0
    source_valid: int = 0
    source_invalid_json: int = 0
    source_missing_type: int = 0
    source_out_of_scope: int = 0

    # Silver counts
    silver_accepted: int = 0
    silver_duplicates_suppressed: int = 0

    # Quarantine counts
    quarantined_total: int = 0
    quarantined_by_reason: dict[str, int] = field(default_factory=dict)

    # Explicitly excluded
    explicitly_excluded: int = 0

    def balances(self) -> bool:
        """Check if reconciliation balances."""
        accounted = (
            self.silver_accepted
            + self.silver_duplicates_suppressed
            + self.quarantined_total
            + self.explicitly_excluded
        )
        return accounted == self.source_valid

    def discrepancy(self) -> int:
        """Return difference (should be 0)."""
        accounted = (
            self.silver_accepted
            + self.silver_duplicates_suppressed
            + self.quarantined_total
            + self.explicitly_excluded
        )
        return self.source_valid - accounted

    def to_dict(self) -> dict:
        return asdict(self)

    def to_markdown(self) -> str:
        """Generate Markdown reconciliation report."""
        lines = [
            f"# Reconciliation Report: {self.resource_type}",
            f"**Batch ID:** {self.batch_id}  ",
            f"**Generated:** {self.generated_at}  ",
            "",
            "## Source Records",
            f"- **Total lines read:** {self.source_total:,}",
            f"- **Valid FHIR resources:** {self.source_valid:,}",
            f"- **Invalid JSON:** {self.source_invalid_json:,}",
            f"- **Missing resourceType:** {self.source_missing_type:,}",
            f"- **Out of scope:** {self.source_out_of_scope:,}",
            "",
            "## Silver Layer",
            f"- **Accepted (unique):** {self.silver_accepted:,}",
            f"- **Duplicates suppressed:** {self.silver_duplicates_suppressed:,}",
            "",
            "## Quarantine",
            f"- **Total quarantined:** {self.quarantined_total:,}",
        ]

        if self.quarantined_by_reason:
            lines.append("")
            lines.append("| Reason | Count |")
            lines.append("|--------|-------|")
            for reason, count in sorted(self.quarantined_by_reason.items()):
                lines.append(f"| {reason} | {count:,} |")

        lines.extend([
            "",
            "## Explicitly Excluded",
            f"- **Count:** {self.explicitly_excluded:,}",
            "",
            "## Balance Check",
            f"- **Source valid:** {self.source_valid:,}",
            f"- **Accounted:** {self.silver_accepted + self.silver_duplicates_suppressed + self.quarantined_total + self.explicitly_excluded:,}",
            f"- **Discrepancy:** {self.discrepancy():+,}",
            f"- **Balanced:** {'✅ YES' if self.balances() else '❌ NO'}",
        ])

        return "\n".join(lines)


class ReconciliationEngine:
    """
    Reconciliation Engine — Tracks record flow from Bronze to Silver.

    Produces auditable reconciliation reports proving no data loss.
    """

    def __init__(self):
        pass

    def reconcile_batch(
        self,
        batch_id: str,
        resource_type: str,
        bronze_manifest_path: Path,
        silver_table_path: Path,
        quarantine_root: Path,
    ) -> ReconciliationReport:
        """
        Generate full reconciliation report for a batch + resource type.

        Args:
            batch_id: Batch identifier
            resource_type: FHIR resource type
            bronze_manifest_path: Path to Bronze manifest
            silver_table_path: Path to Silver Parquet file(s)
            quarantine_root: Root of quarantine directory

        Returns:
            ReconciliationReport with all counts
        """
        report = ReconciliationReport(
            batch_id=batch_id,
            resource_type=resource_type,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Load Bronze manifest for source counts
        if bronze_manifest_path.exists():
            import json
            with open(bronze_manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            resource_counts = manifest.get("resource_counts", {})
            report.source_valid = resource_counts.get(resource_type, 0)

            # We'd need more granular source stats from the ingestion logs
            # For now, use what we have
            report.source_total = manifest.get("total_records", 0)

        # Load Silver table for accepted count
        if silver_table_path.exists():
            silver_table = pq.read_table(str(silver_table_path))
            silver_df = silver_table.to_pandas()

            # Count unique primary keys for accepted count
            pk_col = self._get_primary_key(resource_type)
            if pk_col and pk_col in silver_df.columns:
                unique_silver = int(silver_df[pk_col].nunique())
                total_silver = len(silver_df)
                report.silver_accepted = unique_silver
                report.silver_duplicates_suppressed = total_silver - unique_silver
            else:
                report.silver_accepted = len(silver_df)

        # Load quarantine counts
        if quarantine_root.exists():
            for reason_dir in quarantine_root.iterdir():
                if not reason_dir.is_dir():
                    continue
                for date_dir in reason_dir.iterdir():
                    if not date_dir.is_dir():
                        continue
                    for pq_file in date_dir.glob("*.parquet"):
                        q_table = pq.read_table(str(pq_file))
                        q_df = q_table.to_pandas()
                        # Filter by resource_type and batch_id
                        if "resource_type" in q_df.columns and "batch_id" in q_df.columns:
                            mask = (q_df["resource_type"] == resource_type) & (q_df["batch_id"] == batch_id)
                            count = int(mask.sum())
                            if count > 0:
                                report.quarantined_by_reason[reason_dir.name] = (
                                    report.quarantined_by_reason.get(reason_dir.name, 0) + count
                                )

            report.quarantined_total = sum(report.quarantined_by_reason.values())

        return report

    def _get_primary_key(self, resource_type: str) -> Optional[str]:
        """Get primary key column for resource type."""
        pk_map = {
            "Patient": "patient_id",
            "Encounter": "encounter_id",
            "Condition": "condition_id",
            "Observation": "observation_id",
        }
        return pk_map.get(resource_type)

    def save_report(self, report: ReconciliationReport, output_dir: Path) -> tuple[Path, Path]:
        """Save ReconciliationReport as JSON and Markdown."""
        output_dir.mkdir(parents=True, exist_ok=True)

        json_file = output_dir / f"reconciliation_{report.resource_type.lower()}_{report.batch_id}.json"
        md_file = output_dir / f"reconciliation_{report.resource_type.lower()}_{report.batch_id}.md"

        with open(json_file, "w", encoding="utf-8") as f:
            import json
            json.dump(report.to_dict(), f, indent=2)

        with open(md_file, "w", encoding="utf-8") as f:
            f.write(report.to_markdown())

        logger.info(f"Saved reconciliation report: {json_file}, {md_file}")
        return json_file, md_file