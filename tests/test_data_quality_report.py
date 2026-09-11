"""
test_data_quality_report.py — the DQ audit must run, report, and stay truthful
==============================================================================
Pins the Phase-4 upgrade: the generator runs, the report contains every check,
and the zero-failure claim matches reality (the report must never claim cleaner
data than the audit found).
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "data_quality_report.md"


def test_dq_script_runs_and_writes_report():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "data_quality_report.py")],
        capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, f"script failed:\n{result.stderr[-400:]}"
    assert REPORT.exists(), "reports/data_quality_report.md not written"


def test_report_contains_all_check_families():
    text = REPORT.read_text(encoding="utf-8")
    for family in ["Completeness", "Uniqueness", "Validity", "Consistency", "Stability"]:
        assert family in text, f"check family missing: {family}"
    # design characteristics surfaced, not hidden
    assert "Known (by design)" in text
    assert "model_honesty" in text


def test_reported_failures_match_audit_truth():
    """The summary's 'Failures: N' must equal the count of High/Critical rows
    in the table — the report may never understate issues."""
    text = REPORT.read_text(encoding="utf-8")
    m = re.search(r"Failures:\s*\*\*(\d+)\*\*", text)
    assert m, "summary failure count not found"
    claimed = int(m.group(1))
    actual = len(re.findall(r"\| (High|Critical) \|", text))
    assert claimed == actual, f"report claims {claimed} failures, table shows {actual}"
