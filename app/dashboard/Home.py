import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from app.dashboard.utils import hospital_data as data

st.set_page_config(
    page_title="HealthGuard AI | Hospital Outcomes",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------- Palette ----------------
BG = "#0B1220"
SIDEBAR_BG = "#0D1526"
CARD_BG = "#141B2D"
CARD_BORDER = "#1F2A44"
TEXT = "#E8ECF4"
MUTED = "#8B95A7"
INDIGO = "#6366F1"
CYAN = "#22D3EE"
GREEN = "#34D399"
AMBER = "#FBBF24"
RED = "#F87171"

st.markdown(f"""
<style>
[data-testid="stAppViewContainer"] {{
    background: {BG};
}}
[data-testid="stHeader"] {{
    background: {BG};
}}
[data-testid="stSidebar"] {{
    background: {SIDEBAR_BG};
    border-right: 1px solid {CARD_BORDER};
}}
[data-testid="stSidebar"] * {{
    color: {TEXT} !important;
}}
.block-container {{
    padding-top: 1.4rem;
    padding-bottom: 3rem;
    max-width: 1400px;
}}
html, body, [class*="css"] {{
    font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
    color: {TEXT};
}}
.hg-brand {{
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.2rem;
}}
.hg-brand-title {{
    font-size: 1.3rem;
    font-weight: 800;
    color: {TEXT};
}}
.hg-brand-sub {{
    color: {MUTED};
    font-size: 0.78rem;
    margin-bottom: 1.2rem;
}}
.hg-page-title {{
    font-size: 1.7rem;
    font-weight: 800;
    color: {TEXT};
}}
.hg-page-sub {{
    color: {MUTED};
    font-size: 0.92rem;
    margin-bottom: 1.3rem;
}}
.kpi-card {{
    background: {CARD_BG};
    border: 1px solid {CARD_BORDER};
    border-radius: 16px;
    padding: 1.1rem 1.2rem;
    height: 100%;
}}
.kpi-icon {{
    width: 38px; height: 38px;
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.1rem;
    margin-bottom: 0.6rem;
}}
.kpi-label {{
    color: {MUTED};
    font-size: 0.78rem;
    font-weight: 600;
    margin-bottom: 0.15rem;
}}
.kpi-value {{
    color: {TEXT};
    font-size: 1.55rem;
    font-weight: 800;
    line-height: 1.1;
}}
.section-title {{
    color: {TEXT};
    font-size: 1.1rem;
    font-weight: 700;
    margin: 1.6rem 0 0.7rem 0;
}}
.chart-card {{
    background: {CARD_BG};
    border: 1px solid {CARD_BORDER};
    border-radius: 16px;
    padding: 1.1rem 1.2rem 0.4rem 1.2rem;
}}
.card-heading {{
    color: {TEXT};
    font-weight: 700;
    font-size: 0.98rem;
    margin-bottom: 0.6rem;
}}
.profile-row {{
    display: flex;
    justify-content: space-between;
    padding: 0.4rem 0;
    border-bottom: 1px solid {CARD_BORDER};
    font-size: 0.88rem;
}}
.profile-row:last-child {{ border-bottom: none; }}
.profile-label {{ color: {MUTED}; }}
.profile-value {{ color: {TEXT}; font-weight: 600; }}
.badge {{
    display: inline-block;
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 700;
}}
[data-testid="stMetricValue"] {{ color: {TEXT}; }}
hr {{ border-color: {CARD_BORDER}; }}
</style>
""", unsafe_allow_html=True)

CHART_FONT = dict(family="-apple-system, Segoe UI, Roboto, sans-serif", color=TEXT, size=12)


def style_fig(fig, height=340, legend=True):
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=25, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=CHART_FONT,
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color=TEXT)),
    )
    fig.update_xaxes(gridcolor=CARD_BORDER, zeroline=False, color=MUTED)
    fig.update_yaxes(gridcolor=CARD_BORDER, zeroline=False, color=MUTED)
    return fig


try:
    raw = data.load_patients()

    with st.sidebar:
        st.markdown(f"""
        <div class="hg-brand">
            <div style="font-size:1.5rem;">🛡️</div>
            <div class="hg-brand-title">HealthGuard AI</div>
        </div>
        <div class="hg-brand-sub">Hospital Outcomes Intelligence</div>
        """, unsafe_allow_html=True)
        st.markdown("##### Filters")
        conditions = st.multiselect("Condition", sorted(raw.Condition.unique()))
        genders = st.multiselect("Gender", sorted(raw.Gender.unique()))
        outcomes = st.multiselect("Outcome", sorted(raw.Outcome.unique()))
        age_range = st.slider(
            "Age range",
            int(raw.Age.min()), int(raw.Age.max()),
            (int(raw.Age.min()), int(raw.Age.max()))
        )
        st.caption(f"{len(raw)} patients in dataset")

    df = data.apply_filters(raw, conditions, genders, outcomes, age_range)

    st.markdown('<div class="hg-page-title">Dashboard</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="hg-page-sub">Cohort analytics across {len(df)} of {len(raw)} patients</div>', unsafe_allow_html=True)

    if df.empty:
        st.warning("No patients match the current filters.")
        st.stop()

    kpis = data.get_kpis(df)

    # ---------------- KPI row ----------------
    k = st.columns(4)
    kpi_specs = [
        ("👥", INDIGO, "TOTAL PATIENTS", f"{kpis['total_patients']:,}"),
        ("💰", CYAN, "AVG COST / PATIENT", f"${kpis['avg_cost']:,.0f}"),
        ("🛏️", AMBER, "AVG LENGTH OF STAY", f"{kpis['avg_los']} days"),
        ("↩️", RED if kpis['readmission_rate'] > 30 else AMBER, "READMISSION RATE", f"{kpis['readmission_rate']}%"),
    ]
    for col, (icon, color, label, value) in zip(k, kpi_specs):
        col.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-icon" style="background:{color}22; color:{color};">{icon}</div>
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
        </div>
        """, unsafe_allow_html=True)

    k2 = st.columns(4)
    kpi_specs2 = [
        ("✅", GREEN, "RECOVERED RATE", f"{kpis['recovered_rate']}%"),
        ("⭐", CYAN, "AVG SATISFACTION", f"{kpis['avg_satisfaction']} / 5"),
        ("🩺", INDIGO, "CONDITIONS TRACKED", f"{df.Condition.nunique()}"),
        ("📊", AMBER, "AVG AGE", f"{kpis['avg_age']}"),
    ]
    for col, (icon, color, label, value) in zip(k2, kpi_specs2):
        col.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-icon" style="background:{color}22; color:{color};">{icon}</div>
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
        </div>
        """, unsafe_allow_html=True)

    # ---------------- Distribution + condition volume ----------------
    st.markdown('<div class="section-title">Patient Distribution</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.3, 1])

    with c1:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Outcome Distribution</div>', unsafe_allow_html=True)
        fig = px.pie(
            df, names="Outcome", hole=0.62,
            color="Outcome",
            color_discrete_map={"Recovered": GREEN, "Stable": AMBER},
        )
        fig.update_traces(textinfo="percent+label", textfont_color=TEXT)
        st.plotly_chart(style_fig(fig, height=330), use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Average Cost by Condition</div>', unsafe_allow_html=True)
        cond_summary = data.condition_summary(df)
        cs = cond_summary.sort_values("avg_cost", ascending=False)
        fig = px.bar(
            cs, x="Condition", y="avg_cost",
            color_discrete_sequence=[INDIGO],
            labels={"avg_cost": "Avg Cost ($)", "Condition": ""},
        )
        fig.update_traces(marker_line_width=0)
        fig.update_xaxes(tickangle=-40)
        st.plotly_chart(style_fig(fig, height=330, legend=False), use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    with c3:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Top Conditions by Volume</div>', unsafe_allow_html=True)
        top = cond_summary.sort_values("patients", ascending=False).head(6)
        max_p = top.patients.max()
        rows = ""
        colors = [INDIGO, CYAN, GREEN, AMBER, RED, "#A78BFA"]
        for i, (_, r) in enumerate(top.iterrows()):
            pct = round(r.patients / max_p * 100)
            share = round(r.patients / len(df) * 100, 1)
            color = colors[i % len(colors)]
            rows += f"""
            <div style="margin-bottom:0.55rem;">
                <div style="display:flex; justify-content:space-between; font-size:0.82rem; margin-bottom:0.2rem;">
                    <span style="color:{TEXT};">{r.Condition}</span>
                    <span style="color:{MUTED};">{share}%</span>
                </div>
                <div style="background:{CARD_BORDER}; border-radius:6px; height:6px;">
                    <div style="background:{color}; width:{pct}%; height:6px; border-radius:6px;"></div>
                </div>
            </div>
            """
        st.markdown(rows, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ---------------- Readmission + demographics ----------------
    st.markdown('<div class="section-title">Readmissions & Demographics</div>', unsafe_allow_html=True)
    c4, c5, c6 = st.columns(3)

    with c4:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Readmission Rate by Condition</div>', unsafe_allow_html=True)
        cs2 = cond_summary.sort_values("readmission_rate", ascending=False)
        fig = px.bar(
            cs2, x="Condition", y="readmission_rate",
            color="readmission_rate",
            color_continuous_scale=[GREEN, AMBER, RED],
            labels={"readmission_rate": "Rate (%)", "Condition": ""},
        )
        fig.update_xaxes(tickangle=-40)
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(style_fig(fig, height=320, legend=False), use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    with c5:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Age Distribution</div>', unsafe_allow_html=True)
        fig = px.histogram(df, x="Age", nbins=15, color_discrete_sequence=[CYAN])
        st.plotly_chart(style_fig(fig, height=320, legend=False), use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    with c6:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Gender Split</div>', unsafe_allow_html=True)
        fig = px.pie(df, names="Gender", hole=0.62, color_discrete_sequence=[INDIGO, AMBER])
        fig.update_traces(textinfo="percent+label", textfont_color=TEXT)
        st.plotly_chart(style_fig(fig, height=320), use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    # ---------------- Patient lookup + records ----------------
    st.markdown('<div class="section-title">Patient Lookup</div>', unsafe_allow_html=True)
    p1, p2 = st.columns([1, 1.6])

    with p1:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Patient Profile</div>', unsafe_allow_html=True)
        pid = st.selectbox("Patient ID", sorted(df.Patient_ID.tolist()))
        prof = data.patient_profile(df, pid)
        if prof:
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=prof["cost_percentile"],
                number={"suffix": "%", "font": {"color": TEXT, "size": 28}},
                gauge={
                    "axis": {"range": [0, 100], "tickcolor": MUTED},
                    "bar": {"color": INDIGO},
                    "bgcolor": CARD_BG,
                    "borderwidth": 0,
                    "steps": [
                        {"range": [0, 50], "color": "#1E2A44"},
                        {"range": [50, 80], "color": "#2A2440"},
                        {"range": [80, 100], "color": "#3A1F2E"},
                    ],
                },
            ))
            fig.update_layout(
                height=190, margin=dict(l=20, r=20, t=10, b=0),
                paper_bgcolor="rgba(0,0,0,0)", font=CHART_FONT,
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.caption("Cost percentile vs. cohort")

            outcome_color = GREEN if prof["outcome"] == "Recovered" else AMBER
            readmit_color = RED if prof["readmission"] == "Yes" else GREEN
            st.markdown(f"""
            <div class="profile-row"><span class="profile-label">Age / Gender</span><span class="profile-value">{prof['age']} · {prof['gender']}</span></div>
            <div class="profile-row"><span class="profile-label">Condition</span><span class="profile-value">{prof['condition']}</span></div>
            <div class="profile-row"><span class="profile-label">Procedure</span><span class="profile-value">{prof['procedure']}</span></div>
            <div class="profile-row"><span class="profile-label">Cost</span><span class="profile-value">${prof['cost']:,}</span></div>
            <div class="profile-row"><span class="profile-label">Length of Stay</span><span class="profile-value">{prof['los']} days</span></div>
            <div class="profile-row"><span class="profile-label">Outcome</span><span class="badge" style="background:{outcome_color}22; color:{outcome_color};">{prof['outcome']}</span></div>
            <div class="profile-row"><span class="profile-label">Readmission</span><span class="badge" style="background:{readmit_color}22; color:{readmit_color};">{prof['readmission']}</span></div>
            <div class="profile-row"><span class="profile-label">Satisfaction</span><span class="profile-value">{prof['satisfaction']} / 5</span></div>
            """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with p2:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Patient Records</div>', unsafe_allow_html=True)
        st.dataframe(
            df.sort_values("Patient_ID").reset_index(drop=True),
            use_container_width=True,
            height=430,
        )
        st.download_button(
            "Download filtered data (CSV)",
            df.to_csv(index=False).encode("utf-8"),
            "hospital_data_filtered.csv",
            "text/csv",
        )
        st.markdown('</div>', unsafe_allow_html=True)

    st.divider()
    st.caption("Demo analytics dashboard. Not intended for diagnosis, treatment, or clinical decision-making.")

except Exception as e:
    st.error(f"Error loading dashboard: {str(e)}")
