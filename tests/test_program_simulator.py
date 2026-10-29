"""
test_program_simulator.py — the program simulator must reproduce verified numbers
================================================================================
Day-2 upgrade pin. The dataset is synthetic and seeded, so every economic
quantity is a known value. These tests fail if the simulator, the targeting
rule (stratum risk score), or the cost model drift apart.

Verified values (recomputed from data/ + reports/program_simulator.json):
984 patients · 264 readmitted · 24 strata ·
enroll_all net -₹1,039,325.05 (break-even efficacy 52.98%) ·
enroll_top_decile 98 enrolled net ₹131,892.99 ·
enroll_top_quartile 246 enrolled net ₹298,297.58 (recommended) ·
enroll_top_half net -₹81,914.85 · above-baseline 301 enrolled net ₹281,003.83.
"""
import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

REPORT = ROOT / "reports" / "program_simulator.json"
MD = ROOT / "reports" / "program_simulator.md"


def _report():
    return json.loads(REPORT.read_text())


def _strategy(report, name):
    return next(s for s in report["strategies"] if s["strategy"] == name)


# ── cohort pins ──────────────────────────────────────────────────────────────

def test_cohort_pins_verified_counts():
    r = _report()
    assert r["cohort"]["patients"] == 984
    assert r["cohort"]["readmitted"] == 264
    assert r["cohort"]["base_readmission_rate"] == 0.2683
    assert r["cohort"]["strata"] == 24


def test_cohort_matches_csv():
    df = pd.read_csv(ROOT / "data" / "hospital" / "hospital_data.csv")
    assert (df["Readmission"] == "Yes").sum() == 264
    assert len(df) == 984


# ── strategy pins ────────────────────────────────────────────────────────────

def test_enroll_all_is_money_losing_and_honest_about_it():
    s = _strategy(_report(), "enroll_all")
    assert s["enrolled"] == 984
    assert s["net_value"] < 0
    assert abs(s["net_value"] - (-1039325.05)) < 0.01
    assert abs(s["break_even_efficacy"] - 0.5298) < 0.0001


def test_top_quartile_pins_and_is_recommended():
    r = _report()
    s = _strategy(r, "enroll_top_quartile")
    assert s["enrolled"] == 246
    assert abs(s["net_value"] - 298297.58) < 0.01
    assert abs(s["roi"] - 0.6063) < 0.0001
    assert abs(s["break_even_efficacy"] - 0.1556) < 0.0001
    assert r["recommended_strategy"] == "enroll_top_quartile"
    assert abs(r["recommended_net_value"] - 298297.58) < 0.01


def test_top_decile_pins():
    s = _strategy(_report(), "enroll_top_decile")
    assert s["enrolled"] == 98
    assert abs(s["net_value"] - 131892.99) < 0.01


def test_above_baseline_pins():
    s = _strategy(_report(), "enroll_above_baseline_risk")
    assert s["enrolled"] == 301
    assert abs(s["net_value"] - 281003.83) < 0.01


def test_targeting_beats_blanket_enrollment():
    r = _report()
    assert _strategy(r, "enroll_top_quartile")["net_value"] > 0
    assert _strategy(r, "enroll_all")["net_value"] < 0


# ── economic identities (must hold for any strategy) ────────────────────────

def test_net_is_savings_minus_cost():
    for s in _report()["strategies"]:
        assert abs(s["expected_savings"] - s["program_cost"] - s["net_value"]) < 0.02
        assert abs(s["program_cost"] - 2000.0 * s["enrolled"]) < 0.02


def test_break_even_efficacy_satisfies_identity():
    for s in _report()["strategies"]:
        if math.isinf(s["break_even_efficacy"]):
            continue
        lhs = 2000.0 * s["enrolled"]
        rhs = s["break_even_efficacy"] * s["expected_readmits_among_enrolled"] * 13650.0
        # 1% tolerance: JSON stores efficacy to 4 dp and readmits to 2 dp.
        assert abs(lhs - rhs) / max(lhs, 1.0) < 0.01, f"{s['strategy']}: break-even identity broken"


# ── sensitivity: the honest phase boundary ───────────────────────────────────

def test_low_efficacy_high_cost_is_money_losing_everywhere():
    g = next(g for g in _report()["sensitivity_grid"]
             if g["efficacy"] == 0.10 and g["program_cost"] == 2000.0)
    # At 10% efficacy the best available strategy still loses money — the
    # report must show that instead of hiding it.
    assert g["best_net_value"] < 0
    assert all(v < 0 for v in g["net_by_strategy"].values())


def test_sensitivity_grid_has_9_scenarios():
    assert len(_report()["sensitivity_grid"]) == 9


# ── equity audit ─────────────────────────────────────────────────────────────

def test_equity_slice_discloses_gender_concentration():
    eq = _report()["equity_slice"]
    # The dataset's readmission rate is far higher for female patients, so the
    # targeting rule concentrates enrollment — the report must PRINT this.
    assert eq["enrolled_gender_share_pct"]["Female"] == 86.2
    assert eq["population_gender_share_pct"]["Female"] == 53.3
    assert "enrolled_age_band_share_pct" in eq


# ── honest reporting ─────────────────────────────────────────────────────────

def test_report_discloses_assumptions():
    md = MD.read_text(encoding="utf-8")
    assert "synthetic" in md.lower()
    assert "assumption" in md.lower()
    r = _report()
    assert "assumptions" in r["honesty"].lower()


def test_run_is_deterministic():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from program_simulator import run
    a = run()
    b = run()
    assert a["recommended_net_value"] == b["recommended_net_value"]
