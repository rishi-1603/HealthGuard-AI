# HealthGuard AI

🚀 Live Dashboard: [https://your-streamlit-url.streamlit.app](https://your-streamlit-url.streamlit.app) *(update this link once deployed)*
⚠️ Disclaimer: Demo/portfolio analytics only. Not intended for diagnosis, treatment, or clinical decision-making.

A hospital outcomes analytics dashboard built entirely in Streamlit. Analyzes a 984-patient
dataset covering condition, cost, length of stay, readmissions, outcomes, and patient
satisfaction.

## Features
- **KPI overview**: patient count, average age/cost/length of stay, readmission rate,
  recovery rate, satisfaction score.
- **Condition analytics**: patient volume, average cost, and readmission rate broken down
  by condition.
- **Demographics**: age distribution, gender split, satisfaction distribution.
- **Cost vs. length-of-stay** scatter plot colored by outcome.
- **Filterable, sortable, downloadable** patient records table.
- Sidebar filters for condition, gender, outcome, and age range.

## Quickstart (Local)

1. **Install dependencies**
```bash
pip install -r requirements.txt
```

2. **Run the dashboard**
```bash
streamlit run app/dashboard/Home.py
```

The dashboard reads the dataset directly from `data/hospital/hospital_data.csv`, which is
committed to the repo — no separate backend, database, or setup step required.

## Deployment (Streamlit Community Cloud)

- Repository: this repo
- Branch: `main`
- Main file path: `app/dashboard/Home.py`
- No secrets or environment variables needed.

## Legacy FHIR risk-model pipeline

`src/`, `scripts/generate_data.py`, and `scripts/train_models.py` contain an earlier,
separate prototype: a synthetic FHIR patient generator and a random-forest risk classifier.
It's independent of the live dashboard above (which uses the hospital outcomes CSV instead)
and is kept for reference / the `tests/test_smoke.py` smoke test. Run
`python scripts/generate_data.py && python scripts/train_models.py` if you want to explore it.
