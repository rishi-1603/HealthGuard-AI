"""
test_qa_eval.py — the QA layer must answer from data AND refuse the unanswerable
================================================================================
Day-2 upgrade pin. Verified: answerable 8/8 grounded · out-of-scope 3/3 refused ·
false-premise traps 3/3 passed · fabrications 0 · verdict PASS.

This suite also pins the PRODUCT FIX the eval caught: questions about
conditions that do not exist ('readmission rate for lung cancer') must refuse —
before the fix, the layer answered with the overall rate (a confident answer to
an unanswerable question). 'lung cancer' must not fuzzy-match the 'Cancer'
condition either.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.dashboard.utils.simple_qa import answer  # noqa: E402

REPORT = ROOT / "reports" / "qa_eval.json"
DATA = ROOT / "data" / "hospital" / "hospital_data.csv"


def _report():
    return json.loads(REPORT.read_text())


@pytest.fixture(scope="module")
def df():
    return pd.read_csv(DATA)


# ── eval result pins ─────────────────────────────────────────────────────────

def test_answerable_all_grounded():
    r = _report()
    assert r["answerable"]["n"] == 8
    assert r["answerable"]["grounded"] == 8
    assert r["answerable"]["accuracy"] == 1.0


def test_refusals_and_traps_all_pass():
    r = _report()
    assert r["out_of_scope"]["refused"] == 3
    assert r["false_premise_traps"]["passed"] == 3
    assert r["false_premise_traps"]["trap_accuracy"] == 1.0


def test_zero_fabrications_verdict_pass():
    r = _report()
    assert r["fabrications_total"] == 0
    assert r["overall_accuracy"] == 1.0
    assert r["verdict"] == "PASS"


# ── product properties (the fix the eval forced) ────────────────────────────

def test_false_premise_lung_cancer_refuses(df):
    res = answer(df, "What is the readmission rate for lung cancer?")
    assert res["ok"] is False, f"answered about a nonexistent condition: {res}"
    assert "refus" in res["text"].lower() or "can't answer" in res["text"].lower()


def test_false_premise_brain_transplant_refuses(df):
    res = answer(df, "What is the readmission rate for brain transplant?")
    assert res["ok"] is False


def test_real_condition_still_answers(df):
    res = answer(df, "What is the readmission rate for diabetes?")
    assert res["ok"] is True
    rate = (df[df.Condition == "Diabetes"].Readmission == "Yes").mean() * 100
    assert f"{rate:.1f}%" in res["text"]


def test_cancer_condition_exact_name_works(df):
    res = answer(df, "What is the readmission rate for cancer?")
    assert res["ok"] is True
    rate = (df[df.Condition == "Cancer"].Readmission == "Yes").mean() * 100
    assert f"{rate:.1f}%" in res["text"]


def test_no_fabrication_in_refusal_text(df):
    res = answer(df, "What is the readmission rate for lung cancer?")
    # the refusal must not present a confident condition rate
    assert "26.8%" not in res["text"]  # the overall rate must not be smuggled in
