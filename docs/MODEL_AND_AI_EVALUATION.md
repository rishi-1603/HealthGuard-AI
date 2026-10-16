# MODEL & AI EVALUATION — HealthGuard

## Model
Random forest readmission classifier (6 features: age, gender, condition,
procedure, cost, length of stay) with class_weight balancing.

## Evaluation chain
| Stage | Method | Finding |
|---|---|---|
| Discrimination | ROC-AUC test | 0.9923 |
| Honesty | baselines probe | lookup 0.929; demographics-only 0.985 -> determinism |
| Calibration | slope, Brier, reliability | slope 1.434 (under-confident) -> isotonic Brier 0.0187->0.0102 |
| Decision value | decision-curve analysis | model beats treat-all at 7/7 thresholds |
| Subgroups | bootstrap 95% CIs + refusal rules | thin bands (0-2 positives) report NOTHING |
| Time | temporal protocol on synthetic dates | inside noise band; protocol is the deliverable |
| Errors | 197-case catalog | 2 errors, both in generator coin-flip conditions |
| Explanations | SHAP local + cohort | faithful to model; model faithful to generator (stated) |

## The point of this project (for interviews)
Not "predicting readmissions" — it is the full evaluation discipline on a
transparent synthetic world: leakage probes, calibration, DCA, subgroup CIs with
refusal, temporal protocol, and an error catalog that explains the metric.

## Limitations (standing, restated in README + model card)
Synthetic data; no clinical validity; SHAP values explain the model, not patient
outcomes; Q&A grounds answers in project data only.

## Interview defense
"Is 0.99 AUC impressive?" · "How do you validate on synthetic data?" · "How do
you handle tiny subgroups?" (reports/INTERVIEW_PREP.md)
