# ARCHITECTURE & INTERFACES — HealthGuard

## Data flow

```text
data/hospital/hospital_data.csv (committed synthetic records, 984 × 10)
  ├─ scripts/sql_analytics.py → SQLite analytics and pandas reconciliation
  ├─ scripts/train_readmission_model.py (optional retrain) → model/encoders
  └─ app/dashboard/Home.py
       ├─ hospital_data.py / ops_layer.py → scoped descriptive analysis
       ├─ analyst_workbench.py + sql/02_analyst_workbench.sql → validation, cohort comparison, scoped SQL/pandas reconciliation and reporting
       ├─ ai_risk.py → synthetic-record scores and SHAP
       └─ assistant_service.py → validated plans and computed evidence
            └─ optional gemini_ai.py → allowed fact-ID selection only
```

The `src/` FHIR prototype and its `data/synthetic/` pipeline are legacy reference code, not the source of the committed hospital table. CI audits the primary model; it does not retrain the shipped readmission artifact on every push.

## Module interfaces
| Module | Input | Output |
|---|---|---|
| train_readmission_model.py | hospital_data.csv | readmission_model.joblib + metrics |
| cohort_shap_analysis.py | model + data | cohort SHAP + reports/cohort_shap.md |
| calibration_decision_curve.py | model + split | calibration/DCA metrics JSON + report + figure |
| temporal_validation.py | model + data | random-vs-temporal AUC + noise band |
| app/ (Streamlit) | scoped records + model | descriptive dashboard, synthetic-model explanations and bounded assistant |
| analyst_workbench.py | validated selected + reference DataFrames | contract checks, SQL/pandas parity, aggregate comparison and report |
| assistant_service.py | question + filtered DataFrame | validated plan, computed value, denominator, provenance and refusals |
| gemini_ai.py | computed fact catalog + supported focus | validated existing card selection, safe failure status |

## Deployment
- **App:** Streamlit Community Cloud — https://healthguard-ai-cyl2viwrsdrrff7pig7u6c.streamlit.app/
- **Container:** Dockerfile included (local/prod parity)
- **CI:** GitHub Actions: calibration + temporal scripts -> pytest (matplotlib optional)

## Design rules
- Explainer layer is separate from the model (SHAP values computed on demand).
- Q&A answers must cite grounded values or refuse (tested).
