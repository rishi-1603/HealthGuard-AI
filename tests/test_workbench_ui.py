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
    assert analyst_workbench.WORKBENCH_VERSION == 2
    assert next(m for m in app.metric if m.label == 'Selected contract checks').value == '12/12'
