"""Reproduce a documented, aggregate-only analyst workbench example.

Run from the repository root: python scripts/export_analyst_example.py
"""
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.dashboard.utils import analyst_workbench as workbench  # noqa: E402


def main():
    reference = pd.read_csv(ROOT / 'data/hospital/hospital_data.csv')
    selected = reference[reference.Condition.eq('Diabetes')]
    if len(selected) != 65:
        raise ValueError('The documented Diabetes example changed; review its population before publishing.')
    text = workbench.build_report(selected, reference, 'costs', generated_at='Reproducible example; dataset version as committed')
    path = ROOT / 'reports/analyst_workbench_example.md'
    path.write_text(text, encoding='utf-8')
    print(f'Wrote {path}; selected {len(selected)} of {len(reference)} records; scoped SQL reconciled.')


if __name__ == '__main__':
    main()
