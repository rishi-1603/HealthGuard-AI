"""
test_cohort_shap.py — cohort explainability must run, report, and stay honest
==============================================================================
Pins the Phase-1 upgrade: the cohort SHAP analysis exists, its report matches
the computed ranking, and the pathway-share invariant (the honesty-audit
finding) holds.
"""
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REPORT = ROOT / "reports" / "cohort_shap.md"


def test_cohort_shap_script_runs_and_writes_report():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "cohort_shap_analysis.py")],
        capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, f"script failed:\n{result.stderr[-400:]}"
    assert REPORT.exists(), "reports/cohort_shap.md not written"


def test_report_contains_all_factors_and_honest_caveat():
    text = REPORT.read_text(encoding="utf-8")
    for factor in ["Procedure", "Cost", "Age", "Gender", "Condition", "Length of stay"]:
        assert factor in text, f"factor missing from report: {factor}"
    # the honest framing must survive future edits
    assert "NOT clinical evidence" in text
    assert "correlated" in text  # explains diffuse attribution


def test_pathway_share_invariant():
    """Procedure + Cost + Condition + LOS must hold >50% of influence —
    the SHAP-side confirmation of the model-honesty finding."""
    from app.dashboard.utils import hospital_data as data
    from scripts.cohort_shap_analysis import compute_cohort_importance
    df = data.load_patients()
    importance, _ = compute_cohort_importance(df)
    total = importance.sum()
    pathway = sum(importance.get(f, 0) for f in
                  ["Procedure_enc", "Cost", "Condition_enc", "Length_of_Stay"])
    assert pathway / total > 0.5, (
        f"Pathway-linked share dropped to {pathway/total:.1%} — if the model or data "
        "changed legitimately, update reports/cohort_shap.md and model_honesty.md")


def test_all_six_features_attributed():
    from app.dashboard.utils import hospital_data as data
    from scripts.cohort_shap_analysis import compute_cohort_importance
    df = data.load_patients()
    importance, _ = compute_cohort_importance(df)
    assert len(importance) == 6, "expected SHAP attribution for all 6 model features"
