import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from app.dashboard.utils import hospital_data as data

st.set_page_config(
    page_title="HealthGuard AI | Hospital Outcomes",
    page_icon="🏥",
    layout="wide"
)

NAVY = "#0F172A"
SLATE = "#475569"
MUTED = "#64748B"
TEAL = "#0E7490"
TEAL_LIGHT = "#67E8F9"
AMBER = "#F59E0B"
RED = "#DC2626"
GREEN = "#16A34A"
BG = "#F8FAFC"
CARD_BORDER = "#E2E8F0"

st.markdown(f"""
<style>
.block-container {{
    padding-top: 1.6rem;
    padding-bottom: 3rem;
    max-width: 1300px;
}}
html, body, [class*="css"] {{
    font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
}}
.hg-header {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 0.2rem;
}}
.hg-title {{
    font-size: 1.9rem;
    font-weight: 800;
    color: {NAVY};
    letter-spacing: -0.02em;
}}
.hg-subtitle {{
    color: {MUTED};
    font-size: 0.95rem;
    margin-bottom: 1.4rem;
}}
.hg-pill {{
    display: inline-block;
    background: #ECFEFF;
    color: {TEAL};
    border: 1px solid #A5F3FC;
    border-radius: 999px;
    padding: 0.15rem 0.7rem;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.02em;
}}
.kpi-card {{
    background: #ffffff;
    border: 1px solid {CARD_BORDER};
    border-radius: 14px;
    padding: 1rem 1.1rem;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    height: 100%;
}}
.kpi-label {{
    color: {MUTED};
    font-size: 0.78rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 0.35rem;
}}
.kpi-value {{
    color: {NAVY};
    font-size: 1.65rem;
    font-weight: 800;
    line-height: 1.1;
}}
.kpi-sub {{
    color: {MUTED};
    font-size: 0.78rem;
    margin-top: 0.25rem;
}}
.section-title {{
    color: {NAVY};
    font-size: 1.15rem;
    font-weight: 700;
    margin: 1.6rem 0 0.6rem 0;
}}
.chart-card {{
    background: #ffffff;
    border: 1px solid {CARD_BORDER};
    border-radius: 14px;
    padding: 1rem 1.1rem 0.3rem 1.1rem;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}}
[data-testid="stMetricValue"] {{ color: {NAVY}; }}
</style>
""", unsafe_allow_html=True)

CHART_FONT = dict(family="-apple-system, Segoe UI, Roboto, sans-serif", color=NAVY, size=13)


def style_fig(fig, height=360, legend=True):
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=CHART_FONT,
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(gridcolor="#EEF2F7", zeroline=False)
    fig.update_yaxes(gridcolor="#EEF2F7", zeroline=False)
    return fig


try:
    raw = data.load_patients()

    st.markdown(f"""
    <div class="hg-header">
        <div class="hg-title">🏥 HealthGuard AI</div>
        <div class="hg-pill">HOSPITAL OUTCOMES ANALYTICS</div>
    </div>
    <div class="hg-subtitle">Cohort analysis across {len(raw)} patients — cost, length of stay, readmissions, and outcomes.</div>
    """, unsafe_allow_html=True)

    # ---------------- Sidebar filters ----------------
    with st.sidebar:
        st.markdown("### Filters")
        conditions = st.multiselect("Condition", sorted(raw.Condition.unique()))
        genders = st.multiselect("Gender", sorted(raw.Gender.unique()))
        outcomes = st.multiselect("Outcome", sorted(raw.Outcome.unique()))
        age_range = st.slider(
            "Age range",
            int(raw.Age.min()), int(raw.Age.max()),
            (int(raw.Age.min()), int(raw.Age.max()))
        )
        st.caption(f"{len(raw)} patients loaded from dataset.")

    df = data.apply_filters(raw, conditions, genders, outcomes, age_range)

    if df.empty:
        st.warning("No patients match the current filters. Adjust filters in the sidebar.")
        st.stop()

    kpis = data.get_kpis(df)

    # ---------------- KPI row ----------------
    k = st.columns(4)
    kpi_specs = [
        ("PATIENTS", f"{kpis['total_patients']:,}", f"of {len(raw):,} total"),
        ("AVG AGE", f"{kpis['avg_age']}", "years"),
        ("AVG COST / PATIENT", f"${kpis['avg_cost']:,.0f}", f"${kpis['total_cost']:,.0f} total"),
        ("AVG LENGTH OF STAY", f"{kpis['avg_los']} days", ""),
    ]
    for col, (label, value, sub) in zip(k, kpi_specs):
        col.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-sub">{sub}</div>
        </div>
        """, unsafe_allow_html=True)

    k2 = st.columns(4)
    readmit_color = RED if kpis["readmission_rate"] > 30 else AMBER if kpis["readmission_rate"] > 15 else GREEN
    kpi_specs2 = [
        ("READMISSION RATE", f"{kpis['readmission_rate']}%", readmit_color),
        ("RECOVERED RATE", f"{kpis['recovered_rate']}%", GREEN),
        ("AVG SATISFACTION", f"{kpis['avg_satisfaction']} / 5", TEAL),
        ("CONDITIONS TRACKED", f"{df.Condition.nunique()}", NAVY),
    ]
    for col, (label, value, color) in zip(k2, kpi_specs2):
        col.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value" style="color:{color}">{value}</div>
        </div>
        """, unsafe_allow_html=True)

    # ---------------- Condition overview ----------------
    st.markdown('<div class="section-title">Condition Overview</div>', unsafe_allow_html=True)
    cond_summary = data.condition_summary(df)

    c1, c2 = st.columns([1.3, 1])

    with c1:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        fig = px.bar(
            cond_summary.sort_values("patients", ascending=True),
            x="patients", y="Condition", orientation="h",
            color="patients", color_continuous_scale=["#A5F3FC", TEAL],
            labels={"patients": "Patients", "Condition": ""},
        )
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(style_fig(fig, height=440, legend=False), use_container_width=True, config={"displayModeBar": False})
        st.caption("Patient volume by condition")
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        fig = px.pie(
            df, names="Outcome", hole=0.6,
            color="Outcome",
            color_discrete_map={"Recovered": TEAL, "Stable": AMBER},
        )
        fig.update_traces(textinfo="percent+label")
        st.plotly_chart(style_fig(fig, height=440), use_container_width=True, config={"displayModeBar": False})
        st.caption("Outcome distribution")
        st.markdown('</div>', unsafe_allow_html=True)

    # ---------------- Cost & readmission by condition ----------------
    st.markdown('<div class="section-title">Cost & Readmission by Condition</div>', unsafe_allow_html=True)
    c3, c4 = st.columns(2)

    with c3:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        fig = px.bar(
            cond_summary.sort_values("avg_cost", ascending=False),
            x="Condition", y="avg_cost",
            color_discrete_sequence=[TEAL],
            labels={"avg_cost": "Avg Cost ($)", "Condition": ""},
        )
        fig.update_xaxes(tickangle=-40)
        st.plotly_chart(style_fig(fig, legend=False), use_container_width=True, config={"displayModeBar": False})
        st.caption("Average treatment cost by condition")
        st.markdown('</div>', unsafe_allow_html=True)

    with c4:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        cs = cond_summary.sort_values("readmission_rate", ascending=False)
        fig = px.bar(
            cs, x="Condition", y="readmission_rate",
            color="readmission_rate",
            color_continuous_scale=[GREEN, AMBER, RED],
            labels={"readmission_rate": "Readmission Rate (%)", "Condition": ""},
        )
        fig.update_xaxes(tickangle=-40)
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(style_fig(fig, legend=False), use_container_width=True, config={"displayModeBar": False})
        st.caption("Readmission rate by condition")
        st.markdown('</div>', unsafe_allow_html=True)

    # ---------------- Demographics & satisfaction ----------------
    st.markdown('<div class="section-title">Demographics & Satisfaction</div>', unsafe_allow_html=True)
    c5, c6, c7 = st.columns(3)

    with c5:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        fig = px.histogram(df, x="Age", nbins=15, color_discrete_sequence=[TEAL])
        st.plotly_chart(style_fig(fig, height=320, legend=False), use_container_width=True, config={"displayModeBar": False})
        st.caption("Age distribution")
        st.markdown('</div>', unsafe_allow_html=True)

    with c6:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        fig = px.pie(
            df, names="Gender", hole=0.6,
            color_discrete_sequence=[TEAL, AMBER],
        )
        fig.update_traces(textinfo="percent+label")
        st.plotly_chart(style_fig(fig, height=320), use_container_width=True, config={"displayModeBar": False})
        st.caption("Gender split")
        st.markdown('</div>', unsafe_allow_html=True)

    with c7:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        sat_counts = df.Satisfaction.value_counts().sort_index()
        fig = px.bar(
            x=sat_counts.index.astype(str), y=sat_counts.values,
            color_discrete_sequence=[TEAL],
            labels={"x": "Satisfaction (1-5)", "y": "Patients"},
        )
        st.plotly_chart(style_fig(fig, height=320, legend=False), use_container_width=True, config={"displayModeBar": False})
        st.caption("Satisfaction score distribution")
        st.markdown('</div>', unsafe_allow_html=True)

    # ---------------- Cost vs LOS ----------------
    st.markdown('<div class="section-title">Cost vs. Length of Stay</div>', unsafe_allow_html=True)
    st.markdown('<div class="chart-card">', unsafe_allow_html=True)
    fig = px.scatter(
        df, x="Length_of_Stay", y="Cost", color="Outcome",
        size="Satisfaction", hover_data=["Patient_ID", "Condition", "Age"],
        color_discrete_map={"Recovered": TEAL, "Stable": AMBER},
        labels={"Length_of_Stay": "Length of Stay (days)", "Cost": "Cost ($)"},
    )
    st.plotly_chart(style_fig(fig, height=380), use_container_width=True, config={"displayModeBar": False})
    st.caption("Each point is one patient — bubble size reflects satisfaction score")
    st.markdown('</div>', unsafe_allow_html=True)

    # ---------------- Patient table ----------------
    st.markdown('<div class="section-title">Patient Records</div>', unsafe_allow_html=True)
    st.dataframe(
        df.sort_values("Patient_ID").reset_index(drop=True),
        use_container_width=True,
        height=380,
    )
    st.download_button(
        "Download filtered data (CSV)",
        df.to_csv(index=False).encode("utf-8"),
        "hospital_data_filtered.csv",
        "text/csv",
    )

    st.divider()
    st.caption("Demo analytics dashboard. Not intended for diagnosis, treatment, or clinical decision-making.")

except Exception as e:
    st.error(f"Error loading dashboard: {str(e)}")
