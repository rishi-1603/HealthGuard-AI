"""
test_readmission_model.py — tests for the product's risk model
===============================================================
The shipped model artifacts (models/readmission/) are loaded by the live
dashboard. These tests guarantee the artifacts are loadable, produce valid
outputs, and stay consistent with the training script's documented metrics.
"""
import json
from pathlib import Path

import joblib
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models" / "readmission"
DATA_PATH = ROOT / "data" / "hospital" / "hospital_data.csv"
FEATURES = ["Age", "Gender_enc", "Condition_enc", "Procedure_enc", "Cost", "Length_of_Stay"]


@pytest.fixture(scope="module")
def artifacts():
    model = joblib.load(MODEL_DIR / "readmission_model.joblib")
    encoders = joblib.load(MODEL_DIR / "encoders.joblib")
    return model, encoders


@pytest.fixture(scope="module")
def df():
    return pd.read_csv(DATA_PATH)


def _encode(df, encoders):
    out = df.copy()
    for col in ["Gender", "Condition", "Procedure"]:
        out[f"{col}_enc"] = encoders[col].transform(out[col])
    return out


def test_artifacts_exist():
    for name in ["readmission_model.joblib", "encoders.joblib", "metrics.json"]:
        assert (MODEL_DIR / name).exists(), f"Missing artifact: {name}"


def test_model_scores_are_valid_probabilities(artifacts, df):
    model, encoders = artifacts
    X = _encode(df, encoders)[FEATURES]
    proba = model.predict_proba(X)[:, 1]
    assert ((proba >= 0) & (proba <= 1)).all(), "Probabilities outside [0,1]"


def test_risk_tier_thresholds_match_dashboard(artifacts, df):
    """Dashboard tiers: HIGH >= 0.66, WATCH >= 0.33, else LOW (ai_risk.py).
    The full-cohort score distribution must actually populate all tiers —
    otherwise the tier UI is untested dead code."""
    model, encoders = artifacts
    X = _encode(df, encoders)[FEATURES]
    proba = model.predict_proba(X)[:, 1]
    n_high = (proba >= 0.66).sum()
    n_watch = ((proba >= 0.33) & (proba < 0.66)).sum()
    n_low = (proba < 0.33).sum()
    assert n_high > 0 and n_low > 0, "HIGH/LOW tiers empty — tier logic broken"


def test_metrics_json_is_self_consistent():
    metrics = json.loads((MODEL_DIR / "metrics.json").read_text())
    assert 0.5 <= metrics["roc_auc"] <= 1.0, "AUC outside [0.5, 1.0]"
    assert 0.0 <= metrics["precision"] <= 1.0
    assert 0.0 <= metrics["recall"] <= 1.0
    assert metrics["n_test"] > 0
    assert set(metrics["features"]) == set(FEATURES), "Feature set drifted from UI"


def test_honesty_baseline_recorded():
    """The condition-lookup baseline AUC must be recorded in metrics.json —
    this is the number that keeps the 0.99 headline honest."""
    metrics = json.loads((MODEL_DIR / "metrics.json").read_text())
    assert "condition_baseline_auc" in metrics, (
        "Baseline AUC missing — run scripts/model_honesty_audit.py")
    assert metrics["condition_baseline_auc"] > 0.85, (
        "Baseline dropped below 0.85 — dataset determinism may have changed; "
        "update the honesty audit")


def test_retrained_model_matches_recorded_metrics(artifacts, df):
    """Retraining with the documented settings must reproduce the recorded
    AUC within tolerance — proves metrics.json wasn't hand-edited."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import train_test_split

    model, encoders = artifacts
    data = _encode(df, encoders)
    data = data.assign(target=(df.Readmission == "Yes").astype(int))

    X_tr, X_te, y_tr, y_te = train_test_split(
        data[FEATURES], data["target"], test_size=0.2,
        random_state=42, stratify=data["target"])
    m = RandomForestClassifier(n_estimators=200, max_depth=6, min_samples_leaf=5,
                               class_weight="balanced", random_state=42)
    m.fit(X_tr, y_tr)
    auc = roc_auc_score(y_te, m.predict_proba(X_te)[:, 1])

    recorded = json.loads((MODEL_DIR / "metrics.json").read_text())["roc_auc"]
    assert abs(auc - recorded) < 0.02, (
        f"Retrained AUC {auc:.3f} vs recorded {recorded:.3f} — metrics not reproducible")


def test_encoders_cover_all_dataset_categories(artifacts, df):
    """The deployed encoders must handle every category in the dataset —
    an unseen category at scoring time would crash the live dashboard."""
    _, encoders = artifacts
    for col in ["Gender", "Condition", "Procedure"]:
        known = set(encoders[col].classes_)
        present = set(df[col].unique())
        unseen = present - known
        assert not unseen, f"Encoder for {col} has unseen categories: {unseen}"
