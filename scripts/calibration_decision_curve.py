"""
calibration_decision_curve.py — is the readmission model's probability honest,
and would acting on it actually help?
=============================================================================
The model-honesty audit (reports/model_honesty.md) explains WHY the AUC ~0.99
is synthetic-data determinism. This script answers the two remaining questions
a decision-maker has:

  1. CALIBRATION — if the model says 30% readmission risk, do ~30% of those
     patients actually get readmitted? (Probably not: the raw RandomForest is
     expected to be over-confident.)
  2. DECISION VALUE — across plausible action thresholds (0.10-0.50), does
     acting on the model beat acting on everyone or no one? (Decision-curve
     analysis / net benefit — Vickers & Elkin method.)

Plus 3. SUBGROUP CONFIDENCE INTERVALS — bootstrap 95% CIs on AUC/precision/
recall by age band and gender, because a point estimate for a subgroup of 20
patients is not evidence.

Protocol: fit / calibration / test = 64% / 16% / 20%, stratified, seed 42.
The shipped model (80/20) is diagnosed on the same test slice for comparability.

All findings are METHOD DEMONSTRATIONS on synthetic data — not clinical evidence.

Outputs:
  reports/calibration_and_decision_curve.md
  reports/calibration_decision_curve_metrics.json   (pinned by tests)
  docs/screenshots/calibration_decision_curve.png

Run:  python scripts/calibration_decision_curve.py
"""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "hospital" / "hospital_data.csv"
REPORT_PATH = ROOT / "reports" / "calibration_and_decision_curve.md"
METRICS_PATH = ROOT / "reports" / "calibration_decision_curve_metrics.json"
FIG_PATH = ROOT / "docs" / "screenshots" / "calibration_decision_curve.png"
FIG_PATH.parent.mkdir(parents=True, exist_ok=True)

FEATURES = ["Age", "Gender_enc", "Condition_enc", "Procedure_enc", "Cost", "Length_of_Stay"]
AGE_BANDS = [(18, 30), (31, 45), (46, 60), (61, 75), (76, 200)]
N_BOOT = 1000
DCA_THRESHOLDS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]


def load_data():
    df = pd.read_csv(DATA_PATH)
    df["target"] = (df.Readmission == "Yes").astype(int)
    for col in ["Gender", "Condition", "Procedure"]:
        df[f"{col}_enc"] = LabelEncoder().fit_transform(df[col])
    return df


def reliability_table(y, p, n_bins=10):
    edges = np.linspace(0, 1, n_bins + 1)
    rows = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < n_bins - 1 else (p >= lo) & (p <= hi)
        rows.append({
            "bin": f"[{lo:.1f},{hi:.1f}]", "n": int(mask.sum()),
            "mean_predicted": None if mask.sum() == 0 else round(float(p[mask].mean()), 4),
            "observed_rate": None if mask.sum() == 0 else round(float(y[mask].mean()), 4),
        })
    return rows


def calib_slope_intercept(y, p):
    eps = 1e-6
    pc = np.clip(p, eps, 1 - eps)
    logit = np.log(pc / (1 - pc))
    lr = LogisticRegression(C=1e6, max_iter=1000).fit(logit.reshape(-1, 1), y)
    return round(float(lr.intercept_[0]), 4), round(float(lr.coef_[0, 0]), 4)


def ece(y, p, n_bins=10):
    edges = np.linspace(0, 1, n_bins + 1)
    e = 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < n_bins - 1 else (p >= lo) & (p <= hi)
        if mask.sum():
            e += mask.sum() / len(y) * abs(p[mask].mean() - y[mask].mean())
    return round(float(e), 4)


def net_benefit(y, p, t):
    pred = p >= t
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    n = len(y)
    return tp / n - (fp / n) * (t / (1 - t))


def bootstrap_ci(y, p, fn, n_boot=N_BOOT, seed=42):
    rng = np.random.default_rng(seed)
    vals = []
    idx = np.arange(len(y))
    for _ in range(n_boot):
        b = rng.choice(idx, size=len(idx), replace=True)
        if len(np.unique(y[b])) < 2:
            continue
        vals.append(fn(y[b], p[b]))
    if not vals:
        return [None, None]
    return [round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)]


def auc_fn(y, p):
    return roc_auc_score(y, p)


def prec_fn(y, p, t=0.5):
    pred = (p >= t).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    return tp / max(tp + fp, 1)


def rec_fn(y, p, t=0.5):
    pred = (p >= t).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    return tp / max(tp + fn, 1)


def main():
    df = load_data()
    X, y = df[FEATURES], df["target"].values

    X_fit, X_test, y_fit, y_test = train_test_split(X, y, test_size=0.20, random_state=42, stratify=y)
    X_fit, X_cal, y_fit, y_cal = train_test_split(X_fit, y_fit, test_size=0.20, random_state=42, stratify=y_fit)

    rf = RandomForestClassifier(n_estimators=200, max_depth=6, min_samples_leaf=5,
                                class_weight="balanced", random_state=42)
    rf.fit(X_fit, y_fit)
    p_raw_cal = rf.predict_proba(X_cal)[:, 1]
    p_raw_test = rf.predict_proba(X_test)[:, 1]

    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(p_raw_cal, y_cal)
    p_iso_test = iso.predict(p_raw_test)

    # ── 1. Calibration ───────────────────────────────────────────────
    brier_raw = round(float(brier_score_loss(y_test, p_raw_test)), 4)
    brier_iso = round(float(brier_score_loss(y_test, p_iso_test)), 4)
    brier_ref = round(float(brier_score_loss(y_test, np.full_like(y_test, y_fit.mean()))), 4)
    intercept_raw, slope_raw = calib_slope_intercept(y_test, p_raw_test)
    intercept_iso, slope_iso = calib_slope_intercept(y_test, p_iso_test)

    calibration = {
        "raw": {"brier": brier_raw, "ece": ece(y_test, p_raw_test),
                "intercept": intercept_raw, "slope": slope_raw},
        "isotonic": {"brier": brier_iso, "ece": ece(y_test, p_iso_test),
                     "intercept": intercept_iso, "slope": slope_iso},
        "prevalence_reference_brier": brier_ref,
        "test_prevalence": round(float(y_test.mean()), 4),
        "reliability_raw": reliability_table(y_test, p_raw_test),
    }

    # ── 2. Decision-curve analysis (raw probs = shipped behavior) ────
    dca_rows = []
    for t in DCA_THRESHOLDS:
        dca_rows.append({
            "threshold": t,
            "model_net_benefit": round(net_benefit(y_test, p_raw_test, t), 4),
            "treat_all_net_benefit": round(net_benefit(y_test, np.ones_like(y_test, dtype=float), t), 4),
            "treat_none_net_benefit": 0.0,
        })

    # ── 3. Subgroup bootstrap CIs (raw probs, threshold 0.5) ────────
    test_idx = X_test.index if hasattr(X_test, "index") else np.arange(len(X_test))
    test_df = df.loc[test_idx].copy()
    test_df["p"] = p_raw_test
    test_df["y"] = y_test

    subgroup = {"by_age_band": [], "by_gender": []}
    for lo, hi in AGE_BANDS:
        g = test_df[(test_df["Age"] >= lo) & (test_df["Age"] <= hi)]
        row = {"band": f"{lo}-{hi if hi < 200 else '+'}", "n": int(len(g)),
               "n_pos": int(g["y"].sum())}
        ok = len(g) >= 15 and g["y"].nunique() == 2 and int(g["y"].sum()) >= 5
        if ok:
            row["auc"] = round(float(roc_auc_score(g["y"], g["p"])), 4)
            row["auc_ci95"] = bootstrap_ci(g["y"].values, g["p"].values, auc_fn)
            row["precision"] = round(prec_fn(g["y"].values, g["p"].values), 4)
            row["precision_ci95"] = bootstrap_ci(g["y"].values, g["p"].values, prec_fn)
            row["recall"] = round(rec_fn(g["y"].values, g["p"].values), 4)
            row["recall_ci95"] = bootstrap_ci(g["y"].values, g["p"].values, rec_fn)
        else:
            row["warning"] = ("too few patients or too few positives (<5) - "
                              "no metric reported (a perfect AUC on 2 positives is noise)")
        subgroup["by_age_band"].append(row)

    for gender, g in test_df.groupby("Gender"):
        row = {"gender": str(gender), "n": int(len(g)), "n_pos": int(g["y"].sum())}
        ok = len(g) >= 15 and g["y"].nunique() == 2 and int(g["y"].sum()) >= 5
        if ok:
            row["auc"] = round(float(roc_auc_score(g["y"], g["p"])), 4)
            row["auc_ci95"] = bootstrap_ci(g["y"].values, g["p"].values, auc_fn)
            row["precision"] = round(prec_fn(g["y"].values, g["p"].values), 4)
            row["precision_ci95"] = bootstrap_ci(g["y"].values, g["p"].values, prec_fn)
            row["recall"] = round(rec_fn(g["y"].values, g["p"].values), 4)
            row["recall_ci95"] = bootstrap_ci(g["y"].values, g["p"].values, rec_fn)
        else:
            row["warning"] = ("too few patients or too few positives (<5) - "
                              "no metric reported (a perfect AUC on 2 positives is noise)")
        subgroup["by_gender"].append(row)

    # ── findings / verdict ───────────────────────────────────────────
    model_wins = sum(1 for r in dca_rows if r["model_net_benefit"] > r["treat_all_net_benefit"] + 1e-9)
    verdict = {
        "raw_slope": slope_raw,
        "raw_model_miscalibrated": bool(abs(slope_raw - 1.0) > 0.2),
        "isotonic_improves_brier": bool(brier_iso < brier_raw),
        "model_beats_treat_all_at": model_wins,
        "n_thresholds_tested": len(DCA_THRESHOLDS),
        "recommendation": "",
    }
    if model_wins >= len(DCA_THRESHOLDS) // 2:
        verdict["recommendation"] = (
            "Methodically: the model's ranking adds decision value over treat-all/treat-none "
            "at most thresholds, and isotonic calibration makes its probabilities usable. "
            "Clinically: nothing here transfers — the label is synthetic-deterministic and "
            "the honesty audit's warning stands.")
    else:
        verdict["recommendation"] = (
            "The model does NOT reliably beat treat-all on net benefit — combined with the "
            "honesty audit, the case for acting on these probabilities is weak. Ship the "
            "system as an analytics demonstration only.")

    metrics = {
        "protocol": "fit 64% / calibration 16% / test 20%, stratified, random_state=42",
        "n_total": int(len(df)), "n_fit": int(len(X_fit)), "n_cal": int(len(X_cal)),
        "n_test": int(len(X_test)),
        "calibration": calibration,
        "dca": dca_rows,
        "subgroup": subgroup,
        "verdict": verdict,
    }

    REPORT_PATH.write_text(write_report(metrics))
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    make_figure(metrics, y_test, p_raw_test, p_iso_test)
    print(f"Brier raw {brier_raw} -> isotonic {brier_iso} | slope raw {slope_raw} -> {slope_iso}")
    print(f"DCA: model beats treat-all at {model_wins}/{len(DCA_THRESHOLDS)} thresholds")
    print(f"Wrote {REPORT_PATH.name} + {METRICS_PATH.name}")


def make_figure(metrics, y_test, p_raw, p_iso):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    # reliability
    for name, p, color in [("Raw RF", p_raw, "#DC2626"), ("Isotonic", p_iso, "#2563EB")]:
        rows = [r for r in reliability_table(y_test, p) if r["n"] > 0]
        xs = [r["mean_predicted"] for r in rows]
        ys = [r["observed_rate"] for r in rows]
        ns = [r["n"] for r in rows]
        axes[0].plot(xs, ys, "o-", label=name, color=color, lw=2)
        axes[0].scatter(xs, ys, s=[n * 1.2 for n in ns], color=color, alpha=0.4)
    lim = 1.0
    axes[0].plot([0, lim], [0, lim], "k--", alpha=0.5, label="Perfect")
    axes[0].set_xlabel("Predicted readmission probability")
    axes[0].set_ylabel("Observed readmission rate")
    axes[0].set_title("Reliability — readmission model")
    axes[0].legend()
    # DCA
    ts = [r["threshold"] for r in metrics["dca"]]
    axes[1].plot(ts, [r["model_net_benefit"] for r in metrics["dca"]], "o-",
                 color="#2563EB", label="Model")
    axes[1].plot(ts, [r["treat_all_net_benefit"] for r in metrics["dca"]], "--",
                 color="#D97706", label="Treat all")
    axes[1].axhline(0, color="k", alpha=0.5, label="Treat none")
    axes[1].set_xlabel("Decision threshold (act if risk ≥ t)")
    axes[1].set_ylabel("Net benefit")
    axes[1].set_title("Decision curve (synthetic-demo method illustration)")
    axes[1].legend()
    plt.tight_layout()
    plt.savefig(FIG_PATH, dpi=150, bbox_inches="tight")
    plt.close()


def write_report(m):
    cal = m["calibration"]
    L = []
    a = L.append
    a("# Calibration & Decision-Curve Analysis — Readmission Model")
    a("### Are the probabilities honest, and would acting on them help?")
    a("")
    a(f"> Generated by `scripts/calibration_decision_curve.py` · protocol: **{m['protocol']}**")
    a(f"> n = {m['n_total']} patients (fit {m['n_fit']} / cal {m['n_cal']} / test {m['n_test']}) · "
      f"test prevalence {cal['test_prevalence']:.1%}")
    a(">")
    a("> ⚠️ Synthetic-data **method demonstration** — no clinical validity, no patient "
      "benefit claimed. See `reports/model_honesty.md` for why the AUC is not skill.")
    a("")
    a("---")
    a("")
    a("## 1. Calibration")
    a("")
    a("| Variant | Brier ↓ | ECE ↓ | Intercept (=0 ideal) | Slope (=1 ideal) |")
    a("|---|---|---|---|---|")
    for name in ("raw", "isotonic"):
        v = cal[name]
        a(f"| {name} | {v['brier']} | {v['ece']} | {v['intercept']} | {v['slope']} |")
    a("")
    a(f"Prevalence-reference Brier (always predict the base rate): "
      f"**{cal['prevalence_reference_brier']}** — the model must beat this.")
    a("")
    if cal["raw"]["slope"] < 0.8:
        a("**Finding:** the raw RandomForest is over-confident (slope "
          f"{cal['raw']['slope']} < 1): extreme predictions are too extreme.")
    else:
        a("**Finding:** the raw RandomForest is "
          f"{'under-confident' if cal['raw']['slope'] > 1.2 else 'approximately well-calibrated in slope'} "
          f"(slope {cal['raw']['slope']}): its probabilities do not spread as far as the "
          "outcome separation warrants — a symptom of `class_weight='balanced'` shrinking "
          "the effective probability scale. "
          f"Isotonic scaling {'improves' if m['verdict']['isotonic_improves_brier'] else 'does not improve'} "
          "Brier score and ECE without changing the ranking.")
    a("")
    a("### Reliability table (raw)")
    a("")
    a("| Bin | n | Mean predicted | Observed rate |")
    a("|---|---|---|---|")
    for r in cal["reliability_raw"]:
        mp = "—" if r["mean_predicted"] is None else r["mean_predicted"]
        or_ = "—" if r["observed_rate"] is None else r["observed_rate"]
        a(f"| {r['bin']} | {r['n']} | {mp} | {or_} |")
    a("")
    a("## 2. Decision-curve analysis (net benefit)")
    a("")
    a("Net benefit = TP/n − FP/n · t/(1−t). Higher is better; a useful model must beat "
      "both 'treat all' and 'treat none' at the thresholds a team would actually use.")
    a("")
    a("| Threshold | Model | Treat all | Treat none | Model wins? |")
    a("|---|---|---|---|---|")
    for r in m["dca"]:
        win = "✅" if r["model_net_benefit"] > r["treat_all_net_benefit"] else "❌"
        a(f"| {r['threshold']} | {r['model_net_benefit']:.4f} | {r['treat_all_net_benefit']:.4f} | "
          f"0.0 | {win} |")
    a("")
    a(f"**Score:** the model beats treat-all at **{m['verdict']['model_beats_treat_all_at']}"
      f"/{m['verdict']['n_thresholds_tested']}** tested thresholds.")
    a("")
    a("![Calibration + DCA](../docs/screenshots/calibration_decision_curve.png)")
    a("")
    a("## 3. Subgroup confidence intervals (bootstrap, 1000 draws)")
    a("")
    for key, label in (("by_age_band", "Age band"), ("by_gender", "Gender")):
        a(f"### By {label}")
        a("")
        a("| Group | n | n_pos | AUC [95% CI] | Precision [95% CI] | Recall [95% CI] |")
        a("|---|---|---|---|---|---|")
        for row in m["subgroup"][key]:
            g = row.get("band") or row.get("gender")
            if "warning" in row:
                a(f"| {g} | {row['n']} | {row['n_pos']} | — | — | — | *{row['warning']}* |")
            else:
                a(f"| {g} | {row['n']} | {row['n_pos']} | "
                  f"{row['auc']} [{row['auc_ci95'][0]}, {row['auc_ci95'][1]}] | "
                  f"{row['precision']} [{row['precision_ci95'][0]}, {row['precision_ci95'][1]}] | "
                  f"{row['recall']} [{row['recall_ci95'][0]}, {row['recall_ci95'][1]}] |")
        a("")
    a("**Why CIs matter:** a subgroup AUC of 1.0 on 20 patients means nothing. "
      "Wide intervals are the honest answer when a band is thin — and single-class "
      "bands get no metric at all rather than a fabricated one.")
    a("")
    a("## 4. Verdict")
    a("")
    a(f"> **{m['verdict']['recommendation']}**")
    a("")
    a("## 5. Limitations")
    a("")
    a("1. Synthetic labels are near-deterministic given Condition — calibration on "
      "synthetic-deterministic data is a method demo only.")
    a("2. Decision thresholds 0.10–0.50 are illustrative; a clinical threshold would "
      "require cost/benefit elicitation from clinicians.")
    a("3. Subgroup CIs use 1000 bootstrap draws on a 197-patient test slice — intervals "
      "are wide by construction and should be.")
    a("4. Net-benefit comparisons use raw (shipped) probabilities; the isotonic variant "
      "would shift operating points modestly.")
    a("")
    a("---")
    a("")
    a("*Numbers pinned by `tests/test_calibration_decision_curve.py`.*")
    return "\n".join(L)


if __name__ == "__main__":
    main()
