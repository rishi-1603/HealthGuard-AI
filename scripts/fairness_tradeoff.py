"""
fairness_tradeoff.py — the fairness/accuracy trade-off, priced and mitigated
================================================================================
THE STORY THIS SCRIPT TELLS:

scripts/fairness_check.py disclosed the problem: the model's error rates differ
sharply by gender on this dataset (base rates F 43.9% / M 7.4%). Disclosure is
day one. The board's next question is:

    "Can we MAKE the model fairer, and what does that cost in accuracy?"

This script answers with numbers:
  1. Reuses the deployed scoring path exactly (ai_risk encoders + the same CV
     scheme as fairness_check) — no drift between audits.
  2. Sweeps the decision threshold 0.05→0.95 and records, per threshold:
     overall recall/precision and per-group TPR/FPR/selection rates.
  3. Measures three standard gaps at every threshold: demographic parity,
     equal opportunity (TPR), equalized odds.
  4. Prices TWO mitigations:
       A. single constrained threshold (best fairness gap subject to
          keeping ≥90% of the unconstrained best-F1 recall)
       B. group-specific thresholds that equalize TPR across genders
     and reports the accuracy each one costs.
  5. Writes reports/fairness_tradeoff.json + reports/fairness_tradeoff.md.

HONESTY DISCLOSURES:
- Synthetic dataset (984 patients). The gender skew (F 43.9% vs M 7.4% base
  rate) is a property of THIS dataset; the trade-off method is the deliverable.
- Equalizing TPR across groups with very different base rates cannot also
  equalize FPR — that impossibility is reported, not hidden.

Run:  python scripts/fairness_tradeoff.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_predict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

JSON_PATH = ROOT / "reports" / "fairness_tradeoff.json"
MD_PATH = ROOT / "reports" / "fairness_tradeoff.md"

THRESHOLDS = [round(t, 2) for t in np.arange(0.05, 1.0, 0.05)]
MIN_RECALL_FRACTION = 0.90   # mitigation A constraint


def score_cohort() -> tuple[pd.DataFrame, pd.Series]:
    """Exact deployed scoring path: ai_risk encoders + fairness_check's CV."""
    from app.dashboard.utils import ai_risk
    from app.dashboard.utils import hospital_data as data

    df = data.load_patients()
    _, encoders = ai_risk.load_model()
    X = df[["Age", "Cost", "Length_of_Stay"]].copy()
    for col in ["Gender", "Condition", "Procedure"]:
        X[f"{col}_enc"] = encoders[col].transform(df[col])
    X = X[["Age", "Gender_enc", "Condition_enc", "Procedure_enc",
           "Cost", "Length_of_Stay"]]
    y = (df["Readmission"] == "Yes").astype(int)

    model = RandomForestClassifier(
        n_estimators=200, max_depth=6, min_samples_leaf=5,
        class_weight="balanced", random_state=42)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    proba = pd.Series(
        cross_val_predict(model, X, y, cv=cv, method="predict_proba")[:, 1],
        index=df.index)
    return df, proba


def group_metrics(y: pd.Series, proba: pd.Series, mask: pd.Series, t: float) -> dict:
    sub_y = y[mask]
    pred = (proba[mask] >= t).astype(int)
    pos = sub_y == 1
    neg = ~pos
    tpr = float(pred[pos].mean()) if pos.any() else float("nan")
    fpr = float(pred[neg].mean()) if neg.any() else float("nan")
    sel = float(pred.mean()) if len(pred) else float("nan")
    return {"n": int(mask.sum()), "tpr": round(tpr, 4), "fpr": round(fpr, 4),
            "selection_rate": round(sel, 4)}


def sweep_point(y: pd.Series, proba: pd.Series, gender: pd.Series, t: float) -> dict:
    pred = (proba >= t).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0

    g = {}
    for label in sorted(gender.unique()):
        g[label] = group_metrics(y, proba, gender == label, t)

    tprs = [m["tpr"] for m in g.values()]
    fprs = [m["fpr"] for m in g.values()]
    sels = [m["selection_rate"] for m in g.values()]

    return {
        "threshold": t,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(2 * precision * recall / (precision + recall), 4) if (precision + recall) else 0.0,
        "groups": g,
        "demo_parity_gap": round(max(sels) - min(sels), 4),
        "equal_opportunity_gap": round(max(tprs) - min(tprs), 4),
        "equalized_odds_gap": round(max(max(tprs) - min(tprs), max(fprs) - min(fprs)), 4),
    }


def run() -> dict:
    df, proba = score_cohort()
    y = (df["Readmission"] == "Yes").astype(int)
    gender = df["Gender"]

    sweep = [sweep_point(y, proba, gender, t) for t in THRESHOLDS]

    best_f1 = max(sweep, key=lambda s: s["f1"])
    deployed = next(s for s in sweep if abs(s["threshold"] - 0.50) < 1e-9)
    min_recall = MIN_RECALL_FRACTION * best_f1["recall"]

    # Mitigation A: single threshold, best equal-opportunity gap with recall floor.
    eligible = [s for s in sweep if s["recall"] >= min_recall]
    mit_a = min(eligible, key=lambda s: (s["equal_opportunity_gap"], -s["recall"]))

    # Mitigation B: per-gender thresholds equalizing TPR (grid search).
    grid = THRESHOLDS
    best_b = None
    for t_f in grid:
        for t_m in grid:
            thr = {"Female": t_f, "Male": t_m}
            tprs, fprs = {}, {}
            for label in ["Female", "Male"]:
                m = group_metrics(y, proba, gender == label, thr[label])
                tprs[label] = m["tpr"]
                fprs[label] = m["fpr"]
            gap = abs(tprs["Female"] - tprs["Male"])
            pred = pd.Series(0, index=y.index)
            for label in ["Female", "Male"]:
                sel = gender == label
                pred[sel] = (proba[sel] >= thr[label]).astype(int)
            tp = int(((pred == 1) & (y == 1)).sum())
            fp = int(((pred == 1) & (y == 0)).sum())
            fn = int(((pred == 0) & (y == 1)).sum())
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            cand = {
                "thresholds": thr,
                "equal_opportunity_gap": round(gap, 4),
                "fpr_gap": round(abs(fprs["Female"] - fprs["Male"]), 4),
                "precision": round(precision, 4),
                "recall": round(recall, 4),
            }
            if best_b is None or (cand["equal_opportunity_gap"], -cand["recall"]) < \
                    (best_b["equal_opportunity_gap"], -best_b["recall"]):
                best_b = cand

    result = {
        "generated_by": "scripts/fairness_tradeoff.py",
        "honesty": ("Synthetic dataset (984 patients). Gender base rates F 43.9% / "
                    "M 7.4% are properties of THIS dataset. Equalizing TPR across "
                    "groups with different base rates cannot also equalize FPR — "
                    "that impossibility is reported, not hidden."),
        "cohort": {
            "patients": int(len(df)),
            "gender_base_rates_pct": {
                str(k): round(float(v) * 100, 1)
                for k, v in y.groupby(gender).mean().items()},
        },
        "deployed_threshold": deployed,
        "best_f1_threshold": best_f1,
        "recall_floor_for_mitigation": round(min_recall, 4),
        "mitigation_single_threshold": mit_a,
        "mitigation_group_thresholds": best_b,
        "accuracy_cost": {
            "single_threshold": {
                "f1_delta": round(mit_a["f1"] - best_f1["f1"], 4),
                "recall_delta": round(mit_a["recall"] - best_f1["recall"], 4),
            },
            "group_thresholds": {
                "recall_delta": round(best_b["recall"] - best_f1["recall"], 4),
            },
        },
        "sweep": sweep,
    }

    JSON_PATH.parent.mkdir(exist_ok=True)
    JSON_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    MD_PATH.write_text(render_md(result), encoding="utf-8")
    return result


def render_md(r: dict) -> str:
    d = r["deployed_threshold"]
    b = r["best_f1_threshold"]
    a = r["mitigation_single_threshold"]
    g = r["mitigation_group_thresholds"]
    lines = [
        "# Fairness Trade-off — how much accuracy does fairness cost?",
        "",
        "> Generated by `scripts/fairness_tradeoff.py`. Same scoring path as",
        "> `scripts/fairness_check.py` (deployed encoders + 5-fold CV, seed 42).",
        "> Synthetic dataset; the trade-off METHOD is the deliverable.",
        "",
        "## Where the model stands today (threshold 0.50)",
        "",
        f"- Recall {d['recall']:.1%} · precision {d['precision']:.1%} · F1 {d['f1']:.3f}",
        f"- Equal-opportunity gap (TPR): **{d['equal_opportunity_gap']:.3f}**",
        f"- Demographic-parity gap (selection rate): **{d['demo_parity_gap']:.3f}**",
        f"- Base rates: {r['cohort']['gender_base_rates_pct']}",
        "",
        "## Mitigations priced",
        "",
        "| Policy | Thresholds | Recall | Precision | TPR gap |",
        "|---|---|---|---|---|",
        f"| Unconstrained best-F1 | {b['threshold']:.2f} | {b['recall']:.1%} | {b['precision']:.1%} | {b['equal_opportunity_gap']:.3f} |",
        f"| A: single fair threshold | {a['threshold']:.2f} | {a['recall']:.1%} | {a['precision']:.1%} | {a['equal_opportunity_gap']:.3f} |",
        f"| B: group thresholds | {g['thresholds']} | {g['recall']:.1%} | {g['precision']:.1%} | {g['equal_opportunity_gap']:.3f} |",
        "",
        f"**Accuracy cost of A:** ΔF1 {r['accuracy_cost']['single_threshold']['f1_delta']:+.3f}, "
        f"Δrecall {r['accuracy_cost']['single_threshold']['recall_delta']:+.1%}.",
        f"**Accuracy cost of B:** Δrecall {r['accuracy_cost']['group_thresholds']['recall_delta']:+.1%}.",
        "",
        "## The impossibility that must be stated out loud",
        "",
        "When base rates differ this sharply (43.9% vs 7.4%), **equalizing TPR",
        "necessarily un-equalizes FPR** — mitigation B's FPR gap is printed in the",
        "JSON (`fpr_gap`) precisely so nobody mistakes this for a free lunch. This",
        "is the Chouldechova/Kleinberg impossibility result, visible in our own data.",
        "",
        "## Threshold sweep (excerpts)",
        "",
        "| Threshold | Recall | Precision | TPR gap | Demographic-parity gap |",
        "|---|---|---|---|---|",
    ]
    for s in r["sweep"]:
        if s["threshold"] in (0.15, 0.25, 0.35, 0.50, 0.65, 0.80):
            lines.append(f"| {s['threshold']:.2f} | {s['recall']:.1%} | {s['precision']:.1%} | "
                         f"{s['equal_opportunity_gap']:.3f} | {s['demo_parity_gap']:.3f} |")
    lines += [
        "",
        "## How to defend this in an interview",
        "",
        "1. **'Fairness' is not a vibe — it is three named metrics** (demographic",
        "   parity, equal opportunity, equalized odds), each measured here.",
        "2. **Mitigations are priced like any other decision** — recall lost is the",
        "   cost, gap closed is the benefit.",
        "3. **The impossibility result is disclosed** — that single sentence separates",
        "   a candidate who has DONE this work from one who has read about it.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    out = run()
    print(f"Deployed t=0.5 TPR-gap {out['deployed_threshold']['equal_opportunity_gap']:.3f} | "
          f"mitigation A t={out['mitigation_single_threshold']['threshold']:.2f} gap "
          f"{out['mitigation_single_threshold']['equal_opportunity_gap']:.3f} | "
          f"mitigation B gap {out['mitigation_group_thresholds']['equal_opportunity_gap']:.3f}")
    print(f"Report: {MD_PATH}")
