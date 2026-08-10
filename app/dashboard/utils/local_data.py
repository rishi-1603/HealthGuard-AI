"""
Self-contained data/model access for the dashboard.

Mirrors the logic in app/api/main.py but runs in-process, so the
Streamlit app has no dependency on a separately deployed API.
Used when running the dashboard standalone (e.g. Streamlit Community Cloud).
"""
import json
from pathlib import Path

import joblib
import pandas as pd
import streamlit as st

from src.features.feature_pipeline import bundle_to_frame
from src.ai_service import answer as _answer

MODEL_PATH = Path("models/artifacts/risk_model.joblib")
METRICS_PATH = Path("models/metrics/risk_metrics.json")
FEATURES = ["age", "mean_heart_rate", "latest_heart_rate", "observation_count", "trend"]


@st.cache_data(ttl=300)
def load_patients() -> pd.DataFrame:
    return bundle_to_frame()


@st.cache_resource
def load_model():
    if MODEL_PATH.exists():
        return joblib.load(MODEL_PATH)
    return None


def get_kpis() -> dict:
    df = load_patients()
    total = len(df)
    high = int(df.risk_target.sum())
    return {
        "total_patients": total,
        "high_risk_patients": high,
        "high_risk_rate": round(high / total * 100, 1) if total else 0.0,
        "avg_risk_score": 0.42,  # Mock, matches API behavior
        "avg_heart_rate": round(df.mean_heart_rate.mean(), 1) if "mean_heart_rate" in df else 80.0,
        "abnormal_observation_rate": round(df.abnormal_count.mean(), 1) if "abnormal_count" in df else 0.0,
        "data_quality_score": 91,
        "model_status": "Demo model",
    }


def get_risk_distribution() -> dict:
    df = load_patients()
    counts = df["risk_target"].value_counts().to_dict()
    return {"stable": int(counts.get(0, 0)), "high": int(counts.get(1, 0))}


def get_model_metrics() -> dict:
    if not METRICS_PATH.exists():
        return {
            "roc_auc": None, "pr_auc": None, "precision": None,
            "recall": None, "f1": None, "status": "metrics_not_found",
        }
    return json.loads(METRICS_PATH.read_text())


def get_patient_risk(patient_id: str) -> dict:
    df = load_patients()
    row = df[df.patient_id == patient_id]
    if row.empty:
        return {"patient_id": patient_id, "risk_score": None, "risk_tier": "UNKNOWN", "reasons": []}
    r = row.iloc[0]
    model = load_model()
    score = float(model.predict_proba(row[FEATURES])[:, 1][0]) if model else float(r.risk_target)

    reasons = []
    if r.abnormal_count > 0:
        reasons.append(f"{int(r.abnormal_count)} abnormal observations")
    if r.trend > 8:
        reasons.append("rising recent observation trend")
    if r.age > 70:
        reasons.append("age-related risk factor")

    return {
        "patient_id": patient_id,
        "risk_score": round(score, 4),
        "risk_tier": "HIGH" if score >= 0.66 else "WATCH" if score >= 0.33 else "STABLE",
        "reasons": reasons,
    }


def ask_assistant(query: str) -> dict:
    return _answer(query)
