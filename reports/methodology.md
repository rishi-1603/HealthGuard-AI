# Methodology & Validation
### How HealthGuard AI was built — and how we know it works

---

## 1. Architecture
```
data/hospital/hospital_data.csv (984 patients, committed)
        ↓
app/dashboard/Home.py (Streamlit)
   ├── utils/hospital_data.py     — load, patient codes, filters
   ├── utils/ai_risk.py           — model + SHAP scoring
   ├── utils/simple_qa.py         — grounded Q&A (template + aggregation)
   └── utils/gemini_ai.py         — optional labelled LLM fallback
        ↓
Live demo (Streamlit Community Cloud)
```

The `src/` tree and `scripts/generate_data.py` + `scripts/train_models.py`
are a **documented legacy FHIR prototype** — kept for reference, exercised
only by the legacy smoke test. The live product is the Streamlit app above.

## 2. The readmission model
- **Task:** predict `Readmission == Yes` from Age, Gender, Condition,
  Procedure, Cost, Length of Stay.
- **Model:** RandomForest (200 trees, depth 6, min_samples_leaf 5,
  class_weight balanced, random_state 42), stratified 80/20 split.
- **Explainability:** SHAP TreeExplainer; the dashboard shows each patient's
  top factors driving the score up/down.
- **Honest evaluation:** see `reports/model_honesty.md`. Summary: AUC ≈ 0.99
  is synthetic-data determinism (a per-condition lookup table alone scores
  0.93; demographics-only scores 0.985). Real clinical readmission models
  score 0.65–0.75. The number is trivially high *and documented as such*.

## 3. The Q&A layer (anti-hallucination by design)
- Keyword-matched templates compute answers **directly from the filtered
  dataframe** — every percentage and count is a real aggregation.
- Unrecognized subgroups **refuse and escalate** to a clearly-labelled
  Gemini fallback rather than silently answering the wrong thing.
- Gemini (optional, `GOOGLE_API_KEY`) is used only for open-ended
  questions/cohort recommendations, grounded in the current filter's actual
  statistics; without a key the app degrades gracefully.

## 4. How this is validated (the trust layer)
| Check | Where |
|---|---|
| Data quality: uniqueness, nulls, ranges, valid categories, base rates | `tests/test_hospital_data_quality.py` |
| Model artifacts load, scores are valid probabilities, tiers populate | `tests/test_readmission_model.py` |
| Retraining reproduces the recorded AUC (no hand-edited metrics) | `tests/test_readmission_model.py` |
| Condition→Procedure 1:1 mapping (docs assumption) | data quality tests |
| Q&A answers always match dataset aggregates | `tests/test_qa_grounding.py` |
| Unknown subgroups escalate instead of guessing | Q&A tests |
| Model honesty audit (baseline comparison) | `scripts/model_honesty_audit.py` → `reports/model_honesty.md` |
| Legacy FHIR pipeline smoke | `tests/test_smoke.py` |

All 25 tests run in CI on every push.

## 5. Reproducibility
```bash
pip install -r requirements.txt
streamlit run app/dashboard/Home.py       # the product
python scripts/model_honesty_audit.py     # regenerates the honesty report
python -m pytest tests/ -v                # all 25 checks
```
Fixed random_state throughout; the dataset and trained artifacts are
committed, so the demo runs with zero setup.

## 6. Security & privacy posture
- No secrets in code; `GOOGLE_API_KEY` comes from the environment
- `.env.example` documents required variables; real `.env` is gitignored
- Demo disclaimer surfaced in the UI footer and README — not for clinical use
