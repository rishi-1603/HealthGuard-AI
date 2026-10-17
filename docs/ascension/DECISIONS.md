# Ascension Log — HealthGuard AI

## U1 — SQL analytics layer (the structural gap vs its siblings)

**Status:** done — 35 tests, 56 baseline + 35 = 91 passing

### What was missing
`database/schema.sql` was a **one-line stub** (`audit_logs` only) and there was no
SQL analytics anywhere in the repo — while the other two portfolio projects both
carry a documented SQL layer with pandas parity. This closes that gap.

### What was built
| File | Purpose |
|---|---|
| `database/schema.sql` | Full analytic schema: `patient_encounters` fact table with CHECK constraints, 4 indexes, 3 dimension views (`dim_condition`, `dim_age_band`, `dim_outcome`). The original `audit_logs` stub is preserved. |
| `sql/01_readmission_cost_burden.sql` | 7 documented business queries, each labelled with the question it answers |
| `scripts/sql_analytics.py` | Builds SQLite from the schema, runs the queries, recomputes in pandas, **reconciles the two** |
| `tests/test_sql_layer.py` | 35 tests: schema constraints, query execution, parity, published headlines |

### Reconciliation policy
The same logic is implemented **twice** — SQL and pandas — and compared. A mismatch
**fails the build**; it is never downgraded to a warning. Only 1e-4 relative rounding
tolerance is allowed. Current state: **15/15 checks pass.**

### Verified against the published story
The layer reproduces the README's figures exactly, so SQL cannot drift from it:
- 264 readmitted patients (26.83%), holding **43.8%** of total cost
- ₹13,650 vs ₹6,431 per patient (**+112.3%** premium)
- Gender base rates **F 43.9% / M 7.4%** — the fairness disclosure, now queryable in SQL

### Bugs caught during this work (disclosed)
1. Column naming drifted between the SQL loader and the pandas path (`Condition` vs
   `condition`) — caught immediately by the KeyError. Fixed by centralising on one
   canonical naming in `prepare()`.
2. The reconciler assumed the SQL alias `avg_cost` where query 1 returns
   `avg_cost_per_patient`. Now mapped explicitly rather than by coincidence.
3. An early `.mean()` call on the `Readmission` string column looked like a data
   corruption bug. It was not — the data is clean (720 No / 264 Yes). The bug was mine.

### Regression check
`pytest tests/` → **91 passed**. All 56 original tests untouched and green.
