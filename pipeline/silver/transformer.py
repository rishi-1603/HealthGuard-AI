"""Silver layer — transformation engine.

Reads from bronze_encounters, applies:
  1. Type coercion (str → int/float where required)
  2. Derived columns (age_band, readmission_flag, cost_per_day)
  3. Data quality gate (raises if CRITICAL checks fail)
  4. Writes clean rows to silver_encounters

Design: returns new DataFrames — never mutates inputs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from pipeline.config import AGE_BANDS, PipelineConfig
from pipeline.silver.quality import QualityReport, run_quality_checks
from pipeline.warehouse import managed_connection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Age-band derivation
# ---------------------------------------------------------------------------

def _assign_age_band(age: int) -> str:
    """Map an integer age to the canonical age-band label."""
    for lo, hi, label in AGE_BANDS:
        if lo <= age <= hi:
            return label
    return "76+"   # fallback for ages beyond last band


# ---------------------------------------------------------------------------
# Type coercion (Bronze strings → Silver typed values)
# ---------------------------------------------------------------------------

def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """Return a new DataFrame with all columns cast to their Silver types."""
    result = df.copy()
    int_cols = ["Patient_ID", "Age", "Cost", "Length_of_Stay", "Satisfaction"]
    for col in int_cols:
        result[col] = pd.to_numeric(result[col], errors="coerce")
    return result


# ---------------------------------------------------------------------------
# Derive computed columns
# ---------------------------------------------------------------------------

def _add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a new DataFrame with derived Silver columns appended."""
    result = df.copy()

    result["age_band"] = result["Age"].apply(
        lambda a: _assign_age_band(int(a)) if pd.notna(a) else "Unknown"
    )
    result["readmission_flag"] = result["Readmission"].map({"Yes": 1, "No": 0})

    # cost_per_day: guard against division by zero
    result["cost_per_day"] = result.apply(
        lambda row: (
            round(row["Cost"] / row["Length_of_Stay"], 4)
            if pd.notna(row["Length_of_Stay"]) and row["Length_of_Stay"] > 0
            else None
        ),
        axis=1,
    )
    return result


# ---------------------------------------------------------------------------
# Column rename: Bronze snake_case → Silver snake_case
# ---------------------------------------------------------------------------

_RENAME_MAP: dict[str, str] = {
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

_SILVER_FINAL_COLS: list[str] = [
    "patient_id",
    "age",
    "age_band",
    "gender",
    "condition",
    "procedure_name",
    "cost",
    "length_of_stay",
    "readmission",
    "readmission_flag",
    "outcome",
    "satisfaction",
    "cost_per_day",
    "_silver_loaded_at",
    "_dq_passed",
]


# ---------------------------------------------------------------------------
# Main transform function
# ---------------------------------------------------------------------------

def transform_to_silver(
    cfg: PipelineConfig,
) -> tuple[int, QualityReport]:
    """Read Bronze → clean → validate → write Silver.

    Returns (rows_written, quality_report).
    Raises RuntimeError if quality gate fails.
    """
    with managed_connection(cfg.warehouse_db) as conn:
        raw = pd.read_sql_query(
            "SELECT * FROM bronze_encounters", conn
        )

    logger.info("Silver: read %d Bronze rows", len(raw))

    # Drop internal Bronze metadata cols before DQ check
    df = raw.drop(
        columns=["_row_id", "_ingested_at", "_source_file", "_source_hash"],
        errors="ignore",
    )

    # 1. Coerce types
    df = _coerce_types(df)

    # 2. DQ gate
    report = run_quality_checks(df, cfg)
    if not report.passed:
        failures = [f"{r.check_name}: {r.detail}" for r in report.critical_failures]
        raise RuntimeError(f"Silver quality gate FAILED: {failures}")

    # 3. Derived columns
    df = _add_derived_columns(df)

    # 4. Rename columns
    df = df.rename(columns=_RENAME_MAP)

    # 5. Add Silver metadata
    loaded_at = datetime.now(timezone.utc).isoformat()
    df = df.copy()
    df["_silver_loaded_at"] = loaded_at
    df["_dq_passed"] = 1

    # 6. Select final column order
    df_final = df[[c for c in _SILVER_FINAL_COLS if c in df.columns]]

    # 7. Write to Silver (truncate-and-reload for idempotency)
    with managed_connection(cfg.warehouse_db) as conn:
        conn.execute("DELETE FROM silver_encounters")
        df_final.to_sql(
            "silver_encounters",
            conn,
            if_exists="append",
            index=False,
            method="multi",
        )
        rows_written = conn.execute(
            "SELECT COUNT(*) FROM silver_encounters"
        ).fetchone()[0]

    logger.info("Silver: wrote %d rows", rows_written)
    return rows_written, report
