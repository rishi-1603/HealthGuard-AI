# SQL Analytics — Readmission Cost Burden

SQLite built from `database/schema.sql`, loaded from `data/hospital/hospital_data.csv` (984 patients).

## Headline

| Measure | Value |
|---|---|
| Readmitted patients | **264** (26.83%) |
| Share of total cost held by readmitted patients | **43.8%** |
| Average cost — readmitted | ₹13,650 |
| Average cost — not readmitted | ₹6,431 |
| Cost premium | **+112.3%** |
| Highest readmission-cost condition | Heart Attack (₹1,206,000) |

## SQL ↔ pandas reconciliation

**15/15 checks passed.** All agree.

The same logic is implemented twice — once in SQL (`sql/01_...sql`) and once in pandas (`scripts/sql_analytics.py::run_pandas`). Two independent implementations agreeing is the cheapest available proof neither has a bug. A mismatch fails the build; it is never downgraded to a warning.

## Queries in this layer

| # | Query | Question it answers |
|---|---|---|
| 1 | `cost_burden` | How much of our cost sits with readmitted patients? |
| 2 | `cost_premium` | What does one readmission cost on average? |
| 3 | `by_condition` | Which conditions drive the readmission cost? |
| 4 | `by_age_band` | At what age does readmission risk rise? |
| 5 | `cost_per_day` | Which conditions consume the most resource per day? |
| 6 | `by_outcome` | Does a good outcome cost less? |
| 7 | `by_gender` | Are outcomes and costs equal across genders? |

## Reproduce

```bash
python scripts/sql_analytics.py
```
