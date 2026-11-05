"""Execute the workbench's state and reporting workflows in Streamlit."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'app/dashboard/Home.py'


def button(app, label):
    return next(x for x in app.button if x.label == label)


def test_workbench_quality_and_comparison_render_without_provider(monkeypatch):
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    app = AppTest.from_file(str(APP)).run(timeout=45)
    assert not app.exception
    assert next(m for m in app.metric if m.label == 'Selected contract checks').value == '12/12'
    app.radio(key='hg_workbench_step').set_value('Compare').run(timeout=45)
    assert not app.exception
    assert any('selection currently matches the full reference' in x.value for x in app.info)
    app.multiselect(key='hg_cond').set_value(['Diabetes']).run(timeout=45)
    assert not app.exception
    assert next(m for m in app.metric if m.label == 'Selected cohort records').value == '65'
    assert next(m for m in app.metric if m.label == 'Full reference records').value == '984'


def test_executed_sql_is_cleared_when_scope_or_query_changes(monkeypatch):
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    app = AppTest.from_file(str(APP)).run(timeout=45)
    app.radio(key='hg_workbench_step').set_value('SQL').run(timeout=45)
    button(app, 'Run scoped SQL').click().run(timeout=45)
    assert not app.exception
    saved = app.session_state['hg_workbench_result']
    assert saved['result']['reconciliation'] == 'PASS'
    assert saved['result']['rows_in_scope'] == 984
    app.selectbox(key='hg_workbench_query').set_value('cost_by_readmission').run(timeout=45)
    assert not app.exception
    assert 'hg_workbench_result' not in app.session_state
    button(app, 'Run scoped SQL').click().run(timeout=45)
    assert app.session_state['hg_workbench_result']['result']['key'] == 'cost_by_readmission'
    app.multiselect(key='hg_cond').set_value(['Diabetes']).run(timeout=45)
    assert 'hg_workbench_result' not in app.session_state
    button(app, 'Run scoped SQL').click().run(timeout=45)
    result = app.session_state['hg_workbench_result']['result']
    assert result['rows_in_scope'] == 65
    assert int(result['table'].records.sum()) == 65


def test_report_requires_a_real_build_and_does_not_survive_a_new_scope(monkeypatch):
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    app = AppTest.from_file(str(APP)).run(timeout=45)
    app.radio(key='hg_workbench_step').set_value('Report').run(timeout=45)
    button(app, 'Build stakeholder report').click().run(timeout=45)
    assert not app.exception
    report = app.session_state['hg_workbench_report']['text']
    assert 'SQL/pandas reconciliation: PASS' in report
    assert 'Selected records: 984; full reference: 984' in report
    app.multiselect(key='hg_cond').set_value(['Diabetes']).run(timeout=45)
    assert 'hg_workbench_report' not in app.session_state
    button(app, 'Build stakeholder report').click().run(timeout=45)
    assert 'Selected records: 65; full reference: 984' in app.session_state['hg_workbench_report']['text']


def test_rolling_update_reloads_older_workbench_module(monkeypatch):
    from app.dashboard.utils import analyst_workbench
    monkeypatch.setattr(analyst_workbench, 'WORKBENCH_VERSION', 1)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    app = AppTest.from_file(str(APP)).run(timeout=45)
    assert not app.exception
    assert analyst_workbench.WORKBENCH_VERSION == 3
    assert next(m for m in app.metric if m.label == 'Selected contract checks').value == '12/12'


def test_sql_warns_about_small_groups(monkeypatch):
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    app = AppTest.from_file(str(APP)).run(timeout=45)
    app.slider(key='hg_age').set_value((25, 30)).run(timeout=45)
    app.radio(key='hg_workbench_step').set_value('SQL').run(timeout=45)
    button(app, 'Run scoped SQL').click().run(timeout=45)
    assert not app.exception
    assert app.session_state['hg_workbench_result']['result']['small_groups'] > 0
    assert any('fewer than 30 records' in message.value for message in app.warning)


def test_older_cached_workbench_result_is_cleared_after_version_change(monkeypatch):
    from app.dashboard.utils import assistant_service
    from app.dashboard.utils.hospital_data import load_patients
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    app = AppTest.from_file(str(APP)).run(timeout=45)
    fingerprint = assistant_service.scope_fingerprint(load_patients())
    app.session_state['hg_workbench_scope'] = f'{fingerprint}:{fingerprint}:v2'
    app.session_state['hg_workbench_result'] = {'signature': 'old', 'result': {}}
    app.session_state['hg_workbench_report'] = {'signature': 'old', 'text': 'old'}
    app.run(timeout=45)
    assert not app.exception
    assert 'hg_workbench_result' not in app.session_state
    assert 'hg_workbench_report' not in app.session_state


def test_decision_record_is_scoped_and_cleared_on_filter_change(monkeypatch):
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    app = AppTest.from_file(str(APP)).run(timeout=45)
    app.radio(key='hg_workbench_step').set_value('Decision').run(timeout=45)
    button(app, 'Build decision record').click().run(timeout=45)
    assert not app.exception
    record = app.session_state['hg_decision_record']
    assert record['scope']['selected_records'] == 984
    assert record['scope']['filter_context']['conditions'] == []
    assert record['scenarios']['base']['records'] == 50
    assert record['observed_outcome'] is None
    app.multiselect(key='hg_cond').set_value(['Diabetes']).run(timeout=45)
    assert not app.exception
    assert 'hg_decision_record' not in app.session_state
    button(app, 'Build decision record').click().run(timeout=45)
    assert app.session_state['hg_decision_record']['scope']['selected_records'] == 65
    assert app.session_state['hg_decision_record']['scope']['filter_context']['conditions'] == ['Diabetes']


def test_decision_history_add_and_manual_followup(monkeypatch):
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    app = AppTest.from_file(str(APP)).run(timeout=45)
    app.radio(key='hg_workbench_step').set_value('Decision').run(timeout=45)
    button(app, 'Build decision record').click().run(timeout=45)
    button(app, 'Add current snapshot to history').click().run(timeout=45)
    assert not app.exception
    assert len(app.session_state['hg_decision_history']['entries']) == 1
    app.text_input(key='hg_decision_follow_metric').set_value('Coding completeness')
    app.text_input(key='hg_decision_follow_unit').set_value('percent')
    app.text_input(key='hg_decision_follow_baseline').set_value('70')
    app.text_input(key='hg_decision_follow_observed').set_value('80')
    button(app, 'Add follow-up').click().run(timeout=45)
    assert not app.exception
    followup = app.session_state['hg_decision_history']['entries'][0]['followups'][0]
    assert followup['difference'] == 10
    assert followup['verification'] == 'user-entered, unverified'
