"""Bounded administrative-review scenario for the validated synthetic cohort."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from numbers import Real

from . import analyst_workbench as workbench


def _number(value, name, upper, *, integer=False):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)):
        raise ValueError(f'{name} must be a finite number.')
    if value < 0 or value > upper or (integer and int(value) != value):
        raise ValueError(f'{name} must be within the supported range.')
    return int(value) if integer else float(value)


def _text(value, name):
    if not isinstance(value, str) or len(value) > 500:
        raise ValueError(f'{name} must be text of at most 500 characters.')
    return value.strip()


def plan_review(selected, reference, capacity, minutes, hourly_rate,
                action='Review data definitions and case mix',
                success_metric='Completeness of the readmission flag definition',
                follow_up='Document source definition and inspect subgroup composition',
                observed_note='', status='proposed', filter_context=None):
    """Build an administrative planning record; it does not prioritize patients."""
    capacity = _number(capacity, 'Capacity', 1_000_000, integer=True)
    minutes = _number(minutes, 'Minutes per record', 1440)
    hourly_rate = _number(hourly_rate, 'Hourly rate', 10_000_000)
    if status not in {'proposed', 'approved', 'deferred'}:
        raise ValueError('Choose a supported decision status.')
    if filter_context is not None and not isinstance(filter_context, dict):
        raise ValueError('Filter context must be a JSON object.')
    try:
        filters = json.loads(json.dumps(filter_context or {}, allow_nan=False, sort_keys=True))
    except (TypeError, ValueError):
        raise ValueError('Filter context must be JSON-compatible.') from None
    if len(json.dumps(filters)) > 4000:
        raise ValueError('Filter context is too large.')
    # This rejects bad reference/selected data, unrelated rows and altered values.
    workbench.compare_cohorts(selected, reference)
    query = workbench.execute_question(selected, 'cost_by_condition')
    snapshot = workbench.metric_snapshot(selected)
    baseline = workbench.metric_snapshot(reference)
    n = min(capacity, len(selected))
    def scenario(multiplier):
        hours = n * minutes * multiplier / 60
        return {'records': n, 'minutes_per_record': minutes * multiplier,
                'hours': hours, 'cost_inr': hours * hourly_rate}
    note = _text(observed_note, 'Observed note')
    return {
        'schema_version': 1, 'project': 'hospital_operations', 'created_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'source': {'dataset': 'data/hospital/hospital_data.csv', 'classification': 'synthetic',
                   'reconciliation': query['reconciliation'], 'reconciled_result_cells': query['checked_values'],
                   'question': query['question']},
        'scope': {'scope_id': snapshot['scope_id'], 'reference_scope_id': baseline['scope_id'],
                  'selected_records': len(selected), 'reference_records': len(reference), 'filter_context': filters,
                  'definition': 'Selected synthetic patient records; the full reference includes the selection.'},
        'evidence': {'readmission_rate_pct': snapshot['values']['readmission_rate'],
                     'mean_recorded_cost_inr': snapshot['values']['average_cost'],
                     'mean_stay_days': snapshot['values']['average_stay'],
                     'reference_readmission_rate_pct': baseline['values']['readmission_rate']},
        'assumptions': {'capacity': capacity, 'base_minutes_per_record': minutes,
                        'administrative_hourly_rate_inr': hourly_rate},
        'scenarios': {'low': scenario(.5), 'base': scenario(1), 'high': scenario(1.5)},
        'decision': {'status': status, 'action': _text(action, 'Action'),
                     'success_metric': _text(success_metric, 'Success metric'),
                     'follow_up': _text(follow_up, 'Follow-up')},
        'observed_outcome': {'source': 'user-entered, unverified', 'note': note} if note else None,
        'limitations': 'Synthetic patient records; administrative effort scenario only, not clinical advice or patient prioritization. The reference includes the selection; readmission lacks a validated 30-day timeline. Costs are assumed effort costs, not measured savings, causal effects or patient benefits.',
    }
