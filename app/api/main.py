from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import json
import joblib
import pandas as pd
from src.features.feature_pipeline import bundle_to_frame
from src.ai_service import answer

app = FastAPI(title='HealthGuard AI API', version='0.1.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'healthguard-api', 'demo_mode': True}

@app.get('/analytics/overview')
def overview():
    df = bundle_to_frame()
    return {
        'total_patients': len(df),
        'high_risk': int(df.risk_target.sum()),
        'data_quality': 91,
        'model_health': 'prototype'
    }

@app.get('/analytics/kpis')
def kpis():
    df = bundle_to_frame()
    total = len(df)
    high = int(df.risk_target.sum())
    
    return {
        "total_patients": total,
        "high_risk_patients": high,
        "high_risk_rate": round(high / total * 100, 1) if total else 0.0,
        "avg_risk_score": 0.42, # Mock
        "avg_heart_rate": round(df.mean_heart_rate.mean(), 1) if 'mean_heart_rate' in df else 80.0,
        "abnormal_observation_rate": round(df.abnormal_count.mean(), 1) if 'abnormal_count' in df else 0.0,
        "data_quality_score": 91,
        "model_status": "Demo model"
    }

@app.get('/analytics/risk-distribution')
def risk_distribution():
    df = bundle_to_frame()
    counts = df["risk_target"].value_counts().to_dict()
    return {
        "stable": int(counts.get(0, 0)),
        "high": int(counts.get(1, 0))
    }

@app.get('/analytics/age-risk')
def age_risk():
    df = bundle_to_frame()
    bins = [0, 30, 45, 60, 75, 120]
    labels = ["18-30", "31-45", "46-60", "61-75", "75+"]
    df["age_group"] = pd.cut(df["age"], bins=bins, labels=labels)
    out = (
        df.groupby("age_group", observed=False)["risk_target"]
        .mean()
        .reset_index()
    )
    out["risk_rate"] = (out["risk_target"] * 100).round(2)
    return out[["age_group", "risk_rate"]].to_dict(orient="records")

@app.get('/analytics/model-metrics')
def model_metrics():
    path = Path("models/metrics/risk_metrics.json")
    if not path.exists():
        return {
            "roc_auc": None,
            "pr_auc": None,
            "precision": None,
            "recall": None,
            "f1": None,
            "status": "metrics_not_found"
        }
    return json.loads(path.read_text())

@app.get('/analytics/condition-distribution')
def condition_distribution():
    df = bundle_to_frame()
    counts = df["condition"].value_counts().to_dict() if 'condition' in df else {}
    return {k: int(v) for k, v in counts.items()}

@app.get('/patients/{patient_id}/timeline')
def patient_timeline(patient_id: str):
    # Mocking timeline based on current implementation
    return {"events": [{"date": "2026-01-01", "type": "Encounter"}]}

@app.get('/patients')
def patients():
    return bundle_to_frame().to_dict(orient='records')

@app.get('/patients/{patient_id}/risk')
def risk(patient_id: str):
    df = bundle_to_frame()
    row = df[df.patient_id == patient_id]
    if row.empty:
        raise HTTPException(404, 'patient not found')
    r = row.iloc[0]
    features = ['age', 'mean_heart_rate', 'latest_heart_rate', 'observation_count', 'trend']
    model_path = Path('models/artifacts/risk_model.joblib')
    model = joblib.load(model_path) if model_path.exists() else None
    
    score = float(model.predict_proba(row[features])[:, 1][0]) if model else float(r.risk_target)
    
    reasons = []
    if r.abnormal_count > 0:
        reasons.append(f'{int(r.abnormal_count)} abnormal observations')
    if r.trend > 8:
        reasons.append('rising recent observation trend')
    if r.age > 70:
        reasons.append('age-related risk factor')
        
    return {
        'patient_id': patient_id,
        'risk_score': round(score, 4),
        'risk_tier': 'HIGH' if score >= 0.66 else 'WATCH' if score >= 0.33 else 'STABLE',
        'reasons': reasons
    }

@app.post('/assistant/query')
def assistant(payload: dict):
    return answer(payload.get('query', ''))
