from pathlib import Path


def test_prediction_methodology_distinguishes_future_study_from_current_data():
    root = Path(__file__).resolve().parents[1]
    text = (root / 'docs/PREDICTION_POINT_METHODOLOGY.md').read_text(encoding='utf-8')
    assert 'no validated admission and discharge timeline or 30-day target' in text
    assert 'design checklist' in text
    assert 'final cost is not necessarily available at discharge' in text
    assert 'not for diagnosis, triage or treatment' in text
    assert 'Zero leakage' not in text
