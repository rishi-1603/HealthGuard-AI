# 🏥 HealthGuard AI

**Hospital Outcomes Intelligence Dashboard** — an AI-assisted analytics platform that turns raw patient data into real-time KPIs, explainable readmission-risk scores, and natural-language insights.

🔗 **Live Demo:** https://healthguard-ai-cyl2viwrsdrrff7pig7u6c.streamlit.app/
💻 **Source Code:** https://github.com/rishi-1603/HealthGuard-AI
⚠️ **Disclaimer:** Demo/portfolio analytics only. Not intended for diagnosis, treatment, or clinical decision-making.

---

## 📌 Overview

HealthGuard AI analyzes a 984-patient hospital outcomes dataset and surfaces it through an interactive Streamlit dashboard. It combines classic BI-style KPI reporting with two applied machine learning features: a **RandomForest readmission-risk model with per-patient explainability**, and **Gemini-powered cohort recommendations and natural-language Q&A**, grounded strictly in the dataset's real statistics.

## ✨ Features

- 📊 **Real-time KPI panel** — patient volume, average age, cost, length of stay, readmission rate, recovery rate, and satisfaction score
- 🧠 **AI Risk Scoring** — a RandomForest classifier predicts per-patient readmission risk, with a "top factors" breakdown showing which features raise or lower each patient's risk
- 💬 **Ask HealthGuard AI** — natural-language Q&A over the dataset, answered directly from real statistics with a Gemini-powered fallback for open-ended questions
- 🤖 **AI Recommendations** — Gemini generates cohort-level action items grounded only in the filtered data's actual numbers, not invented figures
- 🩺 **Condition-level analytics** — patient volume, average cost, and readmission rate broken down by diagnosis
- 👥 **Demographics** — age distribution, gender split, and satisfaction distribution
- 💰 **Cost vs. length-of-stay** analysis, segmented by outcome
- 🔍 **Patient lookup** — searchable per-patient profile with risk gauge, cost percentile, and explainability panel
- 📥 **Interactive records table** — filterable, sortable, and exportable to CSV
- 🎚️ Sidebar filters for condition, gender, outcome, and age range

## 🛠️ Tech Stack

**Python** · **Streamlit** · **Pandas** · **Plotly** · **scikit-learn (RandomForest)** · **Google Gemini API**

## 🚀 Quickstart (Local)

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
2. **(Optional) Enable AI recommendations & Q&A fallback**
   Set a `GOOGLE_API_KEY` environment variable with your Gemini API key. Without it, the dashboard still runs fully — KPIs, charts, risk scoring, and direct-from-data Q&A all work; only the Gemini-generated recommendations and open-ended fallback answers are disabled.
3. **Run the dashboard**
   ```bash
   streamlit run app/dashboard/Home.py
   ```

The dashboard reads the dataset directly from `data/hospital/hospital_data.csv`, which is committed to the repo — no separate backend or database setup required.

## ☁️ Deployment (Streamlit Community Cloud)

- Repository: this repo
- Branch: `main`
- Main file path: `app/dashboard/Home.py`
- Secret required for AI features: `GOOGLE_API_KEY`

## 🧪 About the AI Risk Model

A RandomForest classifier trained on the dataset's own features (age, gender, condition, procedure, cost, length of stay) to predict readmission, with per-patient factor attribution shown in the dashboard's "Why this risk score?" panel. This is a demonstration of the technique on a synthetic dataset, not a validated clinical model — the dashboard makes this explicit throughout the UI.

## 🗂️ Legacy FHIR Risk-Model Pipeline

`src/`, `scripts/generate_data.py`, and `scripts/train_models.py` contain an earlier, separate prototype: a synthetic FHIR patient generator and an independent RandomForest classifier. It's kept for reference and the `tests/test_smoke.py` smoke test, and is not part of the live dashboard above. Run `python scripts/generate_data.py && python scripts/train_models.py` to explore it.

---

📩 **Feedback or questions?** Open an issue on this repo — always happy to discuss the approach.
