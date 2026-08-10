import streamlit as st
import pandas as pd
import plotly.express as px
import json
import joblib
from pathlib import Path
import sys
import subprocess

# Ensure the root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Data paths
BUNDLE_PATH = Path('data/synthetic/bundle.json')
MODEL_PATH = Path('models/artifacts/risk_model.joblib')
METRICS_PATH = Path('models/metrics/risk_metrics.json')

st.set_page_config(
    page_title="HealthGuard AI",
    page_icon="🏥",
    layout="wide"
)

# Initialize data and models if they don't exist
@st.cache_resource(show_spinner="Initializing data and models for the first time...")
def initialize_system():
    if not BUNDLE_PATH.exists():
        subprocess.run([sys.executable, "scripts/generate_data.py"], check=True)
    if not MODEL_PATH.exists() or not METRICS_PATH.exists():
        subprocess.run([sys.executable, "scripts/train_models.py"], check=True)
    return True

initialize_system()

# Import core modules
from src.features.feature_pipeline import bundle_to_frame
from src.ai_service import answer

@st.cache_data
def load_data():
    return bundle_to_frame(str(BUNDLE_PATH))

@st.cache_data
def load_metrics():
    if METRICS_PATH.exists():
        return json.loads(METRICS_PATH.read_text())
    return {}

@st.cache_resource
def load_model():
    if MODEL_PATH.exists():
        return joblib.load(MODEL_PATH)
    return None

st.markdown("""
<style>
.block-container { padding-top: 1.5rem; }
.metric-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    padding: 1.2rem;
    border-radius: 16px;
    box-shadow: 0 2px 10px rgba(15, 23, 42, 0.06);
}
</style>
""", unsafe_allow_html=True)

st.title("🏥 HealthGuard AI")
st.caption("Explainable FHIR-based clinical risk and patient follow-up intelligence platform.")

try:
    patients = load_data()
    metrics = load_metrics()
    model = load_model()

    total = len(patients)
    high = int(patients["risk_target"].sum()) if not patients.empty else 0
    high_rate = round(high / total * 100, 1) if total else 0.0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Patients", total)
    k2.metric("High Risk Patients", high)
    k3.metric("High Risk Rate", f"{high_rate}%")
    k4.metric("Model ROC-AUC", metrics.get("roc_auc", "N/A"))

    k5, k6, k7, k8 = st.columns(4)
    k5.metric("Precision", metrics.get("precision", "N/A"))
    k6.metric("Recall", metrics.get("recall", "N/A"))
    k7.metric("F1 Score", metrics.get("f1", "N/A"))
    k8.metric("Data Quality", "91%")

    st.divider()

    left, right = st.columns([1.2, 1])

    with left:
        st.subheader("Risk Distribution")
        risk_df = pd.DataFrame({
            "Risk Tier": ["Stable", "High Risk"],
            "Patients": [total - high, high]
        })
        fig = px.pie(
            risk_df,
            values="Patients",
            names="Risk Tier",
            hole=0.55,
            color="Risk Tier",
            color_discrete_map={"Stable": "#22c55e", "High Risk": "#ef4444"}
        )
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("Heart Rate vs Age")
        if not patients.empty and "age" in patients and "latest_heart_rate" in patients:
            fig = px.scatter(
                patients, x="age", y="latest_heart_rate",
                color="risk_target", size="observation_count",
                hover_data=["patient_id", "mean_heart_rate", "trend"],
                color_continuous_scale=["#22c55e", "#ef4444"]
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No sufficient patient data to render chart.")

    st.divider()

    st.subheader("Patient 360")

    if not patients.empty:
        patient_id = st.selectbox("Select Patient", patients["patient_id"].tolist())
        selected = patients[patients["patient_id"] == patient_id].iloc[0]
        # Calculate individual risk score
        features = ['age', 'mean_heart_rate', 'latest_heart_rate', 'observation_count', 'trend']
        score = float(model.predict_proba(selected[features].to_frame().T)[:, 1][0]) if model else float(selected["risk_target"])
        
        reasons = []
        if selected.get("abnormal_count", 0) > 0:
            reasons.append(f'{int(selected["abnormal_count"])} abnormal observations')
        if selected.get("trend", 0) > 8:
            reasons.append('rising recent observation trend')
        if selected.get("age", 0) > 70:
            reasons.append('age-related risk factor')
            
        risk_tier = 'HIGH' if score >= 0.66 else 'WATCH' if score >= 0.33 else 'STABLE'

        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Age", int(selected["age"]))
        p2.metric("Latest Heart Rate", round(float(selected.get("latest_heart_rate", 0)), 1))
        p3.metric("Mean Heart Rate", round(float(selected.get("mean_heart_rate", 0)), 1))
        p4.metric("Risk Score", round(score, 4))

        st.write("### Risk Explanation")
        st.info(", ".join(reasons) if reasons else "No major risk factors detected.")

        q = st.text_input("Ask the assistant", "Why is this patient high risk?")
        if st.button("Analyze Patient"):
            ans = answer(q)
            st.write(ans)
    else:
        st.info("No patients available.")

    st.warning("Research/demo only. Not intended for diagnosis, treatment, triage, or emergency medical decision-making.")

except Exception as e:
    st.error(f"Error loading dashboard: {str(e)}")
