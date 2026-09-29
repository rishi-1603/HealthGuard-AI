"""
ops_layer.py — operational analytics layer for the HealthGuard dashboard.
================================================================================
Day-3 upgrade. Pure pandas — no Streamlit, no LLM, nothing hardcoded. Every
number the Ops Context strip and the Root-Cause Drill display is computed here
and pinned by tests/test_ops_layer.py.

Model facts (fairness, honesty audit, cohort SHAP) are model-derived, NOT
computable from the raw patient table — they live in data/metrics.json (the
semantic layer), sourced from reports/fairness_check.md and
reports/model_honesty.md, and are displayed as disclosures.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
METRICS_PATH = REPO_ROOT / "data" / "metrics.json"

AGE_BANDS = [(17, 30, "18-30"), (30, 45, "31-45"), (45, 60, "46-60"),
             (60, 75, "61-75"), (75, 120, "76+")]
AGE_BAND_LABELS = [b[2] for b in AGE_BANDS]


def age_band(age: int) -> str:
    for lo, hi, label in AGE_BANDS:
        if lo < age <= hi:
            return label
    return AGE_BANDS[-1][2]


def add_bands(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["Age_Band"] = out["Age"].apply(age_band)
    return out


def ops_context(df: pd.DataFrame) -> dict:
    """The operational headline: what readmissions cost the hospital."""
    total = len(df)
    if total == 0:
        return {}
    r = df[df.Readmission == "Yes"]
    n = df[df.Readmission == "No"]
    out = {
        "total_patients": total,
        "readmitted_n": len(r),
        "readmission_rate_pct": round(len(r) / total * 100, 1),
        "readmitted_avg_cost": round(r.Cost.mean(), 0) if len(r) else 0,
        "non_readmitted_avg_cost": round(n.Cost.mean(), 0) if len(n) else 0,
        "readmitted_avg_los": round(r.Length_of_Stay.mean(), 1) if len(r) else 0,
        "non_readmitted_avg_los": round(n.Length_of_Stay.mean(), 1) if len(n) else 0,
        "readmitted_total_cost": round(r.Cost.sum(), 0),
        "readmitted_cost_share_pct": round(r.Cost.sum() / df.Cost.sum() * 100, 1) if df.Cost.sum() else 0,
    }
    if out["non_readmitted_avg_cost"]:
        out["cost_premium_pct"] = round(
            (out["readmitted_avg_cost"] / out["non_readmitted_avg_cost"] - 1) * 100, 1)
    else:
        out["cost_premium_pct"] = 0.0
    out["los_premium_days"] = round(out["readmitted_avg_los"] - out["non_readmitted_avg_los"], 1)
    return out


def readmission_by_condition(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("Condition").agg(
        patients=("Patient_ID", "count"),
        readmit_rate_pct=("Readmission", lambda x: (x == "Yes").mean() * 100),
        avg_cost=("Cost", "mean"),
    ).reset_index()
    return g.sort_values("readmit_rate_pct", ascending=False).reset_index(drop=True)


def readmission_by_age_band(df: pd.DataFrame, condition: str | None = None) -> pd.DataFrame:
    d = add_bands(df)
    if condition:
        d = d[d.Condition == condition]
    g = d.groupby("Age_Band").agg(
        patients=("Patient_ID", "count"),
        readmit_rate_pct=("Readmission", lambda x: (x == "Yes").mean() * 100),
    ).reindex(AGE_BAND_LABELS).dropna(subset=["patients"]).reset_index()
    g["patients"] = g["patients"].astype(int)
    g["readmit_rate_pct"] = g["readmit_rate_pct"].round(1)
    return g


def condition_profile(df: pd.DataFrame, condition: str) -> dict:
    """Readmitted vs non-readmitted cost/LOS inside one condition."""
    d = df[df.Condition == condition]
    r = d[d.Readmission == "Yes"]
    n = d[d.Readmission == "No"]
    return {
        "condition": condition,
        "patients": len(d),
        "readmit_rate_pct": round(len(r) / len(d) * 100, 1) if len(d) else 0,
        "readmitted_avg_cost": round(r.Cost.mean(), 0) if len(r) else 0,
        "non_readmitted_avg_cost": round(n.Cost.mean(), 0) if len(n) else 0,
        "readmitted_avg_los": round(r.Length_of_Stay.mean(), 1) if len(r) else 0,
        "non_readmitted_avg_los": round(n.Length_of_Stay.mean(), 1) if len(n) else 0,
    }


def load_model_facts(path: str | Path = METRICS_PATH) -> dict:
    """Verified model facts from the semantic layer (fairness, honesty, SHAP).
    These are model-derived disclosures — the dashboard never recomputes them."""
    with open(path, "r", encoding="utf-8") as fh:
        m = json.load(fh)
    return {
        "fairness": m["metrics"]["fairness"],
        "model_honesty": m["metrics"]["model_honesty"],
        "cohort_shap": m["metrics"]["cohort_shap"],
    }
