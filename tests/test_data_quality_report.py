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
    assert "Observed context" in text
    assert "model_honesty" in text


def test_reported_failures_match_audit_truth():
    """The summary's 'Failures: N' must equal the count of Medium/High/Critical rows
    in the table — the report may never understate issues."""
    text = REPORT.read_text(encoding="utf-8")
    m = re.search(r"Failures:\s*\*\*(\d+)\*\*", text)
    assert m, "summary failure count not found"
    claimed = int(m.group(1))
    actual = len(re.findall(r"\| (Medium|High|Critical) \|", text))
    assert claimed == actual, f"report claims {claimed} failures, table shows {actual}"


def test_audit_uses_record_not_cell_denominators_and_real_scope():
    import pandas as pd
    from scripts.data_quality_report import run_audit
    df = pd.read_csv(ROOT / 'data/hospital/hospital_data.csv').head(10).copy()
    df.loc[0, ['Cost', 'Length_of_Stay']] = float('nan')
    report = run_audit(df)
    missing = next(row for row in report if row['check'] == 'Completeness')
    assert missing['affected'] == 1 and missing['pct'] == 10.0
    assert all(0 <= row['affected'] <= len(df) for row in report)


def test_audit_empty_scope_rejected():
    import pandas as pd
    import pytest
    from scripts.data_quality_report import run_audit
    df = pd.read_csv(ROOT / 'data/hospital/hospital_data.csv').iloc[:0]
    with pytest.raises(ValueError, match='empty'):
        run_audit(df)


def test_audit_report_matches_original_column_count():
    import pandas as pd
    text = REPORT.read_text(encoding='utf-8')
    df = pd.read_csv(ROOT / 'data/hospital/hospital_data.csv')
    assert f'{len(df):,} rows × {len(df.columns)} columns' in text
    assert 'Zero failures, zero warnings' not in text


def test_failing_medium_rule_has_investigate_treatment():
    import pandas as pd
    from scripts.data_quality_report import run_audit
    df = pd.read_csv(ROOT / 'data/hospital/hospital_data.csv').head(20).copy()
    df.loc[df.index[0], 'Satisfaction'] = 8
    row = next(row for row in run_audit(df) if row['check'] == 'Validity — Satisfaction')
    assert row['severity'] == 'Medium'
    assert row['affected'] == 1
    assert row['treatment'] == 'Investigate before use'
