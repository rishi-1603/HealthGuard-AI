# Data Dictionary
### `data/hospital/hospital_data.csv` — the dataset the live dashboard serves

> 984 rows × 10 columns · one row per patient encounter · **synthetic demo data**

| Column | Type | Values / Range | Description |
|---|---|---|---|
| `Patient_ID` | int | 1–984, unique | Primary key |
| `Age` | int | plausible adult range | Patient age in years |
| `Gender` | string | Male / Female | Patient gender |
| `Condition` | string | 15 conditions (see below) | Primary diagnosis |
| `Procedure` | string | 15 procedures | 1:1 with Condition (see honesty audit) |
| `Cost` | int | > 0, INR-labelled (synthetic units) | Episode cost |
| `Length_of_Stay` | int | ≥ 1, days | Inpatient days |
| `Readmission` | string | Yes / No | **Model target.** Nearly deterministic given Condition in this data |
| `Outcome` | string | Recovered / Stable / Deceased | Discharge outcome |
| `Satisfaction` | int | 1–5 | Patient satisfaction score |

## Conditions (15)
Heart Disease, Diabetes, Fractured Arm, Stroke, Cancer, Hypertension,
Appendicitis, Fractured Leg, Heart Attack, Allergic Reaction,
Respiratory Infection, Prostate Cancer, Childbirth, Kidney Stones,
Osteoarthritis.

## Derived fields (runtime, not stored)
- `Patient_Code` — `PT` + condition code + sequence (e.g. `PTDB0001`), assigned
  deterministically at load time
- `*_enc` — label encodings for Gender/Condition/Procedure, fitted at training
  time and persisted in `models/readmission/encoders.joblib`

## Readmission by Condition (the determinism that drives the honesty audit)
| Condition | Readmit rate |
|---|---|
| Heart Attack | 100% |
| Heart Disease | ~98.5% |
| Appendicitis, Cancer, Fractured Arm, Stroke | ~50% |
| Diabetes | ~1.5% |
| All others (9 conditions) | 0% |

## Related files
- Model artifacts & metrics: `models/readmission/`
- Legacy FHIR synthetic bundle: `data/synthetic/bundle.json` (prototype, not served)
- Quality checks pinning this file: `tests/test_hospital_data_quality.py`
