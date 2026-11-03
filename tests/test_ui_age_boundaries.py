"""A chart's age labels must match the records included at each boundary."""
from pathlib import Path
import pandas as pd
import pytest
from app.dashboard.utils.hospital_data import age_group_readmission


def test_age_boundary_labels_and_denominators_are_correct():
    ages = [0, 29, 30, 31, 44, 45, 46, 59, 60, 61, 75, 76, 120]
    frame = pd.DataFrame({'Patient_ID': range(len(ages)), 'Age': ages,
                          'Readmission': ['Yes' if n % 2 else 'No' for n in ages]})
    out = age_group_readmission(frame).set_index('Age Group')
    assert out.loc['0–30', 'patients'] == 3
    assert out.loc['31–45', 'patients'] == 3
    assert out.loc['46–60', 'patients'] == 3
    assert out.loc['61–75', 'patients'] == 2
    assert out.loc['76–120', 'patients'] == 2
    assert out.patients.sum() == len(frame)
    assert out.loc['31–45', 'readmission_rate'] == pytest.approx(66.7)


@pytest.mark.parametrize('bad', [-1, 121, 30.5, None])
def test_invalid_age_is_explicitly_refused(bad):
    frame = pd.DataFrame({'Patient_ID': [1], 'Age': [bad], 'Readmission': ['Yes']})
    with pytest.raises(ValueError, match='whole-number ages'):
        age_group_readmission(frame)


def test_actual_full_dataset_is_accounted_for():
    root = Path(__file__).resolve().parents[1]
    frame = pd.read_csv(root / 'data/hospital/hospital_data.csv')
    out = age_group_readmission(frame)
    assert out.patients.sum() == len(frame) == 984
    assert out.readmissions.sum() == (frame.Readmission == 'Yes').sum() == 264
