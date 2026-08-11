"""
AI layer: readmission risk scoring with SHAP-based explainability.
Loads the model trained by scripts/train_readmission_model.py.
"""
import sys
from pathlib import Path

import joblib
import pandas as pd
import shap
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[3]
MODEL_DIR = REPO_ROOT / "models" / "readmission"
FEATURES = ["Age", "Gender_enc", "Condition_enc", "Procedure_enc", "Cost", "Length_of_Stay"]
FEATURE_LABELS = {
    "Age": "Age",
    "Gender_enc": "Gender",
    "Condition_enc": "Condition",
    "Procedure_enc": "Procedure",
    "Cost": "Cost",
    "Length_of_Stay": "Length of stay",
}


@st.cache_resource
def load_model():
    model = joblib.load(MODEL_DIR / "readmission_model.joblib")
    encoders = joblib.load(MODEL_DIR / "encoders.joblib")
    return model, encoders


@st.cache_resource
def load_explainer():
    model, _ = load_model()
    return shap.TreeExplainer(model)


def get_metrics() -> dict:
    import json
    path = MODEL_DIR / "metrics.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _encode(df: pd.DataFrame, encoders: dict) -> pd.DataFrame:
    out = df.copy()
    for col in ["Gender", "Condition", "Procedure"]:
        out[f"{col}_enc"] = encoders[col].transform(out[col])
    return out


def score_patient(row: pd.Series) -> dict:
    """Return risk score + top SHAP-driven factors for one patient row."""
    model, encoders = load_model()
    explainer = load_explainer()

    df_row = pd.DataFrame([row])
    df_row = _encode(df_row, encoders)
    X = df_row[FEATURES]

    proba = float(model.predict_proba(X)[0][1])

    shap_vals = explainer.shap_values(X)
    # shape: (n_samples, n_features, n_classes) -> take class 1 (readmit)
    if shap_vals.ndim == 3:
        vals = shap_vals[0, :, 1]
    else:
        vals = shap_vals[0]

    factors = sorted(
        zip(FEATURES, vals),
        key=lambda t: abs(t[1]), reverse=True
    )[:4]

    factor_list = [
        {"feature": FEATURE_LABELS[f], "impact": round(float(v), 4)}
        for f, v in factors
    ]

    tier = "HIGH" if proba >= 0.66 else "WATCH" if proba >= 0.33 else "LOW"

    return {
        "risk_score": round(proba, 4),
        "risk_tier": tier,
        "top_factors": factor_list,
    }


def score_cohort(df: pd.DataFrame) -> pd.Series:
    """Vectorized risk scores for a whole dataframe (for KPI/summary use)."""
    model, encoders = load_model()
    enc = _encode(df, encoders)
    X = enc[FEATURES]
    return pd.Series(model.predict_proba(X)[:, 1], index=df.index)
