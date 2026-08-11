"""
Gemini-powered layer: cohort recommendations + grounded free-text Q&A.

The API key is read from the GOOGLE_API_KEY environment variable only --
it is never hardcoded here or committed to the repo. Set it via:
  - Streamlit Cloud: App settings -> Secrets -> GOOGLE_API_KEY = "..."
  - Render: Environment tab -> Add Environment Variable -> GOOGLE_API_KEY
  - Local: export GOOGLE_API_KEY=... before running streamlit

Every Gemini call is grounded: we compute the real numbers from the
dataframe first and pass them in the prompt, with an explicit instruction
not to invent figures that weren't provided. This avoids hallucinated
statistics about patient data.
"""
import os

import pandas as pd
import streamlit as st

MODEL = "gemini-2.5-flash"


def _get_client():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception:
        return None


def is_configured() -> bool:
    return os.getenv("GOOGLE_API_KEY") is not None


def _cohort_context(df: pd.DataFrame) -> str:
    from app.dashboard.utils import hospital_data as data
    kpis = data.get_kpis(df)
    cond = data.condition_summary(df)
    top_readmit = cond.sort_values("readmission_rate", ascending=False).head(5)
    top_cost = cond.sort_values("avg_cost", ascending=False).head(5)

    lines = [
        f"Total patients: {kpis['total_patients']}",
        f"Average age: {kpis['avg_age']}",
        f"Average cost per patient: ${kpis['avg_cost']:,.0f}",
        f"Average length of stay: {kpis['avg_los']} days",
        f"Overall readmission rate: {kpis['readmission_rate']}%",
        f"Recovered rate: {kpis['recovered_rate']}%",
        f"Average satisfaction: {kpis['avg_satisfaction']}/5",
        "",
        "Top 5 conditions by readmission rate:",
    ]
    for _, r in top_readmit.iterrows():
        lines.append(f"- {r.Condition}: {r.readmission_rate:.1f}% readmission, {int(r.patients)} patients, ${r.avg_cost:,.0f} avg cost")
    lines.append("")
    lines.append("Top 5 conditions by average cost:")
    for _, r in top_cost.iterrows():
        lines.append(f"- {r.Condition}: ${r.avg_cost:,.0f} avg cost, {r.readmission_rate:.1f}% readmission")

    return "\n".join(lines)


@st.cache_data(ttl=600, show_spinner=False)
def generate_recommendations(_df_hash: str, context: str) -> dict:
    """Generate 3-5 actionable recommendations grounded in real cohort stats.
    _df_hash is just a cache key (pass a hash of the filtered data)."""
    client = _get_client()
    if client is None:
        return {"ok": False, "text": "Gemini API key not configured (GOOGLE_API_KEY)."}

    prompt = f"""You are a hospital operations analyst. Based ONLY on the following real
cohort statistics, write 3-5 short, concrete, actionable recommendations for hospital
administrators. Do NOT invent any numbers, patient names, or facts not given below.
Cite the specific numbers provided when relevant. Keep each recommendation to 1-2 sentences.
Format as a markdown bulleted list, nothing else.

COHORT STATISTICS:
{context}
"""
    try:
        response = client.models.generate_content(model=MODEL, contents=prompt)
        return {"ok": True, "text": response.text}
    except Exception as e:
        return {"ok": False, "text": f"Gemini request failed: {e}"}


def answer_grounded(df: pd.DataFrame, question: str) -> dict:
    """Free-text Q&A fallback for questions the deterministic matcher can't handle,
    grounded in real cohort stats passed as context."""
    client = _get_client()
    if client is None:
        return {"ok": False, "text": "Gemini API key not configured (GOOGLE_API_KEY)."}

    context = _cohort_context(df)
    prompt = f"""You are a hospital data analyst assistant. Answer the user's question
using ONLY the statistics provided below. If the question cannot be answered from this
data, say so clearly instead of guessing or inventing numbers. Keep your answer to 2-3
sentences.

COHORT STATISTICS:
{context}

QUESTION: {question}
"""
    try:
        response = client.models.generate_content(model=MODEL, contents=prompt)
        return {"ok": True, "text": response.text}
    except Exception as e:
        return {"ok": False, "text": f"Gemini request failed: {e}"}
