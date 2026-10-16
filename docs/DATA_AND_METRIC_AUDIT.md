# DATA & METRIC AUDIT — HealthGuard

## Data provenance
- **Synthetic hospital dataset** (scripts/generate_data.py, seeded): 984 patients x
  10 columns. Condition nearly determines the readmission label (see the
  determinism map in reports/error_analysis.md). Dates are synthetic and
  independent of outcomes (disclosed where temporal validation uses them).

## Metric registry (data/metrics.json — canonical)
| Metric | Definition | Pinned value |
|---|---|---|
| ROC-AUC | random split, test slice | 0.9923 |
| Lookup baseline | condition-rate lookup AUC | 0.929 (honesty audit) |
| Demographics-only | model without condition/procedure | 0.985 (honesty audit) |
| Calibration slope | raw RF | 1.4341 (UNDER-confident, class_weight artifact) |
| Brier | raw -> isotonic | 0.0187 -> 0.0102 |
| Net benefit | DCA vs treat-all | model wins 7/7 thresholds (0.10-0.50) |
| Temporal split AUC | time-based holdout | 0.9963 (inside noise band [0.9934, 1.0]) |
| Subgroup discipline | min n=15 and n_pos=5 else REFUSE | 18-30 and 31-45 bands refuse |

## Audit findings (published everywhere it matters)
1. The headline AUC is data structure, not clinical skill (honesty audit).
2. A perfect subgroup AUC on 2 positives is noise — those bands report nothing.
3. Errors live exactly where the generator is stochastic (error catalog).

## Reproducibility
Seeded generation, pinned dependencies, CI regenerates calibration + temporal
artifacts before tests; test_evaluation_depth.py pins both metrics JSONs.
