"""Backward-compatible entry point for bounded, data-computed analytical answers.

Numerical calculations and question validation live in assistant_service. No
provider call is made here; unsupported questions are explicitly refused rather
than silently forwarded to unrestricted narration.
"""
from .assistant_service import CONDITION_SYNONYMS, answer_question, _contains_phrase


def answer(df, question) -> dict:
    return answer_question(df, question)


def _match_condition(df, question):
    """Compatibility helper: prefer the longest dataset condition phrase."""
    for condition in sorted(df.Condition.dropna().unique(), key=len, reverse=True):
        if _contains_phrase(condition, question):
            return condition
    for condition, aliases in CONDITION_SYNONYMS.items():
        if condition in set(df.Condition) and any(_contains_phrase(alias, question) for alias in aliases):
            return condition
    return None
