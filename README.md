# HealthGuard AI

🚀 Live Dashboard: [https://your-streamlit-url.streamlit.app](https://your-streamlit-url.streamlit.app)  
📊 Model Metrics: ROC-AUC, PR-AUC, Precision, Recall, F1  
⚠️ Disclaimer: Synthetic data only. Research/demo use only.

An explainable, FHIR-based clinical risk and patient follow-up intelligence platform. 
HealthGuard AI is designed as a portfolio piece to showcase modern data analytics, predictive modeling, and responsive dashboard design built entirely in Streamlit.

## Features
- **Synthetic FHIR Data**: Automatically generates realistic patient records with multi-variate vitals (HR, BP, SpO2), demographics, encounters, and conditions on startup.
- **Risk Prediction**: Random Forest model trained locally on startup to predict future high-risk adverse events.
- **Streamlit Dashboard**: A professional, responsive KPI dashboard with Plotly charts and a Patient 360 view all in one application.

## Quickstart (Local)

1. **Install dependencies**
```bash
pip install -r requirements.txt
```

2. **Run Dashboard**
```bash
streamlit run app/dashboard/Home.py
```
*(Note: Data generation and model training will happen automatically on the first run)*

## Deployment Architecture

```text
GitHub Repo
   |
   |-- Streamlit dashboard deployed on Streamlit Community Cloud
   |-- Synthetic dataset generated automatically on first boot
   |-- Model trained automatically on first boot
```

### Streamlit Dashboard Deployment
- Deploy via Streamlit Community Cloud.
- Set **Main file path** to `app/dashboard/Home.py`.
- No environment variables or extra backend services needed!
