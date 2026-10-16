# Final Release Report — HealthGuard AI
**Date:** 2026-10-15 · **Release commit:** `d93eb12` · **CI:** green (44/44 tests)

## A. Overall result
**READY WITH DISCLOSED LIMITATIONS** — synthetic-data demo; no clinical validity claimed anywhere.

## B. Work completed (this release)
- Removed 44 dead extension-point stubs from `src/` (kept 5 working modules: FHIR parser, feature pipeline, train, AI service, package inits)
- Added `models/readmission/MODEL_CARD.md` — honest model card with baselines (0.929 lookup / 0.985 demographics-only) and non-clinical disclaimer
- Added `reports/INTERVIEW_PREP.md` — resume bullets, 5-minute script, 50 Q&A with verified numbers
- Added `reports/analytics_questions.md` — 15 questions mapped to dashboard sections, methods, and tests
- README: linked new artifacts; documented legacy-tree cleanup

## C. Features & verification
| Feature | Status |
|---|---|
| 4-tab analytics dashboard (KPIs, clinical analytics, patient SHAP, Q&A) | Live on Streamlit Cloud |
| Readmission model + per-patient SHAP | Artifacts committed, tests validate probabilities |
| Grounded Q&A (refuses ungroundable questions) | `tests/test_qa_grounding.py` |
| Model honesty audit | Runs in CI on every push |
| Fairness slices + cohort SHAP | Reports + tests |

## D. Data & models
- Metrics independently recomputed by CI scripts: AUC 0.994 vs baselines 0.929/0.985 — documented as synthetic-data determinism
- All limitations disclosed in model card, `reports/model_honesty.md`, `reports/assumptions_and_limitations.md`, UI footer

## E. Quality
44/44 tests green locally and in CI (data quality, model validity, Q&A grounding, legacy smoke). Full CI sequence (honesty audit → legacy pipeline → pytest) re-run after the stub removal.

## F. Known issues / disclosed limitations
1. Synthetic data — metrics do not transfer to real patients
2. No temporal validation possible with the current generator
3. sklearn version pin warnings on artifact unpickle (cosmetic; CI retrains)

## H. Deployment
Live: https://healthguard-ai-cyl2viwrsdrrff7pig7u6c.streamlit.app/ (verified 200 after release) · Docker + Makefile available

---

## Release v2 (2026-10-21) — evaluation-depth week (Days 2–6)

| Evidence | Status |
|---|---|
| Calibration + cost-based thresholds / decision curves | Published + CI-pinned |
| Naive-baseline / rules-vs-ML / temporal comparisons | Published with honest verdicts |
| Error analysis with concrete failure cases | `reports/error_analysis.md` |
| Metric-registry entries for every new metric | `data/metrics.json` |
| New analysis scripts run in CI on every push | ✅ |
| Interview-prep eval-depth Q&A | ✅ |

**Test totals:** E-Commerce 84 · Zomato 80 · HealthGuard 56 (220 combined, all green).

**Notable honest findings shipped this week:** churn calibration slope 0.39 → isotonic fix; t\*=0.10 beats contact-all; forecast ensemble loses to drift baseline (MASE 0.68 vs 0.47); shipped 95% CI covers 9.5%; rules tie ML at investigation cut sizes; readmission model errors sit exactly in the generator's stochastic conditions.

**Status unchanged:** READY / READY WITH DISCLOSED LIMITATIONS — nothing this week weakened a claim; several were tightened downward on purpose.
