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
   ├── utils/simple_qa.py         — compatibility entry point for computed Q&A
   └── utils/gemini_ai.py         — optional validated selection of computed fact cards
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
  0.93; demographics-only scores 0.985). The result does not establish clinical validity; performance on real populations requires a separate evaluation.

## 3. Analytical questions and optional provider assistance
- `assistant_service.py` validates a bounded question plan and computes answers from the filtered DataFrame. It returns scope, formula, source columns and evidence values.
- Unsupported filters, false premises, clinical advice and unavailable time windows are refused. They are not forwarded to a generative fallback.
- Optional Gemini assistance selects IDs from already computed aggregate evidence cards. Extra fields, invalid JSON and unknown IDs are rejected; provider-authored figures or clinical prose are not displayed as verified evidence.
- Scope changes clear stale answers and briefs. A content fingerprint, explicit form submission and an isolated Streamlit fragment reduce unnecessary reruns.
- Provider configuration, actual connection success and computed local mode are labelled separately. See `docs/ASSISTANT_GUIDE.md` for the precise contract and limits.

## 4. How this is validated (the trust layer)
| Check | Where |
|---|---|
| Data quality: uniqueness, nulls, ranges, valid categories, base rates | `tests/test_hospital_data_quality.py` |
| Model artifacts load, scores are valid probabilities, tiers populate | `tests/test_readmission_model.py` |
| Model artifacts and recorded metric consistency | `tests/test_readmission_model.py` |
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
