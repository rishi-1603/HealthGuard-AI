<div align="center">

# 🏥 HealthGuard AI
### Hospital Outcomes Intelligence Dashboard

**An AI-assisted analytics platform that turns raw patient data into real-time KPIs,
explainable readmission-risk scores, and grounded natural-language insights —
with the model's limits documented as carefully as its features.**

[🚀 Live Demo](https://healthguard-ai-cyl2viwrsdrrff7pig7u6c.streamlit.app/) ·
[🧪 25 Automated Tests](tests/) ·
[📄 Analytics Reports](reports/) ·
[🔍 Model Honesty Audit](reports/model_honesty.md)

</div>

> ⚠️ **Disclaimer:** Demo/portfolio analytics only. Not intended for diagnosis,
> treatment, or clinical decision-making. The dataset is synthetic.

---

## 1. 🚀 Live Project

**Dashboard (deployed on Streamlit Community Cloud):**

> ### 👉 https://healthguard-ai-cyl2viwrsdrrff7pig7u6c.streamlit.app/

**GitHub Repository:**

> ### 👉 https://github.com/rishi-1603/HealthGuard-AI

---

## 2. 💼 Business Problem

Hospital operations leadership has three recurring blind spots:

| # | Question | Where it's answered |
|---|---|---|
| 1 | What do our patient outcomes, costs, and utilization actually look like? | KPI panel + condition/demographic analytics |
| 2 | Which patients are likely to be readmitted — and *why* that score? | RandomForest risk model + SHAP per-patient explanations |
| 3 | Can non-analysts ask questions of the data without waiting days? | Grounded Q&A (computed from data, not generated prose) |

**The design principle that shapes everything:** in a healthcare context, an
**unverifiable AI answer is worse than no answer.** So numbers come from the
data or not at all; the LLM is a clearly-labelled fallback, never the source
of statistics.

---

## 3. 🔄 Project Overview

```
data/hospital/hospital_data.csv  (984-patient synthetic outcomes)
        ↓
Streamlit dashboard
   ├── KPI panel & filters (condition / gender / outcome / age)
   ├── Condition, demographic, cost & outcome analytics
   ├── RandomForest readmission model + SHAP explainability
   ├── Grounded Q&A (template + real aggregation)
   └── Optional Gemini layer (labelled fallback for open-ended questions)
        ↓
Grounded insights + honest model documentation
```

A separate **legacy FHIR prototype** (`src/`, `scripts/generate_data.py`,
`scripts/train_models.py`) is kept for reference and covered by a smoke test —
documented in `reports/methodology.md`.

---

## 4. 📦 Dataset

984 patients × 10 columns · 15 conditions · 15 procedures (1:1 mapping) · synthetic.

| Metric | Value |
|---|---|
| Patients | 984 |
| Average age | 53.8 years |
| Average cost | ₹8,367 |
| Average length of stay | 37.7 days |
| Readmission rate | 26.8% |
| Recovery rate | 60.1% |
| Satisfaction | 3.60 / 5 |

Column-by-column documentation: [`data/DATA_DICTIONARY.md`](data/DATA_DICTIONARY.md)

---

## 5. 🛠 Tech Stack

**Only what the repository genuinely uses.**

| Layer | Tools |
|---|---|
| **App** | Python · Streamlit |
| **Data** | pandas |
| **ML** | scikit-learn (RandomForest) |
| **Explainability** | SHAP (TreeExplainer, per-patient factor attribution) |
| **AI layer** | Google Gemini API (optional, env-keyed, graceful degradation) |
| **Visualization** | Plotly |
| **Quality** | pytest (25 tests) · GitHub Actions CI |
| **Deployment** | Streamlit Community Cloud · Docker · Makefile |

---

## 6. 🧠 The AI Layers — and their guardrails

### Readmission risk model (with the honest headline)
A RandomForest predicts per-patient readmission risk and SHAP explains each
score ("why this risk?"). **The headline metric is AUC ≈ 0.99 — and that
number is not skill.** In this synthetic dataset, readmission is essentially
determined by the condition pathway:

| Configuration | AUC |
|---|---|
| Shipped RandomForest | **0.992** |
| Trivial baseline (per-condition lookup, no ML) | 0.929 |
| Demographics/utilization only | 0.985 |

Real clinical readmission models score **0.65–0.75**. The full quantified audit
lives in [`reports/model_honesty.md`](reports/model_honesty.md), is regenerable
via `scripts/model_honesty_audit.py`, and the same caveat appears in the live
UI. *A suspiciously perfect metric, found and documented, is the strongest
signal of judgment a portfolio can show.*

### Grounded Q&A (anti-hallucination by design)
- Keyword-matched templates compute answers **directly from the filtered data** —
  every number is a traceable aggregation
- Unrecognized subgroups **refuse and escalate** to the labelled Gemini
  fallback rather than silently answering the wrong question
- CI-enforced: [`tests/test_qa_grounding.py`](tests/test_qa_grounding.py)
  verifies every answerable percentage matches a dataset-computable value

### Gemini layer (optional)
Used only for open-ended questions and cohort recommendations, grounded in the
current filter's statistics. Enabled via `GOOGLE_API_KEY`; without it the app
runs fully minus those two features. No key is ever hardcoded.

---

## 7. 🧩 Feature Modules

- 📊 **KPI panel** — volume, age, cost, LOS, readmission, recovery, satisfaction
- 🩺 **Condition analytics** — volume, cost, readmission by diagnosis
- 👥 **Demographics** — age distribution, gender split, satisfaction
- 💰 **Cost vs LOS** — segmented by outcome
- 🔍 **Patient lookup** — searchable profile with risk gauge, cost percentile, explainability panel
- 🧠 **AI risk scoring** — per-patient score + SHAP "top factors"
- 💬 **Ask HealthGuard AI** — grounded Q&A + labelled Gemini fallback
- 🤖 **AI recommendations** — cohort action items grounded in filtered stats
- 📥 **Records table** — filterable, sortable, CSV export
- 🎚️ **Sidebar filters** — condition, gender, outcome, age range

---

## 8. 💡 Key Insights (illustrative — synthetic data)

### Insight 1 — Readmissions are almost entirely a cardiac-pathway story
Heart Attack (100% readmit) and Heart Disease (~98.5%) drive nearly all
readmissions; 9 of 15 conditions readmit at 0%.
**Action (on real data):** target transitional-care programs at cardiac
discharges. *Owner: Care Transitions · KPI: 30-day cardiac readmission rate.*

### Insight 2 — Cost and LOS track the condition pathway
The expensive, long-stay pathways are the same ones that readmit.
**Action (on real data):** case-mix-adjusted pathway review before cost
cutting. *Owner: Operations · KPI: cost per episode by pathway.*

### Insight 3 — The perfect AUC is itself the finding
A model scoring 0.99 on a 0.65–0.75 task means the label leaks from the
features — an audit skill that transfers to every future modelling job.
**Proof:** [`reports/model_honesty.md`](reports/model_honesty.md).

---

## 9. 📸 Dashboard Preview

**[➡ Open the live demo](https://healthguard-ai-cyl2viwrsdrrff7pig7u6c.streamlit.app/)**

<img width="813" height="432" alt="image" src="https://github.com/user-attachments/assets/77b82599-0807-4be9-a604-eece83dd12b4" />
<img width="1774" height="873" alt="Healthguard ss-2" src="https://github.com/user-attachments/assets/41fe973d-f452-42e0-902e-3d4be383f1d4" />
<img width="1672" height="844" alt="Healthguard ss-3" src="https://github.com/user-attachments/assets/2f22eb04-64c8-4a19-8c64-be6d60029e73" />
<img width="1625" height="863" alt="Healthguard ss-4" src="https://github.com/user-attachments/assets/4d31d41a-4f6c-455a-b3d2-e5101c4c1542" />

---

## 10. 🏗 Project Architecture

```
HealthGuard-AI/
├── app/dashboard/            # THE PRODUCT (Streamlit app)
│   ├── Home.py               #   main page
│   ├── components/           #   charts, metrics, patient card, risk badge
│   └── utils/                #   data, model+SHAP, grounded Q&A, Gemini
├── data/
│   ├── hospital/             #   hospital_data.csv (served dataset)
│   ├── synthetic/            #   legacy FHIR bundle
│   └── DATA_DICTIONARY.md    #   every column documented
├── models/readmission/       # model + encoders + metrics (committed)
├── scripts/
│   ├── train_readmission_model.py
│   └── model_honesty_audit.py  # quantifies WHY AUC ~0.99
├── tests/                    # 25 tests: data quality, model, Q&A grounding, legacy smoke
├── reports/                  # executive summary, methodology, limitations,
│                             # decision log, model honesty audit
├── src/                      # legacy FHIR prototype (documented, not served)
├── Dockerfile · docker-compose.yml · Makefile
└── .github/workflows/ci.yml  # CI: deps → audit → all tests
```

---

## 11. ▶️ How to Run

```bash
git clone https://github.com/rishi-1603/HealthGuard-AI.git
cd HealthGuard-AI
pip install -r requirements.txt

streamlit run app/dashboard/Home.py        # the dashboard (no setup needed)

# optional: enable Gemini features
export GOOGLE_API_KEY=your_key             # never committed; .env.example documents it

# verify everything
python scripts/model_honesty_audit.py      # regenerate the honesty report
python -m pytest tests/ -v                 # 25 checks
```

Docker alternative: `docker-compose up` (see `docker-compose.yml`).

---

## 12. 🎓 Key Learnings

- **A perfect metric is a debugging signal** — AUC 0.99 meant the label was
  encoded in the features; quantifying *why* (baseline 0.93 lookup) taught me
  more than the model itself
- **Grounding beats generation** for any analytics Q&A where numbers must be
  quotable — compute from data, use the LLM only as a labelled fallback
- **Explainability is a UX requirement** in high-stakes domains — per-patient
  SHAP factors make a score auditable by the person affected by it
- **Testing the product, not just the code** — data-quality, model-consistency,
  and Q&A-grounding tests pin the actual user-facing claims
- **Degrading gracefully** — the app is fully useful with zero API keys

---

## 13. 🔮 Future Improvements

- Re-run the pipeline on a real (de-identified) outcomes dataset and publish
  the honest AUC alongside the system
- Calibration curves + decision-curve analysis for the risk model
- Time-to-readmission survival modelling once temporal data exists
- Role-based access and audit logging for multi-user deployment
- Feedback loop: capture Q&A answers that failed to match, expand templates

---

## 📄 License & Disclaimer

Demo/portfolio project. **Not intended for diagnosis, treatment, or clinical
decision-making.** The dataset is synthetic; the AI features are demonstrations
of technique, not validated clinical tools.

<div align="center">

**⭐ Star this repo if it helped you ·
[🚀 Open the Live Demo](https://healthguard-ai-cyl2viwrsdrrff7pig7u6c.streamlit.app/) ⭐**

</div>
