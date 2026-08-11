"""
Simple natural-language-ish Q&A over the hospital dataset.

This is deliberately NOT an LLM/RAG system -- there's no LLM API key
configured, and fabricated free-text answers over patient data would be a
real accuracy risk. Instead, this matches the question against a small set
of keyword-triggered templates and computes the answer directly from the
dataframe, so every answer is a real, traceable aggregation of your data.
"""
import re

import pandas as pd


def answer(df: pd.DataFrame, question: str) -> dict:
    q = question.lower().strip()

    condition = _match_condition(df, q)

    if "readmission" in q or "readmit" in q:
        if condition:
            rate = (df[df.Condition == condition].Readmission == "Yes").mean() * 100
            return _ok(f"The readmission rate for **{condition}** is **{rate:.1f}%** "
                       f"({(df.Condition == condition).sum()} patients).")
        rate = (df.Readmission == "Yes").mean() * 100
        return _ok(f"The overall readmission rate across all {len(df)} patients is **{rate:.1f}%**.")

    if "cost" in q or "expensive" in q or "cheap" in q:
        if condition:
            avg = df[df.Condition == condition].Cost.mean()
            return _ok(f"The average cost for **{condition}** is **${avg:,.0f}** "
                       f"(dataset average: ${df.Cost.mean():,.0f}).")
        if "highest" in q or "most expensive" in q or "top" in q:
            top = df.groupby("Condition").Cost.mean().sort_values(ascending=False).head(3)
            lines = "\n".join(f"- **{c}**: ${v:,.0f}" for c, v in top.items())
            return _ok(f"The 3 most expensive conditions on average:\n{lines}")
        return _ok(f"The average cost across all patients is **${df.Cost.mean():,.0f}**.")

    if "satisfaction" in q:
        if condition:
            avg = df[df.Condition == condition].Satisfaction.mean()
            return _ok(f"Average satisfaction for **{condition}** is **{avg:.2f} / 5**.")
        return _ok(f"Average satisfaction across all patients is **{df.Satisfaction.mean():.2f} / 5**.")

    if "length of stay" in q or "stay" in q or "days" in q:
        if condition:
            avg = df[df.Condition == condition].Length_of_Stay.mean()
            return _ok(f"Average length of stay for **{condition}** is **{avg:.1f} days**.")
        return _ok(f"Average length of stay across all patients is **{df.Length_of_Stay.mean():.1f} days**.")

    if "how many" in q or "count" in q or "number of" in q:
        if condition:
            n = (df.Condition == condition).sum()
            return _ok(f"There are **{n} patients** with **{condition}** in the dataset.")
        if _is_generic_count_question(q):
            return _ok(f"There are **{len(df)} patients** in the current filtered view.")
        # Mentions a subgroup we don't recognize -- don't silently answer the total,
        # let it escalate to the Gemini fallback instead.
        return {"ok": False, "text": (
            "I couldn't match that to a specific condition in this dataset. "
        )}

    if "outcome" in q or "recovered" in q:
        if condition:
            sub = df[df.Condition == condition]
            rate = (sub.Outcome == "Recovered").mean() * 100
            return _ok(f"**{rate:.1f}%** of **{condition}** patients had a 'Recovered' outcome.")
        rate = (df.Outcome == "Recovered").mean() * 100
        return _ok(f"**{rate:.1f}%** of all patients had a 'Recovered' outcome.")

    return {
        "ok": False,
        "text": "I can only answer questions grounded in this dataset's real columns — "
                "try asking about **readmission rate**, **cost**, **length of stay**, "
                "**satisfaction**, **outcome**, or **patient counts**, optionally for a "
                "specific condition (e.g. \"what's the readmission rate for Diabetes?\").",
    }


CONDITION_SYNONYMS = {
    "Diabetes": ["diabetic"],
    "Heart Disease": ["cardiac disease", "heart problems", "heart condition"],
    "Heart Attack": ["cardiac arrest", "myocardial infarction"],
    "Fractured Arm": ["broken arm"],
    "Fractured Leg": ["broken leg"],
    "Stroke": ["cerebrovascular"],
    "Cancer": ["oncology", "tumor"],
    "Prostate Cancer": ["prostate tumor"],
    "Hypertension": ["high blood pressure"],
    "Respiratory Infection": ["lung infection", "chest infection"],
    "Kidney Stones": ["renal stones"],
    "Allergic Reaction": ["allergy"],
    "Osteoarthritis": ["arthritis"],
}


def _is_generic_count_question(q: str) -> bool:
    stopwords = {
        "how", "many", "patients", "patient", "are", "there", "is", "the",
        "count", "number", "of", "total", "in", "dataset", "?", "what's", "what",
    }
    words = re.findall(r"[a-z']+", q)
    leftover = [w for w in words if w not in stopwords]
    return len(leftover) == 0


def _contains_phrase(phrase: str, q: str) -> bool:
    """Word-boundary match so short terms don't false-positive as substrings
    of unrelated words (e.g. would-be 'mi' inside 'leukemia')."""
    return re.search(r"\b" + re.escape(phrase.lower()) + r"\b", q) is not None


def _match_condition(df: pd.DataFrame, q: str):
    for c in df.Condition.unique():
        if _contains_phrase(c, q):
            return c
    for c, synonyms in CONDITION_SYNONYMS.items():
        if c in df.Condition.unique() and any(_contains_phrase(s, q) for s in synonyms):
            return c
    return None


def _ok(text: str) -> dict:
    return {"ok": True, "text": text}
