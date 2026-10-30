# Independent data, SQL and statistical validation

Audit date: 2026-10-30. Calculations below were rebuilt from CSVs without importing project metric functions, then compared with PostgreSQL execution. Reproduction scripts and detailed machine output are included in the external audit evidence pack.

## Independent calculations
```json
{
  "patient_records": 984,
  "unique_patient_ids": 984,
  "readmitted": 264,
  "readmission_pct": 26.8293,
  "readmission_wilson_95_interval": [
    0.2415,
    0.2968
  ],
  "mean_cost": 8367.4797,
  "mean_los": 37.6636,
  "recovered_pct": 60.061,
  "readmitted_mean_cost": 13649.6212,
  "nonreadmitted_mean_cost": 6430.6944,
  "cost_premium_pct": 112.2573,
  "readmitted_cost_share_pct": 43.7658,
  "gender_base_rates": {
    "Female": 43.8931,
    "Male": 7.3913
  },
  "clinical_scope": "One synthetic patient row; no validated 30-day admission timeline; no causal avoided-cost inference."
}
```

## Actual PostgreSQL execution
Native project is SQLite. Explicit disposable PostgreSQL port: CREATE VIEW IF NOT EXISTS -> CREATE OR REPLACE VIEW; REAL -> NUMERIC. Original analytical SELECTs unchanged. Not a native PostgreSQL claim.

| File | Executed statements | Failures |
|---|---:|---:|
| schema (explicit port) | 9 | 0 |
| 01_readmission_cost_burden.sql | 7 | 0 |

## Runtime-specific external fairness check
The pinned sklearn 1.9.0 report records the runtime and recall-constrained threshold grid. An independent implementation agrees with F=.25/M=.35, recall .9209 and worst TPR/FPR gap .0085. Prior .45/.60 pins came from the earlier runtime and were not reproducible after direct regeneration.
The Wilson interval describes sampling uncertainty on the supplied rows, not uncertainty about real hospital effectiveness. There is no validated 30-day readmission timeline, and cost association is not avoided causal cost.
