"""
program_simulator.py — readmission-prevention program: who to enroll, what it returns
================================================================================
THE STORY THIS SCRIPT TELLS:

The hospital knows readmitted patients cost +112% more (₹13,650 vs ₹6,431 —
verified in scripts/sql_analytics.py). The obvious next question is:

    "If we run a prevention program, WHO do we enroll, how much do we spend,
     and when does the program pay for itself?"

This script is the decision layer for that question:
  1. Targets patients with a transparent, reproducible risk rule: the smoothed
     historical readmission rate of each (Condition × Age-band) stratum. No
     black box — every enrolled patient can be explained in one sentence.
  2. Prices each enrollment strategy (all / top decile / quartile / half /
     above-baseline) with an explicit cost model: program cost per enrollee vs
     the readmission episode cost avoided.
  3. Computes break-even efficacy — the minimum program effectiveness that
     makes each strategy self-funding.
  4. Runs a sensitivity grid over efficacy and unit cost.
  5. Audits WHO gets enrolled (gender / age mix) so the equity impact of the
     targeting rule is visible, not assumed.

HONESTY DISCLOSURES:
- The dataset is synthetic (984 patients, seeded). This demonstrates the
  decision method, not a hospital's real P&L.
- Efficacy (25% relative readmission reduction) is a documented assumption
  borrowed from the literature range — every conclusion is sensitivity-tested
  against it.
- Cost figures (₹2,000 program cost; ₹13,650 avoided episode) — the episode
  cost is MEASURED from this dataset; the program cost is an assumption.

Run:  python scripts/program_simulator.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "hospital" / "hospital_data.csv"
JSON_PATH = ROOT / "reports" / "program_simulator.json"
MD_PATH = ROOT / "reports" / "program_simulator.md"

# ── Cost model (documented assumptions, sensitivity-tested) ──────────────────
PROGRAM_COST = 2000.0        # ₹ per enrolled patient for the prevention program
EPISODE_SAVING = 13650.0     # ₹ avoided per prevented readmission (MEASURED: avg readmitted cost)
EFFICACY = 0.25              # relative reduction in readmission risk for enrollees

SENS_EFFICACY = (0.10, 0.25, 0.40)
SENS_COST = (1000.0, 2000.0, 3000.0)

AGE_BANDS = [(18, 30), (31, 45), (46, 60), (61, 75), (76, 200)]
BAND_LABELS = ["18-30", "31-45", "46-60", "61-75", "76+"]


def age_band(age: int) -> str:
    for (lo, hi), label in zip(AGE_BANDS, BAND_LABELS):
        if lo <= age <= hi:
            return label
    return "unknown"


def load_cohort() -> pd.DataFrame:
    """Patients + stratum risk score (Laplace-smoothed historical rate)."""
    df = pd.read_csv(DATA_PATH)
    df["Readmitted"] = df["Readmission"].str.strip().str.lower().eq("yes")
    df["Age_Band"] = df["Age"].astype(int).map(age_band)
    df["Stratum"] = df["Condition"] + " | " + df["Age_Band"]

    stats = df.groupby("Stratum")["Readmitted"].agg(["sum", "count"])
    # Laplace smoothing: (readmits + 1) / (n + 2) — shrinks tiny strata to the middle.
    df["Risk_Score"] = df["Stratum"].map((stats["sum"] + 1) / (stats["count"] + 2))
    return df


def evaluate_strategy(df: pd.DataFrame, enroll: pd.Series, name: str,
                      program_cost: float = PROGRAM_COST,
                      episode_saving: float = EPISODE_SAVING,
                      efficacy: float = EFFICACY) -> dict:
    """Price one enrollment strategy."""
    e = df[enroll]
    n_enrolled = int(len(e))
    expected_readmits = float(e["Risk_Score"].sum())          # model-free expectation
    actual_readmits = int(e["Readmitted"].sum())              # hindsight on this dataset
    prevented = efficacy * expected_readmits
    savings = prevented * episode_saving
    cost = program_cost * n_enrolled
    net = savings - cost
    roi = net / cost if cost else 0.0
    be = (program_cost * n_enrolled) / (expected_readmits * episode_saving) \
        if expected_readmits else float("inf")

    return {
        "strategy": name,
        "enrolled": n_enrolled,
        "expected_readmits_among_enrolled": round(expected_readmits, 2),
        "actual_readmits_among_enrolled": actual_readmits,
        "expected_prevented": round(prevented, 2),
        "program_cost": round(cost, 2),
        "expected_savings": round(savings, 2),
        "net_value": round(net, 2),
        "roi": round(roi, 4),
        "break_even_efficacy": round(be, 4),
    }


def equity_slice(df: pd.DataFrame, enroll: pd.Series) -> dict:
    """Who gets enrolled — gender and age mix vs the population."""
    e = df[enroll]

    def share(s: pd.Series) -> dict:
        vc = (s.value_counts(normalize=True) * 100).round(1)
        return {str(k): float(v) for k, v in vc.items()}

    return {
        "enrolled_gender_share_pct": share(e["Gender"]),
        "population_gender_share_pct": share(df["Gender"]),
        "enrolled_age_band_share_pct": share(e["Age_Band"]),
        "population_age_band_share_pct": share(df["Age_Band"]),
        "enrolled_mean_age": round(float(e["Age"].mean()), 1),
        "population_mean_age": round(float(df["Age"].mean()), 1),
    }


def run() -> dict:
    df = load_cohort()
    n = len(df)
    base_rate = float(df["Readmitted"].mean())

    ranked = df.sort_values(["Risk_Score", "Cost"], ascending=[False, False])

    strategies = [
        (pd.Series(True, index=df.index), "enroll_all"),
        (df.index.isin(ranked.head(int(n * 0.10)).index), "enroll_top_decile"),
        (df.index.isin(ranked.head(int(n * 0.25)).index), "enroll_top_quartile"),
        (df.index.isin(ranked.head(int(n * 0.50)).index), "enroll_top_half"),
        (df["Risk_Score"] >= base_rate, "enroll_above_baseline_risk"),
    ]
    rows = [evaluate_strategy(df, pd.Series(m, index=df.index), name) for m, name in strategies]

    best = max(rows, key=lambda r: r["net_value"])

    # Sensitivity grid: net value of the best and the recommended strategies.
    grid = []
    for eff in SENS_EFFICACY:
        for cost in SENS_COST:
            opts = [evaluate_strategy(df, pd.Series(m, index=df.index), name,
                                      program_cost=cost, efficacy=eff)
                    for m, name in strategies]
            b = max(opts, key=lambda r: r["net_value"])
            grid.append({
                "efficacy": eff,
                "program_cost": cost,
                "best_strategy": b["strategy"],
                "best_net_value": b["net_value"],
                "best_roi": b["roi"],
                "net_by_strategy": {o["strategy"]: o["net_value"] for o in opts},
            })

    result = {
        "generated_by": "scripts/program_simulator.py",
        "honesty": ("Synthetic seeded dataset (984 patients). Program cost and efficacy "
                    "are documented assumptions; episode saving ₹13,650 is measured from "
                    "this dataset. Decision method demonstration, not a hospital P&L."),
        "cohort": {
            "patients": n,
            "readmitted": int(df["Readmitted"].sum()),
            "base_readmission_rate": round(base_rate, 4),
            "strata": int(df["Stratum"].nunique()),
        },
        "cost_model": {
            "program_cost_per_patient": PROGRAM_COST,
            "episode_saving_per_prevented_readmission": EPISODE_SAVING,
            "efficacy": EFFICACY,
        },
        "strategies": rows,
        "recommended_strategy": best["strategy"],
        "recommended_net_value": best["net_value"],
        "sensitivity_grid": grid,
        "equity_slice": equity_slice(df, df.index.isin(ranked.head(int(n * 0.25)).index)),
    }

    JSON_PATH.parent.mkdir(exist_ok=True)
    JSON_PATH.write_text(json.dumps(result, indent=2))
    MD_PATH.write_text(render_md(result))
    return result


def render_md(r: dict) -> str:
    c = r["cost_model"]
    lines = [
        "# Program Simulator — is readmission prevention worth funding?",
        "",
        "> Generated by `scripts/program_simulator.py`. Targeting rule: Laplace-smoothed",
        "> historical readmission rate of each (Condition × Age-band) stratum — fully",
        "> transparent, no black box. Synthetic dataset; efficacy and program cost are",
        "> assumptions and are sensitivity-tested below.",
        "",
        "## Cost model",
        "",
        f"- Program cost: **₹{c['program_cost_per_patient']:,.0f}** per enrolled patient",
        f"- Avoided readmission episode: **₹{c['episode_saving_per_prevented_readmission']:,.0f}** (measured: avg readmitted cost)",
        f"- Efficacy: **{c['efficacy']:.0%}** relative risk reduction (assumption)",
        "",
        "## Strategies priced",
        "",
        "| Strategy | Enrolled | Expected readmits | Prevented | Cost ₹ | Savings ₹ | Net ₹ | ROI | Break-even efficacy |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in r["strategies"]:
        lines.append(
            f"| {s['strategy']} | {s['enrolled']} | {s['expected_readmits_among_enrolled']:.1f} | "
            f"{s['expected_prevented']:.1f} | ₹{s['program_cost']:,.0f} | ₹{s['expected_savings']:,.0f} | "
            f"₹{s['net_value']:,.0f} | {s['roi']:.2f} | {s['break_even_efficacy']:.1%} |")

    lines += [
        "",
        f"**Recommended strategy: `{r['recommended_strategy']}`** "
        f"(net **₹{r['recommended_net_value']:,.0f}** at base assumptions).",
        "",
        "## Sensitivity — when does the program stop paying?",
        "",
        "| Efficacy | Unit cost | Best strategy | Net ₹ |",
        "|---|---|---|---|",
    ]
    for g in r["sensitivity_grid"]:
        lines.append(f"| {g['efficacy']:.0%} | ₹{g['program_cost']:,.0f} | {g['best_strategy']} | ₹{g['best_net_value']:,.0f} |")

    eq = r["equity_slice"]
    lines += [
        "",
        "## Equity audit of the targeting rule (top-quartile program)",
        "",
        f"- Gender mix of enrollees: {eq['enrolled_gender_share_pct']} vs population {eq['population_gender_share_pct']}",
        f"- Mean age enrollees {eq['enrolled_mean_age']} vs population {eq['population_mean_age']}",
        "- **Why this matters**: a targeting rule that concentrates on one group is a",
        "  policy choice, not just maths. The numbers are printed so the trade-off is",
        "  explicit (see also the fairness trade-off track).",
        "",
        "## How to defend this in an interview",
        "",
        "1. **The targeting rule is auditable** — one sentence per patient, no model API.",
        "2. **Break-even efficacy is the CFO's number**: below it, don't fund.",
        "3. **Sensitivity shows the phase boundary** — the program flips from asset to",
        "   liability at known efficacy/cost combinations.",
        "4. **Equity is measured, not asserted** — enrollee mix is printed alongside value.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    out = run()
    print(f"Recommended: {out['recommended_strategy']} | net ₹{out['recommended_net_value']:,.0f} | "
          f"break-even efficacy shown per strategy")
    print(f"Report: {MD_PATH}")
