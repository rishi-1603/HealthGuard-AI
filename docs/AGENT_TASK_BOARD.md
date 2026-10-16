# AGENT TASK BOARD — HealthGuard
### Completed work items. Rule: script + pinned test + limitation + interview question.

| # | Task | Output | State |
|---|---|---|---|
| 1 | Synthetic hospital data + quality checks | data/hospital/hospital_data.csv (984x10), test_hospital_data_quality.py | Done |
| 2 | Readmission model + SHAP (per-patient + cohort) | models/readmission/, scripts/cohort_shap_analysis.py | Done |
| 3 | Model honesty audit (leakage probe) | reports/model_honesty.md (lookup baseline 0.929 vs 0.994) | Done |
| 4 | Fairness check | scripts/fairness_check.py + reports/fairness_check.md | Done |
| 5 | Calibration + decision-curve analysis | scripts/calibration_decision_curve.py + reports | Done |
| 6 | Subgroup bootstrap CIs + refusal rules | same report (thin bands refuse) | Done |
| 7 | Temporal validation protocol | scripts/temporal_validation.py + reports | Done |
| 8 | Error catalog (determinism map) | reports/error_analysis.md | Done |
| 9 | Grounded Q&A layer (refuses ungroundable) | app + test_qa_grounding.py | Done |
| 10 | Ops/monitoring layer | test_ops_layer.py | Done |
| 11 | Metric registry + MODEL_CARD updates | data/metrics.json, models/readmission/MODEL_CARD.md | Done |
| 12 | Release gates A-E | docs/RELEASE_GATES.md | Done |
