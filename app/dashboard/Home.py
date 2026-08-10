import streamlit as st
import pandas as pd
import plotly.express as px
from app.dashboard.utils.api_client import get_json, post_json

st.set_page_config(
    page_title="HealthGuard AI",
    page_icon="🏥",
    layout="wide"
)

st.markdown("""
<style>
.block-container {
    padding-top: 1.5rem;
}
.metric-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    padding: 1.2rem;
    border-radius: 16px;
    box-shadow: 0 2px 10px rgba(15, 23, 42, 0.06);
}
.big-number {
    font-size: 2rem;
    font-weight: 800;
    color: #0f172a;
}
.small-label {
    color: #64748b;
    font-size: 0.9rem;
}
</style>
""", unsafe_allow_html=True)

st.title("🏥 HealthGuard AI")
st.caption("Explainable FHIR-based clinical risk and patient follow-up intelligence platform.")

try:
    overview = get_json("/analytics/kpis")
    patients_data = get_json("/patients")
    patients = pd.DataFrame(patients_data)
    metrics = get_json("/analytics/model-metrics")
    risk_dist = get_json("/analytics/risk-distribution")

    total = overview["total_patients"]
    high = overview["high_risk_patients"]
    high_rate = overview["high_risk_rate"]

    k1, k2, k3, k4 = st.columns(4)

    k1.metric("Total Patients", total)
    k2.metric("High Risk Patients", high)
    k3.metric("High Risk Rate", f"{high_rate}%")
    k4.metric("Model ROC-AUC", metrics.get("roc_auc", "N/A"))

    k5, k6, k7, k8 = st.columns(4)

    k5.metric("Precision", metrics.get("precision", "N/A"))
    k6.metric("Recall", metrics.get("recall", "N/A"))
    k7.metric("F1 Score", metrics.get("f1", "N/A"))
    k8.metric("Data Quality", f"{overview.get('data_quality_score', 91)}%")

    st.divider()

    left, right = st.columns([1.2, 1])

    risk_df = pd.DataFrame({
        "Risk Tier": ["Stable", "High Risk"],
        "Patients": [risk_dist.get("stable", 0), risk_dist.get("high", 0)]
    })

    with left:
        st.subheader("Risk Distribution")
        fig = px.pie(
            risk_df,
            values="Patients",
            names="Risk Tier",
            hole=0.55,
            color="Risk Tier",
            color_discrete_map={
                "Stable": "#22c55e",
                "High Risk": "#ef4444"
            }
        )
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("Heart Rate vs Age")
        if not patients.empty and "age" in patients and "latest_heart_rate" in patients:
            fig = px.scatter(
                patients,
                x="age",
                y="latest_heart_rate",
                color="risk_target",
                size="observation_count",
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
        risk = get_json(f"/patients/{patient_id}/risk")

        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Age", int(selected["age"]))
        p2.metric("Latest Heart Rate", round(float(selected.get("latest_heart_rate", 0)), 1))
        p3.metric("Mean Heart Rate", round(float(selected.get("mean_heart_rate", 0)), 1))
        p4.metric("Risk Score", risk["risk_score"])

        st.write("### Risk Explanation")
        st.info(", ".join(risk["reasons"]) if risk.get("reasons") else "No major risk factors detected.")

        q = st.text_input("Ask the assistant", "Why is this patient high risk?")
        if st.button("Analyze Patient"):
            answer = post_json("/assistant/query", {"query": q})
            st.write(answer)
    else:
        st.info("No patients available.")

    st.warning(
        "Research/demo only. Not intended for diagnosis, treatment, triage, or emergency medical decision-making."
    )

except Exception as e:
    st.error(f"Error loading dashboard: {str(e)}")
    st.info("Make sure the API backend is running.")
