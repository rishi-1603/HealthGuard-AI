# Assumptions & Limitations
### What HealthGuard AI can and cannot tell you

> An interviewer WILL ask these questions. Answering them first is maturity,
> not weakness.

---

## 1. Data limitations
- **The dataset is synthetic** (984 rows, 10 columns). It behaves like a
  hospital outcomes table but was generated, not collected. No real patients,
  no real costs, no real outcomes.
- **Only 10 columns.** No comorbidities, medications, labs, prior admissions,
  social determinants, or post-discharge follow-up — the features real
  readmission models need. Cost and LOS here are crude proxies, not case-mix
  adjusted.
- **No temporal dimension.** One row per patient; no admission timeline, so
  no true cohort or time-to-readmission analysis is possible.

## 2. The model's headline number is NOT skill (read this)
- AUC ≈ 0.99 because **readmission is nearly deterministic given Condition**
  in this data (11 of 15 conditions readmit at >95% or <5%). A no-ML lookup
  table scores 0.93; demographics-only scores 0.985 (see
  `reports/model_honesty.md`).
- Real-world readmission prediction is a hard problem: published models
  typically achieve **AUC 0.65–0.75**. Anyone quoting ~0.99 on this task is
  either leaking the label or using synthetic data — here it is the latter,
  and it is documented.
- **What the model does demonstrate:** the full MLOps-style system — training
  script, versioned artifacts, per-patient scoring, SHAP explainability,
  dashboard integration, reproducible metrics, and honest evaluation.

## 3. Correlation ≠ causation
Condition/cost/LOS associations with readmission describe the data
generation, not causal care-pathway effects. No causal claim anywhere in the
product should be believed on this data.

## 4. Q&A limitations
- The grounded layer answers a fixed set of question shapes (readmission
  rates, costs, counts, satisfaction, LOS, outcomes) — it is not general NLP.
- The Gemini fallback is clearly labelled and best-effort; it is grounded in
  current-filter statistics but can still produce generic advice. It is
  never used for numbers when the grounded layer can answer.

## 5. What CANNOT be concluded
- Anything clinical. The disclaimer is prominent because it is meant: **not
  for diagnosis, treatment, or clinical decision-making.**
- That the feature importance ranking reflects real clinical drivers — it
  reflects the synthetic generator's logic.
- That the dashboard's risk tiers (LOW/WATCH/HIGH) would generalize to any
  real population.

## 6. Assumptions we make explicitly
- Patient rows are independent (no repeated admissions per patient).
- The committed dataset is the single source of truth; all tests pin to it.
- 984 rows is the documented size; any change fails CI deliberately.
