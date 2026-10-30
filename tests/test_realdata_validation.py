"""
test_realdata_validation.py — headline METHODS must survive on real patients
================================================================================
Day-2 upgrade pin on the REAL external dataset (UCI Cleveland Heart Disease,
303 patients). Verified:

303 rows · positive rate 45.87% · sex base rates F 25.77% / M 55.34% ·
TPR gap at t=0.5 = 0.0782 · FPR gap 0.1431 ·
recall-constrained minimax (F 0.25 / M 0.35) reaches TPR gap 0.0011 / FPR gap 0.0085 under sklearn 1.9.0 ·
economics: enroll_all −₹118,124 · top-quartile +₹46,853 · above-baseline +₹65,038 ·
targeting beats blanket · the impossibility is honestly reported as NOT
reproducing on this set.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "realdata_validation.json"
MD = ROOT / "reports" / "realdata_validation.md"


def _report():
    return json.loads(REPORT.read_text())


def test_dataset_pins():
    d = _report()["dataset"]
    assert d["rows"] == 303
    assert d["positive_rate"] == 0.4587
    assert d["sex_base_rates"] == {"Female": 0.2577, "Male": 0.5534}


def test_gender_gap_exists_on_real_data():
    f = _report()["fairness_structure"]
    assert f["tpr_gap_at_0.5"] == 0.0782
    assert f["fpr_gap_at_0.5"] == 0.1431
    assert f["group_metrics_at_0.5"]["Female"]["tpr"] == 0.72
    assert f["group_metrics_at_0.5"]["Male"]["tpr"] == 0.7982


def test_postprocessing_reaches_equalized_odds():
    f = _report()["fairness_structure"]
    s = f["equalized_odds_search"]
    assert s["t_female"] == 0.25
    assert s["t_male"] == 0.35
    assert s["tpr_gap"] == 0.0011
    assert s["fpr_gap"] == 0.0085
    assert f["postprocess_closes_both_gaps"] is True


def test_economics_transfer_pins():
    e = _report()["economics_transfer"]
    rows = {s["strategy"]: s for s in e["strategies"]}
    assert rows["enroll_all"]["enrolled"] == 303
    assert abs(rows["enroll_all"]["net_value"] - (-118124.13)) < 0.01
    assert rows["enroll_top_quartile"]["enrolled"] == 75
    assert abs(rows["enroll_top_quartile"]["net_value"] - 46853.47) < 0.01
    assert abs(rows["enroll_above_baseline"]["net_value"] - 65037.88) < 0.01
    assert e["targeting_beats_blanket"] is True


def test_targeting_beats_blanket_on_real_outcomes():
    e = _report()["economics_transfer"]
    rows = {s["strategy"]: s for s in e["strategies"]}
    assert rows["enroll_top_quartile"]["net_value"] > rows["enroll_all"]["net_value"]
    assert rows["enroll_all"]["net_value"] < 0


def test_impossibility_reported_as_not_reproducing():
    # The honest negative result is a first-class pinned claim.
    v = next(v for v in _report()["verdicts"]
             if "impossibility" in v["conclusion"].lower())
    assert v["transfers"] is False
    assert "did NOT reproduce" in v["detail"]


def test_method_claims_transfer_but_values_do_not():
    verdicts = _report()["verdicts"]
    by_c = {v["conclusion"]: v for v in verdicts}
    assert by_c["A gender TPR gap exists in the deployed scoring regime"]["transfers"] is True
    assert by_c["Targeted enrollment beats blanket enrollment"]["transfers"] is True
    assert by_c["Specific rupee values (₹2.98L net, +112% premium)"]["transfers"] is False


def test_report_discloses_synthetic_context_and_real_source():
    md = MD.read_text().lower()
    assert "heart disease" in md
    assert "303" in md
    assert "synthetic" in md


def test_committed_real_dataset_exists():
    p = ROOT / "data" / "external" / "heart_disease.csv"
    assert p.exists()
    assert len(p.read_text().strip().splitlines()) == 304  # header + 303 patients


def test_external_fairness_search_retains_recall_and_records_runtime():
    report = _report()
    assert report["sklearn_version"] == "1.9.0"
    fairness = report["fairness_structure"]
    assert fairness["baseline_recall"] == 0.7842
    assert fairness["recall_floor"] == 0.7058
    assert fairness["equalized_odds_search"]["recall"] == 0.9209
    assert fairness["equalized_odds_search"]["recall"] >= fairness["recall_floor"]
