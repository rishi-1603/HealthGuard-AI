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

---

## U2 — Program Simulator (Day 2)

### The question
The SQL layer proved readmissions cost +112% more. The CFO's next question is:
**"If we fund a prevention program, who do we enroll and when does it pay for
itself?"**

### What was built
| File | Purpose |
|---|---|
| `scripts/program_simulator.py` | Prices 5 enrollment strategies with an explicit cost model; break-even efficacy per strategy; sensitivity grid; equity audit of the targeting rule |
| `tests/test_program_simulator.py` | 14 tests pinning every published number + economic identities |
| `reports/program_simulator.json/.md` | The decision artifact |

### Verified findings (pinned by tests)
- **Enrolling everyone loses ₹10.39 lakh** (break-even efficacy 53% — implausible)
- **Recommended: top-quartile by stratum risk (246 patients)** — net **₹2.98 lakh**, ROI 0.61, **break-even efficacy only 15.6%**
- Targeting rule: Laplace-smoothed historical readmission rate of each
  (Condition × Age-band) stratum — auditable in one sentence per patient
- **Sensitivity is honest**: at 10% efficacy / ₹2,000 cost, EVERY strategy
  loses money — the report prints that instead of hiding it
- **Equity disclosure**: the rule concentrates enrollment on female patients
  (86.2% vs 53.3% of population) because the dataset's readmission rate is far
  higher for women — printed as a policy trade-off, not hidden

### Bugs caught during this work (disclosed)
1. The break-even identity test initially demanded exact equality against JSON
   values rounded to 4 dp — false failure. Fixed with an explicit 1% tolerance
   and a comment explaining why.

### Regression check
`pytest tests/` → **105 passed**. All 91 original tests untouched and green.

---

## U3 — Fairness Trade-off Curve (Day 2)

### The question
fairness_check.py disclosed the gender error-rate gap. Disclosure is day one:
**can we reduce it, and what does that cost?**

### What was built
| File | Purpose |
|---|---|
| `scripts/fairness_tradeoff.py` | 19-point threshold sweep (0.05→0.95) with per-group TPR/FPR/selection rates; two priced mitigations; impossibility disclosure |
| `tests/test_fairness_tradeoff.py` | 10 tests pinning every number + math identities + the impossibility pin |
| `reports/fairness_tradeoff.json/.md` | The decision artifact |

### Verified findings (pinned by tests)
- Deployed t=0.50: recall 99.2%, **TPR gap 0.0588** (F 1.00 vs M 0.941), demographic-parity gap 0.375
- **Mitigation A** (single threshold t=0.85): TPR gap **0.0284** (halved) at
  Δrecall −2.65pp — the price of fairness, in one number
- **Mitigation B** (group thresholds F 0.85 / M 0.05): TPR gap **0.001** — but
  **FPR gap jumps to 0.1082** and precision falls to 83.4%
- **The impossibility is pinned as a test**: closing the TPR gap necessarily
  re-opens the FPR gap when base rates differ (43.9% vs 7.4%) — the
  Chouldechova/Kleinberg result visible in our own numbers. The report says
  this out loud instead of selling mitigation B as a free lunch.

### Bugs caught during this work (disclosed)
1. None in code; one in framing: the first draft of the report called
   mitigation B "near-perfect fairness" — corrected to disclose the FPR-gap
   trade-off before commit.

### Regression check
`pytest tests/` → **115 passed**. All previous tests untouched and green.

---

## U4 — Grounded-QA Benchmark + Real-Data Validation Track (Day 2 final)

### What was built
| File | Purpose |
|---|---|
| `evals/qa_benchmark.json` | 8 answerable (runtime recompute specs), 3 out-of-scope, 3 false-premise traps |
| `scripts/qa_eval.py` | Correct-refusal scoring: grounded accuracy, refusal accuracy, trap accuracy, fabrication count — the e-commerce eval lesson applied |
| `scripts/realdata_validation.py` | Re-runs the fairness + intervention-economics METHODS on real patients (UCI Heart Disease, 303 rows, committed) |
| `data/external/heart_disease.csv` | Committed real dataset (UCI ID 45, CC BY 4.0) + source README |
| `tests/test_qa_eval.py`, `tests/test_realdata_validation.py` | 17 pins |

### The eval caught a REAL product bug (and the fix is shipped)
**False-premise questions were confidently answered.** "What is the readmission
rate for lung cancer?" returned the OVERALL rate with ok=true — a confident
answer to a question the data cannot answer. Worse, "lung cancer" fuzzy-matched
the `Cancer` condition via substring. Shipped fix in `simple_qa.py`:
1. questions naming a condition the dataset does not contain now REFUSE and
   list available conditions;
2. condition matching for lookups requires the phrase to NAME the condition
   (or a synonym) — 'lung cancer' no longer matches 'Cancer'.

### Verified findings (pinned by tests)
- **QA eval after fix: 8/8 grounded · 3/3 refusals · 3/3 traps · 0 fabrications → PASS**
- **Real-data transfer (UCI, 303 patients):**
  - Gender TPR gap at deployed threshold: **0.078** — the gap structure TRANSFERS
  - Minimax post-processing (F t=0.45 / M t=0.60) reaches TPR gap 0.0007 / FPR
    gap 0.010 — the mitigation METHOD transfers
  - **Honest negative**: the impossibility result that dominated the synthetic
    set did NOT reproduce here — disclosed with the reason (it pins CALIBRATED
    scores with unequal base rates; this set admits an approximate equalized-odds
    point). Negative results are first-class claims in the verdict table.
  - Economics: enroll-all **−₹1.18L**, top-quartile **+₹0.47L**, above-baseline
    **+₹0.65L** — targeting beats blanket on REAL outcomes

### Regression check
`pytest tests/` → **132 passed**.

---

## U5 — README & Presentation Polish (consistency sweep)

### What changed
- Two charts generated FROM the committed JSON artifacts:
  `docs/program_simulator_strategies.png` (blanket enrollment loses ₹10.4L —
  targeting wins) and `docs/fairness_tradeoff_gaps.png` (the impossibility:
  closing the TPR gap re-opens the FPR gap).
- New README section: "Decision layer: intervention economics (program simulator)".
- Stale count fixed: README claimed 56 tests → corrected to 132, with tests badge.
- DECISIONS.md bug-log pointer added to the governance line.
