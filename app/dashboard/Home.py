import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from app.dashboard.utils import hospital_data as data
from app.dashboard.utils import ai_risk
from app.dashboard.utils import simple_qa
from app.dashboard.utils import gemini_ai

st.set_page_config(
    page_title="HealthGuard AI | Hospital Outcomes",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------- Palette ----------------
BG = "#0B1220"
SIDEBAR_BG = "#0D1526"
CARD_BG = "#182240"
CARD_BORDER = "#31446E"
TEXT = "#E8ECF4"
MUTED = "#9AA7BD"
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
    padding-top: 2.6rem;
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
    line-height: 1.35;
    padding-top: 0.2rem;
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
    font-size: 1.02rem;
    margin-bottom: 0.8rem;
    padding-left: 0.6rem;
    border-left: 3px solid {CYAN};
    line-height: 1.3;
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
[data-testid="stMarkdown"] p,
[data-testid="stMarkdown"] li,
[data-testid="stMarkdown"] strong,
[data-testid="stMarkdown"] span {{
    color: {TEXT} !important;
}}
[data-testid="stTabs"] {{ gap: 0.45rem; }}
[data-testid="stTabs"] [role="tab"] {{
    background: #1D2B4A !important;
    border: 1px solid #46598A !important;
    border-radius: 12px;
    padding: 0.55rem 1.15rem;
    font-weight: 700;
    box-shadow: 0 2px 6px rgba(0,0,0,0.35);
}}
[data-testid="stTabs"] [role="tab"],
[data-testid="stTabs"] [role="tab"] * {{
    color: #FFFFFF !important;
}}
[data-testid="stTabs"] [role="tab"]:hover {{
    background: #2A3B66 !important;
}}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{
    background: #2A3B66 !important;
    border: 1px solid {CYAN} !important;
    border-bottom: 3px solid {CYAN} !important;
    box-shadow: 0 0 14px rgba(34, 211, 238, 0.25);
}}
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


@st.cache_data
def cohort_shap_importance(df: pd.DataFrame) -> pd.Series:
    """Mean |SHAP| per feature across the (filtered) cohort — shared logic with
    scripts/cohort_shap_analysis.py, which generates reports/cohort_shap.md."""
    model, encoders = ai_risk.load_model()
    explainer = ai_risk.load_explainer()
    enc = ai_risk._encode(df, encoders)
    X = enc[ai_risk.FEATURES]
    shap_vals = explainer.shap_values(X)
    if isinstance(shap_vals, list):
        vals = shap_vals[1]
    elif np.ndim(shap_vals) == 3:
        vals = shap_vals[:, :, 1]
    else:
        vals = shap_vals
    return pd.Series(np.abs(vals).mean(axis=0), index=ai_risk.FEATURES).sort_values()


def kpi_card(col, icon, color, label, value):
    col.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-icon" style="background:{color}22; color:{color};">{icon}</div>
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
    </div>
    """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB RENDERERS
# ════════════════════════════════════════════════════════════════════════════

def render_overview(df, kpis, cond_summary):
    # ---- KPI rows (8 cards) ----
    k = st.columns(4)
    kpi_card(k[0], "👥", INDIGO, "TOTAL PATIENTS", f"{kpis['total_patients']:,}")
    kpi_card(k[1], "💰", CYAN, "AVG COST / PATIENT", f"₹{kpis['avg_cost']:,.0f}")
    kpi_card(k[2], "🛏️", AMBER, "AVG LENGTH OF STAY", f"{kpis['avg_los']} days")
    kpi_card(k[3], "↩️", RED if kpis['readmission_rate'] > 30 else AMBER, "READMISSION RATE", f"{kpis['readmission_rate']}%")

    k2 = st.columns(4)
    kpi_card(k2[0], "✅", GREEN, "RECOVERED RATE", f"{kpis['recovered_rate']}%")
    kpi_card(k2[1], "⭐", CYAN, "AVG SATISFACTION", f"{kpis['avg_satisfaction']} / 5")
    kpi_card(k2[2], "🩺", INDIGO, "CONDITIONS TRACKED", f"{df.Condition.nunique()}")
    kpi_card(k2[3], "📊", AMBER, "AVG AGE", f"{kpis['avg_age']}")

    # ---- Distribution + condition volume ----
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
        st.plotly_chart(style_fig(fig, height=330), width='stretch', config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Average Cost by Condition</div>', unsafe_allow_html=True)
        cs = cond_summary.sort_values("avg_cost", ascending=False)
        fig = px.bar(
            cs, x="Condition", y="avg_cost",
            color_discrete_sequence=[INDIGO],
            labels={"avg_cost": "Avg Cost (₹)", "Condition": ""},
        )
        fig.update_traces(marker_line_width=0)
        fig.update_xaxes(tickangle=-40)
        st.plotly_chart(style_fig(fig, height=330, legend=False), width='stretch', config={"displayModeBar": False})
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

    # ---- Cost & satisfaction distribution ----
    st.markdown('<div class="section-title">Cost & Satisfaction Profiles</div>', unsafe_allow_html=True)
    d1, d2 = st.columns(2)
    with d1:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Cost Distribution</div>', unsafe_allow_html=True)
        fig = px.histogram(df, x="Cost", nbins=30, color_discrete_sequence=[CYAN])
        fig.add_vline(x=df.Cost.mean(), line_dash="dash", line_color=AMBER,
                      annotation_text=f"mean ₹{df.Cost.mean():,.0f}")
        st.plotly_chart(style_fig(fig, height=300, legend=False), width='stretch', config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)
    with d2:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Satisfaction Distribution</div>', unsafe_allow_html=True)
        sat = df.Satisfaction.value_counts().sort_index().rename_axis("Satisfaction").reset_index(name="patients")
        fig = px.bar(sat, x="Satisfaction", y="patients",
                     color_discrete_sequence=[GREEN])
        fig.update_traces(marker_line_width=0)
        st.plotly_chart(style_fig(fig, height=300, legend=False), width='stretch', config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    # ---- Computed insight callout ----
    top_readmit = cond_summary.sort_values("readmission_rate", ascending=False).head(2)
    r1_name, r1_rate = top_readmit.iloc[0]["Condition"], top_readmit.iloc[0]["readmission_rate"]
    try:
        r2_name, r2_rate = top_readmit.iloc[1]["Condition"], top_readmit.iloc[1]["readmission_rate"]
        readmit_line = f"**{r1_name}** ({r1_rate}%) and **{r2_name}** ({r2_rate}%) drive readmissions"
    except IndexError:
        readmit_line = f"**{r1_name}** ({r1_rate}%) drives readmissions"
    priciest = cond_summary.sort_values("avg_cost", ascending=False).iloc[0]
    st.info(
        f"📌 **What the data says (computed live):** {readmit_line}. "
        f"The priciest pathway is **{priciest.Condition}** at ₹{priciest.avg_cost:,.0f} average cost. "
        f"Average satisfaction is **{kpis['avg_satisfaction']}/5** across {kpis['total_patients']:,} patients."
    )


def render_clinical(df, cond_summary):
    st.markdown('<div class="section-title">Readmission Analytics</div>', unsafe_allow_html=True)
    c4, c5 = st.columns(2)

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
        st.plotly_chart(style_fig(fig, height=330, legend=False), width='stretch', config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    with c5:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Readmission Rate by Procedure (top 10 by volume)</div>', unsafe_allow_html=True)
        proc = df.groupby("Procedure").agg(
            patients=("Patient_ID", "count"),
            readmissions=("Readmission", lambda s: (s == "Yes").sum()),
        ).reset_index()
        proc["readmission_rate"] = (proc["readmissions"] / proc["patients"] * 100).round(1)
        proc = proc.sort_values("patients", ascending=False).head(10).sort_values("readmission_rate")
        fig = px.bar(
            proc, y="Procedure", x="readmission_rate", orientation="h",
            color_discrete_sequence=[RED], text=proc["readmission_rate"],
            labels={"readmission_rate": "Rate (%)", "Procedure": ""},
        )
        fig.update_traces(textposition="outside", marker_line_width=0)
        st.plotly_chart(style_fig(fig, height=330, legend=False), width='stretch', config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    c6, c7 = st.columns(2)
    with c6:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Readmission Rate by Age Group</div>', unsafe_allow_html=True)
        age_df = df.copy()
        age_df["Age Group"] = pd.cut(
            age_df["Age"], bins=[0, 30, 45, 60, 120],
            labels=["<30", "30–44", "45–59", "60+"],
        )
        ag = age_df.groupby("Age Group", observed=True).agg(
            patients=("Patient_ID", "count"),
            readmissions=("Readmission", lambda s: (s == "Yes").sum()),
        ).reset_index()
        ag["readmission_rate"] = (ag["readmissions"] / ag["patients"] * 100).round(1)
        fig = px.bar(ag, x="Age Group", y="readmission_rate",
                     color_discrete_sequence=[AMBER], text=ag["readmission_rate"],
                     labels={"readmission_rate": "Rate (%)", "Age Group": ""})
        fig.update_traces(textposition="outside", marker_line_width=0)
        st.plotly_chart(style_fig(fig, height=300, legend=False), width='stretch', config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    with c7:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Average Length of Stay by Condition</div>', unsafe_allow_html=True)
        los = cond_summary.sort_values("avg_los", ascending=False)
        fig = px.bar(
            los, x="Condition", y="avg_los",
            color_discrete_sequence=[CYAN],
            labels={"avg_los": "Avg days", "Condition": ""},
        )
        fig.update_traces(marker_line_width=0)
        fig.update_xaxes(tickangle=-40)
        st.plotly_chart(style_fig(fig, height=300, legend=False), width='stretch', config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    # ---- Demographics ----
    st.markdown('<div class="section-title">Demographics</div>', unsafe_allow_html=True)
    c8, c9, c10 = st.columns(3)
    with c8:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Age Distribution</div>', unsafe_allow_html=True)
        fig = px.histogram(df, x="Age", nbins=15, color_discrete_sequence=[CYAN])
        st.plotly_chart(style_fig(fig, height=300, legend=False), width='stretch', config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)
    with c9:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Gender Split</div>', unsafe_allow_html=True)
        fig = px.pie(df, names="Gender", hole=0.62, color_discrete_sequence=[INDIGO, AMBER])
        fig.update_traces(textinfo="percent+label", textfont_color=TEXT)
        st.plotly_chart(style_fig(fig, height=300), width='stretch', config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)
    with c10:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Avg Cost by Outcome</div>', unsafe_allow_html=True)
        oc = df.groupby("Outcome").agg(
            patients=("Patient_ID", "count"),
            avg_cost=("Cost", "mean"),
        ).reset_index()
        fig = px.bar(oc, x="Outcome", y="avg_cost",
                     color_discrete_sequence=[GREEN, AMBER],
                     text=oc["avg_cost"].round(0),
                     labels={"avg_cost": "Avg cost (₹)", "Outcome": ""})
        fig.update_traces(textposition="outside", marker_line_width=0)
        st.plotly_chart(style_fig(fig, height=300, legend=False), width='stretch', config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    # ---- Cohort explainability ----
    st.markdown('<div class="section-title">Model Explainability — What Drives Risk Across This Cohort</div>', unsafe_allow_html=True)
    e1, e2 = st.columns([1.5, 1])
    with e1:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Average influence per factor (mean |SHAP|)</div>', unsafe_allow_html=True)
        try:
            imp = cohort_shap_importance(df)
            total = imp.sum()
            imp_df = pd.DataFrame({
                "Factor": [ai_risk.FEATURE_LABELS.get(f, f) for f in imp.index],
                "Share": (imp / total * 100).round(1) if total else 0,
                "value": imp.values,
            })
            fig = px.bar(imp_df, y="Factor", x="Share", orientation="h",
                         color_discrete_sequence=[INDIGO], text=imp_df["Share"],
                         labels={"Share": "Share of total influence (%)", "Factor": ""})
            fig.update_traces(textposition="outside", texttemplate="%{text:.1f}%", marker_line_width=0)
            st.plotly_chart(style_fig(fig, height=310, legend=False), width='stretch', config={"displayModeBar": False})
        except Exception:
            st.caption("Cohort explainability unavailable for this filter — see reports/cohort_shap.md.")
        st.markdown('</div>', unsafe_allow_html=True)
    with e2:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">How to read this</div>', unsafe_allow_html=True)
        st.markdown(
            """
            <p style="color:{TEXT}; font-size:0.88rem; line-height:1.5;">
            Each bar shows how much a factor moves readmission risk scores across
            this cohort, averaged over patients (mean |SHAP|).
            <br><br>
            <b>Why is influence spread out?</b> Procedure, Cost and Condition carry
            the same underlying signal (they follow the condition pathway), so the
            model splits across them and attribution is distributed.
            <br><br>
            <b style="color:{AMBER};">⚠ Honest read:</b> on this synthetic dataset
            the ranking reflects how the data was generated, not clinical evidence.
            Full write-up: <code>reports/cohort_shap.md</code>.
            </p>
            """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)


def render_patients(df):
    # ---- Cohort-level views ----
    st.markdown('<div class="section-title">Cohort Risk & Utilization</div>', unsafe_allow_html=True)
    r1, r2 = st.columns(2)
    with r1:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Readmission Risk Across This Cohort</div>', unsafe_allow_html=True)
        try:
            probs = ai_risk.score_cohort(df)
            fig = px.histogram(x=probs, nbins=25, color_discrete_sequence=[INDIGO],
                               labels={"x": "Modelled readmission probability"})
            low = int((probs < 0.33).sum()); watch = int(((probs >= 0.33) & (probs < 0.66)).sum()); high = int((probs >= 0.66).sum())
            fig.add_vline(x=0.33, line_dash="dot", line_color=AMBER)
            fig.add_vline(x=0.66, line_dash="dot", line_color=RED)
            st.plotly_chart(style_fig(fig, height=290, legend=False), width='stretch', config={"displayModeBar": False})
            st.caption(f"🟢 LOW: {low} · 🟡 WATCH: {watch} · 🔴 HIGH: {high} (thresholds 0.33 / 0.66)")
        except Exception:
            st.caption("Cohort scoring unavailable — see the model note in the AI Assistant tab.")
        st.markdown('</div>', unsafe_allow_html=True)
    with r2:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Cost vs Length of Stay (coloured by readmission)</div>', unsafe_allow_html=True)
        fig = px.scatter(
            df, x="Length_of_Stay", y="Cost", color="Readmission",
            color_discrete_map={"Yes": RED, "No": GREEN},
            opacity=0.55, hover_data=["Patient_Code", "Condition"],
            labels={"Length_of_Stay": "Days", "Cost": "Cost (₹)"},
        )
        st.plotly_chart(style_fig(fig, height=290), width='stretch', config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    # ---- Patient lookup ----
    st.markdown('<div class="section-title">Patient Lookup</div>', unsafe_allow_html=True)
    p1, p2 = st.columns([1, 1.6])

    with p1:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Patient Profile</div>', unsafe_allow_html=True)
        pcode = st.selectbox("Patient Code", sorted(df.Patient_Code.tolist()))
        prof = data.patient_profile(df, pcode)
        if prof:
            row = df[df.Patient_Code == pcode].iloc[0]
            risk = ai_risk.score_patient(row)
            risk_pct = round(risk["risk_score"] * 100, 1)
            tier_color = {"HIGH": RED, "WATCH": AMBER, "LOW": GREEN}[risk["risk_tier"]]

            gauge_col, cost_col = st.columns(2)
            with gauge_col:
                fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=risk_pct,
                    number={"suffix": "%", "font": {"color": TEXT, "size": 24}},
                    gauge={
                        "axis": {"range": [0, 100], "tickcolor": MUTED},
                        "bar": {"color": tier_color},
                        "bgcolor": CARD_BG,
                        "borderwidth": 0,
                        "steps": [
                            {"range": [0, 33], "color": "#12291F"},
                            {"range": [33, 66], "color": "#2E2410"},
                            {"range": [66, 100], "color": "#3A1F1F"},
                        ],
                    },
                ))
                fig.update_layout(
                    height=160, margin=dict(l=10, r=10, t=10, b=0),
                    paper_bgcolor="rgba(0,0,0,0)", font=CHART_FONT,
                )
                st.plotly_chart(fig, width='stretch', config={"displayModeBar": False})
                st.caption(f"AI readmission risk — {risk['risk_tier']}")

            with cost_col:
                fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=prof["cost_percentile"],
                    number={"suffix": "%", "font": {"color": TEXT, "size": 24}},
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
                    height=160, margin=dict(l=10, r=10, t=10, b=0),
                    paper_bgcolor="rgba(0,0,0,0)", font=CHART_FONT,
                )
                st.plotly_chart(fig, width='stretch', config={"displayModeBar": False})
                st.caption("Cost percentile vs. cohort")

            with st.expander("Why this risk score? (top factors)"):
                for f in risk["top_factors"]:
                    direction = "↑ raises risk" if f["impact"] > 0 else "↓ lowers risk"
                    dcolor = RED if f["impact"] > 0 else GREEN
                    st.markdown(
                        f"<div style='display:flex; justify-content:space-between; padding:0.25rem 0; font-size:0.85rem;'>"
                        f"<span>{f['feature']}</span>"
                        f"<span style='color:{dcolor};'>{direction}</span></div>",
                        unsafe_allow_html=True,
                    )
                st.caption("SHAP values from a RandomForest model trained on this dataset "
                           "(Age, Gender, Condition, Procedure, Cost, Length of Stay).")

            outcome_color = GREEN if prof["outcome"] == "Recovered" else AMBER
            readmit_color = RED if prof["readmission"] == "Yes" else GREEN
            st.markdown(f"""
            <div class="profile-row"><span class="profile-label">Patient Code</span><span class="profile-value">{prof['patient_code']}</span></div>
            <div class="profile-row"><span class="profile-label">Age / Gender</span><span class="profile-value">{prof['age']} · {prof['gender']}</span></div>
            <div class="profile-row"><span class="profile-label">Condition</span><span class="profile-value">{prof['condition']}</span></div>
            <div class="profile-row"><span class="profile-label">Procedure</span><span class="profile-value">{prof['procedure']}</span></div>
            <div class="profile-row"><span class="profile-label">Cost</span><span class="profile-value">₹{prof['cost']:,}</span></div>
            <div class="profile-row"><span class="profile-label">Length of Stay</span><span class="profile-value">{prof['los']} days</span></div>
            <div class="profile-row"><span class="profile-label">Outcome</span><span class="badge" style="background:{outcome_color}22; color:{outcome_color};">{prof['outcome']}</span></div>
            <div class="profile-row"><span class="profile-label">Readmission</span><span class="badge" style="background:{readmit_color}22; color:{readmit_color};">{prof['readmission']}</span></div>
            <div class="profile-row"><span class="profile-label">Satisfaction</span><span class="profile-value">{prof['satisfaction']} / 5</span></div>
            """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with p2:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Patient Records</div>', unsafe_allow_html=True)
        display_cols = ["Patient_Code", "Patient_ID"] + [c for c in df.columns if c not in ("Patient_Code", "Patient_ID")]
        st.dataframe(
            df[display_cols].sort_values("Patient_Code").reset_index(drop=True),
            width='stretch',
            height=430,
        )
        st.download_button(
            "Download filtered data (CSV)",
            df[display_cols].to_csv(index=False).encode("utf-8"),
            "hospital_data_filtered.csv",
            "text/csv",
        )
        st.markdown('</div>', unsafe_allow_html=True)


def render_ai(df):
    # ---------------- AI Recommendations ----------------
    st.markdown('<div class="section-title">AI Recommendations</div>', unsafe_allow_html=True)
    st.markdown('<div class="chart-card">', unsafe_allow_html=True)
    if not gemini_ai.is_configured():
        st.info("Gemini API key not configured — set the `GOOGLE_API_KEY` environment "
                "variable to enable AI-generated recommendations.")
    else:
        if st.button("Generate recommendations for this cohort"):
            with st.spinner("Analyzing cohort with Gemini..."):
                ctx = gemini_ai._cohort_context(df)
                df_hash = str(hash((len(df), tuple(sorted(df.Condition.unique())))))
                rec = gemini_ai.generate_recommendations(df_hash, ctx)
            if rec["ok"]:
                st.markdown(rec["text"])
            else:
                st.warning(rec["text"])
        st.caption("Grounded in this filtered cohort's real statistics — Gemini is instructed "
                   "not to invent numbers beyond what's provided.")
    st.markdown('</div>', unsafe_allow_html=True)

    # ---------------- Ask HealthGuard AI ----------------
    st.markdown('<div class="section-title">Ask HealthGuard AI</div>', unsafe_allow_html=True)
    st.markdown('<div class="chart-card">', unsafe_allow_html=True)
    st.caption("Common questions (readmission rate, cost, length of stay, satisfaction, "
               "outcome, patient counts) are answered directly from this dataset with no LLM "
               "involved. Anything else falls back to Gemini, grounded in the same real stats.")
    question = st.text_input("Ask a question about this dataset", placeholder="e.g. What's the readmission rate for Diabetes?")
    if question:
        result = simple_qa.answer(df, question)
        if result["ok"]:
            st.success(result["text"])
        elif gemini_ai.is_configured():
            with st.spinner("Asking Gemini..."):
                gresult = gemini_ai.answer_grounded(df, question)
            if gresult["ok"]:
                st.success(gresult["text"])
            else:
                st.warning(gresult["text"])
        else:
            st.info(result["text"])
    st.markdown('</div>', unsafe_allow_html=True)

    # ---------------- Model quality note ----------------
    with st.expander("About the AI risk model"):
        m = ai_risk.get_metrics()
        if m:
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("ROC AUC", m.get("roc_auc"))
            mc2.metric("Condition-only baseline", m.get("condition_baseline_auc", "—"))
            mc3.metric("Precision", m.get("precision"))
            mc4.metric("Recall", m.get("recall"))
        st.caption(
            "This is a RandomForest classifier trained on this dataset's own columns "
            "(Age, Gender, Condition, Procedure, Cost, Length of Stay) to predict the "
            "Readmission field. Accuracy looks very high because Condition alone is "
            "an almost perfect predictor of Readmission in this specific dataset — "
            "consistent with it being a synthetic/demo dataset rather than noisy real-world "
            "clinical data. For scale: a trivial Condition-only lookup table (no ML) already "
            "scores ~0.93 AUC here, while real-world clinical readmission models typically "
            "achieve 0.65–0.75. The quantified audit lives in reports/model_honesty.md "
            "(run scripts/model_honesty_audit.py to regenerate it). Treat this as a "
            "demonstration of the technique, not a validated clinical risk model."
        )


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

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

    st.markdown('<div class="hg-page-title">Hospital Outcomes Intelligence Dashboard</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="hg-page-sub">AI-assisted analytics across {len(df)} of {len(raw)} patients — cost, length of stay, readmissions, and outcomes, with per-patient risk scoring and explainability.</div>', unsafe_allow_html=True)

    if df.empty:
        st.warning("No patients match the current filters.")
        st.stop()

    kpis = data.get_kpis(df)
    cond_summary = data.condition_summary(df)

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Executive Overview",
        "🩺 Clinical Analytics",
        "👤 Patient Intelligence",
        "🤖 AI Assistant",
    ])
    with tab1:
        render_overview(df, kpis, cond_summary)
    with tab2:
        render_clinical(df, cond_summary)
    with tab3:
        render_patients(df)
    with tab4:
        render_ai(df)

    st.divider()
    st.caption("Demo analytics dashboard. Not intended for diagnosis, treatment, or clinical decision-making.")

except Exception as e:
    st.error(f"Error loading dashboard: {str(e)}")
