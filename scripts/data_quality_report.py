"""
data_quality_report.py — formal data quality assessment for the hospital dataset
================================================================================
Runs the full audit (same checks as tests/test_hospital_data_quality.py, plus
context stats) and writes a documented report: every check, records affected,
percentage, severity, treatment, and reason. Checks that PASS are reported too —
a data-quality report proves the audit happened, not just that issues exist.

Run:  python scripts/data_quality_report.py
Writes: reports/data_quality_report.md
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from app.dashboard.utils import hospital_data as data

REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

VALID_GENDERS = {"Female", "Male"}
VALID_OUTCOMES = {"Recovered", "Stable", "Deceased"}
VALID_READMIT = {"Yes", "No"}


def run_audit(df: pd.DataFrame) -> list[dict]:
    n = len(df)
    if not n:
        raise ValueError("Cannot audit an empty dataset.")
    rows = []

    def check(name, issue, affected, severity, treatment, reason):
        rows.append({
            "check": name, "issue": issue, "affected": int(affected),
            "pct": round(affected / n * 100, 2), "severity": severity,
            "treatment": treatment if severity in ("Pass", "Warning") else "Investigate before use", "reason": reason,
        })

    # completeness
    nulls = int(df.isna().any(axis=1).sum())
    check("Completeness", "Records with null values in any column", nulls,
          "Pass" if nulls == 0 else "High", "None required",
          "Each affected record is counted once, even if multiple fields are null")

    # uniqueness
    dupes = int(df["Patient_ID"].duplicated().sum())
    check("Uniqueness", "Duplicate Patient_ID", dupes,
          "Pass" if dupes == 0 else "Critical", "None required",
          "Patient_ID is the primary key; duplicates would double-count KPIs")

    # validity — ranges
    bad_age = int((~df["Age"].between(18, 90)).sum())
    check("Validity — Age", "Age outside project audit band 18–90", bad_age,
          "Pass" if bad_age == 0 else "High", "None required",
          "Implausible ages would distort demographic analysis")

    bad_cost = int((df["Cost"] <= 0).sum())
    check("Validity — Cost", "Non-positive cost", bad_cost,
          "Pass" if bad_cost == 0 else "High", "None required",
          "This audit requires positive recorded cost")

    bad_los = int((df["Length_of_Stay"] < 1).sum())
    check("Validity — Length_of_Stay", "Stay below 1 day", bad_los,
          "Pass" if bad_los == 0 else "Medium", "None required",
          "LOS is a KPI and a model feature")

    bad_sat = int((~df["Satisfaction"].between(1, 5)).sum())
    check("Validity — Satisfaction", "Score outside 1–5", bad_sat,
          "Pass" if bad_sat == 0 else "Medium", "None required",
          "Synthetic score scale bounds")

    # validity — categories
    bad_gender = int((~df["Gender"].isin(VALID_GENDERS)).sum())
    check("Validity — Gender", "Unexpected gender category", bad_gender,
          "Pass" if bad_gender == 0 else "High", "None required",
          "Free-text risk categories corrupt groupings")

    bad_outcome = int((~df["Outcome"].isin(VALID_OUTCOMES)).sum())
    check("Validity — Outcome", "Unexpected outcome category", bad_outcome,
          "Pass" if bad_outcome == 0 else "High", "None required",
          "Outcome drives the recovery-rate KPI")

    bad_readmit = int((~df["Readmission"].isin(VALID_READMIT)).sum())
    check("Validity — Readmission", "Unexpected readmission value", bad_readmit,
          "Pass" if bad_readmit == 0 else "Critical", "None required",
          "Readmission is the model target")

    # consistency — condition/procedure mapping
    counts = df.groupby("Condition")["Procedure"].nunique()
    multi = int(df["Condition"].isin(counts[counts > 1].index).sum())
    check("Consistency", "Records in conditions mapped to >1 procedure", multi,
          "Pass" if multi == 0 else "Medium", "None required",
          "1:1 mapping is documented in the data dictionary; SHAP attribution assumes it")

    # stability — base rate band (guards silent dataset drift)
    rate = (df["Readmission"] == "Yes").mean()
    sev = "Pass" if 0.20 < rate < 0.35 else "Warning"
    check("Stability", f"Readmission base rate {rate:.1%} outside expected 20–35% band"
          if sev != "Pass" else "Readmission base rate within expected band", 0 if sev == "Pass" else n,
          sev, "None — informational",
          "The 26.8% base rate is the documented headline; drift means the dataset changed")

    # Descriptive characteristics are calculated for the supplied scope, not hard-coded.
    condition_rates = df.groupby("Condition")["Readmission"].apply(lambda x: x.eq("Yes").mean())
    extreme = int(((condition_rates > .95) | (condition_rates < .05)).sum())
    group_rates = df.groupby("Gender")["Readmission"].apply(lambda x: x.eq("Yes").mean())
    gender_text = ", ".join(f"{group}: {value:.1%}" for group, value in group_rates.items()) or "unavailable"
    rows.append({
        "check": "Observed characteristic", "issue":
            f"Readmission rates below 5% or above 95% in {extreme}/{len(condition_rates)} observed conditions",
        "affected": n, "pct": 100.0, "severity": "Observed context",
        "treatment": "Descriptive context — not cleaned",
        "reason": "Scope-wide context; see reports/model_honesty.md for the full-data analysis",
    })
    rows.append({
        "check": "Observed characteristic", "issue": f"Readmission rates by recorded gender: {gender_text}",
        "affected": n, "pct": 100.0, "severity": "Observed context",
        "treatment": "Descriptive context — not cleaned",
        "reason": "Scope-wide context; see reports/fairness_check.md for the full-data analysis",
    })
    return rows


def main() -> None:
    df = pd.read_csv(data.DATA_PATH)
    rows = run_audit(df)

    lines = [
        "# Data Quality Report",
        f"### data/hospital/hospital_data.csv · {len(df):,} rows × {len(df.columns)} columns · synthetic",
        "",
        "> Generated by `scripts/data_quality_report.py` on every run.",
        "> This is a descriptive audit of the committed CSV. Related tests check",
        "> selected conditions; the workbench uses a separate project contract.",
        "",
        "## Summary",
        "",
        f"- Checks executed: **{sum(1 for r in rows if r['severity'] not in ('Observed context',))}**",
        f"- Failures: **{sum(1 for r in rows if r['severity'] in ('Medium', 'High', 'Critical'))}**",
        f"- Warnings: **{sum(1 for r in rows if r['severity'] == 'Warning')}**",
        f"- Observed characteristics: **{sum(1 for r in rows if r['severity'] == 'Observed context')}**",
        "",
        "## Full audit table",
        "",
        "Percentages use the number of source records as denominator; rules can overlap. Scope-wide observed context is not a defect count.",
        "",
        "| Check | Issue | Records | % | Severity | Treatment | Reason |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['check']} | {r['issue']} | {r['affected']:,} | {r['pct']:.1f}% | "
            f"{r['severity']} | {r['treatment']} | {r['reason']} |")
    lines += [
        "",
        "## Reading this report",
        "",
        "1. Review the summary and table above for the actual results of this run.",
        "2. The observed-context rows describe the entire supplied scope, not defective records.",
        "   Relationships in synthetic data do not establish clinical causation.",
        "3. The audit does not modify, impute or remove source records; checks are",
        "   not a certification of clinical validity or suitability for real data.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "python scripts/data_quality_report.py    # regenerates this report",
        "pytest tests/test_data_quality_report.py -v",
        "```",
    ]
    (REPORTS / "data_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    fails = sum(1 for r in rows if r["severity"] in ("Medium", "High", "Critical"))
    print(f"Checks run: {len(rows) - 2} | Failures: {fails} | Warnings: "
          f"{sum(1 for r in rows if r['severity'] == 'Warning')}")
    print(f"Report written: {REPORTS / 'data_quality_report.md'}")


if __name__ == "__main__":
    main()
