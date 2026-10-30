# Demographic Subgroup & Algorithmic Fairness Audit
**Audit Dimensions:** Gender (Male vs Female) and Age Bands (<50, 50-65, >65)

---

## 1. Subgroup Performance Breakdown

| Subgroup | Sample Size ($N$) | Readmission Prevalence | Model ROC-AUC | False Positive Rate | False Negative Rate |
|---|---|---|---|---|---|
| **Female** | 498 | 26.5% | 0.994 | 2.5% | 1.8% |
| **Male** | 486 | 27.2% | 0.994 | 2.8% | 2.0% |
| **Age < 50** | 312 | 18.2% | 0.991 | 1.9% | 2.4% |
| **Age 50-65** | 394 | 28.4% | 0.995 | 2.7% | 1.9% |
| **Age > 65** | 278 | 34.2% | 0.993 | 3.2% | 1.7% |

> **Fairness Finding:** The gender AUC parity gap is negligible (**0.000 to 0.006**). However, because synthetic generator distributions were balanced by design, true real-world algorithmic bias cannot be definitively evaluated without real-world EHR data.
