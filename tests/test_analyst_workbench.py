"""Independent acceptance checks for an analyst's validate/query/report workflow."""
from pathlib import Path

import pandas as pd
import pytest

from app.dashboard.utils import analyst_workbench as workbench

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def patients():
    return pd.read_csv(ROOT / 'data/hospital/hospital_data.csv')


def test_supplied_dataset_passes_all_twelve_contract_checks(patients):
    quality = workbench.quality_report(patients)
    assert quality['all_passed'] and quality['passed'] == 12
    assert quality['failed'] == quality['blocked'] == 0
    assert quality['records'] == 984


@pytest.mark.parametrize('column,value', [('Age', 150), ('Cost', -1),
                                         ('Length_of_Stay', -4), ('Satisfaction', 9),
                                         ('Readmission', 'unknown'), ('Gender', 'not-a-project-label'),
                                         ('Outcome', 'unknown'), ('Condition', 'invented')])
def test_contract_flags_bad_values_without_repairing_input(patients, column, value):
    data = patients.copy()
    data.loc[0, column] = value
    before = data.copy(deep=True)
    quality = workbench.quality_report(data)
    assert not quality['all_passed'] and quality['failed'] >= 1
    pd.testing.assert_frame_equal(before, data)


def test_duplicate_and_missing_ids_are_not_hidden(patients):
    duplicated = pd.concat([patients, patients.head(1)], ignore_index=True)
    assert not workbench.quality_report(duplicated)['all_passed']
    missing = patients.copy()
    missing.loc[0, 'Patient_ID'] = float('nan')
    assert not workbench.quality_report(missing)['all_passed']


def test_missing_schema_and_empty_data_are_not_passed(patients):
    report = workbench.quality_report(patients.drop(columns='Cost'))
    assert not report['all_passed'] and report['blocked'] == 1
    assert not workbench.quality_report(patients.iloc[:0])['all_passed']
    with pytest.raises(ValueError):
        workbench.execute_question(patients.iloc[:0], 'cost_by_condition')


def test_comparison_uses_explicit_units_and_population(patients):
    selected = patients[patients.Condition.eq('Diabetes')]
    comparison = workbench.compare_cohorts(selected, patients).set_index('metric')
    row = comparison.loc['Readmission rate']
    expected_selected = selected.Readmission.eq('Yes').mean() * 100
    expected_reference = patients.Readmission.eq('Yes').mean() * 100
    assert row.selected_value == pytest.approx(expected_selected)
    assert row.reference_value == pytest.approx(expected_reference)
    assert row.difference == pytest.approx(expected_selected - expected_reference)
    assert row.difference_unit == 'percentage points'
    assert row.selected_n == 65 and row.reference_n == 984
    assert comparison.loc['Mean recorded cost', 'selected_value'] == 2000


def test_full_scope_has_zero_differences(patients):
    result = workbench.compare_cohorts(patients, patients)
    assert result.difference.eq(0).all()


def test_reference_cannot_silently_expand_an_unrelated_or_altered_selection(patients):
    altered = patients.head(2).copy()
    altered['Cost'] = altered.Cost.astype(float)
    altered.loc[0, 'Cost'] += .001
    with pytest.raises(ValueError, match='values do not match'):
        workbench.compare_cohorts(altered, patients)
    altered.loc[0, 'Patient_ID'] = 99999
    with pytest.raises(ValueError, match='not a subset'):
        workbench.compare_cohorts(altered, patients)


@pytest.mark.parametrize('question', list(workbench.QUERY_LABELS))
@pytest.mark.parametrize('scope', ['all', 'diabetes'])
def test_all_trusted_sql_questions_execute_and_reconcile(patients, question, scope):
    selected = patients if scope == 'all' else patients[patients.Condition.eq('Diabetes')]
    result = workbench.execute_question(selected, question)
    assert result['reconciliation'] == 'PASS' and result['checked_values'] > 0
    assert result['rows_in_scope'] == len(selected)
    assert int(result['table'].records.sum()) == len(selected)
    if question == 'cost_by_condition':
        assert result['table'].total_cost.sum() == pytest.approx(selected.Cost.sum(), abs=.005)
        assert result['table'].cost_share_pct.sum() == pytest.approx(100, abs=.1)
        if scope == 'diabetes':
            assert list(result['table'].condition) == ['Diabetes']


def test_half_up_rounding_does_not_create_false_reconciliation_failures(patients):
    sample = patients.head(32).copy()
    sample['Gender'] = 'Male'
    sample['Condition'] = 'Diabetes'
    sample['Readmission'] = ['Yes'] * 25 + ['No'] * 7
    result = workbench.execute_question(sample, 'readmission_by_gender')
    assert result['table'].iloc[0].readmission_rate_pct == 78.13
    assert result['reconciliation'] == 'PASS'


def test_absent_status_groups_are_not_fabricated_as_zero_cost(patients):
    selected = patients[patients.Condition.eq('Heart Attack')]
    result = workbench.execute_question(selected, 'cost_by_readmission')
    assert list(result['table'].readmission) == ['Yes']
    assert result['table'].iloc[0].avg_cost == 18000


def test_zero_recorded_cost_share_is_unavailable_not_a_fabricated_percentage(patients):
    selected = patients.head(5).copy()
    selected['Cost'] = 0
    result = workbench.execute_question(selected, 'cost_by_condition')
    assert result['table'].cost_share_pct.isna().all()


def test_untrusted_sql_key_cannot_be_executed(patients):
    with pytest.raises(ValueError):
        workbench.execute_question(patients, 'SELECT * FROM raw_patients; DROP TABLE x;')


def test_report_is_a_reproducible_snapshot_with_no_causal_savings_claim(patients):
    selected = patients[patients.Condition.eq('Diabetes')]
    text = workbench.build_report(selected, patients, 'costs', generated_at='2026-11-03T00:00:00Z')
    assert text == workbench.build_report(selected, patients, 'costs', generated_at='2026-11-03T00:00:00Z')
    assert 'Selected records: 65; full reference: 984' in text
    assert 'not an independent control group' in text
    assert 'SQL/pandas reconciliation: PASS' in text
    assert 'percentage points' in text
    assert 'not an estimate of preventable savings' in text
    assert 'Patient_ID' not in text and 'Patient_Code' not in text


def test_report_blocks_a_bad_reference_even_when_selection_is_clean(patients):
    selected = patients.head(5).copy()
    reference = pd.concat([patients, patients.head(1)])
    with pytest.raises(ValueError, match='data contract'):
        workbench.build_report(selected, reference)


def test_no_input_mutation_and_no_provider_needed(patients, monkeypatch):
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    before = patients.copy(deep=True)
    workbench.build_report(patients.head(20), patients, 'readmissions', generated_at='test')
    pd.testing.assert_frame_equal(before, patients)


def test_unsupported_report_focus_is_rejected(patients):
    with pytest.raises(ValueError):
        workbench.build_report(patients, patients, 'prescribe or guarantee savings')


def test_blank_required_text_is_not_counted_as_complete(patients):
    for column in ['Patient_ID', 'Procedure']:
        data = patients.copy()
        data[column] = data[column].astype(object)
        data.loc[0, column] = '   '
        quality = workbench.quality_report(data)
        assert not quality['all_passed']
        assert any(c['check'] == 'Required cells present' and c['status'] == 'FAIL' for c in quality['checks'])


def test_broken_tracked_query_does_not_publish_an_unverified_result(patients, monkeypatch):
    monkeypatch.setattr(workbench, 'load_queries', lambda: {'cost_by_condition': 'SELECT missing_column FROM scope_encounters'})
    with pytest.raises(ValueError, match='tracked SQL question could not execute'):
        workbench.execute_question(patients, 'cost_by_condition')
