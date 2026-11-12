"""Gold layer — analytics mart aggregator.

Reads from silver_encounters and materialises 5 pre-aggregated mart tables:
  gold_condition_mart  — per-condition rollup
  gold_age_band_mart   — per-age-band rollup
  gold_gender_mart     — per-gender rollup
  gold_outcome_mart    — per-outcome rollup
  gold_daily_summary   — single-row overall summary (snapshot date = today)

Design: pure SQL aggregations via pandas groupby → immutable result DataFrames
written to the warehouse.  Each mart is truncated before reload (idempotent).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import pandas as pd

from pipeline.config import PipelineConfig
from pipeline.warehouse import managed_connection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: load silver into DataFrame
# ---------------------------------------------------------------------------

def _load_silver(cfg: PipelineConfig) -> pd.DataFrame:
    with managed_connection(cfg.warehouse_db) as conn:
        df = pd.read_sql_query("SELECT * FROM silver_encounters", conn)
    logger.info("Gold: loaded %d Silver rows", len(df))
    return df


# ---------------------------------------------------------------------------
# Mart builders (each returns a new DataFrame — no mutation)
# ---------------------------------------------------------------------------

def _build_condition_mart(df: pd.DataFrame, loaded_at: str) -> pd.DataFrame:
    grp = df.groupby("condition", sort=True)
    total = grp["patient_id"].count().rename("total_patients")
    readmitted = grp["readmission_flag"].sum().rename("readmitted_count")
    rate = (readmitted / total * 100).round(2).rename("readmission_rate_pct")
    total_cost = grp["cost"].sum().round(2).rename("total_cost")
    avg_cost = grp["cost"].mean().round(2).rename("avg_cost")
    avg_los = grp["length_of_stay"].mean().round(2).rename("avg_length_of_stay")
    avg_sat = grp["satisfaction"].mean().round(2).rename("avg_satisfaction")

    mart = pd.concat(
        [total, readmitted, rate, total_cost, avg_cost, avg_los, avg_sat], axis=1
    ).reset_index()
    mart["_gold_loaded_at"] = loaded_at
    return mart


def _build_age_band_mart(df: pd.DataFrame, loaded_at: str) -> pd.DataFrame:
    # Canonical sort order
    band_order = ["18-30", "31-45", "46-60", "61-75", "76+"]
    df = df.copy()
    df["age_band"] = pd.Categorical(df["age_band"], categories=band_order, ordered=True)
    grp = df.groupby("age_band", sort=True, observed=True)

    mart = pd.DataFrame({
        "age_band": band_order,
    })
    agg = (
        grp.agg(
            total_patients=("patient_id", "count"),
            readmitted_count=("readmission_flag", "sum"),
            avg_cost=("cost", "mean"),
            avg_length_of_stay=("length_of_stay", "mean"),
        )
        .round(2)
        .reset_index()
    )
    agg["readmission_rate_pct"] = (
        agg["readmitted_count"] / agg["total_patients"] * 100
    ).round(2)
    agg["_gold_loaded_at"] = loaded_at
    return agg


def _build_gender_mart(df: pd.DataFrame, loaded_at: str) -> pd.DataFrame:
    grp = df.groupby("gender", sort=True)
    agg = (
        grp.agg(
            total_patients=("patient_id", "count"),
            readmitted_count=("readmission_flag", "sum"),
            avg_cost=("cost", "mean"),
            avg_satisfaction=("satisfaction", "mean"),
        )
        .round(2)
        .reset_index()
    )
    agg["readmission_rate_pct"] = (
        agg["readmitted_count"] / agg["total_patients"] * 100
    ).round(2)
    agg["_gold_loaded_at"] = loaded_at
    return agg


def _build_outcome_mart(df: pd.DataFrame, loaded_at: str) -> pd.DataFrame:
    total_patients = len(df)
    grp = df.groupby("outcome", sort=True)
    agg = (
        grp.agg(
            total_patients=("patient_id", "count"),
            avg_cost=("cost", "mean"),
            readmission_rate_pct=("readmission_flag", "mean"),
        )
        .round(2)
        .reset_index()
    )
    agg["share_pct"] = (agg["total_patients"] / total_patients * 100).round(2)
    agg["readmission_rate_pct"] = (agg["readmission_rate_pct"] * 100).round(2)
    agg["_gold_loaded_at"] = loaded_at
    return agg[
        ["outcome", "total_patients", "share_pct", "avg_cost",
         "readmission_rate_pct", "_gold_loaded_at"]
    ]


def _build_daily_summary(df: pd.DataFrame, loaded_at: str) -> pd.DataFrame:
    total = len(df)
    readmitted = int(df["readmission_flag"].sum())
    return pd.DataFrame([{
        "summary_date": date.today().isoformat(),
        "total_patients": total,
        "total_cost": round(float(df["cost"].sum()), 2),
        "readmitted_count": readmitted,
        "readmission_rate_pct": round(readmitted / total * 100, 2) if total else 0.0,
        "avg_cost": round(float(df["cost"].mean()), 2),
        "avg_length_of_stay": round(float(df["length_of_stay"].mean()), 2),
        "avg_satisfaction": round(float(df["satisfaction"].mean()), 2),
        "_gold_loaded_at": loaded_at,
    }])


# ---------------------------------------------------------------------------
# Writer helper
# ---------------------------------------------------------------------------

def _write_mart(
    df: pd.DataFrame,
    table: str,
    cfg: PipelineConfig,
) -> int:
    with managed_connection(cfg.warehouse_db) as conn:
        conn.execute(f"DELETE FROM {table}")
        df.to_sql(table, conn, if_exists="append", index=False, method="multi")
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    logger.info("Gold: %s — %d rows", table, count)
    return count


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_gold_marts(cfg: PipelineConfig) -> dict[str, int]:
    """Build all Gold mart tables from Silver.

    Returns mapping of {table_name: rows_written}.
    """
    df = _load_silver(cfg)
    loaded_at = datetime.now(timezone.utc).isoformat()

    mart_rows: dict[str, int] = {}

    mart_rows[cfg.gold_condition_mart] = _write_mart(
        _build_condition_mart(df, loaded_at), cfg.gold_condition_mart, cfg
    )
    mart_rows[cfg.gold_age_band_mart] = _write_mart(
        _build_age_band_mart(df, loaded_at), cfg.gold_age_band_mart, cfg
    )
    mart_rows[cfg.gold_gender_mart] = _write_mart(
        _build_gender_mart(df, loaded_at), cfg.gold_gender_mart, cfg
    )
    mart_rows[cfg.gold_outcome_mart] = _write_mart(
        _build_outcome_mart(df, loaded_at), cfg.gold_outcome_mart, cfg
    )
    mart_rows[cfg.gold_daily_summary] = _write_mart(
        _build_daily_summary(df, loaded_at), cfg.gold_daily_summary, cfg
    )

    return mart_rows
