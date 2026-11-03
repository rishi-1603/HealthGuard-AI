"""Bounded hospital-data assistant: validated questions, deterministic results.

This module never calls a model, runs generated code/SQL, or expands beyond the
DataFrame supplied by the dashboard. Provider assistance can select evidence cards;
it cannot supply numerical answers or clinical advice.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
import re

import pandas as pd

CONDITION_SYNONYMS = {
    'Diabetes': ['diabetic'],
    'Heart Disease': ['cardiac disease', 'heart problems', 'heart condition'],
    'Heart Attack': ['myocardial infarction'],
    'Fractured Arm': ['broken arm'], 'Fractured Leg': ['broken leg'],
    'Stroke': ['cerebrovascular'], 'Cancer': ['oncology', 'tumor'],
    'Prostate Cancer': ['prostate tumor'], 'Hypertension': ['high blood pressure'],
    'Respiratory Infection': ['lung infection', 'chest infection'],
    'Kidney Stones': ['renal stones'], 'Allergic Reaction': ['allergy'],
    'Osteoarthritis': ['arthritis'], 'Appendicitis': [], 'Childbirth': [],
}
SERVICE_VERSION = 3
AGE_LABELS = ['0-30', '31-45', '46-60', '61-75', '76-120']
CAUTION = 'Synthetic patient records; descriptive analysis, not medical advice or causal evidence.'
METRICS = {'count', 'readmission_rate', 'average_cost', 'total_cost', 'average_stay',
           'satisfaction', 'recovery_rate', 'average_age'}
GROUPS = {'Condition', 'Gender', 'Outcome', 'Readmission', 'Age_Band'}
STOP_WORDS = set('''what whats s is are was were the a an of in on for with among from to
and or by per across all every each overall total current filtered filter view dataset about much do does we
this these those our data cohort hospital show tell me please can you give calculate
computed number count counts many how patients patient records record people person
readmission readmissions readmit readmitted cost costs spend spending expenditure
expensive cheapest cheap highest lowest most least top bottom average avg mean
length stay days satisfaction satisfied outcome outcomes recovered recovery stable
rate rates percent percentage share compare comparison breakdown distribution
condition conditions gender genders sex age ages aged band bands group groups between than older
younger over under above below non not marked had have has having there value values
'''.split())


@dataclass(frozen=True)
class QueryPlan:
    metric: str
    condition: str | None = None
    gender: str | None = None
    outcome: str | None = None
    readmission: str | None = None
    age_min: int | None = None
    age_max: int | None = None
    group_by: str | None = None
    top: int | None = None
    ascending: bool = False


def scope_fingerprint(df: pd.DataFrame) -> str:
    """Scope identity, not a claim of deployment provenance."""
    hashed = pd.util.hash_pandas_object(df, index=True).values.tobytes()
    columns = '|'.join(map(str, df.columns)).encode()
    return hashlib.sha256(columns + hashed).hexdigest()[:20]


def _refuse(text: str, code='unsupported') -> dict:
    return {'ok': False, 'text': "I can't answer that from this dataset. " + text,
            'status': code, 'mode': 'refused', 'warnings': [CAUTION]}


def _contains_phrase(phrase: str, question: str) -> bool:
    return re.search(r'\b' + re.escape(phrase.lower()) + r'\b', question.lower()) is not None


def _conditions(question: str) -> tuple[list[str], str]:
    phrases = [(phrase.lower(), condition) for condition, aliases in CONDITION_SYNONYMS.items()
               for phrase in [condition, *aliases]]
    remaining = question
    found = []
    for phrase, condition in sorted(phrases, key=lambda p: len(p[0]), reverse=True):
        pattern = r'\b' + re.escape(phrase) + r'\b'
        if re.search(pattern, remaining):
            if condition not in found:
                found.append(condition)
            remaining = re.sub(pattern, ' ', remaining)
    return found, remaining


def parse_question(question) -> QueryPlan | dict:
    if not isinstance(question, str) or not question.strip():
        return _refuse('Enter a question about patient counts, readmissions, costs, stays or outcomes.', 'invalid_input')
    if len(question) > 500:
        return _refuse('Use a question of at most 500 characters.', 'invalid_input')
    q = question.lower().strip().replace('\u2019', "'")
    if re.search(r'ignore.*(?:instruction|rule)|system prompt|api.?key|password|secret|\btoken\b|drop\s+table|\bexecute\b|\bexec\b', q):
        return _refuse('Instructions, credentials and executable requests are outside the assistant scope.', 'unsafe_request')
    if re.search(r'\b(diagnos\w*|prescrib\w*|dosage|medication\w*|therapy|cure|triage)\b|should i|am i |will i |treat(?:ment)?\s+(?:me|this|a patient)|recommend.*(?:drug|treatment)', q):
        return _refuse('I do not diagnose, prescribe or recommend care. Ask a descriptive question about the records.', 'medical_request')
    if re.search(r'\b(predict\w*|forecast\w*|tomorrow|yesterday|future|mortality|death\w*|revenue)\b|next\s+(?:month|year|week)|last\s+(?:month|year|week)|over time|\btrend\w*|\b(?:19|20)\d{2}\b|\b\d+[- ]day\s+readmission|readmission.*\bwithin\b', q):
        return _refuse('There is no validated admissions timeline, prediction horizon, revenue or mortality measure here.', 'unavailable_data')
    if re.search(r'\bor\b', q):
        return _refuse('OR combinations are not supported; ask one question at a time.', 'clarification')
    if re.search(r'\brecovered\b', q) and re.search(r'\bstable\b', q):
        return _refuse('Choose one outcome or ask for a breakdown by outcome.', 'clarification')
    if re.search(r'\b(?:non[- ]readmitted|not\s+readmitted)\b', q) and re.search(r'\breadmitted\b', re.sub(r'\b(?:non[- ]readmitted|not\s+readmitted)\b', '', q)):
        return _refuse('Choose one readmission status or ask for a breakdown.', 'clarification')
    # Only the explicitly supported negative readmission phrasing is interpreted.
    # Every other negation must fail closed rather than turn into the opposite filter.
    negation_check = re.sub(r'\b(?:non[- ]readmitted|not\s+readmitted)\b', 'readmitted', q)
    if re.search(r"\b(?:not|non|without|exclude|excluding|except|neither|nor)\b|n't\b", negation_check):
        return _refuse('Negated filters are not supported except not readmitted. Rephrase using a supported positive filter.', 'clarification')
    group_terms = r'(?:conditions?|genders?|sex|age(?:\s+(?:bands?|groups?))?|outcomes?|readmission)'
    if re.search(r'\b(?:by|per|across|for each|in each)\s+' + group_terms + r'\s+(?:and|or)\s+(?:(?:by|per|across)\s+)?' + group_terms + r'\b', q):
        return _refuse('Compare one grouping dimension at a time.', 'clarification')
    # Explicit ranking counts are consumed before checking for unsupported digits.
    ranking = re.search(r'\b(top|bottom)\s+(3|5|10|three|five|ten)\b', q)
    ranking_n = None
    remaining_q = q
    if ranking:
        ranking_n = {'3': 3, 'three': 3, '5': 5, 'five': 5, '10': 10, 'ten': 10}[ranking.group(2)]
        remaining_q = q[:ranking.start(2)] + ' ' + q[ranking.end(2):]
    elif re.search(r'\b(?:top|bottom|first)\s+\w+', q) and re.search(r'\b(?:three|five|ten)\b', q):
        return _refuse('Use top or bottom 3, 5 or 10 conditions.', 'clarification')
    conditions, remaining = _conditions(remaining_q)
    if len(conditions) > 1:
        return _refuse('Use one named condition, or ask for a breakdown by condition.', 'clarification')
    gender_matches = []
    for pattern, label in [(r'\b(female|women|woman)\b', 'Female'), (r'\b(male|men|man)\b', 'Male')]:
        if re.search(pattern, remaining):
            gender_matches.append(label)
            remaining = re.sub(pattern, ' ', remaining)
    age_min = age_max = None
    match = re.search(r'\b(?:aged?|between)\s*(\d{1,3})\s*(?:to|and|-)\s*(\d{1,3})\b', remaining)
    if match:
        age_min, age_max = map(int, match.groups())
        remaining = remaining[:match.start()] + ' ' + remaining[match.end():]
    else:
        match = re.search(r'\b(?:older than|over|above)\s+(\d{1,3})\b', remaining)
        if match:
            if re.match(r'(?:over|above)', match.group()) and not re.search(r'\b(?:age|aged|patients?|people)(?:\s+aged?)?\s+(?:over|above)\s+\d+\b', q):
                return _refuse('Specify that the threshold is an age; cost thresholds are not supported.', 'clarification')
            age_min = int(match.group(1)) + 1
            remaining = remaining[:match.start()] + ' ' + remaining[match.end():]
        match = re.search(r'\b(?:younger than|under|below)\s+(\d{1,3})\b', remaining)
        if match:
            if re.match(r'(?:under|below)', match.group()) and not re.search(r'\b(?:age|aged|patients?|people)(?:\s+aged?)?\s+(?:under|below)\s+\d+\b', q):
                return _refuse('Specify that the threshold is an age; cost thresholds are not supported.', 'clarification')
            age_max = int(match.group(1)) - 1
            remaining = remaining[:match.start()] + ' ' + remaining[match.end():]
    if (age_min is not None and not 0 <= age_min <= 120) or (age_max is not None and not 0 <= age_max <= 120) or (age_min is not None and age_max is not None and age_min > age_max):
        return _refuse('Use a valid age range between 0 and 120.', 'invalid_input')
    if re.search(r'\d', remaining):
        return _refuse('I cannot apply that numeric filter. Age ranges are supported; dates, patient IDs and time windows are not.', 'unsupported_filter')
    unknown = sorted(set(re.findall(r'[a-z]+', remaining)) - STOP_WORDS)
    if unknown:
        return _refuse('That question names an unsupported filter or term: ' + ', '.join(unknown[:5]) +
                       '. Conditions must match the dataset; unsupported filters are never silently dropped.', 'unsupported_filter')
    readmission_mentioned = bool(re.search(r'\breadmi\w*', q))
    count_requested = bool(re.search(r'how many|\bcounts?\b|\bnumber\b', q))
    cost_mentioned = bool(re.search(r'cost|expensive|spend|expenditure', q))
    age_metric = bool(re.search(r'(?:average|mean) age', q))
    recovery_explicit = bool(re.search(r'(?:recovered|recovery) (?:rate|percentage|share)', q))
    readmission_explicit = bool(re.search(r'readmission (?:rate|percentage|share)|readmit (?:rate|percentage)', q))
    other_metric = cost_mentioned or 'stay' in q or 'satisfaction' in q or age_metric
    readmission_rate_requested = readmission_mentioned and (readmission_explicit or not (other_metric or recovery_explicit))
    recovery_rate_requested = ('recovered' in q or 'recovery' in q) and (recovery_explicit or not (other_metric or readmission_rate_requested))
    metric_mentions = sum([readmission_rate_requested, cost_mentioned, 'satisfaction' in q,
                           'stay' in q, recovery_rate_requested, age_metric])
    if count_requested and re.search(r'\b(?:average|avg|mean|rate|rates|percent|percentage|satisfaction|costs?|spend|expenditure)\b|length of stay', q):
        return _refuse('Ask for a count or another metric separately.', 'clarification')
    if not count_requested and metric_mentions > 1:
        return _refuse('Ask one metric at a time so no part of the question is silently ignored.', 'clarification')
    by_condition = bool(re.search(r'(?:by|per|across|for each|in each) conditions?|which condition|most expensive conditions|cheapest conditions|highest.*conditions|lowest.*conditions|top.*conditions|bottom.*conditions', q))
    group = None
    if by_condition:
        group = 'Condition'
    elif re.search(r'(?:by|per|across|for each|in each) (?:genders?|sex)|gender comparison|compare.*(?:women|female).*(?:men|male)', q) or len(gender_matches) > 1:
        group = 'Gender'
    elif re.search(r'(?:by|per|for each|in each) age|age bands|age groups', q):
        group = 'Age_Band'
    elif re.search(r'(?:by|per|across|for each|in each) outcomes?|outcome distribution|outcome breakdown', q):
        group = 'Outcome'
    elif re.search(r'(?:by|per|for each|in each) readmission|compare.*readmitted.*non', q):
        group = 'Readmission'
    if count_requested:
        metric = 'count'
    elif readmission_rate_requested:
        metric = 'readmission_rate'
    elif re.search(r'\bcosts?\b|\bexpensive\b|\bspend\w*|\bexpenditure\b|\bcheap\w*', q):
        metric = 'total_cost' if re.search(r'\btotal\b|\bexpenditure\b|\bspend(?:ing)?\b', q) and not re.search(r'\b(?:average|avg|mean)\b', q) else 'average_cost'
    elif 'satisfaction' in q or 'satisfied' in q:
        metric = 'satisfaction'
    elif 'stay' in q or 'days' in q:
        metric = 'average_stay'
    elif re.search(r'\bage\b', q):
        metric = 'average_age'
    elif 'recovered' in q or 'recovery' in q or 'outcome' in q:
        metric = 'count' if group == 'Outcome' else 'recovery_rate'
    else:
        return _refuse('Ask about counts, readmission, cost, stay, satisfaction, age or recovered outcomes.')
    if len(gender_matches) > 1 and group != 'Gender':
        return _refuse('Compare gender as the grouping dimension, or use one gender filter.', 'clarification')
    if group is None and re.search(r'\b(?:highest|lowest|most|least|top|bottom|cheapest)\b', q):
        return _refuse('Specify a supported grouping for the requested ranking.', 'clarification')
    if group and group != 'Condition' and re.search(r'\b(?:highest|lowest|most|least|top|bottom|cheapest)\b', q):
        return _refuse('Ranking is only supported for condition breakdowns.', 'clarification')
    if ranking_n and group != 'Condition':
        return _refuse('Rankings are supported only for a condition breakdown.', 'clarification')
    if readmission_rate_requested and not count_requested and re.search(r'\b(?:readmitted|non[- ]readmitted|not\s+readmitted)\b', q):
        return _refuse('A readmission rate cannot also use a readmission-status filter. Ask for a count or compare by readmission.', 'clarification')
    target_readmission = None
    if readmission_mentioned and group != 'Readmission' and (count_requested or not readmission_rate_requested):
        target_readmission = 'No' if re.search(r'non[- ]readmitted|not readmitted', q) else 'Yes'
    outcome = None
    if group != 'Outcome':
        if 'recovered' in q and (count_requested or not recovery_rate_requested):
            outcome = 'Recovered'
        elif re.search(r'\bstable\b', q):
            outcome = 'Stable'
    top = (ranking_n or 3) if group == 'Condition' and re.search(r'\btop\b|\bbottom\b|\bmost\b|\bhighest\b|\bcheapest\b|\blowest\b', q) else None
    return QueryPlan(metric=metric, condition=conditions[0] if conditions else None,
                     gender=gender_matches[0] if len(gender_matches) == 1 else None,
                     outcome=outcome, readmission=target_readmission, age_min=age_min,
                     age_max=age_max, group_by=group, top=top,
                     ascending=bool(re.search(r'\b(?:lowest|least|cheapest|bottom)\b', q)))


def _apply_plan(df: pd.DataFrame, plan: QueryPlan) -> pd.DataFrame:
    sub = df.copy()
    for column, value in [('Condition', plan.condition), ('Gender', plan.gender),
                          ('Outcome', plan.outcome), ('Readmission', plan.readmission)]:
        if value is not None:
            if column not in sub.columns:
                raise ValueError('The required column is missing: ' + column)
            sub = sub[sub[column].eq(value)]
    if plan.age_min is not None or plan.age_max is not None:
        if 'Age' not in sub.columns:
            raise ValueError('The required column is missing: Age')
        age = pd.to_numeric(sub.Age, errors='coerce')
        if plan.age_min is not None:
            sub = sub[age >= plan.age_min]
        if plan.age_max is not None:
            sub = sub[pd.to_numeric(sub.Age, errors='coerce') <= plan.age_max]
    return sub


def _measure(df: pd.DataFrame, metric: str) -> tuple[float, str, int, list[str], str]:
    if metric == 'count':
        return float(len(df)), 'patients', len(df), [], 'COUNT(rows in scope)'
    if metric in {'readmission_rate', 'recovery_rate'}:
        col, yes, domain = ('Readmission', 'Yes', ['Yes', 'No']) if metric == 'readmission_rate' else ('Outcome', 'Recovered', ['Recovered', 'Stable'])
        if col not in df:
            raise ValueError('The required column is missing: ' + col)
        valid = df[col].isin(domain)
        if not valid.any():
            raise ValueError('No valid values are available for ' + col)
        value = float(df.loc[valid, col].eq(yes).mean() * 100)
        return value, '%', int(valid.sum()), [col], f'COUNT({col}={yes}) / COUNT(valid {col}) × 100'
    column, unit, formula = {
        'average_cost': ('Cost', 'INR', 'MEAN(valid Cost)'),
        'total_cost': ('Cost', 'INR', 'SUM(valid Cost)'),
        'average_stay': ('Length_of_Stay', 'days', 'MEAN(valid Length_of_Stay)'),
        'satisfaction': ('Satisfaction', '/5', 'MEAN(valid Satisfaction)'),
        'average_age': ('Age', 'years', 'MEAN(valid Age)'),
    }[metric]
    if column not in df:
        raise ValueError('The required column is missing: ' + column)
    numbers = pd.to_numeric(df[column], errors='coerce').dropna()
    numbers = numbers[numbers.map(math.isfinite)]
    low, high = (1, 5) if column == 'Satisfaction' else (0, 120) if column == 'Age' else (0, float('inf'))
    numbers = numbers[numbers.between(low, high)]
    if numbers.empty:
        raise ValueError('No valid numeric values are available for ' + column)
    value = numbers.sum() if metric == 'total_cost' else numbers.mean()
    return float(value), unit, len(numbers), [column], formula


def _format(value: float, unit: str) -> str:
    if unit == 'patients':
        return f'{value:,.0f}'
    if unit == 'INR':
        return f'₹{value:,.0f}'
    if unit == '%':
        return f'{value:.1f}%'
    if unit == '/5':
        return f'{value:.2f} / 5'
    return f'{value:.1f} {unit}'


def answer_plan(df: pd.DataFrame, plan: QueryPlan) -> dict:
    """Execute an already bounded plan; no arbitrary expression is accepted."""
    if not isinstance(plan, QueryPlan) or plan.metric not in METRICS or (plan.group_by and plan.group_by not in GROUPS):
        return _refuse('The analytical plan is unsupported.', 'invalid_plan')
    if not isinstance(df, pd.DataFrame) or df.empty:
        return _refuse('No records are available in the selected dashboard scope.', 'empty_scope')
    try:
        sub = _apply_plan(df, plan)
        if sub.empty:
            return _refuse('No records match that question within the current dashboard filters. Change the filters if you need a different cohort.', 'empty_scope')
        if plan.group_by == 'Age_Band':
            if 'Age' not in sub:
                raise ValueError('The required column is missing: Age')
            age = pd.to_numeric(sub.Age, errors='coerce')
            if age.isna().any() or not age.between(0, 120).all() or not age.mod(1).eq(0).all():
                raise ValueError('Age bands require whole-number ages from 0 to 120 for every matching record.')
            sub = sub.assign(Age_Band=pd.cut(age, [-1, 30, 45, 60, 75, 120], labels=AGE_LABELS))
        sources = []
        if plan.group_by:
            if plan.group_by not in sub:
                raise ValueError('The required grouping column is missing: ' + plan.group_by)
            rows = []
            for label, group in sub.groupby(plan.group_by, observed=True, dropna=False):
                value, unit, denom, cols, formula = _measure(group, plan.metric)
                sources = cols
                rows.append({'group': str(label), 'value': value, 'rows': len(group), 'denominator': denom})
            rows.sort(key=lambda x: x['value'], reverse=not plan.ascending)
            if plan.top:
                rows = rows[:plan.top]
            if not rows:
                return _refuse('No valid groups are available.', 'empty_scope')
            title = (('The most expensive condition on average' if len(rows) == 1 else 'The ' + str(len(rows)) + ' most expensive conditions on average') if plan.metric == 'average_cost' and plan.top and not plan.ascending else plan.metric.replace('_', ' ').capitalize() + ' by ' + plan.group_by)
            text = title + ':\n' + '\n'.join(f"- **{row['group']}**: {_format(row['value'], unit)} (n={row['rows']})" for row in rows)
            value = None
            denominator = sum(row['denominator'] for row in rows)
        else:
            value, unit, denominator, sources, formula = _measure(sub, plan.metric)
            rows = [{'value': value, 'rows': len(sub), 'denominator': denominator}]
            cond = f' for **{plan.condition}**' if plan.condition else ''
            metric_labels = {'readmission_rate': 'readmission rate', 'average_cost': 'average cost',
                             'total_cost': 'total recorded cost', 'average_stay': 'average length of stay',
                             'satisfaction': 'average satisfaction', 'recovery_rate': 'recovered outcome rate',
                             'average_age': 'average age'}
            if plan.metric == 'count':
                noun = 'patient' if len(sub) == 1 else 'patients'
                verb = 'is' if len(sub) == 1 else 'are'
                text = f'There {verb} **{len(sub)} {noun}**' + (f' with **{plan.condition}**' if plan.condition else '')
                if plan.readmission:
                    text += ' marked ' + ('readmitted' if plan.readmission == 'Yes' else 'not readmitted')
                if plan.outcome:
                    text += f' with a **{plan.outcome}** outcome'
                text += ' in the current filtered view.'
            else:
                prefix = 'The overall ' if plan.metric == 'readmission_rate' and not plan.condition else 'The '
                text = f'{prefix}{metric_labels[plan.metric]}{cond} is **{_format(value, unit)}** ({len(sub)} patients).'
        if plan.gender:
            text += f' Gender filter: **{plan.gender}**.'
        filters = {k: v for k, v in asdict(plan).items() if k not in {'metric', 'group_by', 'top', 'ascending'} and v is not None}
        warnings = [CAUTION]
        displayed_rows = sum(row['rows'] for row in rows)
        if denominator < displayed_rows:
            warnings.append(f'{displayed_rows-denominator} missing or invalid metric values were excluded from displayed results; valid denominator is {denominator}.')
        if plan.group_by and any(row['denominator'] < 30 for row in rows):
            warnings.append('At least one displayed group has fewer than 30 valid records in its denominator; interpret descriptive rates cautiously. This threshold is a heuristic, not a significance test.')
        sources = sorted(set(sources + list({'condition': 'Condition', 'gender': 'Gender', 'outcome': 'Outcome', 'readmission': 'Readmission', 'age_min': 'Age', 'age_max': 'Age'}[k] for k in filters)))
        if plan.group_by:
            sources = sorted(set(sources + ['Age' if plan.group_by == 'Age_Band' else plan.group_by]))
            formula += ' grouped by ' + plan.group_by
        return {'ok': True, 'status': 'answered', 'mode': 'computed', 'text': text,
                'intent': plan.metric, 'value': value, 'unit': unit, 'row_count': len(sub),
                'dashboard_rows': len(df), 'denominator': denominator, 'filters': filters,
                'group_by': plan.group_by, 'formula': formula, 'source_columns': sources,
                'table': rows, 'scope_id': scope_fingerprint(df), 'warnings': warnings}
    except (ValueError, KeyError, TypeError) as e:
        return _refuse(str(e), 'data_unavailable')


def answer_question(df: pd.DataFrame, question) -> dict:
    plan = parse_question(question)
    return plan if isinstance(plan, dict) else answer_plan(df, plan)


def evidence_cards(df: pd.DataFrame) -> list[dict]:
    """Precomputed facts available to both offline and optional provider briefs."""
    if df.empty:
        return []
    cards = []
    for id, title, question in [
        ('population', 'Population', 'How many patients are there?'),
        ('readmission', 'Readmission', 'What is the readmission rate?'),
        ('cost', 'Recorded cost', 'What is the average cost?'),
        ('stay', 'Length of stay', 'What is the average length of stay?'),
        ('outcome', 'Recovered outcome', 'What is the recovered rate?'),
        ('condition_cost', 'Condition comparison', 'What are the most expensive conditions?'),
    ]:
        answer = answer_question(df, question)
        if answer['ok']:
            exclusions = [note for note in answer['warnings'] if note != CAUTION]
            card_text = answer['text'] + ('\n' + ' '.join(exclusions) if exclusions else '')
            cards.append({'id': id, 'title': title, 'text': card_text,
                          'formula': answer['formula'], 'source_columns': answer['source_columns'],
                          'row_count': answer['row_count'], 'scope_id': answer['scope_id']})
    return cards
