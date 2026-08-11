"""
Trains a readmission-risk classifier on the hospital outcomes dataset
(data/hospital/hospital_data.csv) and saves the model + a fitted
SHAP explainer for use in the dashboard.

Run: python scripts/train_readmission_model.py
"""
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score
from sklearn.preprocessing import LabelEncoder

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "hospital" / "hospital_data.csv"
MODEL_DIR = ROOT / "models" / "readmission"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

FEATURES = ["Age", "Gender_enc", "Condition_enc", "Procedure_enc", "Cost", "Length_of_Stay"]


def main():
    df = pd.read_csv(DATA_PATH)
    df["target"] = (df.Readmission == "Yes").astype(int)

    encoders = {}
    for col in ["Gender", "Condition", "Procedure"]:
        le = LabelEncoder()
        df[f"{col}_enc"] = le.fit_transform(df[col])
        encoders[col] = le

    X = df[FEATURES]
    y = df["target"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    model = RandomForestClassifier(
        n_estimators=200, max_depth=6, min_samples_leaf=5,
        class_weight="balanced", random_state=42
    )
    model.fit(X_train, y_train)

    proba = model.predict_proba(X_test)[:, 1]
    preds = (proba >= 0.5).astype(int)

    metrics = {
        "roc_auc": round(roc_auc_score(y_test, proba), 4),
        "precision": round(precision_score(y_test, preds, zero_division=0), 4),
        "recall": round(recall_score(y_test, preds, zero_division=0), 4),
        "f1": round(f1_score(y_test, preds, zero_division=0), 4),
        "n_test": len(y_test),
        "features": FEATURES,
    }

    joblib.dump(model, MODEL_DIR / "readmission_model.joblib")
    joblib.dump(encoders, MODEL_DIR / "encoders.joblib")

    import json
    (MODEL_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))

    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
