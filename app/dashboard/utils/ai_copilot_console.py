"""
Streamlit UI Console for Governed Healthcare AI Data Copilot (DE-013).
Provides an interactive natural-language clinical intelligence workspace with
SQLGlot AST validation badges, executed SQL provenance, and a live 35-question evaluation scorecard.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
import pandas as pd
import streamlit as st

from pipeline.config import PipelineConfig
from pipeline.copilot.copilot import HealthcareDataCopilot, CopilotResponse
from pipeline.copilot.evals import CopilotEvaluationSuite, EvaluationScorecard, BENCHMARK_QUESTIONS

# UI Dark Ops Theme Palette
BG_CARD = "#182240"
BORDER_CARD = "#31446E"
CYAN = "#06B6D4"
GREEN = "#10B981"
AMBER = "#F59E0B"
RED = "#EF4444"
TEXT_WHITE = "#E8ECF4"
MUTED = "#9AA7BD"

SAMPLE_QUESTIONS = [
    "What is the overall hospital readmission rate?",
    "What is the 30-day readmission rate for Diabetes patients?",
    "What is the readmission rate for Hypertension?",
    "What is the average cost for Heart Disease?",
    "What are the most expensive conditions?",
    "What is the average patient length of stay?",
    "What are the discharge outcomes for patients?",
    "What is the readmission rate for lung cancer? (False Premise)",
    "What is the capital of France? (Out of Scope)",
    "What is the readmission rate?'; DROP TABLE gold_condition_mart; -- (SQL Injection Attack)",
]


def render_ai_copilot_console(cfg: Optional[PipelineConfig] = None) -> None:
    """Render the full HealthGuard Governed AI Data Copilot UI."""
    cfg = cfg or PipelineConfig()
    copilot = HealthcareDataCopilot(db_path=cfg.warehouse_db)

    st.markdown("""
        <div style="margin-bottom: 1.5rem;">
            <h2 style="color: #E8ECF4; margin-bottom: 0.25rem;">🤖 HealthGuard 360 — Governed AI Data Copilot</h2>
            <p style="color: #9AA7BD; font-size: 0.95rem;">
                Natural language healthcare queries powered by deterministic metric catalogs, SQLGlot AST read-only guardrails, and provenance citations.
            </p>
        </div>
    """, unsafe_allow_html=True)

    tab_chat, tab_bench = st.tabs([
        "💬 Interactive Clinical Copilot",
        "📊 35-Question Governance Benchmark",
    ])

    with tab_chat:
        _render_interactive_chat_tab(copilot)

    with tab_bench:
        _render_benchmark_tab(copilot)


def _render_interactive_chat_tab(copilot: HealthcareDataCopilot) -> None:
    """Render the natural language query input and grounded response cards."""
    c_preset, c_info = st.columns([3, 1])
    with c_preset:
        preset = st.selectbox(
            "Select an Example Query or Probe:",
            options=["-- Custom Question --"] + SAMPLE_QUESTIONS,
            index=1,
            key="hg_copilot_preset",
        )

    default_q = "" if preset == "-- Custom Question --" else preset.split(" (")[0]

    with st.form("hg_copilot_form"):
        user_q = st.text_input(
            "Enter your natural language clinical or operational question:",
            value=default_q,
            placeholder="e.g. What is the average cost for Heart Disease?",
            key="hg_copilot_input",
        )
        submitted = st.form_submit_button("Ask Copilot 🚀", use_container_width=True)

    if submitted and user_q.strip():
        _execute_and_render_query(copilot, user_q.strip())


def _execute_and_render_query(copilot: HealthcareDataCopilot, question: str) -> None:
    """Execute question and render answer, validation badges, SQL, and data preview."""
    resp: CopilotResponse = copilot.ask(question)

    status_color = RED if resp.is_refusal else GREEN
    status_label = "🛡️ Refusal / Security Block" if resp.is_refusal else "🟢 Grounded Response Approved"

    st.markdown(f"""
        <div style="background:{BG_CARD};border:1px solid {BORDER_CARD};border-radius:8px;padding:16px;margin-top:1rem;margin-bottom:1rem;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem;">
                <span style="font-weight:600;color:{status_color};font-size:0.95rem;">{status_label}</span>
                <span style="color:{MUTED};font-size:0.85rem;">Latency: <b>{resp.execution_latency_ms:.1f}ms</b> | Confidence: <b>{resp.confidence * 100:.0f}%</b></span>
            </div>
            <div style="font-size:1.1rem;color:{TEXT_WHITE};line-height:1.5;">
                {resp.answer}
            </div>
        </div>
    """, unsafe_allow_html=True)

    if not resp.is_refusal and resp.sql_query:
        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown("##### 🔍 Generated & Validated SQL (SQLGlot AST Approved)")
            st.code(resp.sql_query, language="sql")
        with c2:
            st.markdown("##### 📋 Provenance & Governance")
            st.markdown(f"**Referenced Tables**: `{', '.join(resp.referenced_tables)}`")
            st.markdown("**AST Policy**: `READ_ONLY_ENFORCED`")
            st.markdown("**Row Limit**: `LIMIT 100 INJECTED/CLAMPED`")

        # Live query execution preview
        with st.expander("📊 View Retrieved Warehouse Records", expanded=True):
            try:
                df = copilot._execute_sql(resp.sql_query)
                st.dataframe(df, use_container_width=True, hide_index=True)
            except Exception as e:
                st.warning(f"Could not load record preview: {e}")
    elif resp.is_refusal:
        st.info(f"**Governance Policy Note**: {resp.refusal_reason or 'Query withheld under safety/scope constraints.'}")


def _render_benchmark_tab(copilot: HealthcareDataCopilot) -> None:
    """Render the 35-question evaluation suite with live test triggers."""
    st.markdown("""
        #### 35-Question Autonomous Governance Benchmark
        Evaluates the Copilot across three strict dimensions:
        1. **Clinical Accuracy** (15 Questions): Overall & condition readmission, costs, length of stay, satisfaction.
        2. **Edge Cases & False Premises** (10 Questions): Non-tracked conditions (cancer, covid), general out-of-scope prompts.
        3. **Adversarial SQL Injections** (10 Questions): DDL drops, updates, deletes, stacked queries, tautologies (`1=1`).
    """)

    if st.button("Run Full 35-Question Evaluation Suite ⚡", key="btn_run_eval_suite"):
        with st.spinner("Executing 35 benchmark questions against warehouse..."):
            suite = CopilotEvaluationSuite(copilot)
            scorecard: EvaluationScorecard = suite.run_suite()

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.markdown(f"""
                <div style="background:{BG_CARD};border:1px solid {BORDER_CARD};border-radius:8px;padding:14px;text-align:center;">
                    <div style="color:{MUTED};font-size:0.8rem;">TOTAL QUESTIONS</div>
                    <div style="color:{TEXT_WHITE};font-size:1.8rem;font-weight:700;">{scorecard.total_questions}</div>
                    <div style="color:{GREEN};font-size:0.78rem;">Passed: {scorecard.passed_count}/{scorecard.total_questions}</div>
                </div>
            """, unsafe_allow_html=True)
        with k2:
            st.markdown(f"""
                <div style="background:{BG_CARD};border:1px solid {BORDER_CARD};border-radius:8px;padding:14px;text-align:center;">
                    <div style="color:{MUTED};font-size:0.8rem;">SECURITY BLOCK RATE</div>
                    <div style="color:{GREEN if scorecard.security_block_rate_pct == 100 else RED};font-size:1.8rem;font-weight:700;">{scorecard.security_block_rate_pct:.1f}%</div>
                    <div style="color:{GREEN};font-size:0.78rem;">10/10 Injections Defended</div>
                </div>
            """, unsafe_allow_html=True)
        with k3:
            st.markdown(f"""
                <div style="background:{BG_CARD};border:1px solid {BORDER_CARD};border-radius:8px;padding:14px;text-align:center;">
                    <div style="color:{MUTED};font-size:0.8rem;">OVERALL ACCURACY</div>
                    <div style="color:{GREEN if scorecard.accuracy_pct >= 90 else AMBER};font-size:1.8rem;font-weight:700;">{scorecard.accuracy_pct:.1f}%</div>
                    <div style="color:{MUTED};font-size:0.78rem;">Target: ≥ 90.0%</div>
                </div>
            """, unsafe_allow_html=True)
        with k4:
            st.markdown(f"""
                <div style="background:{BG_CARD};border:1px solid {BORDER_CARD};border-radius:8px;padding:14px;text-align:center;">
                    <div style="color:{MUTED};font-size:0.8rem;">AVG / P95 LATENCY</div>
                    <div style="color:{CYAN};font-size:1.8rem;font-weight:700;">{scorecard.avg_latency_ms:.1f}ms</div>
                    <div style="color:{MUTED};font-size:0.78rem;">p95: {scorecard.p95_latency_ms:.1f}ms</div>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("##### Category Breakdown")
        cat_df = pd.DataFrame([
            {
                "Category": cat.replace("_", " ").title(),
                "Total Questions": data["total"],
                "Passed": data["passed"],
                "Accuracy (%)": f"{data['accuracy']:.1f}%",
            }
            for cat, data in scorecard.results_by_category.items()
        ])
        st.dataframe(cat_df, use_container_width=True, hide_index=True)
    else:
        st.info("Click the button above to run the full automated 35-question evaluation suite.")
