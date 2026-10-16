"""
temporal_validation.py — what a TIME-BASED split does to the headline metric
============================================================================
WHY THIS EXISTS: the shipped model is evaluated with a random stratified split.
In deployment, models are trained on the PAST and predict the FUTURE. Random
splits leak future distribution into training; temporal splits don't. This
script demonstrates the correct protocol and reports what it costs the metric.

THE HONEST DISCLOSURE UP FRONT: the hospital dataset has no dates. The discharge
dates used here are SYNTHETIC AND INDEPENDENT OF OUTCOMES (seeded uniform draws
over 2022-2024). Therefore:

  - this demonstrates the METHOD of temporal validation,
  - it does NOT reproduce real temporal drift,
  - on this generator the time-split result should be close to the random-split
    result (outcomes don't drift over time) — any gap is sampling noise, and we
    report it whatever direction it goes.

On real data, a gap between random and temporal performance is the rule, not
the exception — and the size of that gap is what you report to stakeholders.

Outputs:
  reports/temporal_validation.md
  reports/temporal_validation_metrics.json   (pinned by tests)

Run:  python scripts/temporal_validation.py
"""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "hospital" / "hospital_data.csv"
REPORT_PATH = ROOT / "reports" / "temporal_validation.md"
METRICS_PATH = ROOT / "reports" / "temporal_validation_metrics.json"

FEATURES = ["Age", "Gender_enc", "Condition_enc", "Procedure_enc", "Cost", "Length_of_Stay"]
SEED = 42


def make_model():
    return RandomForestClassifier(n_estimators=200, max_depth=6, min_samples_leaf=5,
                                  class_weight="balanced", random_state=SEED)


def load_data():
    df = pd.read_csv(DATA_PATH)
    df["target"] = (df.Readmission == "Yes").astype(int)
    for col in ["Gender", "Condition", "Procedure"]:
        df[f"{col}_enc"] = LabelEncoder().fit_transform(df[col])

    # SYNTHETIC discharge dates — independent of outcomes, seeded.
    rng = np.random.default_rng(SEED)
    start = np.datetime64("2022-01-01")
    days = rng.integers(0, 1095, size=len(df))          # 3 years
    df["discharge_date"] = start + days.astype("timedelta64[D]")
    return df


def evaluate(X_tr, y_tr, X_te, y_te):
    m = make_model()
    m.fit(X_tr, y_tr)
    p = m.predict_proba(X_te)[:, 1]
    return {
        "roc_auc": round(float(roc_auc_score(y_te, p)), 4),
        "pr_auc": round(float(average_precision_score(y_te, p)), 4),
        "n_train": int(len(X_tr)), "n_test": int(len(X_te)),
        "test_prevalence": round(float(np.mean(y_te)), 4),
    }


def main():
    df = load_data()
    X, y = df[FEATURES], df["target"].values

    # ── A. Random stratified split (the shipped protocol) ────────────
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=SEED, stratify=y)
    random_split = evaluate(X_tr, y_tr, X_te, y_te)

    # ── B. Temporal split — train on the past 70%, test on the future 30% ─
    order = np.argsort(df["discharge_date"].values)
    cut = int(len(df) * 0.70)
    tr_idx, te_idx = order[:cut], order[cut:]
    temporal_split = evaluate(X.iloc[tr_idx], y[tr_idx], X.iloc[te_idx], y[te_idx])

    # ── C. Repeated random splits (sampling-noise band, 20 repeats) ──
    aucs = []
    for s in range(20):
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=s, stratify=y)
        m = make_model()
        m.fit(X_tr, y_tr)
        aucs.append(roc_auc_score(y_te, m.predict_proba(X_te)[:, 1]))
    noise_band = {
        "mean": round(float(np.mean(aucs)), 4),
        "p2_5": round(float(np.percentile(aucs, 2.5)), 4),
        "p97_5": round(float(np.percentile(aucs, 97.5)), 4),
    }

    gap = round(temporal_split["roc_auc"] - random_split["roc_auc"], 4)
    in_band = bool(noise_band["p2_5"] <= temporal_split["roc_auc"] <= noise_band["p97_5"])

    metrics = {
        "date_disclosure": ("synthetic discharge dates, uniform over 2022-2024, "
                            "INDEPENDENT of outcomes — method demonstration only"),
        "random_split": random_split,
        "temporal_split": temporal_split,
        "temporal_minus_random_auc": gap,
        "random_repeat_band": noise_band,
        "temporal_result_inside_sampling_noise_band": in_band,
        "verdict": "",
    }
    if in_band:
        metrics["verdict"] = (
            f"Time-split AUC ({temporal_split['roc_auc']}) falls INSIDE the random-split "
            f"sampling-noise band [{noise_band['p2_5']}, {noise_band['p97_5']}] — expected, "
            f"because the synthetic dates carry no distribution drift. The protocol is the "
            f"deliverable: on real data this comparison reveals exactly how much random "
            f"splits flatter your model.")
    else:
        metrics["verdict"] = (
            f"Time-split AUC ({temporal_split['roc_auc']}) differs from random-split "
            f"({random_split['roc_auc']}) by {gap:+.4f} — beyond the sampling-noise band. "
            f"Even with drift-free synthetic dates the split choice moves the number: "
            f"always validate on time when time exists.")

    REPORT_PATH.write_text(write_report(metrics))
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    print(f"random AUC {random_split['roc_auc']} | temporal AUC {temporal_split['roc_auc']} "
          f"({gap:+.4f}) | noise band [{noise_band['p2_5']}, {noise_band['p97_5']}]")
    print(f"Wrote {REPORT_PATH.name} + {METRICS_PATH.name}")


def write_report(m):
    L = []
    a = L.append
    a("# Temporal Validation Prototype — Readmission Model")
    a("### What happens when you validate on the future instead of a random slice")
    a("")
    a("> Generated by `scripts/temporal_validation.py`.")
    a(f">")
    a(f"> ⚠️ **Date disclosure:** {m['date_disclosure']}.")
    a("")
    a("---")
    a("")
    a("## 1. The two protocols")
    a("")
    a("| Protocol | ROC-AUC | PR-AUC | Train n | Test n | Test prevalence |")
    a("|---|---|---|---|---|---|")
    r, t = m["random_split"], m["temporal_split"]
    a(f"| Random stratified 80/20 (shipped) | **{r['roc_auc']}** | {r['pr_auc']} | "
      f"{r['n_train']} | {r['n_test']} | {r['test_prevalence']:.1%} |")
    a(f"| Temporal: train past 70%, test future 30% | **{t['roc_auc']}** | {t['pr_auc']} | "
      f"{t['n_train']} | {t['n_test']} | {t['test_prevalence']:.1%} |")
    a("")
    a(f"**Difference (temporal − random): {m['temporal_minus_random_auc']:+.4f} AUC**")
    a("")
    a("## 2. Is the gap real? (sampling-noise band)")
    a("")
    nb = m["random_repeat_band"]
    a(f"20 repeated random splits give AUC mean {nb['mean']} with a 95% band "
      f"**[{nb['p2_5']}, {nb['p97_5']}]**. The temporal result "
      f"{'falls inside' if m['temporal_result_inside_sampling_noise_band'] else 'falls OUTSIDE'} "
      "this band.")
    a("")
    a(f"> **{m['verdict']}**")
    a("")
    a("## 3. Why this protocol matters (even with drift-free dates)")
    a("")
    a("1. **Random splits flatter models.** Training sees patients from the same "
      "period as the test set. In deployment, training data is always older than "
      "predictions.")
    a("2. **The band is the honesty tool.** Without the repeated-split band, any "
      "AUC difference looks meaningful. With it, you can say 'within noise' vs "
      "'real degradation' — the same discipline as the churn and forecast work.")
    a("3. **What a real run would add:** seasonal drift, protocol changes, "
      "case-mix shifts. Synthetic drift-free dates cannot show those — the "
      "deliverable here is the protocol and the analysis template.")
    a("")
    a("## 4. Limitations")
    a("")
    a("1. Dates are synthetic and independent of outcomes — no temporal signal exists "
      "to find. This is a method demonstration, not a temporal finding.")
    a("2. One model family (RandomForest) and one split ratio; the comparison is "
      "illustrative.")
    a("3. The label is near-deterministic given Condition (see model_honesty.md), so "
      "both protocols inherit that ceiling.")
    a("4. With real dates and real drift, expect the temporal AUC to be LOWER — that "
      "gap is the honest performance estimate.")
    a("")
    a("---")
    a("")
    a("*Numbers pinned by `tests/test_temporal_validation.py`.*")
    return "\n".join(L)


if __name__ == "__main__":
    main()
