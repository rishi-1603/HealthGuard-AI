# Executive Summary
### HealthGuard AI — Hospital Outcomes Intelligence Dashboard
*Prepared for: Hospital Operations / Quality leadership · Dataset: 984-patient synthetic outcomes*

> **Read me first:** One page, non-technical. Full methodology in
> `reports/methodology.md`. **Caveat:** the dataset is synthetic (demo/portfolio);
> numbers illustrate the *system*, they are not real clinical performance.

---

## 1. What was the problem?
Operations leadership could not see, in one place: **who our patients are, what
their outcomes and costs look like, and which patients are likely to be
readmitted** — and when they did get numbers, they couldn't ask follow-up
questions without waiting on an analyst.

## 2. What does the product do?
A live dashboard (Streamlit) that turns one 984-row outcomes dataset into:
- **KPI panel** — volume, age, cost, length of stay, readmission, recovery, satisfaction
- **Condition & demographic analytics** — where volume and cost concentrate
- **Per-patient risk scoring with explanations** — a RandomForest readmission
  score plus a "why this score?" SHAP factor breakdown
- **Grounded Q&A** — ask in plain English; answers computed from the data, not
  generated prose

## 3. Top findings in the data (illustrative — synthetic)
1. **Readmission is heavily condition-concentrated** — Heart Attack and Heart
   Disease account for the overwhelming majority of readmissions; most other
   conditions readmit at ~0%.
2. **Cost and length of stay track condition severity** — the expensive,
   long-stay pathways are the same ones that readmit.
3. **Overall readmission rate is ~26.8%**, driven almost entirely by two
   conditions.

## 4. Biggest risk / most important caveat
**The readmission model's AUC of ~0.99 is a property of the synthetic data, not
predictive skill.** In this dataset, readmission is essentially determined by
the condition pathway (see `reports/model_honesty.md` for the quantified
audit: a no-ML condition lookup scores 0.93; real clinical models score
0.65–0.75). The model demonstrates the *scoring-and-explanation system*; it
must not be read as clinical accuracy.

## 5. What should leadership take from this?
- The **dashboard + grounded Q&A pattern** is production-appropriate: every
  number is traceable, no LLM fabrication.
- The **explainability layer** (per-patient "why this score?") is the right
  UX pattern for any high-stakes scoring system — adopt it for real models.
- On real data, the same pipeline would report honest (much lower) AUCs, and
  the condition-concentration insight would become an actual care-pathway
  finding worth acting on.

## 6. What to monitor
- Data quality checks (25 automated tests) — all green in CI
- Model-vs-metrics consistency (retrain reproduces recorded AUC)
- Q&A grounding tests — answers always match dataset aggregates
