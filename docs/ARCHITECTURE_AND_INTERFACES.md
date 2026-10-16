# ARCHITECTURE & INTERFACES — HealthGuard

## Data flow
```
scripts/generate_data.py -> data/hospital/hospital_data.csv (984x10, synthetic)
   └─> scripts/train_readmission_model.py -> models/readmission/
         ├─> app/dashboard (Streamlit: risk view, SHAP, cohort, Q&A, ops)
         └─> scripts/{fairness_check, calibration_decision_curve,
                      temporal_validation, cohort_shap_analysis,
                      model_honesty_audit}.py -> reports/
```

## Module interfaces
| Module | Input | Output |
|---|---|---|
| train_readmission_model.py | hospital_data.csv | readmission_model.joblib + metrics |
| cohort_shap_analysis.py | model + data | cohort SHAP + reports/cohort_shap.md |
| calibration_decision_curve.py | model + split | calibration/DCA metrics JSON + report + figure |
| temporal_validation.py | model + data | random-vs-temporal AUC + noise band |
| app/ (Streamlit) | model + SHAP | patient view, drivers, grounded Q&A, ops panel |

## Deployment
- **App:** Streamlit Community Cloud — https://healthguard-ai-cyl2viwrsdrrff7pig7u6c.streamlit.app/
- **Container:** Dockerfile included (local/prod parity)
- **CI:** GitHub Actions: calibration + temporal scripts -> pytest (matplotlib optional)

## Design rules
- Explainer layer is separate from the model (SHAP values computed on demand).
- Q&A answers must cite grounded values or refuse (tested).
