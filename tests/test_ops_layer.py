"""
test_ops_layer.py — the ops layer must reproduce verified numbers
================================================================================
Day-3 upgrade pin. The dataset is synthetic and seeded, so every operational
KPI is a known value. These tests fail if the ops layer, the dashboard, or the
semantic layer (data/metrics.json) drift apart.

Verified values (recomputed from data/hospital/hospital_data.csv):
984 patients · 264 readmitted (26.8%) · readmitted avg cost ₹13,650 vs ₹6,431
(+112.3%) · readmitted patients hold 43.8% of total cost · Heart Attack 100%
readmission · age-band rates 18-30: 0.0%, 46-60: 36.5%, 76+: 50.0%.
Model facts (fairness/honesty/SHAP) are pinned from the reports via
data/metrics.json.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.dashboard.utils import ops_layer  # noqa: E402


def _df():
    return pd.read_csv(ROOT / "data" / "hospital" / "hospital_data.csv")


# ── ops context ──────────────────────────────────────────────────────────────

def test_ops_context_pins_verified_values():
    c = ops_layer.ops_context(_df())
    assert c["total_patients"] == 984
    assert c["readmitted_n"] == 264
    assert c["readmission_rate_pct"] == 26.8
    assert c["readmitted_avg_cost"] == 13650
    assert c["non_readmitted_avg_cost"] == 6431
    assert c["cost_premium_pct"] == 112.3
    assert c["readmitted_cost_share_pct"] == 43.8
    assert c["readmitted_avg_los"] == 39.2
    assert c["non_readmitted_avg_los"] == 37.1
    assert c["readmitted_total_cost"] == 3603500


def test_readmission_by_condition_ranking():
    g = ops_layer.readmission_by_condition(_df())
    assert len(g) == 15
    assert g.iloc[0]["Condition"] == "Heart Attack"
    assert g.iloc[0]["readmit_rate_pct"] == 100.0
    assert g.iloc[1]["Condition"] == "Heart Disease"
    assert round(g.iloc[1]["readmit_rate_pct"], 1) == 98.5


def test_age_band_mapping_and_rates():
    assert ops_layer.age_band(25) == "18-30"
    assert ops_layer.age_band(31) == "31-45"
    assert ops_layer.age_band(60) == "46-60"
    assert ops_layer.age_band(61) == "61-75"
    assert ops_layer.age_band(80) == "76+"
    g = ops_layer.readmission_by_age_band(_df())
    rates = dict(zip(g["Age_Band"], g["readmit_rate_pct"]))
    assert rates["18-30"] == 0.0
    assert rates["46-60"] == 36.5
    assert rates["76+"] == 50.0


def test_condition_profile_heart_attack():
    p = ops_layer.condition_profile(_df(), "Heart Attack")
    assert p["patients"] == 67
    assert p["readmit_rate_pct"] == 100.0


def test_drill_respects_scope():
    df = _df()
    df = df[df.Gender == "Female"]
    c = ops_layer.ops_context(df)
    # verified: female base rate is 43.9%
    assert abs(c["readmission_rate_pct"] - 43.9) < 0.1


# ── semantic layer (model facts) ─────────────────────────────────────────────

def test_metrics_json_model_facts():
    facts = ops_layer.load_model_facts()
    f = facts["fairness"]
    assert f["auc_gap_gender"] == 0.006
    assert f["auc_gap_age"] == 0.003
    assert f["base_rate_female_pct"] == 43.9
    assert f["base_rate_male_pct"] == 7.4
    assert f["base_rate_gap_pp"] == 36.5
    h = facts["model_honesty"]
    assert h["shipped_rf_auc"] == 0.992
    assert h["condition_only_baseline_auc"] == 0.93
    s = facts["cohort_shap"]["top_features_pct"]
    assert s["Procedure"] == 27.6
    assert s["Cost"] == 23.8


def test_metrics_json_matches_reports():
    """The semantic layer must not drift from the model audit reports."""
    fair_txt = (ROOT / "reports" / "fairness_check.md").read_text(encoding="utf-8")
    hon_txt = (ROOT / "reports" / "model_honesty.md").read_text(encoding="utf-8")
    assert "43.9%" in fair_txt and "7.4%" in fair_txt and "0.006" in fair_txt
    assert "0.992" in hon_txt


# ── dashboard integration ────────────────────────────────────────────────────

def test_home_has_ops_layer_integrated():
    home = (ROOT / "app" / "dashboard" / "Home.py").read_text(encoding="utf-8")
    for anchor in [
        "from app.dashboard.utils import ops_layer",
        "def render_ops_drill(df)",
        "Operations Context",
        "Root-Cause Drill",
        "Fairness &amp; Model Honesty",
        "readmission_by_age_band",
    ]:
        assert anchor in home, f"missing: {anchor}"


def test_dashboard_renders_end_to_end():
    """AppTest smoke: the upgraded 5-tab dashboard renders without errors."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app" / "dashboard" / "Home.py"), default_timeout=300)
    at.run()
    assert not at.exception, f"raised: {at.exception}"
    assert len(at.error) == 0, [e.value for e in at.error]
    # 5 tabs present
    assert len(at.tabs) == 5, f"expected 5 tabs, got {len(at.tabs)}"
