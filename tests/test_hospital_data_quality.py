"""
test_hospital_data_quality.py — data quality checks for the ACTUAL product dataset
===================================================================================
The legacy smoke test covers the FHIR prototype; these tests cover the dataset
the live dashboard actually serves (data/hospital/hospital_data.csv).

If any of these fail, every KPI on the live dashboard is untrustworthy.
"""
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "hospital" / "hospital_data.csv"

VALID_READMISSION = {"Yes", "No"}
VALID_OUTCOMES = {"Recovered", "Stable", "Deceased"}
VALID_GENDERS = {"Male", "Female"}


@pytest.fixture(scope="module")
def df():
    return pd.read_csv(DATA_PATH)


def test_dataset_loads_and_expected_size(df):
    # 984 patients is the documented size; a silent row loss would change every KPI
    assert len(df) == 984, f"Expected 984 patients, found {len(df)}"


def test_patient_id_unique_and_complete(df):
    assert df["Patient_ID"].notna().all()
    assert df["Patient_ID"].is_unique, "Duplicate Patient_IDs would double-count KPIs"


def test_no_missing_values_in_required_columns(df):
    required = ["Patient_ID", "Age", "Gender", "Condition", "Procedure",
                "Cost", "Length_of_Stay", "Readmission", "Outcome", "Satisfaction"]
    missing = [c for c in required if df[c].isna().any()]
    assert not missing, f"Nulls found in: {missing}"


def test_age_in_plausible_range(df):
    assert df["Age"].between(0, 120).all(), "Implausible ages present"


def test_cost_and_los_positive(df):
    assert (df["Cost"] > 0).all(), "Non-positive costs present"
    assert (df["Length_of_Stay"] > 0).all(), "Non-positive lengths of stay present"


def test_categorical_values_valid(df):
    bad_readmit = set(df["Readmission"].unique()) - VALID_READMISSION
    assert not bad_readmit, f"Invalid Readmission values: {bad_readmit}"
    bad_outcome = set(df["Outcome"].unique()) - VALID_OUTCOMES
    assert not bad_outcome, f"Invalid Outcome values: {bad_outcome}"
    bad_gender = set(df["Gender"].unique()) - VALID_GENDERS
    assert not bad_gender, f"Invalid Gender values: {bad_gender}"


def test_satisfaction_in_range(df):
    assert df["Satisfaction"].between(1, 5).all(), "Satisfaction outside 1-5"


def test_condition_procedure_mapping_is_consistent(df):
    """The dataset maps each condition to exactly one procedure (documented in
    the model honesty audit). If this changes, the audit and data dictionary
    must be updated — so test it."""
    n_proc = df.groupby("Condition")["Procedure"].nunique()
    multi = n_proc[n_proc > 1]
    assert multi.empty, f"Conditions with >1 procedure (docs assume 1:1): {dict(multi)}"


def test_readmission_base_rate_reasonable(df):
    """26.8% readmission rate is the documented headline; a drift here means
    the dataset changed and every dashboard stat shifted."""
    rate = (df["Readmission"] == "Yes").mean()
    assert 0.20 < rate < 0.35, f"Readmission rate {rate:.1%} outside expected band"


def test_every_condition_has_enough_patients(df):
    """Condition-level analytics need non-trivial group sizes."""
    counts = df["Condition"].value_counts()
    tiny = counts[counts < 30]
    assert tiny.empty, f"Conditions with <30 patients: {dict(tiny)}"
