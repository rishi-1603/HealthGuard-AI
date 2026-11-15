"""Quarantine routing and isolation engine.

Evaluates raw incoming records against the clinical rule suite, automatically
diverting records with critical quality violations to `silver_quarantine`,
while permitting compliant records to land safely in `silver_encounters`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from typing import Any
import pandas as pd

from pipeline.config import PipelineConfig
from pipeline.data_quality.rules import ClinicalRuleSuite, RuleValidationResult
from pipeline.silver.transformer import _coerce_types, _add_derived_columns, _assign_age_band
from pipeline.warehouse import managed_connection

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QuarantineBatchResult:
    """Summary of quarantine evaluation for a batch."""
    total_records: int
    valid_count: int
    quarantined_count: int
    valid_df: pd.DataFrame
    quarantined_records: list[dict[str, Any]]


class QuarantineEngine:
    """Separates clean clinical data from flawed records, preventing pipeline stops."""

    def __init__(self, cfg: PipelineConfig) -> None:
        self.cfg = cfg

    def process_and_quarantine(self, df_input: pd.DataFrame) -> QuarantineBatchResult:
        """Route valid records to silver and corrupt records to silver_quarantine."""
        valid_rows: list[dict[str, Any]] = []
        quarantined_rows: list[dict[str, Any]] = []
        now_ts = datetime.now(timezone.utc).isoformat()

        records = df_input.to_dict(orient="records")
        for rec in records:
            eval_res: RuleValidationResult = ClinicalRuleSuite.validate_record(rec)
            
            pat_id = rec.get("Patient_ID") if "Patient_ID" in rec else rec.get("patient_id")

            if eval_res.is_valid:
                valid_rows.append(rec)
            else:
                critical_violations = [v for v in eval_res.violations if v.severity == "CRITICAL"]
                reasons = "; ".join(f"{v.rule_name}: {v.message}" for v in critical_violations)
                
                quarantined_rows.append({
                    "quarantined_at": now_ts,
                    "patient_id": int(pat_id) if pd.notna(pat_id) else None,
                    "raw_payload_json": json.dumps({k: (str(v) if pd.notna(v) else None) for k, v in rec.items()}),
                    "quarantine_reason": reasons,
                    "severity": "CRITICAL",
                    "reprocessed_flag": 0,
                })

        # Save quarantined records to database
        if quarantined_rows:
            with managed_connection(self.cfg.warehouse_db) as conn:
                for q in quarantined_rows:
                    conn.execute(
                        """
                        INSERT INTO silver_quarantine 
                        (quarantined_at, patient_id, raw_payload_json, quarantine_reason, severity, reprocessed_flag)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            q["quarantined_at"],
                            q["patient_id"],
                            q["raw_payload_json"],
                            q["quarantine_reason"],
                            q["severity"],
                            q["reprocessed_flag"],
                        ),
                    )
            logger.warning(f"Quarantined {len(quarantined_rows)} records with quality violations.")

        # Save valid records into silver_encounters
        valid_df = pd.DataFrame(valid_rows) if valid_rows else pd.DataFrame(columns=df_input.columns)
        if not valid_df.empty:
            # Apply silver schema transformations
            clean_df = _coerce_types(valid_df)
            clean_df = _add_derived_columns(clean_df)
            
            # Map column names to silver schema
            rename_map = {
                "Patient_ID": "patient_id",
                "Age": "age",
                "Gender": "gender",
                "Condition": "condition",
                "Procedure": "procedure_name",
                "Cost": "cost",
                "Length_of_Stay": "length_of_stay",
                "Readmission": "readmission",
                "Outcome": "outcome",
                "Satisfaction": "satisfaction",
            }
            clean_df = clean_df.rename(columns=rename_map)
            clean_df["_silver_loaded_at"] = now_ts
            clean_df["_dq_passed"] = 1

            silver_cols = [
                "patient_id", "age", "age_band", "gender", "condition",
                "procedure_name", "cost", "length_of_stay", "readmission",
                "readmission_flag", "outcome", "satisfaction", "cost_per_day",
                "_silver_loaded_at", "_dq_passed"
            ]
            final_df = clean_df[[c for c in silver_cols if c in clean_df.columns]]

            with managed_connection(self.cfg.warehouse_db) as conn:
                # Use INSERT OR REPLACE to be idempotent across repeated runs
                placeholders = ", ".join(["?"] * len(silver_cols))
                col_names = ", ".join(silver_cols)
                stmt = f"INSERT OR REPLACE INTO silver_encounters ({col_names}) VALUES ({placeholders})"
                
                rows_to_insert = [
                    tuple(row[c] if c in row and pd.notna(row[c]) else None for c in silver_cols)
                    for _, row in final_df.iterrows()
                ]
                conn.executemany(stmt, rows_to_insert)
            logger.info(f"Loaded {len(final_df)} valid records into silver_encounters.")

        return QuarantineBatchResult(
            total_records=len(df_input),
            valid_count=len(valid_rows),
            quarantined_count=len(quarantined_rows),
            valid_df=valid_df,
            quarantined_records=quarantined_rows,
        )
