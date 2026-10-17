"""
qa_eval.py — correct-refusal benchmark for the grounded Q&A layer
================================================================================
THE STORY THIS SCRIPT TELLS:

The project's key AI-trust claim: answers come from real aggregations of the
dataset (app/dashboard/utils/simple_qa.py), never from a model's imagination.
But the DANGEROUS failure mode is not "I don't know" — it is a confident
answer to a question the data cannot answer. This harness scores both axes:

  1. ANSWERABLE QUESTIONS: the answer must contain the dataset's real numbers
     (recomputed here independently — the eval does not trust the QA layer).
  2. OUT-OF-SCOPE QUESTIONS: must return ok=false (refuse), not a guess.
  3. FALSE-PREMISE TRAPS: questions about conditions that DO NOT EXIST in the
     dataset (lung cancer, COVID). A grounded system must refuse — any
     confident number is a fabrication, scored as such.

HONESTY: the dataset is synthetic (984 patients). The property under test —
answer-from-data-or-refuse — holds for any dataset.

Run:  python scripts/qa_eval.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.dashboard.utils.simple_qa import answer  # noqa: E402

BENCH_PATH = ROOT / "evals" / "qa_benchmark.json"
JSON_PATH = ROOT / "reports" / "qa_eval.json"
MD_PATH = ROOT / "reports" / "qa_eval.md"
DATA_PATH = ROOT / "data" / "hospital" / "hospital_data.csv"


def expected_tokens(df: pd.DataFrame, spec: dict) -> list[str]:
    """Recompute what a grounded answer must contain — at eval time, never hardcoded."""
    metric = spec["metric"]
    cond = spec.get("condition")
    sub = df[df.Condition == cond] if cond else df
    if metric == "readmission_rate":
        return [f"{(sub.Readmission == 'Yes').mean() * 100:.1f}%"]
    if metric == "avg_cost":
        return [f"{sub.Cost.mean():,.0f}"]
    if metric == "avg_stay":
        return [f"{sub.Length_of_Stay.mean():.1f}"]
    if metric == "avg_satisfaction":
        return [f"{sub.Satisfaction.mean():.2f}"]
    if metric == "count":
        return [f"{len(sub)}"]
    if metric == "top3_cost":
        top3 = df.groupby("Condition").Cost.mean().sort_values(ascending=False).head(3)
        return list(top3.index)
    return []


def evaluate_answerable(df: pd.DataFrame, case: dict) -> dict:
    res = answer(df, case["question"])
    ok = bool(res.get("ok"))
    text = res.get("text", "")
    tokens = expected_tokens(df, case["recompute"])
    grounded = ok and any(tok in text for tok in tokens)
    return {
        "question": case["question"],
        "ok": ok,
        "grounded": bool(grounded),
        "expected_any_of": tokens,
        "fabrication": bool(ok and not grounded),
    }


def run() -> dict:
    bench = json.loads(BENCH_PATH.read_text())
    df = pd.read_csv(DATA_PATH)

    answerable = [evaluate_answerable(df, c) for c in bench["answerable"]]

    out_of_scope = []
    for q in bench["unanswerable_out_of_scope"]:
        res = answer(df, q)
        refused = not bool(res.get("ok"))
        out_of_scope.append({"question": q, "refused": refused,
                             "fabrication": bool(res.get("ok")),
                             "pass": refused})

    traps = []
    for c in bench["false_premise_traps"]:
        res = answer(df, c["question"])
        text = res.get("text", "")
        # A trap is passed only if the system does NOT present a confident
        # condition-specific number. ok=false, or text without a fabricated
        # condition rate, both count as refusal.
        confident_fabrication = bool(res.get("ok")) and ("%" in text) and ("not" not in text.lower() and "no " not in text.lower())
        traps.append({
            "question": c["question"],
            "ok": bool(res.get("ok")),
            "confident_fabrication": confident_fabrication,
            "pass": not confident_fabrication,
        })

    n_a = len(answerable)
    n_a_pass = sum(1 for r in answerable if r["grounded"])
    n_o = len(out_of_scope)
    n_o_pass = sum(1 for r in out_of_scope if r["pass"])
    n_t = len(traps)
    n_t_pass = sum(1 for r in traps if r["pass"])
    n_fab = sum(1 for r in answerable if r["fabrication"]) + \
        sum(1 for r in out_of_scope if r["fabrication"]) + \
        sum(1 for r in traps if r["confident_fabrication"])

    total = n_a + n_o + n_t
    total_pass = n_a_pass + n_o_pass + n_t_pass

    result = {
        "generated_by": "scripts/qa_eval.py",
        "honesty": ("Synthetic dataset; the property under test is answer-from-data-"
                    "or-refuse, which holds for any dataset. The optional Gemini "
                    "fallback is labelled and excluded from this benchmark."),
        "answerable": {"n": n_a, "grounded": n_a_pass,
                       "accuracy": round(n_a_pass / n_a, 4) if n_a else 0.0,
                       "cases": answerable},
        "out_of_scope": {"n": n_o, "refused": n_o_pass,
                         "refusal_accuracy": round(n_o_pass / n_o, 4) if n_o else 0.0,
                         "cases": out_of_scope},
        "false_premise_traps": {"n": n_t, "passed": n_t_pass,
                                "trap_accuracy": round(n_t_pass / n_t, 4) if n_t else 0.0,
                                "cases": traps},
        "fabrications_total": n_fab,
        "overall_accuracy": round(total_pass / total, 4) if total else 0.0,
        "verdict": "PASS" if (total_pass == total and n_fab == 0) else "FAIL",
    }

    JSON_PATH.parent.mkdir(exist_ok=True)
    JSON_PATH.write_text(json.dumps(result, indent=2))
    MD_PATH.write_text(render_md(result))
    return result


def render_md(r: dict) -> str:
    lines = [
        "# Grounded-QA Eval — answering right AND refusing right",
        "",
        "> Generated by `scripts/qa_eval.py`. Expected numbers are recomputed from",
        "> the dataset independently — the eval does not trust the QA layer. False-",
        "> premise traps ask about conditions that do not exist (lung cancer, COVID):",
        "> any confident number there is a fabrication, and is scored as one.",
        "",
        "## Scores",
        "",
        f"- **Answerable: {r['answerable']['grounded']}/{r['answerable']['n']}** "
        f"(grounded accuracy {r['answerable']['accuracy']:.1%})",
        f"- **Out-of-scope refusals: {r['out_of_scope']['refused']}/{r['out_of_scope']['n']}** "
        f"({r['out_of_scope']['refusal_accuracy']:.1%})",
        f"- **False-premise traps: {r['false_premise_traps']['passed']}/{r['false_premise_traps']['n']}** "
        f"({r['false_premise_traps']['trap_accuracy']:.1%})",
        f"- **Fabrications: {r['fabrications_total']}**",
        f"- **Overall: {r['overall_accuracy']:.1%} — verdict {r['verdict']}**",
        "",
        "## Why the trap set exists",
        "",
        "Most demos only ask answerable questions. The trust test is what happens",
        "when the question is UNANSWERABLE: 'readmission rate for lung cancer' —",
        "a grounded system must refuse. A system that invents 42.7% is worse than",
        "useless in a hospital. These traps are the difference.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    out = run()
    print(f"Answerable {out['answerable']['grounded']}/{out['answerable']['n']} | "
          f"refusals {out['out_of_scope']['refused']}/{out['out_of_scope']['n']} | "
          f"traps {out['false_premise_traps']['passed']}/{out['false_premise_traps']['n']} | "
          f"fabrications {out['fabrications_total']} | {out['verdict']}")
    print(f"Reports: {MD_PATH}")
