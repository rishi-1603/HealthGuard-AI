# Interview Preparation Pack
### HealthGuard AI — questions and answers based ONLY on the actual project

---

## Resume Bullets (verified numbers only)

- **Built an explainable readmission-risk pipeline over 984 synthetic patient records** (26.8% readmission rate) — RandomForest scoring, per-patient SHAP explanations in a live 4-tab dashboard, and CI-tested grounded Q&A that refuses to answer outside the dataset (44 automated tests).
- **Wrote a model-honesty audit that explains why the headline AUC of 0.994 is not skill**: a per-condition lookup baseline already reaches 0.929 and a demographics-only model 0.985, because the synthetic generator makes `Condition → Readmission` nearly deterministic (11/15 conditions >95% or <5%). Real clinical models score 0.65–0.75 — the audit, the UI, and the README all say so.
- **Quantified the operational cost of readmission in the dataset**: readmitted patients average ₹13,650 vs ₹6,431 for non-readmitted (+112%) and hold 43.8% of total cost — framed as association, not causation — plus cohort-level SHAP (which factors drive risk across all patients) and fairness slices (AUC/precision/recall by age group and gender).

## One-Line Description

An explainable healthcare-analytics platform: readmission risk scoring with per-patient SHAP, cohort-level driver analysis, fairness checks, grounded Q&A, and a model-honesty audit that shows exactly why its own headline metric is inflated.

## 5-Minute Presentation Script

**[30s] Business problem**
"Hospital readmissions are expensive and operationally painful. A hospital analytics team wants to know: which patients are at higher risk of coming back, why, and what the readmission problem costs them — without pretending a demo model is a clinical device."

**[60s] Data & methodology**
"The dataset is synthetic — 984 patients with age, gender, condition, procedure, cost, length of stay, and a readmission label — and I disclose that everywhere. I trained a RandomForest classifier on six features with a stratified holdout, then built three trust layers around it: per-patient SHAP explanations, cohort-level SHAP analysis, and a fairness check slicing metrics by age group and gender. The Q&A assistant computes every number from the dataset — it refuses questions it can't ground."

**[90s] The key finding — model honesty**
"The most important result is negative. The model reports AUC 0.994 — and that number is meaningless on its own. My honesty audit shows a trivial per-condition lookup table already scores 0.929, and a demographics-only model scores 0.985, because in this synthetic generator, condition almost determines the label — 11 of 15 conditions have readmission rates above 95% or below 5%. Real-world readmission models land at 0.65 to 0.75. So the deliverable is not the AUC — it's the system and the discipline to explain why the AUC can't be trusted."

**[60s] Business findings**
"On the operational side, readmitted patients average ₹13,650 versus ₹6,431 for everyone else — a 112% cost premium — and hold 43.8% of total cost while being 26.8% of patients. I frame that as association, not causation: costlier cases may be more complex and also more likely to be readmitted. The dashboard lets an analyst see which factors drive risk across the whole cohort, then drill into any single patient with a SHAP 'why this score?' panel."

**[60s] Limitations**
"Everything is synthetic, so metrics don't transfer to real patients. There's no temporal validation possible. The fairness slices demonstrate the method, not real-world fairness. And nothing here is a medical device — the UI footer, the README, and the reports all carry that disclaimer."

## 10 Business Questions

1. **What share of patients are readmitted?** 264 of 984 (26.8%).
2. **What does readmission cost in this dataset?** Readmitted patients average ₹13,650 vs ₹6,431 (+112.3%) and hold 43.8% of total cost (₹36.0L of the total).
3. **Is that causal?** No — association only. Complex cases may cost more and readmit more; the data cannot separate these.
4. **Which conditions drive readmission?** 11/15 conditions have rates >95% or <5% — e.g., Heart Attack → 100%. That's generator determinism, not a clinical discovery.
5. **What would a hospital do with this?** Prioritize follow-up outreach for high-risk discharges, monitor case-mix shifts, and investigate drivers per cohort — as an analytics aid, never as a clinical rule.
6. **What's the average length of stay?** 37.7 days across the dataset.
7. **Why is an honest AUC better than a high one?** A metric that doesn't survive scrutiny destroys trust in everything else; knowing why 0.99 is fake proves I can evaluate, not just fit.
8. **Who is the user of this product?** A hospital operations/analytics team — not clinicians at the bedside.
9. **What are the fairness findings?** Performance is sliced by age group and gender and reported in `reports/fairness_check.md` — on synthetic data this demonstrates the method, not real-world parity.
10. **What should management take away?** The cost concentration story (26.8% of patients hold 43.8% of cost) justifies a follow-up program *to be tested*; the model output is a starting point for investigation, not a decision.

## 10 SQL / Data Questions

1. **How would you compute the readmission rate by condition?** `SELECT condition, AVG(CASE WHEN readmission='Yes' THEN 1.0 ELSE 0 END) FROM patients GROUP BY condition`.
2. **How do you compute cost share of readmitted patients?** Conditional aggregation: `SUM(CASE WHEN readmission='Yes' THEN cost ELSE 0 END) / SUM(cost)`.
3. **How would you find patients with above-average cost per condition?** Window functions: `AVG(cost) OVER (PARTITION BY condition)` compared against each row.
4. **How is data quality checked here?** `scripts/data_quality_report.py` produces `reports/data_quality_report.md` (issues, counts, %, severity, treatment); tests assert the invariants.
5. **How are metrics kept consistent with the UI?** Every displayed number is defined in `data/metrics.json`; the dashboard and Q&A layer read definitions from it and tests pin the values.
6. **What's a cohort analysis?** Grouping patients by a shared attribute (condition, age band) and comparing outcomes across the groups.
7. **How would you detect duplicates in patient records?** `GROUP BY patient_id HAVING COUNT(*) > 1` — the loader asserts one row per patient.
8. **Why does the Q&A layer compute from the dataset instead of an LLM?** Exact numbers must be deterministic; the LLM only phrases the answer — every figure is computed by code and CI-tested against the dataset.
9. **How would you handle NULL costs?** Validate at load (completeness check), report in the data-quality report, and never silently impute clinical values.
10. **How do age bands work?** 18-30, 31-45, 46-60, 61-75, 76+ (exclusive lower, inclusive upper) — defined in `data/metrics.json` so every chart uses the same cuts.

## 10 Python Questions

1. **How is the model trained?** `scripts/train_readmission_model.py` — RandomForest, `random_state=42`, stratified 80/20, artifacts saved with joblib; CI retrains and re-evaluates every push.
2. **How does the Q&A grounding work?** `app/dashboard/utils/simple_qa.py` computes answers from dataframe aggregates; unknown subgroups return a refusal instead of a guess; tests assert answers match dataset values.
3. **How is SHAP used?** TreeExplainer on the RandomForest — per-patient attributions in the UI, cohort-level summary in `reports/cohort_shap.md`.
4. **What happens when the Gemini API key is missing?** The AI fallback degrades gracefully — grounded Q&A keeps working; the key is env-only (`.env.example`, nothing committed).
5. **Why joblib for artifacts?** Standard scikit-learn persistence; model + encoders + metrics travel together and are version-pinned in requirements.
6. **How do you prevent the app from drifting from the analysis?** Tests load `data/metrics.json` and the committed artifacts and assert the dashboard's numbers match.
7. **What's in the feature pipeline?** `src/features/feature_pipeline.py` — converts the FHIR-style bundle into a modeling frame; exercised by the smoke test.
8. **How do you test an AI feature?** Deterministic first: every numeric answer has a test asserting it equals the dataset aggregate; refusal behavior is tested too.
9. **Why is the legacy `src/` tree kept?** It documents the prototype architecture (FHIR parsing, feature pipeline, training) that the CI legacy pipeline exercises — pruned to only real, working modules.
10. **How do you reproduce the whole project?** `python scripts/generate_data.py && python scripts/train_models.py && pytest` — the exact CI sequence, in the Makefile.

## 10 ML / Responsible-AI Questions

1. **Why is AUC 0.994 not impressive here?** Because a lookup table baseline hits 0.929 and demographics-only 0.985 — the label leaks through condition, procedure, cost, and LOS. The audit proves it.
2. **How do you detect label leakage?** Baseline comparisons (lookup tables, feature-subset models), feature-target correlation inspection, and asking whether a feature could be a proxy for the label — condition→procedure is 1:1 here.
3. **What would a trustworthy AUC look like?** For real readmission, 0.65–0.75 with temporal validation and calibration — and it should beat its baselines by a meaningful margin.
4. **What is calibration and why does it matter?** A calibrated model's 70% predictions fail ~30% of the time; risk scores used for prioritization need that property, so the reports discuss it explicitly.
5. **When would you NOT use this model?** Any real clinical, insurance, or triage decision — synthetic data, unvalidated thresholds, no regulatory approval.
6. **What fairness checks did you run?** AUC/precision/recall sliced by age group and gender with an honest writeup — method demonstration only on synthetic data.
7. **What does SHAP actually tell you?** How the model distributes credit for its score across features for one patient (local) or across the cohort (global) — it explains the model, not the medicine.
8. **How do you handle class imbalance?** 26.8% positive — mild; stratified splits preserve it; PR-AUC (0.943) is reported alongside ROC-AUC.
9. **What's your stance on LLMs in healthcare?** Grounded use only: compute numbers deterministically, phrase with the model, refuse unsupported questions, and disclose limitations — never let a language model invent a clinical figure.
10. **What did you learn from the honesty audit?** A high metric without baselines is marketing, not science; the ability to show why your own result is inflated is what makes the rest credible.

## 10 Project Deep-Dive Questions

1. **What did you build end-to-end?** Synthetic data generation → training pipeline → model artifacts → SHAP explainability → 4-tab analytics dashboard → grounded Q&A → honesty/fairness/quality reports → Docker + CI + live deployment.
2. **Why is the dashboard 4 tabs?** Executive Overview (KPIs + cost story), Clinical Analytics (drivers, cohort SHAP), Patient Intelligence (per-patient SHAP drill-down), AI Assistant (grounded Q&A) — one workflow from question to evidence.
3. **What's the test strategy?** 44 tests across data quality (invariants on the dataset), model validity (valid probabilities, reproducibility), Q&A grounding (answers == dataset aggregates), and a legacy smoke test.
4. **What would you improve next?** Temporal data to enable time-based validation; calibrated probabilities with a decision-threshold analysis; prospective evaluation design if real data ever appeared.
5. **How is this different from a notebook?** Deployed product with pinned metrics, CI that re-runs the honesty audit and training, and documentation where every claim maps to a script.
6. **Why synthetic data?** It's honest demo data with disclosed limitations and recoverable structure — which is exactly what let me demonstrate the leakage analysis; real clinical data can't be shipped in a portfolio.
7. **What's the risk of shipping this?** Someone mistaking it for a clinical tool — mitigated by disclaimers in the UI footer, README, model card, and reports, plus zero claims of patient benefit.
8. **How do the three trust reports interact?** `model_honesty.md` (is the metric real?), `fairness_check.md` (does it behave evenly across groups?), `cohort_shap.md` (what drives the scores?) — together they answer "can this be trusted, where does it fail, and why."
9. **What did you deliberately NOT do?** No fine-tuned LLM, no multi-agent stack, no fake "99% accurate clinical AI" claims — each would add noise without evidence.
10. **How do you defend a project whose model is 'bad'?** The model isn't bad — the metric is uninformative, and proving that is the contribution. The system around it (explainability, grounding, evaluation discipline) is what transfers to real work.
