"""Daily analyst workflow: validate, compare, execute scoped SQL and report.

The reference is explicitly the full synthetic dataset, not an independent control.
No input rows are repaired, imputed or overwritten. SQL comes from a trusted named
query bank, runs against the selected cohort only and is checked against pandas.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from numbers import Real
import re
import sqlite3

import pandas as pd

from . import assistant_service as assistant
from .hospital_data import CONDITION_CODES

WORKBENCH_VERSION = 3
ROOT = Path(__file__).resolve().parents[3]
SQL_FILE = ROOT / 'sql/02_analyst_workbench.sql'
BASE_COLUMNS = ['Patient_ID', 'Age', 'Gender', 'Condition', 'Procedure', 'Cost',
                'Length_of_Stay', 'Readmission', 'Outcome', 'Satisfaction']
QUERY_LABELS = {
    'cost_by_condition': 'Where is recorded cost concentrated?',
    'readmission_by_gender': 'How do readmission flags differ by gender?',
    'cost_by_readmission': 'How do recorded costs differ by readmission flag?',
    'outcomes_by_condition': 'How do recorded outcomes differ by condition?',
}
QUERY_COLUMNS = {
    'cost_by_condition': ['condition', 'records', 'total_cost', 'avg_cost', 'cost_share_pct', 'readmitted', 'readmission_rate_pct'],
    'readmission_by_gender': ['gender', 'records', 'readmitted', 'readmission_rate_pct', 'avg_cost', 'avg_stay_days'],
    'cost_by_readmission': ['readmission', 'records', 'total_cost', 'avg_cost', 'avg_stay_days', 'cost_share_pct'],
    'outcomes_by_condition': ['condition', 'records', 'recovered', 'recovered_rate_pct', 'avg_satisfaction'],
}
FOCUSES = {'costs': 'Recorded cost review', 'readmissions': 'Readmission-flag review',
           'outcomes': 'Outcome reporting review'}
METRICS = [
    ('readmission_rate', 'Readmission rate', '%', 'percentage points'),
    ('average_cost', 'Mean recorded cost', 'INR', 'INR'),
    ('average_stay', 'Mean length of stay', 'days', 'days'),
    ('recovery_rate', 'Recovered outcome rate', '%', 'percentage points'),
]


def quality_report(df: pd.DataFrame) -> dict:
    checks = []

    def record(name, bad, detail):
        checks.append({'check': name, 'status': 'PASS' if bad == 0 else 'FAIL',
                       'affected': int(bad), 'definition': detail})

    record('Records available', 0 if len(df) else 1, 'An empty scope is not a measured zero rate.')
    missing = sorted(set(BASE_COLUMNS) - set(df.columns))
    record('Required columns', len(missing), 'Missing: ' + (', '.join(missing) or 'none'))
    if missing:
        checks.append({'check': 'Remaining contract checks', 'status': 'BLOCKED',
                       'affected': None, 'definition': 'Required columns must exist first.'})
    else:
        ids = df.Patient_ID
        missing_ids = ids.isna() | ids.map(lambda value: isinstance(value, str) and not value.strip()).astype(bool)
        record('Complete unique patient identifiers', int(missing_ids.sum()) + int(ids[~missing_ids].duplicated().sum()),
               'One row per synthetic patient; missing/duplicated IDs are not silently repaired.')
        blank_cells = sum(sum(isinstance(value, str) and not value.strip() for value in df[c]) for c in BASE_COLUMNS)
        record('Required cells present', int(df[BASE_COLUMNS].isna().sum().sum()) + blank_cells,
               'Missing values in the original schema are reported, not filled.')
        for column, lo, hi in [('Age', 0, 120), ('Cost', 0, float('inf')),
                              ('Length_of_Stay', 0, float('inf')), ('Satisfaction', 1, 5)]:
            values = pd.to_numeric(df[column], errors='coerce')
            numeric_type = df[column].map(lambda value: isinstance(value, Real) and not isinstance(value, bool)).astype(bool)
            valid = numeric_type & values.between(lo, hi) & values.notna() & ~values.isin([float('inf'), -float('inf')])
            if column == 'Age':
                valid &= values.mod(1).eq(0)
            detail = f'Finite numeric values in [{lo}, {hi}]; numeric strings and booleans are rejected.'
            if column == 'Age':
                detail += ' Age must be a whole number for the age-band chart.'
            record(column + ' range', int((~valid).sum()), detail + ' No imputation is performed.')
        for column, allowed in [('Readmission', {'Yes', 'No'}), ('Outcome', {'Recovered', 'Stable'}),
                                ('Gender', {'Female', 'Male'}), ('Condition', set(CONDITION_CODES))]:
            record(column + ' project labels', int((~df[column].isin(allowed)).sum()),
                   'Expected categories for this supplied synthetic dataset; not a universal clinical domain rule.')
    return {'records': len(df), 'checks': checks,
            'passed': sum(c['status'] == 'PASS' for c in checks),
            'failed': sum(c['status'] == 'FAIL' for c in checks),
            'blocked': sum(c['status'] == 'BLOCKED' for c in checks),
            'all_passed': all(c['status'] == 'PASS' for c in checks)}


def _require_quality(df: pd.DataFrame):
    result = quality_report(df)
    if not result['all_passed']:
        raise ValueError('The cohort does not pass the project data contract. Inspect the quality checks first.')


def metric_snapshot(df: pd.DataFrame) -> dict:
    """Use the same bounded calculation service as the assistant, not new formulas."""
    _require_quality(df)
    values = {}
    for metric in ['count', 'total_cost', *[m[0] for m in METRICS]]:
        result = assistant.answer_plan(df, assistant.QueryPlan(metric))
        if not result['ok']:
            raise ValueError('A required metric could not be calculated: ' + metric)
        values[metric] = result['value']
    return {'records': len(df), 'scope_id': assistant.scope_fingerprint(df), 'values': values}


def _assert_selected_snapshot(selected: pd.DataFrame, reference: pd.DataFrame):
    """Prevent unrelated or silently altered records being labelled a filtered subset."""
    ids = selected.Patient_ID
    if not ids.isin(reference.Patient_ID).all():
        raise ValueError('Selected records are not a subset of this reference snapshot.')
    expected = reference.set_index('Patient_ID').reindex(ids)[BASE_COLUMNS[1:]].reset_index()
    actual = selected[BASE_COLUMNS].reset_index(drop=True)
    expected = expected[BASE_COLUMNS].reset_index(drop=True)
    try:
        pd.testing.assert_frame_equal(actual, expected, check_dtype=False, check_exact=True)
    except AssertionError:
        raise ValueError('Selected values do not match the reference snapshot.') from None


def compare_cohorts(selected: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    _require_quality(selected)
    _require_quality(reference)
    _assert_selected_snapshot(selected, reference)
    selected_metrics, baseline = metric_snapshot(selected), metric_snapshot(reference)
    return pd.DataFrame([{
        'metric': label,
        'selected_value': selected_metrics['values'][metric],
        'reference_value': baseline['values'][metric],
        'difference': selected_metrics['values'][metric] - baseline['values'][metric],
        'unit': unit, 'difference_unit': difference_unit,
        'selected_n': len(selected), 'reference_n': len(reference),
    } for metric, label, unit, difference_unit in METRICS])


def load_queries() -> dict[str, str]:
    text = SQL_FILE.read_text(encoding='utf-8')
    chunks = re.split(r'^-- name: ([a-z_]+)\s*$', text, flags=re.M)
    result = {chunks[i]: chunks[i + 1].strip() for i in range(1, len(chunks), 2)}
    if set(result) != set(QUERY_LABELS):
        raise ValueError('The tracked workbench query bank is incomplete or unexpected.')
    return result


def round_value(value: float) -> float:
    """Display/query parity follows SQLite ROUND (half away from zero)."""
    return float(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def _pandas_query(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Independent raw-column calculation; does not consume the SQL result table."""
    labels = {'cost_by_condition': ('Condition', 'condition'),
              'readmission_by_gender': ('Gender', 'gender'),
              'cost_by_readmission': ('Readmission', 'readmission'),
              'outcomes_by_condition': ('Condition', 'condition')}
    column, output = labels[name]
    grouped = df.groupby(column, observed=True)
    rows = []
    total_cost = float(df.Cost.sum())
    for key, part in grouped:
        row = {output: key, 'records': len(part)}
        if name in {'cost_by_condition', 'cost_by_readmission'}:
            row.update(total_cost=round_value(float(part.Cost.sum())),
                       avg_cost=round_value(float(part.Cost.mean())),
                       cost_share_pct=round_value(float(part.Cost.sum()) / total_cost * 100) if total_cost else None)
        if name in {'cost_by_condition', 'readmission_by_gender'}:
            row.update(readmitted=int(part.Readmission.eq('Yes').sum()),
                       readmission_rate_pct=round_value(float(part.Readmission.eq('Yes').mean() * 100)))
        if name in {'readmission_by_gender', 'cost_by_readmission'}:
            row.update(avg_cost=round_value(float(part.Cost.mean())),
                       avg_stay_days=round_value(float(part.Length_of_Stay.mean())))
        if name == 'outcomes_by_condition':
            row.update(recovered=int(part.Outcome.eq('Recovered').sum()),
                       recovered_rate_pct=round_value(float(part.Outcome.eq('Recovered').mean() * 100)),
                       avg_satisfaction=round_value(float(part.Satisfaction.mean())))
        rows.append(row)
    result = pd.DataFrame(rows)
    if name == 'cost_by_condition':
        return result.sort_values(['total_cost', 'condition'], ascending=[False, True]).reset_index(drop=True)
    if name == 'outcomes_by_condition':
        return result.sort_values(['records', 'condition'], ascending=[False, True]).reset_index(drop=True)
    return result.sort_values(output).reset_index(drop=True)


def execute_question(df: pd.DataFrame, name: str) -> dict:
    """No user SQL. The in-memory table contains the selected cohort only."""
    if name not in QUERY_LABELS:
        raise ValueError('Choose a supported workbench question.')
    _require_quality(df)
    sql = load_queries()[name]
    scoped = df[['Condition', 'Gender', 'Readmission', 'Cost', 'Length_of_Stay', 'Outcome', 'Satisfaction']].rename(columns={
        'Condition': 'condition', 'Gender': 'gender', 'Readmission': 'readmission',
        'Cost': 'cost', 'Length_of_Stay': 'length_of_stay', 'Outcome': 'outcome', 'Satisfaction': 'satisfaction'})
    try:
        with closing(sqlite3.connect(':memory:')) as connection:
            scoped.to_sql('scope_encounters', connection, index=False)
            connection.execute('PRAGMA query_only = ON')
            result = pd.read_sql_query(sql, connection)
    except (sqlite3.Error, pd.errors.DatabaseError):
        raise ValueError('The tracked SQL question could not execute. Inspect the query file before publishing a result.') from None
    if result.columns.tolist() != QUERY_COLUMNS[name]:
        raise ValueError('SQL result columns do not match the required question schema; no result is published.')
    expected = _pandas_query(df, name).reindex(columns=QUERY_COLUMNS[name])
    try:
        pd.testing.assert_frame_equal(result, expected, check_dtype=False, atol=.005, rtol=1e-8)
    except AssertionError:
        raise ValueError('SQL/pandas reconciliation failed; no unverified query result is published.') from None
    return {'question': QUERY_LABELS[name], 'key': name, 'sql': sql, 'table': result,
            'rows_in_scope': len(df), 'scope_id': assistant.scope_fingerprint(df),
            'reconciliation': 'PASS', 'checked_values': int(result.size),
            'small_groups': int(result['records'].lt(30).sum()),
            'scope_note': 'The SQL table contains only the selected cohort. Cost shares use this cohort, not the full reference.'}


def build_report(selected: pd.DataFrame, reference: pd.DataFrame, focus='costs', generated_at=None) -> str:
    if focus not in FOCUSES:
        raise ValueError('Choose a supported stakeholder-report focus.')
    comparison = compare_cohorts(selected, reference)
    selected_metrics, reference_metrics = metric_snapshot(selected), metric_snapshot(reference)
    question = {'costs': 'cost_by_condition', 'readmissions': 'readmission_by_gender',
                'outcomes': 'outcomes_by_condition'}[focus]
    query = execute_question(selected, question)
    when = generated_at or datetime.now(timezone.utc).isoformat(timespec='seconds')
    lines = ['# ' + FOCUSES[focus], '', 'Report generated (UTC): ' + when,
             'This is a synthetic-data analysis snapshot, not a care-period or clinical report.', '',
             '## Population and evidence',
             f'- Selected records: {len(selected)}; full reference: {len(reference)}.',
             '- The reference includes the selection. It is not an independent control group.',
             '- Each record is one synthetic patient, not a validated admission timeline.',
             '- Selected scope ID: ' + selected_metrics['scope_id'],
             '- Reference scope ID: ' + reference_metrics['scope_id'],
             '- Both source and selected data-contract checks: PASS.', '',
             '## Observed selected-cohort composition',
             'These are observed values in the resulting records, not the filter settings; they may not uniquely reconstruct the selection.',
             *[f"- {column}: " + ', '.join(f"{label} ({count})" for label, count in selected[column].value_counts().sort_index().items())
               for column in ['Condition', 'Gender', 'Outcome']],
             f"- Observed age range: {int(selected.Age.min())}–{int(selected.Age.max())} years.", '',
             '## Selected cohort versus reference',
             'Differences use unrounded metrics; displayed numbers use two-decimal half-up rounding.',
             '| Metric | Selected | Full reference | Difference | Difference unit |',
             '|---|---:|---:|---:|---|']
    for row in comparison.to_dict('records'):
        lines.append(f"| {row['metric']} | {round_value(row['selected_value']):,.2f} {row['unit']} | {round_value(row['reference_value']):,.2f} {row['unit']} | {round_value(row['difference']):+,.2f} | {row['difference_unit']} |")
    lines += ['', '## Executed SQL question', query['question'], '',
              f"SQL/pandas reconciliation: PASS ({query['checked_values']} result cells checked).",
              '```sql', query['sql'], '```', '', '## Scoped SQL results',
              '| ' + ' | '.join(query['table'].columns) + ' |',
              '| ' + ' | '.join('---' for _ in query['table'].columns) + ' |']
    for row in query['table'].itertuples(index=False, name=None):
        lines.append('| ' + ' | '.join('Not available' if pd.isna(value) else str(value).replace('|', '/') for value in row) + ' |')
    if query['small_groups']:
        lines += ['', f"Caution: {query['small_groups']} SQL result group(s) have fewer than 30 records. This is a heuristic, not a statistical significance test."]
    lines += ['', '## Interpretation and next checks']
    if focus == 'costs':
        lines += ['Review which conditions account for recorded cost, then check case mix and data definitions before attributing the difference to a service or intervention. Recorded cost is not an estimate of preventable savings.']
    elif focus == 'readmissions':
        lines += ['Check subgroup sizes and the readmission-label definition before interpreting differences. The data has no validated 30-day window, and this comparison is not a causal or fairness conclusion.']
    else:
        lines += ['Review outcome definitions and subgroup composition with the source owner. A recorded Recovered label does not establish treatment effectiveness or a longitudinal clinical outcome.']
    if len(selected) < 30:
        lines += ['The selected cohort has fewer than 30 records; treat its descriptive rates cautiously rather than as stable population estimates.']
    lines += ['', '## Boundaries', 'No diagnosis, treatment or care prioritisation is supported. No model or provider generated the report numbers. Aggregate output is not a certification of privacy, clinical validity or causal business impact.']
    return '\n'.join(lines) + '\n'
