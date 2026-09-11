# Data Dictionary
### `data/hospital/hospital_data.csv` — the dataset the live dashboard serves

> 984 rows × 10 columns · one row per patient episode · **synthetic demo data**
> (generated with fixed seeds; every statistic in the project is reproducible)

---

## Source columns

| # | Column | Type | Allowed values / range | Description | Example | Known quality notes | Model usage |
|---|---|---|---|---|---|---|---|
| 1 | `Patient_ID` | int | 1–984, unique | Primary key | 512 | None — uniqueness & completeness CI-tested | Not a feature |
| 2 | `Age` | int | 18–90 (observed) | Patient age in years | 64 | Plausible range enforced by tests | **Feature** |
| 3 | `Gender` | string | Female / Male | Patient gender | Female | Base-rate note: readmission differs sharply by gender in this data (43.9% F vs 7.4% M — see `reports/fairness_check.md`) | **Feature** (encoded) |
| 4 | `Condition` | string | 15 conditions (below) | Primary diagnosis | Heart Disease | Near-deterministic relationship with Readmission (honesty audit) | **Feature** (encoded) |
| 5 | `Procedure` | string | 15 procedures | Treatment delivered | Angioplasty | **1:1 mapping with Condition** — documented, CI-tested; acts as a correlated proxy in the model | **Feature** (encoded) |
| 6 | `Cost` | int | ₹100–₹20,000 (observed) | Episode cost (INR-labelled synthetic units) | 4,500 | Positive values enforced; follows the condition pathway | **Feature** |
| 7 | `Length_of_Stay` | int | 1–30 days (observed) | Inpatient days | 5 | ≥1 enforced by tests | **Feature** |
| 8 | `Readmission` | string | Yes / No | **Model target.** Readmitted within the dataset window | Yes | Near-deterministic given Condition (11/15 conditions readmit at >95% or <5%) — the central honesty caveat | **Target** |
| 9 | `Outcome` | string | Recovered / Stable / Deceased | Discharge outcome | Recovered | Valid categories CI-tested | Not a feature (post-outcome) |
| 10 | `Satisfaction` | int | 1–5 | Patient satisfaction score | 4 | Range enforced by tests | Not a feature |

## The 15 conditions
Heart Disease · Diabetes · Fractured Arm · Stroke · Cancer · Hypertension ·
Appendicitis · Fractured Leg · Heart Attack · Allergic Reaction ·
Respiratory Infection · Prostate Cancer · Childbirth · Kidney Stones ·
Osteoarthritis

## Runtime-derived fields (not stored)

| Field | Produced by | Description |
|---|---|---|
| `Patient_Code` | `utils/hospital_data.py` | Stable display code (`PT` + condition code + sequence, e.g. `PTDB0001`) |
| `Gender_enc`, `Condition_enc`, `Procedure_enc` | `utils/ai_risk.py` (LabelEncoders persisted in `models/readmission/encoders.joblib`) | Integer encodings for the RandomForest — fitted once at training, reused at scoring |

## Design characteristics an analyst must know (documented, not hidden)

1. **Readmission is condition-driven by construction** — the generator assigns
   each condition a near-fixed readmission behaviour. This is why the model's
   AUC ≈ 0.99 is a dataset property, quantified in `reports/model_honesty.md`
   (a no-ML condition lookup scores 0.93; real clinical models reach 0.65–0.75).
2. **Gender base-rate disparity** — Female patients in this dataset readmit at
   43.9% vs Male 7.4% (condition mix differs by gender). Full analysis:
   `reports/fairness_check.md`.
3. **Procedure ↔ Condition is 1:1** — correlated features; SHAP attribution
   across them is diffuse (see `reports/cohort_shap.md`).

## Related files
- Quality checks pinning this file: `tests/test_hospital_data_quality.py`
- Documented issues report: `reports/data_quality_report.md`
- Legacy synthetic FHIR bundle (prototype, not served): `data/synthetic/bundle.json`
