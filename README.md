# 🏥 HealthGuard AI

**Explainable FHIR-Based Clinical Risk & Patient Follow-Up Intelligence Platform**

A runnable, synthetic-data research prototype for SDE, data, and AI portfolios. It ingests FHIR-shaped resources, creates longitudinal features, trains a risk model, exposes FastAPI endpoints, and serves a Streamlit dashboard. It does **not** diagnose, prescribe, or replace clinicians.

## What is included
- Synthetic FHIR R4-shaped Patient, Observation, Encounter, Condition, and MedicationRequest resources
- Feature engineering and a Random Forest risk model with ROC-AUC, PR-AUC, precision, recall, and F1 metrics
- Explainable-style reason generation from patient features
- Fallback-safe local keyword RAG/mock assistant; no API key required
- FastAPI REST API with OpenAPI docs
- Streamlit Patient 360 dashboard
- Docker, Compose, pytest, GitHub Actions, and deployment guides

## Medical disclaimer
For research and demonstration purposes only. Synthetic data only. Not intended for diagnosis, treatment, triage, emergency medical decision-making, or use with real patient data. Any AI-generated output requires review by a qualified healthcare professional.

## Run locally (exact commands)
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python scripts/generate_data.py && python scripts/train_models.py
uvicorn app.api.main:app --reload
# in a second terminal: streamlit run app/dashboard/Home.py
```
API: http://localhost:8000/docs · Dashboard: http://localhost:8501

## Docker
```bash
docker compose up --build
```

## Deploy a live demo
1. Push this repository to GitHub.
2. **Render API:** New Web Service → connect repo → build `pip install -r requirements.txt && python scripts/generate_data.py && python scripts/train_models.py` → start `uvicorn app.api.main:app --host 0.0.0.0 --port $PORT`.
3. **Streamlit Community Cloud:** New app → choose repo/branch → main file `app/dashboard/Home.py` → deploy. Add secrets only if enabling a real provider.
4. Update the dashboard's API client if you later switch from local feature execution to the deployed API. A public URL is created by those platforms; this package does not claim to have deployed one.

## Architecture
FHIR JSON → validation/features → model artifact → FastAPI → Streamlit. RAG/LLM is behind `src/ai_service.py` and remains safe in mock mode without `LLM_API_KEY`.

## Roadmap / documented stubs
The repository contains the planned package boundaries for PostgreSQL/pgvector, Redis workers, RBAC, audit logs, drift monitoring, SHAP, and React. Modules not required by this runnable MVP contain explicit `NotImplementedError` stubs; implement them incrementally before using real clinical data.

## License
MIT
