import sys
import logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from app.dashboard.utils import hospital_data as data
from app.dashboard.utils import ai_risk
from app.dashboard.utils import gemini_ai
from app.dashboard.utils import ops_layer

if getattr(ops_layer, "COMPARISON_SCHEMA_VERSION", 0) != 2:
    from importlib import reload
    ops_layer = reload(ops_layer)

st.set_page_config(
    page_title="HealthGuard AI | Hospital Outcomes",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

def display_stat(value, kind="money"):
    """Missing comparison groups are not measured zero-cost/zero-stay groups."""
    if value is None or pd.isna(value):
        return "Not available"
    if kind == "money":
        return f"₹{value:,.0f}"
    if kind == "percent":
        return f"{value:+.1f}%"
    if kind == "difference":
        return f"{value:+.1f}d"
    return f"{value:.1f}d"


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
.chart-card:empty {{ display: none; }}
[data-testid="stToolbarActionButtonLabel"] {{ color: {TEXT} !important; }}
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
        hoverlabel=dict(bgcolor="#0B1220", bordercolor=CARD_BORDER, font=dict(color=TEXT, size=12.5)),
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


def kpi_card(col, icon, color, label, value, context=None):
    ctx = f'<div class="kpi-context">{context}</div>' if context else ""
    col.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-icon" style="background:{color}22; color:{color};">{icon}</div>
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {ctx}
    </div>
    """, unsafe_allow_html=True)


def tab_intro(text):
    """One line under each tab title: the question this page answers."""
    st.markdown(f'<div class="tab-intro">{text}</div>', unsafe_allow_html=True)


def inject_css_v2():
    """Day-4 UI layer: KPI context, tab intros, QA trust chips, filter chips."""
    st.markdown(f"""
<style>
.kpi-context {{
    color: {MUTED};
    font-size: 0.76rem;
    margin-top: 0.35rem;
    line-height: 1.35;
    font-variant-numeric: tabular-nums;
}}
.tab-intro {{
    color: {CYAN};
    font-size: 0.86rem;
    font-weight: 600;
    margin: -0.2rem 0 1.0rem 0;
}}
.qa-trust {{
    display: inline-block;
    font-size: 0.74rem;
    font-weight: 700;
    color: {GREEN};
    background: rgba(52, 211, 153, 0.10);
    border: 1px solid rgba(52, 211, 153, 0.35);
    border-radius: 999px;
    padding: 3px 11px;
    margin-top: 0.4rem;
}}
.fchip {{
    display: inline-block;
    font-size: 0.74rem;
    font-weight: 700;
    color: {CYAN};
    background: rgba(34, 211, 238, 0.10);
    border: 1px solid rgba(34, 211, 238, 0.35);
    border-radius: 999px;
    padding: 3px 11px;
    margin: 2px 4px 2px 0;
}}
.fchips-wrap {{ margin: 6px 0 2px; }}
[data-testid="stDataFrame"] {{ font-size: 0.84rem; }}
</style>
""", unsafe_allow_html=True)


def filter_chips(conditions, genders, outcomes, age_range, raw):
    """Active-scope chips for the sidebar filters."""
    chips = []
    if conditions:
        chips.append(f"Condition: {', '.join(conditions)}")
    if genders:
        chips.append(f"Gender: {', '.join(genders)}")
    if outcomes:
        chips.append(f"Outcome: {', '.join(outcomes)}")
    full_range = (int(raw.Age.min()), int(raw.Age.max()))
    if tuple(age_range) != full_range:
        chips.append(f"Age: {age_range[0]}–{age_range[1]}")
    if chips:
        html = "".join(f'<span class="fchip">{c}</span>' for c in chips)
        st.sidebar.markdown(f'<div class="fchips-wrap">{html}</div>', unsafe_allow_html=True)
    else:
        st.sidebar.markdown(
            f'<div class="fchips-wrap"><span style="font-size:0.78rem;color:{MUTED};">'
            f'No filters active — all {len(raw):,} patients in scope</span></div>',
            unsafe_allow_html=True,
        )


# ════════════════════════════════════════════════════════════════════════════
# TAB RENDERERS
# ════════════════════════════════════════════════════════════════════════════

def render_overview(df, kpis, cond_summary):
    tab_intro("Review volumes, recorded costs and outcomes for the selected synthetic cohort.")

    # ---- KPI rows (8 cards, each with one line of context) ----
    ops = ops_layer.ops_context(df)
    n_readmitted = int((df.Readmission == "Yes").sum())
    n_recovered = int((df.Outcome == "Recovered").sum())

    k = st.columns(4)
    kpi_card(k[0], "👥", INDIGO, "TOTAL PATIENTS", f"{kpis['total_patients']:,}",
             context="current filter scope")
    kpi_card(k[1], "💰", CYAN, "AVG COST / PATIENT", f"₹{kpis['avg_cost']:,.0f}",
             context=f"total ₹{kpis['total_cost']:,.0f} across cohort")
    kpi_card(k[2], "🛏️", AMBER, "AVG LENGTH OF STAY", f"{kpis['avg_los']} days",
             context="recorded days per synthetic row")
    kpi_card(k[3], "↩️", RED if kpis['readmission_rate'] > 30 else AMBER, "READMISSION RATE", f"{kpis['readmission_rate']}%",
             context=f"{n_readmitted:,} patients readmitted")

    k2 = st.columns(4)
    kpi_card(k2[0], "✅", GREEN, "RECOVERED RATE", f"{kpis['recovered_rate']}%",
             context=f"{n_recovered:,} patients recovered")
    kpi_card(k2[1], "⭐", CYAN, "AVG SATISFACTION", f"{kpis['avg_satisfaction']} / 5",
             context="self-reported, scale of 5")
    kpi_card(k2[2], "🩺", INDIGO, "CONDITIONS TRACKED", f"{df.Condition.nunique()}",
             context="in current filter scope")
    kpi_card(k2[3], "📊", AMBER, "AVG AGE", f"{kpis['avg_age']}",
             context=f"range {int(df.Age.min())}–{int(df.Age.max())} years")

    # ---- Day-3 ops layer: what readmissions cost (computed, not assumed) ----
    ops = ops_layer.ops_context(df)
    facts = ops_layer.load_model_facts()
    st.markdown('<div class="section-title">Operations Context — recorded cost and readmission flags</div>',
                unsafe_allow_html=True)
    o1, o2, o3 = st.columns(3)
    with o1:
        st.markdown(
            f"""<div style="border:1px solid rgba(248,113,113,0.35); border-radius:10px;
                 padding:12px 14px; background:rgba(248,113,113,0.07);">
              <div style="font-size:0.95rem; font-weight:700; color:{TEXT};">
                {ops['readmitted_n']} readmitted patients hold ₹{ops['readmitted_total_cost']:,.0f}
                — {ops['readmitted_cost_share_pct']}% of all cost</div>
              <div style="font-size:0.8rem; color:{MUTED}; margin-top:4px;">
                {ops['readmission_rate_pct']}% of patients, {ops['readmitted_cost_share_pct']}% of spend —
                association, not causation (disclosed in data/metrics.json)</div>
            </div>""", unsafe_allow_html=True)
    with o2:
        st.markdown(
            f"""<div style="border:1px solid {CARD_BORDER}; border-radius:10px;
                 padding:12px 14px; background:rgba(251,191,36,0.06);">
              <div style="font-size:0.95rem; font-weight:700; color:{TEXT};">
                Readmitted cost {display_stat(ops['readmitted_avg_cost'])} vs {display_stat(ops['non_readmitted_avg_cost'])}
                ({display_stat(ops['cost_premium_pct'], 'percent')})</div>
              <div style="font-size:0.8rem; color:{MUTED}; margin-top:4px;">
                Avg length of stay {display_stat(ops['readmitted_avg_los'], 'days')} vs {display_stat(ops['non_readmitted_avg_los'], 'days')}
                ({display_stat(ops['los_premium_days'], 'difference')}) — observed length-of-stay difference</div>
            </div>""", unsafe_allow_html=True)
    with o3:
        top_cond = ops_layer.readmission_by_condition(df).iloc[0]
        st.markdown(
            f"""<div style="border:1px solid rgba(99,102,241,0.4); border-radius:10px;
                 padding:12px 14px; background:rgba(99,102,241,0.07);">
              <div style="font-size:0.95rem; font-weight:700; color:{TEXT};">
                Highest readmission rate: {top_cond['Condition']} ({top_cond['readmit_rate_pct']:.1f}%)</div>
              <div style="font-size:0.8rem; color:{MUTED}; margin-top:4px;">
                {int(top_cond['patients'])} patients — drill into condition and age bands on the
                Condition & Age tab</div>
            </div>""", unsafe_allow_html=True)

    with st.expander("Model evaluation — supporting evidence", expanded=False):
        # ---- Fairness strip (model-derived disclosures from the audit) ----
        st.markdown('<div class="section-title">Fairness &amp; Model Honesty (from the model audit)</div>',
                    unsafe_allow_html=True)
        f1, f2 = st.columns(2)
        fair = facts["fairness"]
        hon = facts["model_honesty"]
        with f1:
            st.markdown(
                f"""<div style="border:1px solid {CARD_BORDER}; border-radius:10px; padding:12px 14px;">
                  <div style="font-size:0.9rem; font-weight:700; color:{TEXT};">
                    Fairness: AUC gap {fair['auc_gap_gender']} (gender) · {fair['auc_gap_age']} (age)</div>
                  <div style="font-size:0.8rem; color:{MUTED}; margin-top:4px;">
                    Disclosed: readmission base rate is {fair['base_rate_female_pct']}% (Female) vs
                    {fair['base_rate_male_pct']}% (Male) — a {fair['base_rate_gap_pp']}-point dataset property.
                    Parity in one metric is not fairness.</div>
                </div>""", unsafe_allow_html=True)
        with f2:
            st.markdown(
                f"""<div style="border:1px solid {CARD_BORDER}; border-radius:10px; padding:12px 14px;">
                  <div style="font-size:0.9rem; font-weight:700; color:{TEXT};">
                    Model honesty: AUC {hon['shipped_rf_auc']} vs {hon['condition_only_baseline_auc']} no-ML baseline</div>
                  <div style="font-size:0.8rem; color:{MUTED}; margin-top:4px;">
                    This result reflects the generated target structure and does not establish
                    clinical performance. See reports/model_honesty.md.</div>
                </div>""", unsafe_allow_html=True)

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
        readmit_line = f"**{r1_name}** ({r1_rate:.1f}%) and **{r2_name}** ({r2_rate:.1f}%) have the highest observed readmission rates"
    except IndexError:
        readmit_line = f"**{r1_name}** ({r1_rate:.1f}%) is the only condition in this filtered view"
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
    tab_intro("Which patients carry the highest predicted risk — and what drives each score (SHAP)?")
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
                st.caption(f"Synthetic-model score — {risk['risk_tier']} (not a clinical prediction)")

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


def render_ops_drill(df):
    """Day-3 root-cause drill: readmission -> condition -> age band -> cost/LOS.
    Every number computed live from the filtered scope by ops_layer.py."""
    overall = ops_layer.ops_context(df)
    by_cond = ops_layer.readmission_by_condition(df)
    if not len(by_cond):
        st.info("No patients match the current filters.")
        return

    st.markdown('<div class="section-title">Condition & Age — readmission &rarr; condition &rarr; age band</div>',
                unsafe_allow_html=True)
    st.caption(
        f"Selected cohort: {overall['readmission_rate_pct']}% readmission "
        f"({overall['readmitted_n']} of {overall['total_patients']}) — now drill into WHERE it concentrates."
    )

    cond = st.selectbox(
        "Condition (sorted by readmission rate, highest first)",
        by_cond["Condition"].tolist(), index=0,
    )
    prof = ops_layer.condition_profile(df, cond)
    by_band = ops_layer.readmission_by_age_band(df, cond)
    bands_with_data = by_band[by_band["patients"] > 0]
    worst = bands_with_data.sort_values("readmit_rate_pct", ascending=False).iloc[0] if len(bands_with_data) else None

    # breadcrumb
    crumb = (
        f"**Selected cohort {overall['readmission_rate_pct']}%** &rarr; "
        f"**{cond} {prof['readmit_rate_pct']}%** (n={prof['patients']})"
    )
    if worst is not None and len(bands_with_data) > 1:
        crumb += f" &rarr; **{worst['Age_Band']} {worst['readmit_rate_pct']}%** (n={int(worst['patients'])})"
    st.markdown(crumb)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="card-heading">Readmission rate by condition</div>', unsafe_allow_html=True)
        colors = [RED if c == cond else CARD_BORDER for c in by_cond["Condition"]]
        fig = px.bar(
            by_cond, x="Condition", y="readmit_rate_pct",
            color_discrete_sequence=[INDIGO], labels={"readmit_rate_pct": "Readmission %", "Condition": ""},
        )
        fig.update_traces(marker_color=colors, marker_line_width=0)
        fig.update_xaxes(tickangle=-40)
        st.plotly_chart(style_fig(fig, height=340, legend=False), width='stretch',
                        config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="card-heading">Readmission by age band — {cond}</div>', unsafe_allow_html=True)
        fig = px.bar(
            by_band, x="Age_Band", y="readmit_rate_pct",
            color_discrete_sequence=[CYAN],
            labels={"readmit_rate_pct": "Readmission %", "Age_Band": ""},
        )
        if worst is not None:
            fig.update_traces(
                marker_color=[RED if b == worst["Age_Band"] else CYAN for b in by_band["Age_Band"]],
                marker_line_width=0)
        else:
            fig.update_traces(marker_line_width=0)
        st.plotly_chart(style_fig(fig, height=340, legend=False), width='stretch',
                        config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    # cost / LOS profile for the selected condition
    p1, p2, p3 = st.columns(3)
    kpi_card(p1, "💰", RED if prof["readmit_rate_pct"] > overall["readmission_rate_pct"] else GREEN,
             "READMITTED AVG COST", display_stat(prof['readmitted_avg_cost']))
    kpi_card(p2, "💰", GREEN, "NON-READMITTED AVG COST", display_stat(prof['non_readmitted_avg_cost']))
    comparable = prof["readmitted_avg_cost"] is not None and bool(prof["non_readmitted_avg_cost"])
    _prem = ((prof["readmitted_avg_cost"] / prof["non_readmitted_avg_cost"] - 1) * 100
             if comparable else None)
    kpi_card(p3, "📈", AMBER, "COST DIFFERENCE", display_stat(_prem, "percent"))

    # findings (computed sentences — no LLM)
    findings = (
        f"**Findings (computed):** {cond} records are marked readmitted at {prof['readmit_rate_pct']}% versus "
        f"{overall['readmission_rate_pct']}% overall. "
    )
    if worst is not None and len(bands_with_data) > 1:
        findings += (
            f"Within {cond}, the observed rate in the {worst['Age_Band']} band is {worst['readmit_rate_pct']}% "
            f"(n={int(worst['patients'])}). "
        )
    if comparable:
        findings += (
            f"Mean recorded cost: {display_stat(prof['readmitted_avg_cost'])} versus "
            f"{display_stat(prof['non_readmitted_avg_cost'])} ({display_stat(_prem, 'percent')}). "
            f"Mean stays: {display_stat(prof['readmitted_avg_los'], 'days')} versus "
            f"{display_stat(prof['non_readmitted_avg_los'], 'days')}. "
        )
    else:
        findings += "A readmitted/non-readmitted cost comparison is not available because a comparison group is absent or has no usable cost baseline. "
    findings += "Association, not causation — definitions in data/metrics.json."
    st.info(findings)


@st.fragment
def render_workbench(df, reference):
    """Validate -> compare -> execute trusted SQL -> export a stakeholder snapshot."""
    from app.dashboard.utils import analyst_workbench as workbench
    from app.dashboard.utils import assistant_service as assistant
    import importlib
    import json

    # Streamlit can retain imported modules while deploying updated source files.
    if getattr(workbench, "WORKBENCH_VERSION", 0) != 2:
        workbench = importlib.reload(workbench)
    selected_id = assistant.scope_fingerprint(df)
    reference_id = assistant.scope_fingerprint(reference)
    signature = selected_id + ":" + reference_id
    if st.session_state.get("hg_workbench_scope") != signature:
        st.session_state["hg_workbench_scope"] = signature
        st.session_state.pop("hg_workbench_result", None)
        st.session_state.pop("hg_workbench_report", None)
    selected_quality = workbench.quality_report(df)
    source_quality = workbench.quality_report(reference)
    tab_intro("A reporting workflow: validate the records, investigate a cohort, inspect executed SQL and share an evidence-led summary.")
    n1, n2, n3 = st.columns(3)
    n1.metric("Full reference records", f"{len(reference):,}")
    n2.metric("Selected cohort records", f"{len(df):,}")
    n3.metric("Selected contract checks", f"{selected_quality['passed']}/{len(selected_quality['checks'])}")
    st.caption("Reference = the full supplied synthetic dataset, including the selection. It is not an independent control group or a time-period comparison.")
    if (reference.Condition == "Diabetes").any():
        st.caption(f"Try the sidebar Condition filter: Diabetes selects {int(reference.Condition.eq('Diabetes').sum())} records. The comparison, SQL and exports will use that selection.")
    step = st.radio("Workbench step", ["Check data", "Compare", "SQL", "Report"],
                    horizontal=True, key="hg_workbench_step")
    if not source_quality["all_passed"]:
        st.warning("The full reference fails the project data contract. Inspect the checks before trusting a baseline or exporting a comparison.")
    if not selected_quality["all_passed"]:
        st.warning("The selected cohort fails the data contract. SQL/report publication is blocked rather than silently repairing the records.")

    if step == "Check data":
        st.subheader("Data contract and reporting grain")
        st.write("One source row represents one synthetic patient record. There is no validated longitudinal admissions or 30-day readmission timeline.")
        same_scope = selected_id == reference_id
        datasets = [("Source and selection (same scope)", source_quality)] if same_scope else [
            ("Full source contract", source_quality), ("Selected cohort contract", selected_quality)]
        for label, quality in datasets:
            with st.container(border=True):
                st.markdown("**" + label + "**")
                if quality["all_passed"]:
                    st.success("All checked project-contract rules pass for this scope.")
                else:
                    st.warning(f"{quality['failed']} failed checks; {quality['blocked']} blocked checks.")
                checks = pd.DataFrame(quality["checks"])
                st.dataframe(checks[["check", "status", "affected"]], hide_index=True, width="stretch")
                with st.expander("Definitions and failure counts"):
                    st.dataframe(checks, hide_index=True, width="stretch")
                    st.caption("A record can fail more than one rule. Affected counts must not be added as if they were distinct records.")
        audit = {"selected_scope_id": selected_id, "reference_scope_id": reference_id,
                 "selected": selected_quality, "reference": source_quality,
                 "boundary": "Project-specific synthetic-data contract; not a clinical quality or privacy certification."}
        st.download_button("Download data-check snapshot", json.dumps(audit, indent=2).encode("utf-8"),
                           "healthguard_data_checks.json", "application/json", key="hg_download_checks")
        with st.expander("Metric definitions"):
            st.markdown("- **Readmission rate:** Yes records / valid Yes-or-No records in the cohort. No time window is implied.\n"
                        "- **Recorded cost:** a data field, not an incremental or avoidable readmission cost.\n"
                        "- **Length of stay:** recorded days per synthetic row, not a reconstructed admissions history.\n"
                        "- **Recovered rate:** Recovered labels / valid outcome labels; not measured intervention effectiveness.")

    elif step == "Compare":
        st.subheader("Selected cohort versus full reference")
        if not selected_quality["all_passed"] or not source_quality["all_passed"]:
            st.info("Repair or review the failed data checks before comparing cohorts.")
            return
        try:
            comparison = workbench.compare_cohorts(df, reference)
        except ValueError as error:
            st.error(str(error))
            return
        if len(df) == len(reference):
            st.info("The selection currently matches the full reference, so its differences are zero. Choose a cohort in the sidebar to investigate a contrast.")
        c1, c2 = st.columns(2)
        for container, row in zip([c1, c2, c1, c2], comparison.to_dict("records")):
            number = workbench.round_value(row["selected_value"])
            value = f"₹{number:,.2f}" if row["unit"] == "INR" else f"{number:,.2f} {row['unit']}"
            container.metric(row["metric"], value,
                             delta=f"{workbench.round_value(row['difference']):+,.2f} {row['difference_unit']} vs reference",
                             delta_color="off")
        st.dataframe(comparison, hide_index=True, width="stretch")
        st.caption("Rate differences are percentage points, not percent improvements. Differences use unrounded metrics; displayed values use two-decimal half-up rounding.")
        st.info("These groups have different composition and are not randomized. Investigate case mix, label definitions and sample size before attributing any difference to a service, characteristic or intervention.")
        if len(df) < 30:
            st.warning("Fewer than 30 selected records: treat the descriptive rates cautiously, not as stable population estimates.")
        st.download_button("Download cohort comparison (CSV)", comparison.to_csv(index=False).encode("utf-8"),
                           f"healthguard_comparison_{selected_id[:8]}.csv", "text/csv", key="hg_download_comparison")

    elif step == "SQL":
        st.subheader("Inspect and execute a scoped SQL question")
        key = st.selectbox("Analytical question", list(workbench.QUERY_LABELS),
                           format_func=lambda name: workbench.QUERY_LABELS[name], key="hg_workbench_query")
        query_signature = signature + ":" + key
        previous = st.session_state.get("hg_workbench_result")
        if previous and previous["signature"] != query_signature:
            st.session_state.pop("hg_workbench_result", None)
        with st.expander("View the tracked SQL", expanded=False):
            st.code(workbench.load_queries()[key], language="sql")
        st.caption("Read-only query from the tracked SQL file. The in-memory table contains only the validated selected cohort; no free-text or model-generated SQL is executed.")
        if st.button("Run scoped SQL", key="hg_run_workbench_sql", type="primary",
                     disabled=not selected_quality["all_passed"]):
            try:
                result = workbench.execute_question(df, key)
                st.session_state["hg_workbench_result"] = {"signature": query_signature, "result": result}
            except ValueError as error:
                st.error(str(error))
        previous = st.session_state.get("hg_workbench_result")
        if previous:
            result = previous["result"]
            st.success(f"SQL/pandas reconciliation PASS: {result['checked_values']} result cells checked for {result['rows_in_scope']:,} selected records.")
            st.caption(result["scope_note"])
            st.dataframe(result["table"], hide_index=True, width="stretch")
            st.download_button("Download scoped SQL results (CSV)", result["table"].to_csv(index=False).encode("utf-8"),
                               f"healthguard_{key}_{selected_id[:8]}.csv", "text/csv", key="hg_download_sql")
        else:
            st.info("Choose a question and run it. A query being displayed is not proof that it has executed.")

    else:
        st.subheader("Prepare a stakeholder snapshot")
        st.write("Create a short report with the population, definitions, comparison, a fresh SQL/pandas check and questions for follow-up. No provider key is required.")
        focus = st.selectbox("Stakeholder focus", list(workbench.FOCUSES),
                             format_func=lambda key: workbench.FOCUSES[key], key="hg_workbench_focus")
        report_signature = signature + ":" + focus
        previous = st.session_state.get("hg_workbench_report")
        if previous and previous["signature"] != report_signature:
            st.session_state.pop("hg_workbench_report", None)
        if st.button("Build stakeholder report", key="hg_build_workbench_report", type="primary",
                     disabled=not (selected_quality["all_passed"] and source_quality["all_passed"])):
            try:
                text = workbench.build_report(df, reference, focus)
                st.session_state["hg_workbench_report"] = {"signature": report_signature, "text": text}
            except ValueError as error:
                st.error(str(error))
        previous = st.session_state.get("hg_workbench_report")
        if previous:
            st.success("Stakeholder snapshot prepared from this cohort with a fresh scoped SQL reconciliation.")
            st.download_button("Download stakeholder report", previous["text"].encode("utf-8"),
                               f"healthguard_{focus}_{selected_id[:8]}.md", "text/markdown", key="hg_download_report")
            with st.expander("Read the report", expanded=True):
                st.markdown(previous["text"])
        st.caption("Use the AI Assistant tab if you also want optional Gemini selection of existing computed evidence cards. That does not change these deterministic report figures.")


@st.fragment
def render_ai(df):
    """Scope-aware analytical Q&A and optional validated Gemini fact selection."""
    import importlib
    from app.dashboard.utils import assistant_service as assistant
    if getattr(assistant, "SERVICE_VERSION", 0) != 2:
        assistant = importlib.reload(assistant)

    # Streamlit may retain an imported adapter across a rolling source refresh.
    if getattr(gemini_ai, "ADAPTER_VERSION", 0) != 3:
        importlib.reload(gemini_ai)
    provider_capable = getattr(gemini_ai, "ADAPTER_VERSION", 0) == 3
    scope_id = assistant.scope_fingerprint(df)
    previous_scope = st.session_state.get("hg_assistant_scope")
    if previous_scope != scope_id:
        st.session_state["hg_assistant_scope"] = scope_id
        st.session_state["hg_assistant_history"] = []
        st.session_state.pop("hg_assistant_brief", None)
        st.session_state.pop("qa_input", None)
    config_id = gemini_ai.configuration_id() if provider_capable else "updating"
    if st.session_state.get("hg_assistant_config") != config_id:
        st.session_state["hg_assistant_config"] = config_id
        st.session_state.pop("hg_assistant_connection", None)
        st.session_state.pop("hg_assistant_brief", None)

    tab_intro("Ask analytical questions, inspect the calculation, and prepare an evidence-based cohort brief.")
    st.caption("Synthetic records · Current dashboard filters apply · No diagnosis, prescribing or care prioritisation")
    n1, n2, n3 = st.columns(3)
    n1.metric("Records in assistant scope", f"{len(df):,}")
    n2.metric("Numerical answer engine", "Computed")
    configured = provider_capable and gemini_ai.is_configured()
    n3.metric("Optional Gemini assistance", "Configured" if configured else "Local mode")
    if previous_scope and previous_scope != scope_id:
        st.info("The cohort changed. Earlier answers and briefs were cleared so they cannot be mistaken for this scope.")

    with st.container(border=True):
        st.subheader("Ask the cohort data")
        st.write("Get counts, rates, average or total costs, stays, satisfaction and outcome summaries. "
                 "You can narrow by a named condition, gender or age range, or compare supported groups.")
        examples = [
            ("Readmission rate", "What is the overall readmission rate?"),
            ("Readmitted count", "How many patients were readmitted?"),
            ("Cost by condition", "What is the average cost by condition?"),
            ("Recovered count", "How many patients recovered?"),
            ("Gender comparison", "Compare readmission rate by gender"),
            ("Diabetes rate", "What is the readmission rate for diabetes?"),
        ]
        selected_question = None
        for start in (0, 3):
            cols = st.columns(3)
            for col, (label, question) in zip(cols, examples[start:start + 3]):
                if col.button(label, key=f"hg_example_{start}_{label}", width="stretch"):
                    selected_question = question
        with st.form("hg_analyst_question_form", clear_on_submit=True):
            question = st.text_input("Ask a question about this dataset", key="qa_input", max_chars=500,
                                     placeholder="For example: What is the total cost for male patients with diabetes?")
            submitted = st.form_submit_button("Calculate answer", type="primary")
        if submitted:
            selected_question = question
        history = st.session_state.setdefault("hg_assistant_history", [])
        if selected_question is not None:
            response = assistant.answer_question(df, selected_question)
            history.append({"question": selected_question, "response": response})
            st.session_state["hg_assistant_history"] = history[-6:]
        if history and st.button("Clear answers", key="hg_clear_answers"):
            st.session_state["hg_assistant_history"] = []
            history = []
        if not history:
            st.caption("Choose an example or enter a question. Unsupported filters are refused rather than silently ignored.")
        for item in st.session_state["hg_assistant_history"][-3:]:
            with st.container(border=True):
                st.markdown("**Question:** " + item["question"])
                result = item["response"]
                if result["ok"]:
                    st.success(result["text"])
                    st.caption(f"Computed from {result['row_count']:,} matching records within this "
                               f"{result['dashboard_rows']:,}-record dashboard scope. No model calculated the answer.")
                    with st.expander("How this was calculated"):
                        st.code(result["formula"], language=None)
                        st.write("Source columns: " + (", ".join(result["source_columns"]) or "row count"))
                        st.write("Additional question filters: " + (str(result["filters"]) if result["filters"] else "none"))
                        st.dataframe(pd.DataFrame(result["table"]), hide_index=True, width="stretch")
                        for note in result["warnings"]:
                            st.caption(note)
                else:
                    st.info(result["text"])
                    st.caption("No external provider was called for this unsupported request.")

    cards = assistant.evidence_cards(df)
    with st.container(border=True):
        st.subheader("Computed cohort evidence")
        st.caption("These facts are available without a provider key. They describe the current cohort and do not prescribe action.")
        for card in cards[:3]:
            st.markdown("**" + card["title"] + "**")
            st.write(card["text"])
        with st.expander("See all computed evidence and definitions"):
            for card in cards:
                st.markdown("**" + card["title"] + "**")
                st.write(card["text"])
                st.caption(card["formula"] + " · Columns: " + (", ".join(card["source_columns"]) or "row count"))

    with st.container(border=True):
        st.subheader("Optional Gemini-assisted brief")
        st.write("Gemini can select a few relevant cards from the computed evidence. "
                 "It cannot add new figures, clinical recommendations or unrestricted narration to this view.")
        if not provider_capable:
            st.info("The provider adapter is refreshing. Local questions and evidence remain available.")
        elif not configured:
            st.info("Local mode is ready. The app owner can configure GOOGLE_API_KEY to enable optional Gemini assistance.")
        else:
            if st.button("Check Gemini connection", key="hg_check_provider"):
                with st.spinner("Verifying an available model with a small structured-response request…"):
                    st.session_state["hg_assistant_connection"] = gemini_ai.connection_status()
            connection = st.session_state.get("hg_assistant_connection")
            if connection:
                if connection["ok"]:
                    st.success(connection["text"])
                    st.caption("Verified model: " + connection["model"])
                else:
                    st.warning(connection["text"])
                    st.caption("Selection mode: " + connection.get("selection_mode", "unknown") +
                               " · Stage: " + connection.get("phase", "unknown") +
                               " · Attempted models: " + (", ".join(connection.get("attempted_models", [])) or "none"))
            else:
                st.caption("Configured does not mean verified. Use the connection check to test the provider.")
            focus_label = st.selectbox("Brief focus", ["Balanced review", "Costs", "Readmissions", "Outcomes"], key="hg_brief_focus")
            focus = {"Balanced review": "balanced", "Costs": "costs", "Readmissions": "readmissions", "Outcomes": "outcomes"}[focus_label]
            if st.button("Prepare AI-assisted brief", key="hg_prepare_brief", disabled=len(df) < 5):
                with st.spinner("Selecting from this cohort's computed evidence…"):
                    st.session_state["hg_assistant_brief"] = gemini_ai.generate_brief(df, focus)
            if len(df) < 5:
                st.caption("For fewer than five records, keep the analysis local.")
            brief = st.session_state.get("hg_assistant_brief")
            if brief:
                if brief["ok"]:
                    st.success("Validated evidence selection received.")
                    st.caption("Model: " + brief["model"] + " · " + brief["note"])
                    for card in brief["cards"]:
                        st.markdown("**" + card["title"] + "**")
                        st.write(card["text"])
                    export = "# Cohort evidence brief\n\n" + "\n\n".join(c["title"] + "\n" + c["text"] for c in brief["cards"])
                    export += "\n\nSynthetic data. Descriptive analysis, not clinical advice or causal evidence.\n"
                    st.download_button("Download evidence brief", export.encode("utf-8"),
                                       "healthguard_evidence_brief.md", "text/markdown", key="hg_download_brief")
                else:
                    st.warning(brief["text"])
                    st.caption("The computed evidence above remains the fallback; no unverified provider prose is displayed.")

    with st.expander("About the readmission model and assistant limits"):
        m = ai_risk.get_metrics()
        if m:
            a, b = st.columns(2)
            a.metric("Recorded model ROC-AUC", m.get("roc_auc"))
            b.metric("Condition-only baseline", m.get("condition_baseline_auc", "—"))
        st.write("The predictive model uses a synthetic target with strong condition/procedure structure. "
                 "Its score and SHAP explanations are not clinical validation. The analyst assistant "
                 "does not predict a patient's future readmission or provide treatment advice.")
        st.caption("No validated 30-day admissions timeline is present. Aggregate provider context is not a privacy certification for real patient data.")


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

try:
    inject_css_v2()
    raw = data.load_patients()

    with st.sidebar:
        st.markdown("""
        <div class="hg-brand">
            <div style="font-size:1.5rem;">🛡️</div>
            <div class="hg-brand-title">HealthGuard AI</div>
        </div>
        <div class="hg-brand-sub">Hospital Outcomes Intelligence</div>
        """, unsafe_allow_html=True)
        st.markdown("##### Filters")
        conditions = st.multiselect("Condition", sorted(raw.Condition.unique()), key="hg_cond")
        genders = st.multiselect("Gender", sorted(raw.Gender.unique()), key="hg_gender")
        outcomes = st.multiselect("Outcome", sorted(raw.Outcome.unique()), key="hg_outcome")
        age_range = st.slider(
            "Age range",
            int(raw.Age.min()), int(raw.Age.max()),
            (int(raw.Age.min()), int(raw.Age.max())),
            key="hg_age",
        )
        st.caption(f"{len(raw)} patients in dataset")

    # Active-scope chips + one-click reset (empty selection == no filter)
    filter_chips(conditions, genders, outcomes, age_range, raw)
    any_filter = bool(conditions or genders or outcomes) or tuple(age_range) != (
        int(raw.Age.min()), int(raw.Age.max())
    )
    if any_filter and st.sidebar.button("↺ Reset all filters"):
        for _k in ("hg_cond", "hg_gender", "hg_outcome", "hg_age"):
            st.session_state.pop(_k, None)
        st.rerun()

    df = data.apply_filters(raw, conditions, genders, outcomes, age_range)

    st.markdown('<div class="hg-page-title">Hospital Outcomes Analytics</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="hg-page-sub">Select a cohort, check the numbers and prepare a report — {len(df)} of {len(raw)} records in scope.</div>', unsafe_allow_html=True)

    st.caption("Synthetic patient records · Descriptive demonstration · Not for clinical decisions")

    if df.empty:
        st.warning("No patients match the current filters.")
        st.stop()

    kpis = data.get_kpis(df)
    cond_summary = data.condition_summary(df)

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Overview",
        "Analyst Workbench",
        "Cohort Analysis",
        "Condition & Age",
        "Patient Records",
        "AI Assistant",
    ])
    with tab1:
        render_overview(df, kpis, cond_summary)
    with tab2:
        render_workbench(df, raw)
    with tab3:
        render_clinical(df, cond_summary)
    with tab4:
        render_ops_drill(df)
    with tab5:
        render_patients(df)
    with tab6:
        render_ai(df)

    # ---- Methodology & data trust ----
    with st.expander("📖 Methodology & how to read this dashboard"):
        st.markdown(
            f"**Data:** {len(raw):,}-patient hospital dataset (synthetic — disclosed). "
            "One row per patient: demographics, condition, procedure, cost, length of stay, "
            "readmission flag, outcome, satisfaction.\n\n"
            "**KPIs** are computed live from the filtered scope: readmission rate = "
            "readmitted ÷ patients in scope; cost figures are per-patient averages unless labeled total.\n\n"
            "**Risk model:** RandomForest trained on this dataset's own columns, explained with "
            "per-patient and cohort SHAP. The headline 0.99 AUC is audited as synthetic-data "
            "determinism (condition-only baseline: 0.93) — disclosed, not hidden. Fairness: "
            "gender AUC gap 0.006 with base-rate disparity reported.\n\n"
            "**AI answers:** common questions are answered by deterministic code over this "
            "cohort. Unsupported requests are refused. Optional Gemini assistance selects only "
            "precomputed evidence cards; provider text is not used as a source of numerical answers.\n\n"
            "**Not medical advice:** demo analytics — not for diagnosis, treatment, or clinical decisions. "
            "Reproduction commands, automated checks and limitations are documented in the repository."
        )

    st.divider()
    st.caption("Demo analytics dashboard. Not intended for diagnosis, treatment, or clinical decision-making.")

except Exception as e:
    logging.getLogger(__name__).error("Dashboard view could not load (%s)", type(e).__name__)
    st.error("This dashboard view could not load. Refresh or reset the filters; the app owner can inspect the server logs.")
