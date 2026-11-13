"""Execute the Streamlit workflow, not just source-string assertions."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from app.dashboard.utils import gemini_ai

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'app/dashboard/Home.py'


def button(app, label):
    return next(b for b in app.button if b.label == label)


def test_local_question_workflow_and_provenance_without_provider(monkeypatch):
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    app = AppTest.from_file(str(APP)).run(timeout=80)
    assert not app.exception
    app.text_input(key='qa_input').set_value('How many patients were readmitted?')
    button(app, 'Calculate answer').click().run(timeout=80)
    assert not app.exception
    assert any('264 patients' in item.value for item in app.success)
    result = app.session_state['hg_assistant_history'][-1]['response']
    assert result['mode'] == 'computed' and result['formula']
    assert result['value'] == 264


def test_filter_change_clears_prior_answer_and_updates_scope(monkeypatch):
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    app = AppTest.from_file(str(APP)).run(timeout=80)
    button(app, 'Readmission rate').click().run(timeout=80)
    assert app.session_state['hg_assistant_history']
    old_scope = app.session_state['hg_assistant_scope']
    app.multiselect(key='hg_cond').set_value(['Diabetes']).run(timeout=80)
    assert not app.exception
    assert app.session_state['hg_assistant_history'] == []
    assert app.session_state['hg_assistant_scope'] != old_scope
    assert next(m for m in app.metric if m.label == 'Records in assistant scope').value == '65'


def test_false_premise_does_not_trigger_a_provider_fallback(monkeypatch):
    monkeypatch.setenv('GOOGLE_API_KEY', 'test-only-not-a-real-key')
    def forbidden_call():
        raise AssertionError('Provider must not be called by unsupported Q&A')
    monkeypatch.setattr(gemini_ai, '_get_client', forbidden_call)
    app = AppTest.from_file(str(APP)).run(timeout=80)
    app.text_input(key='qa_input').set_value('Readmission rate for lung cancer')
    button(app, 'Calculate answer').click().run(timeout=80)
    assert not app.exception
    assert not app.session_state['hg_assistant_history'][-1]['response']['ok']
    assert any("I can't answer" in item.value for item in app.info)


def test_single_outcome_cohort_does_not_show_a_fictitious_zero_comparator(monkeypatch):
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    app = AppTest.from_file(str(APP)).run(timeout=80)
    app.multiselect(key='hg_cond').set_value(['Heart Attack']).run(timeout=80)
    assert not app.exception
    rendered = '\n'.join(item.value for item in app.markdown)
    assert 'Not available' in rendered
    findings = [item.value for item in app.info if 'Findings (computed)' in item.value]
    assert findings and 'comparison group is absent' in findings[0]
    assert 'versus ₹0' not in findings[0]


def test_outer_dashboard_error_does_not_expose_exception_body(monkeypatch, caplog):
    from app.dashboard.utils import hospital_data
    def broken_load():
        raise RuntimeError('PRIVATE_BACKEND_SECRET_SHOULD_NOT_APPEAR')
    monkeypatch.setattr(hospital_data, 'load_patients', broken_load)
    app = AppTest.from_file(str(APP)).run(timeout=80)
    assert not app.exception
    assert any('This dashboard view could not load' in item.value for item in app.error)
    assert 'PRIVATE_BACKEND_SECRET' not in '\n'.join(item.value for item in app.error) + caplog.text


def test_ambiguous_question_is_refused_in_app(monkeypatch):
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    app = AppTest.from_file(str(APP)).run(timeout=80)
    app.text_input(key='qa_input').set_value('How many patients not female?')
    button(app, 'Calculate answer').click().run(timeout=80)
    assert not app.exception
    response = app.session_state['hg_assistant_history'][-1]['response']
    assert not response['ok'] and response['status'] == 'clarification'


def test_service_version_change_clears_old_assistant_history(monkeypatch):
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    app = AppTest.from_file(str(APP)).run(timeout=80)
    app.session_state['hg_assistant_scope'] = 'old-scope:v2'
    app.session_state['hg_assistant_history'] = [{'question': 'old', 'response': {}}]
    app.session_state['hg_assistant_brief'] = {'old': True}
    app.run(timeout=80)
    assert not app.exception
    assert app.session_state['hg_assistant_history'] == []
    assert 'hg_assistant_brief' not in app.session_state
