# Consolidated Baseline & Model Evaluation Matrix
**Held-Out Test Set:** 197 Patients (20% Stratified Split)  
**Target Label:** 30-Day All-Cause Readmission (Prevalence: 26.8%)

---

## 1. Multi-Model Benchmark Comparison

| Model Architecture | Features Utilized | ROC-AUC | PR-AUC | Brier Score | Calibration Error (ECE) | Sensitivity @ Top 25% Cutoff | Specificity @ Top 25% Cutoff |
|---|---|---|---|---|---|---|---|
| **1. Prevalence Baseline** | Constant (0.268) | 0.500 | 0.268 | 0.196 | 0.000 | 0.250 | 0.750 |
| **2. Condition-Only Lookup (No ML)** | Primary Condition | **0.929** | 0.842 | 0.068 | 0.042 | 0.887 | 0.890 |
| **3. Logistic Regression** | Demographics + Vitals + Condition | 0.948 | 0.885 | 0.052 | 0.035 | 0.924 | 0.912 |
| **4. Random Forest Challenger** | Full Feature Space (at Discharge) | 0.994* | 0.988* | 0.018* | 0.021* | 0.981* | 0.972* |

*\*Note: Reflected synthetic data structural rules as documented in SYNTHETIC_DATA_LIMITATIONS.md.*
