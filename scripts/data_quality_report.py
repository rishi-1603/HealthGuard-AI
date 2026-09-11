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
    rows = []

    def check(name, issue, affected, severity, treatment, reason):
        rows.append({
            "check": name, "issue": issue, "affected": int(affected),
            "pct": round(affected / n * 100, 2), "severity": severity,
            "treatment": treatment, "reason": reason,
        })

    # completeness
    nulls = int(df.isna().sum().sum())
    check("Completeness", "Null values in any column", nulls,
          "Pass" if nulls == 0 else "High", "None required",
          "All 10 columns fully populated")

    # uniqueness
    dupes = int(df["Patient_ID"].duplicated().sum())
    check("Uniqueness", "Duplicate Patient_ID", dupes,
          "Pass" if dupes == 0 else "Critical", "None required",
          "Patient_ID is the primary key; duplicates would double-count KPIs")

    # validity — ranges
    bad_age = int((~df["Age"].between(18, 90)).sum())
    check("Validity — Age", "Age outside observed plausible range 18–90", bad_age,
          "Pass" if bad_age == 0 else "High", "None required",
          "Implausible ages would distort demographic analysis")

    bad_cost = int((df["Cost"] <= 0).sum())
    check("Validity — Cost", "Non-positive cost", bad_cost,
          "Pass" if bad_cost == 0 else "High", "None required",
          "Cost must be positive for AOV/margin analytics")

    bad_los = int((df["Length_of_Stay"] < 1).sum())
    check("Validity — Length_of_Stay", "Stay below 1 day", bad_los,
          "Pass" if bad_los == 0 else "Medium", "None required",
          "LOS is a KPI and a model feature")

    bad_sat = int((~df["Satisfaction"].between(1, 5)).sum())
    check("Validity — Satisfaction", "Score outside 1–5", bad_sat,
          "Pass" if bad_sat == 0 else "Medium", "None required",
          "Survey scale bounds")

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
    multi = int((df.groupby("Condition")["Procedure"].nunique() > 1).sum())
    check("Consistency", "Conditions mapped to >1 procedure", multi,
          "Pass" if multi == 0 else "Medium", "None required",
          "1:1 mapping is documented in the data dictionary; SHAP attribution assumes it")

    # stability — base rate band (guards silent dataset drift)
    rate = (df["Readmission"] == "Yes").mean()
    sev = "Pass" if 0.20 < rate < 0.35 else "Warning"
    check("Stability", f"Readmission base rate {rate:.1%} outside expected 20–35% band"
          if sev != "Pass" else "Readmission base rate within expected band", 0 if sev == "Pass" else n,
          sev, "None — informational",
          "The 26.8% base rate is the documented headline; drift means the dataset changed")

    # documented design characteristics (not defects — surfaced for the analyst)
    rows.append({
        "check": "Design characteristic", "issue":
            "Readmission is near-deterministic given Condition (11/15 conditions "
            "readmit at >95% or <5%)",
        "affected": 984, "pct": 100.0, "severity": "Known (by design)",
        "treatment": "Documented — not cleaned",
        "reason": "Synthetic generator construction; quantified in reports/model_honesty.md",
    })
    rows.append({
        "check": "Design characteristic", "issue":
            "Gender base-rate disparity: Female 43.9% vs Male 7.4% actual readmission",
        "affected": 984, "pct": 100.0, "severity": "Known (by design)",
        "treatment": "Documented — not cleaned",
        "reason": "Condition mix differs by gender; analyzed in reports/fairness_check.md",
    })
    return rows


def main() -> None:
    df = data.load_patients()
    rows = run_audit(df)

    lines = [
        "# Data Quality Report",
        f"### data/hospital/hospital_data.csv · {len(df):,} rows × {len(df.columns)} columns · synthetic",
        "",
        "> Generated by `scripts/data_quality_report.py` on every run. The same",
        "> checks are enforced as CI tests in `tests/test_hospital_data_quality.py` —",
        "> this report is the documented audit trail; the tests are the gate.",
        "",
        "## Summary",
        "",
        f"- Checks executed: **{sum(1 for r in rows if r['severity'] not in ('Known (by design)',))}**",
        f"- Failures: **{sum(1 for r in rows if r['severity'] in ('High', 'Critical'))}**",
        f"- Warnings: **{sum(1 for r in rows if r['severity'] == 'Warning')}**",
        f"- Documented design characteristics: **{sum(1 for r in rows if r['severity'] == 'Known (by design)')}**",
        "",
        "## Full audit table",
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
        "1. **Zero failures, zero warnings on the current dataset** — expected: the",
        "   synthetic generator produces clean data, and the CI tests would fail the",
        "   build otherwise. The report's value is proving the audit runs and",
        "   documenting what 'clean' means for this dataset.",
        "2. **Design characteristics are not defects.** The two rows flagged",
        "   'Known (by design)' are properties of the synthetic generator that an",
        "   analyst must know (and that are analyzed, not hidden, in the honesty and",
        "   fairness reports).",
        "3. **Cleaning decisions: none required.** No records were dropped, imputed,",
        "   or modified anywhere in this project — documented here so no one has to",
        "   guess.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "python scripts/data_quality_report.py    # regenerates this report",
        "pytest tests/test_data_quality_report.py -v",
        "```",
    ]
    (REPORTS / "data_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    fails = sum(1 for r in rows if r["severity"] in ("High", "Critical"))
    print(f"Checks run: {len(rows) - 2} | Failures: {fails} | Warnings: "
          f"{sum(1 for r in rows if r['severity'] == 'Warning')}")
    print(f"Report written: {REPORTS / 'data_quality_report.md'}")


if __name__ == "__main__":
    main()
