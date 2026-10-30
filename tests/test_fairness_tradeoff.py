"""
test_fairness_tradeoff.py — the fairness trade-off must reproduce verified numbers
================================================================================
Day-2 upgrade pin. The scoring path (deployed encoders + 5-fold CV, seed 42) is
deterministic, so every gap and every mitigation cost is a known value. These
tests fail if the scoring path, the gap math, or the mitigation search drift.

Verified values (recomputed from reports/fairness_tradeoff.json):
984 patients · base rates F 43.9% / M 7.4% ·
deployed t=0.50: recall 99.24%, TPR gap 0.0588 ·
best-F1 t=0.70 · mitigation A t=0.85: TPR gap 0.0284 at Δrecall −2.65pp ·
mitigation B (F 0.85 / M 0.05): TPR gap 0.0010 but FPR gap 0.1082 — the
impossibility pin: closing the TPR gap un-closes the FPR gap.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REPORT = ROOT / "reports" / "fairness_tradeoff.json"
MD = ROOT / "reports" / "fairness_tradeoff.md"


def _report():
    return json.loads(REPORT.read_text())


# ── cohort pins ──────────────────────────────────────────────────────────────

def test_cohort_and_base_rates_pin():
    r = _report()
    assert r["cohort"]["patients"] == 984
    assert r["cohort"]["gender_base_rates_pct"] == {"Female": 43.9, "Male": 7.4}


# ── deployed operating point ─────────────────────────────────────────────────

def test_deployed_threshold_pins():
    d = _report()["deployed_threshold"]
    assert d["threshold"] == 0.5
    assert d["recall"] == 0.9924
    assert d["precision"] == 0.9887
    assert d["equal_opportunity_gap"] == 0.0588
    assert d["groups"]["Female"]["tpr"] == 1.0
    assert d["groups"]["Male"]["tpr"] == 0.9412


def test_best_f1_threshold_pins():
    b = _report()["best_f1_threshold"]
    assert b["threshold"] == 0.7
    assert abs(b["f1"] - 0.9924) < 1e-4


# ── mitigation A: single constrained threshold ──────────────────────────────

def test_mitigation_a_halves_the_gap_at_known_cost():
    r = _report()
    a = r["mitigation_single_threshold"]
    assert a["threshold"] == 0.85
    assert a["equal_opportunity_gap"] == 0.0284
    assert r["accuracy_cost"]["single_threshold"]["recall_delta"] == -0.0265
    # The gap must actually improve vs deployed.
    assert a["equal_opportunity_gap"] < r["deployed_threshold"]["equal_opportunity_gap"]


# ── mitigation B: group thresholds + THE IMPOSSIBILITY PIN ──────────────────

def test_mitigation_b_closes_tpr_gap_but_opens_fpr_gap():
    r = _report()
    b = r["mitigation_group_thresholds"]
    assert b["thresholds"] == {"Female": 0.85, "Male": 0.05}
    assert b["equal_opportunity_gap"] == 0.001
    # Chouldechova/Kleinberg visible in our own numbers: the FPR gap gets WORSE.
    deployed_fpr_gap = abs(
        r["deployed_threshold"]["groups"]["Female"]["fpr"] -
        r["deployed_threshold"]["groups"]["Male"]["fpr"])
    assert b["fpr_gap"] > deployed_fpr_gap
    assert abs(b["fpr_gap"] - 0.11) < 0.005  # 0.1082 or 0.1106 across sklearn versions
    # And precision pays for it.
    assert b["precision"] < r["best_f1_threshold"]["precision"]


# ── math identities (must hold for every sweep point) ───────────────────────

def test_f1_identity_holds_across_sweep():
    for s in _report()["sweep"]:
        p, rc = s["precision"], s["recall"]
        expected = 2 * p * rc / (p + rc) if (p + rc) else 0.0
        assert abs(expected - s["f1"]) < 1e-3, f"t={s['threshold']}"


def test_gap_is_max_minus_min_of_group_metrics():
    for s in _report()["sweep"]:
        tprs = [m["tpr"] for m in s["groups"].values()]
        sels = [m["selection_rate"] for m in s["groups"].values()]
        assert abs((max(tprs) - min(tprs)) - s["equal_opportunity_gap"]) < 2e-4
        assert abs((max(sels) - min(sels)) - s["demo_parity_gap"]) < 2e-4


def test_sweep_covers_19_thresholds():
    assert len(_report()["sweep"]) == 19
    assert _report()["sweep"][0]["threshold"] == 0.05
    assert _report()["sweep"][-1]["threshold"] == 0.95


# ── honest reporting ─────────────────────────────────────────────────────────

def test_report_discloses_impossibility_and_synthetic_nature():
    md = MD.read_text().lower()
    assert "impossibility" in md
    assert "synthetic" in md
    r = _report()
    assert "impossibility" in r["honesty"].lower()


def test_run_is_deterministic():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from fairness_tradeoff import run
    a = run()
    b = run()
    assert a["mitigation_group_thresholds"]["equal_opportunity_gap"] == \
           b["mitigation_group_thresholds"]["equal_opportunity_gap"]
    assert a["deployed_threshold"]["equal_opportunity_gap"] == \
           b["deployed_threshold"]["equal_opportunity_gap"]
