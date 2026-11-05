import math
from pathlib import Path

import pandas as pd
import pytest

from app.dashboard.utils import decision_engine

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def patients():
    return pd.read_csv(ROOT / 'data/hospital/hospital_data.csv')


def test_admin_review_scenarios_use_scoped_population_and_assumptions(patients):
    selected = patients[patients.Condition.eq('Diabetes')]
    result = decision_engine.plan_review(selected, patients, capacity=20, minutes=30, hourly_rate=600)
    assert result['source']['reconciliation'] == 'PASS'
    assert result['source']['reconciled_result_cells'] > 0
    assert result['scope']['selected_records'] == 65
    assert result['scope']['reference_records'] == 984
    assert result['evidence']['readmission_rate_pct'] == pytest.approx(selected.Readmission.eq('Yes').mean() * 100)
    assert result['scenarios']['base']['records'] == 20
    assert result['scenarios']['base']['hours'] == 10
    assert result['scenarios']['base']['cost_inr'] == 6000
    assert result['scenarios']['low']['cost_inr'] == 3000
    assert result['scenarios']['high']['cost_inr'] == 9000
    assert result['observed_outcome'] is None


def test_capacity_is_capped_and_zero_is_not_a_fabricated_benefit(patients):
    sample = patients.head(3)
    record = decision_engine.plan_review(sample, patients, capacity=100, minutes=10, hourly_rate=300)
    assert record['scenarios']['base']['records'] == 3
    assert record['scenarios']['base']['cost_inr'] == 150
    assert decision_engine.plan_review(sample, patients, capacity=0, minutes=10, hourly_rate=300)['scenarios']['base']['cost_inr'] == 0
    assert 'savings' not in record['scenarios']['base']


@pytest.mark.parametrize('kw', [dict(capacity=-1), dict(capacity=1.5), dict(minutes=-1),
                                dict(minutes=math.inf), dict(hourly_rate=float('nan'))])
def test_invalid_or_unbounded_assumptions_are_rejected(patients, kw):
    args = dict(capacity=20, minutes=30, hourly_rate=600); args.update(kw)
    with pytest.raises(ValueError):
        decision_engine.plan_review(patients.head(5), patients, **args)


def test_bad_or_altered_cohort_cannot_generate_decision(patients):
    selection = patients.head(5).copy()
    selection.loc[selection.index[0], 'Cost'] += 1
    with pytest.raises(ValueError):
        decision_engine.plan_review(selection, patients, capacity=5, minutes=10, hourly_rate=500)


def test_decision_tracking_does_not_turn_planned_into_observed(patients):
    rec = decision_engine.plan_review(patients.head(5), patients, capacity=5, minutes=10, hourly_rate=500,
                                     action='Investigate coding', success_metric='Readmission flag definition',
                                     follow_up='Review source definitions')
    assert rec['decision']['status'] == 'proposed'
    assert rec['observed_outcome'] is None
    assert 'not clinical' in rec['limitations'].lower()


def test_record_includes_a_copy_of_filter_context(patients):
    filters = {'conditions': ['Diabetes'], 'age_range': [25, 78]}
    rec = decision_engine.plan_review(patients[patients.Condition.eq('Diabetes')], patients,
                                       capacity=5, minutes=10, hourly_rate=500, filter_context=filters)
    filters['conditions'].append('Stroke')
    assert rec['scope']['filter_context']['conditions'] == ['Diabetes']


def test_invalid_filter_context_rejected(patients):
    with pytest.raises(ValueError, match='Filter context'):
        decision_engine.plan_review(patients.head(5), patients, capacity=5, minutes=10, hourly_rate=500,
                                    filter_context={'age': float('nan')})
