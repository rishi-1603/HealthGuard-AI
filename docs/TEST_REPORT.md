# TEST REPORT — HealthGuard
### Last full run: 2026-10-18 — 132/132 passed

| Suite | Pins |
|---|---|
| test_smoke.py | app boots, imports resolve |
| test_hospital_data_quality.py | dataset schema + generator invariants |
| test_readmission_model.py | training + core metrics |
| test_cohort_shap.py | SHAP analysis outputs |
| test_fairness_check.py | fairness metrics + report |
| test_evaluation_depth.py | calibration + DCA + temporal metrics JSONs (12 tests) |
| test_qa_grounding.py | grounded answers / refusals |
| test_ops_layer.py | ops panel behavior |
| test_data_quality_report.py | report regeneration |

## Pinning style
Scripts write reports/*_metrics.json; tests pin values with cross-version-safe
tolerances and assert directional invariants (isotonic beats raw on Brier; model
beats treat-all on net benefit). Subgroup refusal behavior is itself tested.

## CI
GitHub Actions: calibration_decision_curve.py + temporal_validation.py -> pytest.
Matplotlib is OPTIONAL (lean Streamlit Cloud requirements) — figures degrade,
metrics do not. Status at audit: **success**.

## Not covered (disclosed)
No clinical validation (impossible on synthetic data); no browser automation;
no load tests.
