"""
HealthGuard 360: Governed Healthcare AI Data Copilot Console.

Dedicated multi-page Streamlit application page providing natural language
clinical queries, SQLGlot AST validation, and a live 35-question evaluation suite.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from app.dashboard.utils.ai_copilot_console import render_ai_copilot_console

st.set_page_config(
    page_title="HealthGuard 360 | AI Data Copilot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

render_ai_copilot_console()
