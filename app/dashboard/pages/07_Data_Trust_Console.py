"""
HealthGuard 360: Streamlit Data Trust & Observability Ops Console.

Dedicated multi-page Streamlit application page providing real-time
clinical Data Trust Scores, Schema Drift detection, and Freshness SLA monitoring.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st

from app.dashboard.utils.data_trust_console import render_data_trust_console

st.set_page_config(
    page_title="HealthGuard 360 | Data Trust Ops Console",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

render_data_trust_console()
