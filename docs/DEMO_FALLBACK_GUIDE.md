# Live Demo & Offline Fallback Guide — HealthGuard AI
**Primary Live Streamlit App:** https://healthguard-ai-cyl2viwrsdrrff7pig7u6c.streamlit.app/  

---

## 1. What to Do If Streamlit Community Cloud is Asleep

### Option A: Local Instant Execution
```bash
# Clone and enter directory
git clone https://github.com/rishi-1603/HealthGuard-AI.git
cd HealthGuard-AI

# Install requirements
pip install -r requirements.txt

# Launch Streamlit local hospital console
streamlit run streamlit_app.py
```
Console runs on `http://localhost:8501`.

### Option B: Quick Model Evaluation & Baseline Comparison CLI
```bash
python -m src.baseline_models --eval
```

### Option C: Inspect Core Methodological Reports
- **Methodology & Limitations:** See `docs/SYNTHETIC_DATA_LIMITATIONS.md`
- **Consolidated Model Baselines:** See `docs/MODEL_EVALUATION_CONSOLIDATION.md`
- **Hospital Operations Analytics:** See `docs/HOSPITAL_OPERATIONS_ANALYTICS.md`
- **Fairness & Demographic Audit:** See `docs/FAIRNESS_AND_SUBGROUP_AUDIT.md`
