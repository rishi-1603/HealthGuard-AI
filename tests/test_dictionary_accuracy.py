"""Guard the observed dataset facts used in the human-readable dictionary."""
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def test_dictionary_observed_ranges_and_labels_match_committed_csv():
    df = pd.read_csv(ROOT / 'data/hospital/hospital_data.csv')
    text = (ROOT / 'data/DATA_DICTIONARY.md').read_text(encoding='utf-8')
    for column, label in [('Patient_ID', '1–1000 observed, unique'),
                          ('Age', '25–78 observed'), ('Cost', '₹100–₹25,000 observed'),
                          ('Length_of_Stay', '1–76 days observed')]:
        assert label in text
        numbers = {'Patient_ID': (1, 1000), 'Age': (25, 78),
                   'Cost': (100, 25000), 'Length_of_Stay': (1, 76)}
        assert (df[column].min(), df[column].max()) == numbers[column]
    assert set(df.Outcome) == {'Recovered', 'Stable'}
    assert 'timing is not established' in text


def test_documented_age_bands_match_current_chart():
    from app.dashboard.utils.hospital_data import age_group_readmission
    df = pd.read_csv(ROOT / 'data/hospital/hospital_data.csv')
    registry = json.loads((ROOT / 'data/metrics.json').read_text(encoding='utf-8'))
    stated = registry['metrics']['age_bands']['verified_readmit_rates_pct']
    chart = age_group_readmission(df)
    for row in chart.itertuples(index=False, name=None):
        label, _, _, rate = row
        assert stated[str(label).replace('–', '-')] == rate
