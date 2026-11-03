# Data Dictionary
### `data/hospital/hospital_data.csv` — the dataset the live dashboard serves

> 984 rows × 10 columns · one row per synthetic patient record · **synthetic demo data**
> (the committed CSV is the analytical source; its original generation process is not established here)

---

## Source columns

| # | Column | Type | Allowed values / range | Description | Example | Known quality notes | Model usage |
|---|---|---|---|---|---|---|---|
| 1 | `Patient_ID` | int | 1–1000 observed, unique | Primary key | 512 | None — uniqueness & completeness CI-tested | Not a feature |
| 2 | `Age` | int | 25–78 observed | Patient age in years | 64 | Plausible range enforced by tests | **Feature** |
| 3 | `Gender` | string | Female / Male | Patient gender | Female | Base-rate note: readmission differs sharply by gender in this data (43.9% F vs 7.4% M — see `reports/fairness_check.md`) | **Feature** (encoded) |
| 4 | `Condition` | string | 15 conditions (below) | Primary diagnosis | Heart Disease | Near-deterministic relationship with Readmission (honesty audit) | **Feature** (encoded) |
| 5 | `Procedure` | string | 15 procedures | Treatment delivered | Angioplasty | **1:1 mapping with Condition** — documented, CI-tested; acts as a correlated proxy in the model | **Feature** (encoded) |
| 6 | `Cost` | int | ₹100–₹25,000 observed | Episode cost (INR-labelled synthetic units) | 4,500 | Positive values enforced; follows the condition pathway | **Feature** |
| 7 | `Length_of_Stay` | int | 1–76 days observed | Inpatient days | 5 | ≥1 enforced by tests | **Feature** |
| 8 | `Readmission` | string | Yes / No | **Model target.** Recorded Yes/No readmission flag; timing is not established | Yes | Near-deterministic given Condition (11/15 conditions readmit at >95% or <5%) — the central honesty caveat | **Target** |
| 9 | `Outcome` | string | Recovered / Stable observed | Recorded synthetic outcome label | Recovered | Valid categories CI-tested | Not a feature (post-outcome) |
| 10 | `Satisfaction` | int | 1–5 | Recorded synthetic satisfaction score | 4 | Range enforced by tests | Not a feature |

## The 15 conditions
Heart Disease · Diabetes · Fractured Arm · Stroke · Cancer · Hypertension ·
Appendicitis · Fractured Leg · Heart Attack · Allergic Reaction ·
Respiratory Infection · Prostate Cancer · Childbirth · Kidney Stones ·
Osteoarthritis

## Runtime-derived fields (not stored)

| Field | Produced by | Description |
|---|---|---|
| `Patient_Code` | `utils/hospital_data.py` | Display code derived from condition and row order (`PT` + condition code + sequence, e.g. `PTDB0001`); not a persistent identifier across reordered or changed source data |
| `Gender_enc`, `Condition_enc`, `Procedure_enc` | `utils/ai_risk.py` (LabelEncoders persisted in `models/readmission/encoders.joblib`) | Integer encodings for the RandomForest — fitted once at training, reused at scoring |

## Design characteristics an analyst must know (documented, not hidden)

1. **Readmission is condition-driven by construction** — each condition has an observed near-fixed readmission pattern. This helps explain why the model's
   AUC ≈ 0.99 is a dataset property, quantified in `reports/model_honesty.md`
   (a condition-only lookup scores about 0.93 here; this is not a clinical validation).
2. **Gender base-rate disparity** — Female patients in this dataset readmit at
   43.9% vs Male 7.4% (condition mix differs by gender). Full analysis:
   `reports/fairness_check.md`.
3. **Procedure ↔ Condition is 1:1** — correlated features; SHAP attribution
   across them is diffuse (see `reports/cohort_shap.md`).

## Related files
- Quality checks pinning this file: `tests/test_hospital_data_quality.py`
- Documented issues report: `reports/data_quality_report.md`
- Legacy synthetic FHIR bundle (prototype, not served): `data/synthetic/bundle.json`
