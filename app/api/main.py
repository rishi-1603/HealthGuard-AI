from fastapi import FastAPI, HTTPException
from pathlib import Path
import json, joblib
from src.features.feature_pipeline import bundle_to_frame
from src.ai_service import answer
app=FastAPI(title='HealthGuard AI API',version='0.1.0')
@app.get('/health')
def health(): return {'status':'ok','service':'healthguard-api','demo_mode':True}
@app.get('/analytics/overview')
def overview():
 df=bundle_to_frame(); return {'total_patients':len(df),'high_risk':int(df.risk_target.sum()),'data_quality':91,'model_health':'prototype'}
@app.get('/patients')
def patients(): return bundle_to_frame().to_dict(orient='records')
@app.get('/patients/{patient_id}/risk')
def risk(patient_id:str):
 df=bundle_to_frame(); row=df[df.patient_id==patient_id]
 if row.empty: raise HTTPException(404,'patient not found')
 r=row.iloc[0]; features=['age','observation_count','latest_heart_rate','mean_heart_rate','abnormal_count','trend']; model=joblib.load('models/artifacts/risk_model.joblib') if Path('models/artifacts/risk_model.joblib').exists() else None
 score=float(model.predict_proba(row[features])[:,1][0]) if model else float(r.risk_target)
 reasons=[]
 if r.abnormal_count: reasons.append(f'{int(r.abnormal_count)} abnormal observations')
 if r.trend>8: reasons.append('rising recent observation trend')
 if r.age>70: reasons.append('age-related risk factor')
 return {'patient_id':patient_id,'risk_score':round(score,4),'risk_tier':'HIGH' if score>=.66 else 'WATCH' if score>=.33 else 'STABLE','reasons':reasons}
@app.post('/assistant/query')
def assistant(payload:dict): return answer(payload.get('query',''))
