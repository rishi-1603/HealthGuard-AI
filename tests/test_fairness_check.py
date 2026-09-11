"""
test_fairness_check.py — the fairness audit must run, report, and stay honest
==============================================================================
Pins the Phase-2 upgrade: script runs, report contains all demographic slices,
the AUC-parity finding, and — critically — the honest framing (no fairness
certification from synthetic data).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "fairness_check.md"


def test_fairness_script_runs_and_writes_report():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "fairness_check.py")],
        capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, f"script failed:\n{result.stderr[-400:]}"
    assert REPORT.exists(), "reports/fairness_check.md not written"


def test_report_contains_all_slices_and_findings():
    text = REPORT.read_text(encoding="utf-8")
    for slice_label in ["Age Under 40", "Age 40-59", "Age 60+",
                        "Gender Female", "Gender Male", "Overall"]:
        assert slice_label in text, f"slice missing: {slice_label}"
    # the two findings must be present
    assert "AUC gap" in text
    assert "base-rate disparity" in text
    # the honest framing must survive future edits
    assert "No fairness conclusion is drawn from synthetic data" in text
    assert "synthetic" in text


def test_auc_gaps_are_small_on_this_dataset():
    """The measured invariant: out-of-fold AUC gaps < 0.05 across groups.
    If this ever fails after a legitimate model/data change, update the report."""
    import re
    text = REPORT.read_text(encoding="utf-8")
    gaps = [float(g) for g in re.findall(r"AUC gap[^0-9]*([0-9]+\.[0-9]+)", text)]
    assert gaps, "no AUC gaps parsed from report"
    assert max(gaps) < 0.05, f"AUC gap grew beyond noise band: {gaps}"
