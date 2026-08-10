# HealthGuard AI

🚀 Live Dashboard: [https://your-streamlit-url](https://your-streamlit-url)  
⚙️ Live API Docs: [https://your-render-url.onrender.com/docs](https://your-render-url.onrender.com/docs)  
📊 Model Metrics: ROC-AUC, PR-AUC, Precision, Recall, F1  
⚠️ Disclaimer: Synthetic data only. Research/demo use only.

An explainable, FHIR-based clinical risk and patient follow-up intelligence platform. 
HealthGuard AI is designed as a portfolio piece to showcase modern data analytics, predictive modeling, and responsive dashboard design.

## Features
- **Synthetic FHIR Data**: Generates realistic patient records with multi-variate vitals (HR, BP, SpO2), demographics, encounters, and conditions.
- **Risk Prediction**: Random Forest model trained to predict future high-risk adverse events.
- **FastAPI Backend**: Provides endpoints for patient querying, analytics, risk distributions, and model metrics.
- **Streamlit Dashboard**: A professional, responsive KPI dashboard with Plotly charts and a Patient 360 view.

## Quickstart (Local)

1. **Install dependencies**
```bash
pip install -r requirements.txt
```

2. **Generate data and train model**
```bash
python scripts/generate_data.py
python scripts/train_models.py
```

3. **Run API**
```bash
uvicorn app.api.main:app --reload
```

4. **Run Dashboard**
```bash
streamlit run app/dashboard/Home.py
```

## Deployment Architecture

```text
GitHub Repo
   |
   |-- FastAPI backend deployed on Render
   |-- Streamlit dashboard deployed on Streamlit Community Cloud
   |-- Synthetic dataset generated during build
   |-- Model trained during build
   |-- Dashboard fetches live API data from Render
```

### Render API Deployment
- Create a new Web Service on Render and link this repository.
- Build Command: `pip install -r requirements.txt && python scripts/generate_data.py && python src/models/train.py` (ensure scripts run correctly).
- Start Command: `uvicorn app.api.main:app --host 0.0.0.0 --port $PORT`

### Streamlit Dashboard Deployment
- Deploy via Streamlit Community Cloud.
- Set Main file to `app/dashboard/Home.py`.
- Add Streamlit secret: `API_BASE_URL = "https://your-render-api-url.onrender.com"`
