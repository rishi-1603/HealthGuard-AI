import json
import joblib
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, average_precision_score, precision_score, recall_score, f1_score
from src.features.feature_pipeline import bundle_to_frame

def train():
    df = bundle_to_frame()
    
    # Train on past features that don't directly calculate the target to avoid perfect leakage
    # Target in feature_pipeline is based on encounter_count, abnormal_count, spo2_min, mean_systolic_bp
    # So we use different proxy features to predict it
    features = ['age', 'mean_heart_rate', 'latest_heart_rate', 'observation_count', 'trend']
    X = df[features]
    y = df.risk_target
    
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
    
    model = RandomForestClassifier(n_estimators=120, max_depth=5, random_state=42, class_weight='balanced')
    model.fit(Xtr, ytr)
    
    p = model.predict_proba(Xte)[:, 1]
    pred = (p >= 0.5).astype(int)
    
    Path('models/artifacts').mkdir(parents=True, exist_ok=True)
    Path('models/metrics').mkdir(parents=True, exist_ok=True)
    
    joblib.dump(model, 'models/artifacts/risk_model.joblib')
    
    metrics = {
        'roc_auc': round(roc_auc_score(yte, p), 4),
        'pr_auc': round(average_precision_score(yte, p), 4),
        'precision': round(precision_score(yte, pred), 4),
        'recall': round(recall_score(yte, pred), 4),
        'f1': round(f1_score(yte, pred), 4),
        'n_test': len(yte)
    }
    
    Path('models/metrics/risk_metrics.json').write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics))
    return metrics

if __name__ == '__main__':
    train()
