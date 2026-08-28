"""
test_qa_grounding.py — the Q&A layer must answer from DATA, never invent
==========================================================================
The project's key AI-trust claim: answers come from real aggregations of the
dataset (keyword-matched templates), with an optional Gemini fallback that is
clearly labelled. These tests pin the grounded path to actual dataset numbers.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.dashboard.utils.simple_qa import answer  # noqa: E402

DATA_PATH = ROOT / "data" / "hospital" / "hospital_data.csv"


@pytest.fixture(scope="module")
def df():
    return pd.read_csv(DATA_PATH)


def _ok(result):
    assert result.get("ok") is True, f"Q&A failed: {result}"
    return result["text"]


def test_overall_readmission_rate_is_grounded(df):
    text = _ok(answer(df, "What is the overall readmission rate?"))
    expected = (df.Readmission == "Yes").mean() * 100
    assert f"{expected:.1f}%" in text, (
        f"Answer did not contain the dataset's real rate ({expected:.1f}%): {text}")


def test_condition_specific_readmission_is_grounded(df):
    text = _ok(answer(df, "readmission rate for heart attack"))
    sub = df[df.Condition == "Heart Attack"]
    expected = (sub.Readmission == "Yes").mean() * 100
    assert f"{expected:.1f}%" in text


def test_patient_count_is_grounded(df):
    text = _ok(answer(df, "how many patients with diabetes"))
    expected = (df.Condition == "Diabetes").sum()
    assert f"**{expected} patients**" in text


def test_average_cost_is_grounded(df):
    text = _ok(answer(df, "average cost"))
    expected = df.Cost.mean()
    assert f"₹{expected:,.0f}" in text


def test_satisfaction_is_grounded(df):
    text = _ok(answer(df, "average satisfaction"))
    expected = df.Satisfaction.mean()
    assert f"{expected:.2f}" in text


def test_unknown_subgroup_does_not_answer_with_total():
    """Trust behaviour: if the question names an unrecognized subgroup, the
    grounded layer must REFUSE (escalate to the labelled Gemini fallback),
    never silently answer the total count."""
    result = answer(pd.DataFrame(
        {"Condition": ["Diabetes"], "Readmission": ["Yes", "No"][:1],
         "Cost": [1000], "Satisfaction": [4], "Outcome": ["Recovered"],
         "Length_of_Stay": [3]}),
        "how many pediatric patients")
    assert result.get("ok") is False, (
        f"Unrecognized subgroup was answered instead of escalated: {result}")


def test_numbers_in_answers_always_come_from_data(df):
    """Fuzz-style invariant: for a battery of questions, every percentage in
    the answer must equal a rate computable from the dataframe — the grounded
    layer cannot invent statistics."""
    questions = [
        "overall readmission rate",
        "readmission rate for cancer",
        "readmission rate for stroke",
        "average length of stay",
        "average satisfaction",
    ]
    for q in questions:
        text = _ok(answer(df, q))
        # extract percentages and check they match real dataset values
        import re
        for pct_str in re.findall(r"(\d+\.\d)%", text):
            pct = float(pct_str)
            candidates = {
                (df.Readmission == "Yes").mean() * 100,
                *[((df[df.Condition == c].Readmission == "Yes").mean() * 100)
                  for c in df.Condition.unique()],
            }
            assert any(abs(pct - c) < 0.15 for c in candidates), (
                f"Answer to '{q}' contains percentage {pct}% not derivable "
                f"from the dataset — hallucination risk")
