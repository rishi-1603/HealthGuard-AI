"""User-managed decision history: bounded JSON, not server-side case management.

Imported records and manual follow-ups are unverified. Arithmetic differences
are not causal effects. No external provider is called.
"""
from __future__ import annotations

import json
import math
import re
import uuid
from datetime import date, datetime, timezone
from numbers import Real

MAX_BYTES = 256_000
MAX_ENTRIES = 30
MAX_FOLLOWUPS = 30
PROJECTS = {'refund_risk', 'hospital_operations', 'ecommerce'}


def _text(value, label, limit=500, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError(f'{label} must be valid text of at most {limit} characters.')
    return value.strip()


def _num(value, label, optional=False):
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)) or abs(value) > 1e15:
        raise ValueError(f'{label} must be a finite number in range.')
    return float(value)


def _copy(obj):
    try:
        text = json.dumps(obj, allow_nan=False, ensure_ascii=False)
        if len(text.encode('utf-8')) > MAX_BYTES:
            raise ValueError('History is too large.')
        return json.loads(text)
    except (TypeError, OverflowError, RecursionError) as exc:
        raise ValueError('History must contain bounded JSON values.') from exc


def new_history(project):
    if project not in PROJECTS:
        raise ValueError('Unsupported project.')
    return {'schema_version': 1, 'project': project, 'trust': 'local session, unverified', 'entries': []}


def _check(history, project):
    if project not in PROJECTS or not isinstance(history, dict) or history.get('schema_version') != 1 or history.get('project') != project:
        raise ValueError('History version or project does not match.')
    entries = history.get('entries')
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise ValueError('History has too many entries or invalid entries.')
    ids = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('id'), str) or len(entry['id']) != 32:
            raise ValueError('Invalid entry identifier.')
        try:
            uuid.UUID(hex=entry['id'])
        except (ValueError, AttributeError):
            raise ValueError('Invalid entry identifier.') from None
        if entry['id'] in ids:
            raise ValueError('Duplicate entry identifier.')
        ids.add(entry['id'])
        rec = entry.get('record')
        if not isinstance(rec, dict) or rec.get('schema_version') != 1 or rec.get('project') != project or any(not isinstance(rec.get(key), dict) for key in ('source', 'scope', 'evidence', 'assumptions', 'scenarios', 'decision')):
            raise ValueError('Decision record does not match this project.')
        _text(rec['decision'].get('action', ''), 'Action')
        if rec['decision'].get('status') not in {'proposed', 'approved', 'deferred'}:
            raise ValueError('Invalid decision status.')
        followups = entry.get('followups')
        if not isinstance(followups, list) or len(followups) > MAX_FOLLOWUPS:
            raise ValueError('Invalid follow-ups.')
        for item in followups:
            if not isinstance(item, dict):
                raise ValueError('Invalid follow-up.')
            _text(item.get('metric'), 'Metric', 120, True)
            _text(item.get('unit'), 'Unit', 80, True)
            _text(item.get('note'), 'Note')
            if item.get('verification') != 'user-entered, unverified':
                raise ValueError('Follow-up verification label is invalid.')
            _text(item.get('recorded_at_utc'), 'Recorded time', 50, True)
            baseline = _num(item.get('baseline'), 'Baseline', optional=True)
            observed = _num(item.get('observed'), 'Observed value')
            try:
                if not isinstance(item.get('observed_date'), str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', item['observed_date']):
                    raise ValueError('Noncanonical date')
                date.fromisoformat(item['observed_date'])
            except (TypeError, ValueError):
                raise ValueError('Observed date must be YYYY-MM-DD.') from None
            diff = item.get('difference')
            if baseline is None:
                if diff is not None:
                    raise ValueError('Difference requires a baseline.')
            elif not isinstance(diff, Real) or isinstance(diff, bool) or not math.isfinite(float(diff)) or not math.isclose(float(diff), observed-baseline, rel_tol=1e-12, abs_tol=1e-9):
                raise ValueError('Follow-up difference does not reconcile.')
    return history


def add_snapshot(history, record):
    h = _copy(history)
    _check(h, h.get('project'))
    if len(h['entries']) >= MAX_ENTRIES:
        raise ValueError('History is full; export it before starting a new one.')
    rec = _copy(record)
    if not isinstance(rec, dict) or rec.get('schema_version') != 1 or rec.get('project') != h['project'] or any(not isinstance(rec.get(key), dict) for key in ('source', 'scope', 'evidence', 'assumptions', 'scenarios', 'decision')):
        raise ValueError('Decision record does not match this project.')
    h['entries'].append({'id': uuid.uuid4().hex, 'record': rec, 'followups': []})
    return _check(h, h['project'])


def add_followup(history, entry_id, *, metric, unit, baseline, observed, observed_date, note):
    h = _copy(history)
    _check(h, h.get('project'))
    target = next((e for e in h['entries'] if e['id'] == entry_id), None)
    if target is None or len(target['followups']) >= MAX_FOLLOWUPS:
        raise ValueError('Entry is missing or has too many follow-ups.')
    metric = _text(metric, 'Metric', 120, True)
    unit = _text(unit, 'Unit', 80, True)
    note = _text(note, 'Note')
    baseline = _num(baseline, 'Baseline', optional=True)
    observed = _num(observed, 'Observed value')
    try:
        if not isinstance(observed_date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', observed_date):
            raise ValueError('Noncanonical date')
        observed_date = date.fromisoformat(observed_date).isoformat()
    except (TypeError, ValueError):
        raise ValueError('Observed date must be YYYY-MM-DD.') from None
    target['followups'].append({'metric': metric, 'unit': unit, 'baseline': baseline,
        'observed': observed, 'difference': observed-baseline if baseline is not None else None,
        'observed_date': observed_date, 'note': note, 'verification': 'user-entered, unverified',
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds')})
    return _check(h, h['project'])


def export_history(history):
    h = _check(_copy(history), history.get('project'))
    return json.dumps(h, ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8')


def import_history(payload, project):
    if not isinstance(payload, bytes) or len(payload) > MAX_BYTES:
        raise ValueError('Import must be JSON no larger than 256 KB.')
    try:
        def reject_constant(_value):
            raise ValueError('Non-finite values are not allowed.')
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('Duplicate JSON keys are not allowed.')
                result[key] = value
            return result
        h = json.loads(payload.decode('utf-8'), parse_constant=reject_constant, object_pairs_hook=unique_object)
        _check(h, project)
        h['trust'] = 'imported, unverified'
        return _copy(h)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('Invalid JSON history.') from exc


def render_history(project, record, prefix):
    """Streamlit controls; file persistence is user's responsibility."""
    import streamlit as st

    key = prefix + '_history'
    if key not in st.session_state:
        st.session_state[key] = new_history(project)
    st.divider()
    st.subheader('Decision history & follow-up')
    st.caption('User-managed JSON: not server-side storage or verified impact. Do not enter sensitive information. Download and re-import the file to retain it across sessions.')
    if st.button('Add current snapshot to history', disabled=record is None, key=prefix+'_add_history'):
        try:
            st.session_state[key] = add_snapshot(st.session_state[key], record)
        except ValueError as error:
            st.error(str(error))
    file = st.file_uploader('Import history JSON (replaces current history)', type=['json'], key=prefix+'_history_file')
    if st.button('Import selected history', disabled=file is None, key=prefix+'_import_history'):
        try:
            if file.size > MAX_BYTES:
                raise ValueError('Import must be JSON no larger than 256 KB.')
            st.session_state[key] = import_history(file.getvalue(), project)
            st.success('Imported history; all imported content remains unverified.')
        except ValueError as error:
            st.error(str(error))
    history = st.session_state[key]
    entries = history['entries']
    if not entries:
        st.info('No saved snapshots in this session.')
        return
    st.caption(f"{len(entries)} snapshot(s); {history['trust']}.")
    labels = {e['id']: (e['record'].get('decision', {}).get('action', '')[:80] or 'Untitled') + ' · ' + e['id'][:8] for e in entries}
    selected = st.selectbox('Select a saved decision', list(labels), format_func=lambda k: labels[k], key=prefix+'_history_choice')
    chosen = next(e for e in entries if e['id'] == selected)
    st.json(chosen['record'], expanded=False)
    if chosen['followups']:
        st.dataframe(chosen['followups'], hide_index=True, width='stretch')
    with st.form(prefix+'_followup_form'):
        metric = st.text_input('Follow-up metric', max_chars=120, key=prefix+'_follow_metric')
        unit = st.text_input('Metric unit', max_chars=80, key=prefix+'_follow_unit')
        baseline = st.text_input('Baseline value (optional)', key=prefix+'_follow_baseline')
        observed = st.text_input('Observed value (user-entered)', key=prefix+'_follow_observed')
        when = st.date_input('Observation date', key=prefix+'_follow_date')
        note = st.text_input('Evidence note (unverified)', max_chars=500, key=prefix+'_follow_note')
        submit = st.form_submit_button('Add follow-up')
    if submit:
        try:
            observed_number = float(observed)
            baseline_number = float(baseline) if baseline.strip() else None
            st.session_state[key] = add_followup(history, selected, metric=metric, unit=unit,
                baseline=baseline_number, observed=observed_number, observed_date=when.isoformat(), note=note)
            st.success('Follow-up added as user-entered, unverified data. Difference is arithmetic, not causal impact.')
            history = st.session_state[key]
        except ValueError as error:
            st.error('Could not add follow-up: ' + str(error))
    st.download_button('Download decision history (JSON)', export_history(history),
                       f'{project}_decision_history.json', 'application/json', key=prefix+'_history_download')
