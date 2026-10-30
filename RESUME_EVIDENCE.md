# HealthGuard AI — Hospital Operations Analytics & Model Evaluation — Resume Evidence Index
**Repository:** https://github.com/rishi-1603/HealthGuard-AI  
**Live Application:** https://healthguard-ai-cyl2viwrsdrrff7pig7u6c.streamlit.app/  
**Verification Date:** 2026-10-30  
**CI Test Status:** 132 Passing Tests (100% Passing)

---

## 1. Resume Claim Verification Matrix

| # | Resume Claim | Canonical Metric Value | Target Population / Grain | Source File / Implementation | Reproduction Command | Automated Test File | Documented Limitation |
|---|---|---|---|---|---|---|---|
| 1 | **Total Patient Cohort** | 984 Patient Records | Patient admission encounters | data/hospital_admissions.csv | python -m src.eda --patients | 	ests/test_data_integrity.py | Synthetic cohort designed with realistic clinical attributes and hospital cost pathways. |
| 2 | **Clinical Conditions** | 15 Medical Conditions | Inpatient diagnostic categories | src/condition_profiling.py | python -m src.condition_profiling | 	ests/test_condition_analytics.py | Fixed synthetic ICD/diagnosis taxonomy. |
| 3 | **Readmission Prevalence** | 26.8% of Admissions (264 records) | 30-day all-cause readmissions | src/outcomes_analysis.py | python -m src.outcomes_analysis | 	ests/test_outcomes_consistency.py | Readmissions drive 43.8% of total inpatient expenditure. |
| 4 | **No-ML Clinical Baseline** | 0.929 ROC-AUC | Condition-only lookup benchmark | src/baseline_models.py | python -m src.baseline_models --eval | 	ests/test_readmission_model.py | Demonstrates that medical condition alone explains majority of variance. |
| 5 | **Methodology & Synthetic Ceiling** | Apparent 0.99 AUC reflects synthetic structure | Held-out test split under ML model | src/model_audit.py | python -m src.model_audit --synthetic-check | 	ests/test_model_honesty.py | **Documented limitation:** High performance reflects synthetic generator deterministic rules, not clinical magic. |
| 6 | **SHAP Interpretability Audit** | Top factors: Admission Age, LOS, Medication Count | SHAP TreeExplainer feature attributions | src/explainability.py | python -m src.explainability --shap | 	ests/test_cohort_shap.py | Explains model associations, not direct biological causation. |
| 7 | **Intervention Economics** | Rs. 2.98L net benefit (top-quartile) vs Rs. 10.4L loss (blanket) | Simulated clinical follow-up program | src/program_economics.py | python -m src.program_economics --simulate | 	ests/test_program_economics.py | Modeled economic simulation based on Rs. 5,000 intervention cost and 25% readmission prevention efficacy. |
| 8 | **Automated CI Footprint** | 132 Passing Tests | Unit, regression, & fairness tests | 	ests/ directory | python -m pytest | GitHub Actions workflow .github/workflows/ci.yml | Validates schema integrity, demographic parity, and inference logic. |

---

## 2. Analytical Question & Prediction Point Definition

`
Clinical Inpatient Encounter Timeline:
 [Admission] ------------------> [In-Hospital Stay] ------------------> [Discharge] ------------------> [30-Day Follow-up]
     │                                     │                                │                                │
     ├─ Admission Vitals (BP, HR)          ├─ Daily Lab Trend Records       ├─ Total Length of Stay (Days)   └─ Readmission Status (0/1)
     ├─ Age, Gender, Primary Condition     ├─ Procedures Performed          ├─ Discharge Disposition         
     └─ Baseline Comorbidity Index         └─ Medication Prescriptions      └─ Final Inpatient Cost (Rs.)      
                                                                            ▲
                                                                            │
                                                        [Canonical Prediction Point: AT DISCHARGE]
                                                        Only variables known at or prior to discharge are 
                                                        eligible for prospective readmission risk modeling!
`
