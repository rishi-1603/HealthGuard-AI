# Analytics Questions Map
### Every question the dashboard answers → where it's answered → how it's verified

> 15 questions an interviewer or stakeholder might ask, each mapped to the dashboard
> section, the method, and the test/report that pins it.

| # | Question | Where it's answered | Method | Verified by |
|---|---|---|---|---|
| 1 | How many patients are in scope, and what's the readmission rate? | Executive Overview KPI strip | Direct aggregation | `data/metrics.json` (984 patients, 26.8%) + data-quality tests |
| 2 | What does readmission cost the operation? | Executive Overview — cost-burden panel | Conditional means and cost share | `metrics.json` (₹13,650 vs ₹6,431, +112%, 43.8% share) |
| 3 | Is the cost difference causal? | Cost panel caveat + reports | — (explicitly refused) | `reports/assumptions_and_limitations.md` (association only) |
| 4 | Which conditions have the highest readmission rates? | Clinical Analytics — readmission by condition | Group-wise rates | `reports/model_honesty.md` documents the extreme split (11/15 >95% or <5%) |
| 5 | Which factors drive risk across the whole cohort? | Clinical Analytics — cohort SHAP panel | SHAP summary over all patients | `reports/cohort_shap.md` + `tests/test_cohort_shap.py` |
| 6 | Why does *this* patient have this score? | Patient Intelligence — per-patient SHAP | TreeExplainer attributions | Model validity tests + SHAP panel |
| 7 | Does the model perform evenly across age groups and gender? | Reports (linked from README) | Slice metrics (AUC/precision/recall) | `reports/fairness_check.md` + `tests/test_fairness_check.py` |
| 8 | Can the headline AUC be trusted? | 'About the AI risk model' expander + reports | Baseline comparisons (lookup 0.929, demographics 0.985) | `scripts/model_honesty_audit.py` runs in CI |
| 9 | What's the relationship between cost and length of stay? | Clinical Analytics — cost vs LOS scatter | Correlation visualization | Dashboard renders from validated dataset |
| 10 | How does LOS vary by condition/procedure? | Clinical Analytics — box plots | Group distributions | Data-quality invariants |
| 11 | What does the readmission risk distribution look like? | Executive/clinical risk distribution chart | Score histogram + bands | Model output tests (valid probabilities) |
| 12 | How do I ask a question in plain English? | AI Assistant tab | Grounded Q&A: numbers computed from dataset, LLM phrases only | `tests/test_qa_grounding.py` (answers == dataset aggregates) |
| 13 | What happens if I ask something outside the data? | AI Assistant tab | Refusal instead of guessing | Refusal-path tests in `test_qa_grounding.py` |
| 14 | Is this safe to use clinically? | UI footer + README + model card | — (explicit disclaimer) | `models/readmission/MODEL_CARD.md` |
| 15 | Can I reproduce all of this? | README quickstart + Makefile | CI sequence: generate → audit → train → test | GitHub Actions runs it on every push |

**How to use this in an interview:** pick the question, name the dashboard section,
state the verified number, then state its caveat. That sequence — answer, evidence,
limitation — is the habit this project is designed to demonstrate.
