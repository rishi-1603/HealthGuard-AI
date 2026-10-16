# FEATURE SPECIFICATIONS — HealthGuard

| Feature | Input | Output | Acceptance (tested) |
|---|---|---|---|
| Readmission risk model | 6 features | calibrated-ready probabilities | metrics pinned (test_readmission_model) |
| Per-patient SHAP | patient row | local explanation in UI | cohort/local consistency (test_cohort_shap) |
| Cohort driver analysis | model + cohort | ranked global drivers | report regenerated + pinned |
| Model honesty audit | baselines | determinism findings | lookup 0.929 / demo-only 0.985 documented |
| Fairness check | protected attributes | group metrics | test_fairness_check |
| Calibration + isotonic | fit/cal/test 64/16/20 | slope, Brier, reliability | 1.4341 raw / Brier 0.0187->0.0102 pinned |
| Decision-curve analysis | thresholds 0.10-0.50 | net benefit vs treat-all | 7/7 model wins pinned |
| Subgroup CIs | demographics | bootstrap 95% CIs | refusal rules tested (thin bands) |
| Temporal validation | synthetic dates | split comparison + noise band | 0.9963 vs 0.9923 pinned |
| Grounded Q&A | question | grounded answer or refusal | test_qa_grounding (0 ungrounded answers) |
| Ops layer | app events | monitoring view | test_ops_layer |

**Hard non-features:** clinical decision support, treatment advice, real-patient
data, "99% accurate clinical AI" claims of any kind.
