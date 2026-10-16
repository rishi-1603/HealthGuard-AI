"""
test_evaluation_depth.py — calibration, DCA, temporal validation cannot drift.
=============================================================================
Pins reports/calibration_decision_curve_metrics.json and
reports/temporal_validation_metrics.json (Day-5 release) and locks the
findings: miscalibrated raw probabilities, model beats treat-all on net
benefit, temporal-vs-random gap inside sampling noise.

Run:  python -m pytest tests/test_evaluation_depth.py -v
"""
import json
import os

import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAL_PATH = os.path.join(BASE, "reports", "calibration_decision_curve_metrics.json")
TEMP_PATH = os.path.join(BASE, "reports", "temporal_validation_metrics.json")


@pytest.fixture(scope="module")
def cal():
    assert os.path.exists(CAL_PATH), "run scripts/calibration_decision_curve.py"
    with open(CAL_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def temp():
    assert os.path.exists(TEMP_PATH), "run scripts/temporal_validation.py"
    with open(TEMP_PATH) as f:
        return json.load(f)


# ── Calibration: pinned values ────────────────────────────────────────
def test_pinned_calibration(cal):
    c = cal["calibration"]
    assert c["raw"]["brier"] == pytest.approx(0.0187, abs=5e-3)
    assert c["isotonic"]["brier"] == pytest.approx(0.0102, abs=5e-3)
    assert c["raw"]["slope"] == pytest.approx(1.434, abs=0.05)
    assert c["test_prevalence"] == pytest.approx(0.269, abs=5e-3)


def test_isotonic_improves_probability_quality(cal):
    c = cal["calibration"]
    assert c["isotonic"]["brier"] < c["raw"]["brier"]
    assert c["isotonic"]["ece"] < c["raw"]["ece"]
    assert cal["verdict"]["isotonic_improves_brier"] is True


def test_raw_slope_miscalibrated(cal):
    # slope 1.43 => under-confident; |slope - 1| > 0.2 must flag it
    assert cal["verdict"]["raw_model_miscalibrated"] is True


def test_model_beats_prevalence_reference(cal):
    assert cal["calibration"]["isotonic"]["brier"] < cal["calibration"]["prevalence_reference_brier"]


# ── DCA: pinned + invariant ───────────────────────────────────────────
def test_dca_model_beats_treat_all_everywhere(cal):
    assert cal["verdict"]["model_beats_treat_all_at"] == 7
    for row in cal["dca"]:
        assert row["model_net_benefit"] > row["treat_all_net_benefit"]
        assert row["treat_none_net_benefit"] == 0.0


def test_dca_has_7_thresholds(cal):
    assert len(cal["dca"]) == 7
    assert cal["dca"][0]["threshold"] == 0.10


# ── Subgroup CI discipline ────────────────────────────────────────────
def test_small_bands_refuse_to_report_metrics(cal):
    bands = {r["band"]: r for r in cal["subgroup"]["by_age_band"]}
    # 18-30 has 0 positives, 31-45 has 2 -> both must refuse
    assert "warning" in bands["18-30"]
    assert "warning" in bands["31-45"]
    assert "auc" not in bands["18-30"]
    assert "auc" not in bands["31-45"]


def test_healthy_bands_report_ci(cal):
    bands = {r["band"]: r for r in cal["subgroup"]["by_age_band"]}
    for name in ("46-60", "61-75", "76-+"):
        assert "auc_ci95" in bands[name]
        lo, hi = bands[name]["auc_ci95"]
        assert 0 <= lo <= hi <= 1.0
    genders = {r["gender"]: r for r in cal["subgroup"]["by_gender"]}
    assert "auc_ci95" in genders["Male"]
    assert "auc_ci95" in genders["Female"]


# ── Temporal validation: pinned + verdict ─────────────────────────────
def test_pinned_temporal(temp):
    assert temp["random_split"]["roc_auc"] == pytest.approx(0.9923, abs=5e-3)
    assert temp["temporal_split"]["roc_auc"] == pytest.approx(0.9963, abs=5e-3)
    assert temp["temporal_minus_random_auc"] == pytest.approx(0.0040, abs=5e-3)


def test_temporal_inside_sampling_noise(temp):
    assert temp["temporal_result_inside_sampling_noise_band"] is True
    nb = temp["random_repeat_band"]
    assert nb["p2_5"] <= temp["temporal_split"]["roc_auc"] <= nb["p97_5"]


def test_date_disclosure_present(temp):
    assert "INDEPENDENT of outcomes" in temp["date_disclosure"]


def test_verdict_mentions_protocol_value(temp):
    assert "protocol" in temp["verdict"]
