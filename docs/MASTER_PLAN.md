# MASTER PLAN — HealthGuard AI
### Portfolio project · week of 2026-10-15 · status: COMPLETE

## Objective
An explainable readmission-risk platform over a synthetic hospital dataset
(984 patients): trained model, per-patient SHAP explanations in the UI, cohort
driver analysis, grounded Q&A that refuses unanswerable questions — and a
model-honesty audit that proves the headline AUC is synthetic-data determinism.

## Scope
**In:** data pipeline, readmission model, SHAP explainability, fairness check,
calibration + decision curves, temporal validation protocol, error catalog,
Streamlit dashboard, Docker packaging.
**Out:** clinical use of any kind, real patient data, treatment recommendations.

## Timeline
| Day | Plan | Status |
|---|---|---|
| D1 | Baseline + honesty audit + evidence layer | Done |
| D5 (Oct 19) | Calibration, DCA, temporal validation, subgroup CIs | Done |
| D6 | Error catalog, metric registry, interview depth | Done |
| D7 | Resume/interview/release kit | Done |

## Success criteria — all met
- Calibration chart + Brier + slope with isotonic fix: reports/calibration_and_decision_curve.md
- Decision-curve analysis across thresholds: 7/7 model wins (0.10-0.50)
- Subgroup metrics with bootstrap CIs + refusal rules: same report
- Temporal validation protocol: reports/temporal_validation.md
- 132/132 tests green (verified 2026-10-18)

## Key links
- Live demo: https://healthguard-ai-cyl2viwrsdrrff7pig7u6c.streamlit.app/
- Honesty audit: reports/model_honesty.md
- Calibration + DCA: reports/calibration_and_decision_curve.md
- Release gates: docs/RELEASE_GATES.md
