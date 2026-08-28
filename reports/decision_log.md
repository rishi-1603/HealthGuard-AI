# Key Decisions Supported
### Decision log — evidence → action → owner → KPI

> Illustrative (synthetic data). The *structure* is what transfers to a real
> hospital analytics engagement.

---

## Decision 1 — Target readmission-reduction effort at the cardiac pathway
| Field | Detail |
|---|---|
| **Problem** | Readmissions concentrate in a small number of conditions |
| **Evidence** | Heart Attack readmits at 100%, Heart Disease at ~98% in-dataset; most other conditions ~0% |
| **Recommended decision** | Focus transitional-care / follow-up program design on cardiac discharges first |
| **Owner** | Care Transitions Lead |
| **KPI** | 30-day cardiac readmission rate, quarter over quarter |
| **Expected outcome** | Largest achievable readmission reduction per unit of effort |
| **Cost of inaction** | Readmissions remain concentrated where they are most preventable |

## Decision 2 — Treat the risk score as a triage UI, not a clinical model
| Field | Detail |
|---|---|
| **Problem** | A per-patient risk score invites over-trust unless framed honestly |
| **Evidence** | `reports/model_honesty.md`: AUC 0.99 is data determinism; condition lookup alone scores 0.93 |
| **Recommended decision** | Keep the score+SHAP panel as a workflow demonstration; label it demo-grade in the UI; never route real decisions through it as-is |
| **Owner** | Product / Clinical Informatics |
| **KPI** | Zero incidents of the demo score influencing real workflows |
| **Expected outcome** | Trust is preserved; the explainability pattern still gets evaluated honestly |

## Decision 3 — Keep Q&A grounded by default
| Field | Detail |
|---|---|
| **Problem** | Free-text answers over patient data invite hallucinated statistics |
| **Evidence** | `tests/test_qa_grounding.py`: every grounded answer must match a dataset aggregate; unknown subgroups refuse instead of guessing |
| **Recommended decision** | Maintain the grounded-first, LLM-fallback-labelled pattern in any future deployment |
| **Owner** | Engineering |
| **KPI** | 100% of numeric answers traceable to data (CI-enforced) |
| **Expected outcome** | Stakeholders can quote dashboard numbers without verification anxiety |

## Decision 4 — On real data, re-run the honesty audit before any rollout
| Field | Detail |
|---|---|
| **Problem** | The same pipeline on real data will produce much lower (honest) metrics |
| **Evidence** | Published readmission models: AUC 0.65–0.75 |
| **Recommended decision** | Re-run `scripts/model_honesty_audit.py`; if the baseline gap collapses, the model has real signal; ship with the updated report |
| **Owner** | Data Science |
| **KPI** | Honest AUC reported alongside any deployment |
| **Expected outcome** | Credible model governance from day one |
