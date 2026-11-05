# Analyst workbench

The workbench demonstrates a reporting cycle for an operations analyst using the existing synthetic hospital dataset. It does not connect to a hospital, measure live performance or recommend treatment.

## 1. Check data

The workbench runs 12 project-specific checks on the full reference and selected cohort: required schema/cells, unique patient identifiers, finite numeric ranges, whole-number age and expected labels. Failures are displayed; values are not silently repaired. Contract failures block comparison or report generation rather than presenting a successful-looking result. Rule counts can overlap and should not be summed as distinct records.

## 2. Compare a selected cohort

Use the sidebar to select a condition, gender, outcome or age range. The comparison shows four metrics for the selected rows and the full supplied dataset, including population sizes and differences. The full reference includes the selection: it is not an independent control group. Rate changes are expressed in **percentage points**, not percent improvement.

Example: filtering to Diabetes selects 65 of 984 records. Its readmission rate is approximately 1.54% compared with 26.83% in the full reference. The difference is descriptive and not case-mix adjusted. It is not evidence of a causal effect or a validated 30-day outcome.

## 3. Run and inspect SQL

Four named questions live in [`sql/02_analyst_workbench.sql`](../sql/02_analyst_workbench.sql):

1. Recorded cost by condition.
2. Readmission flags by gender.
3. Recorded cost by readmission status.
4. Recorded outcomes by condition.

The expected result-column schema is checked before reconciliation; incomplete query output is rejected. SQL groups with fewer than 30 records are flagged as a heuristic, not a significance test.

The app loads **only the selected cohort** into an in-memory SQLite table and enables SQLite query-only mode. It does not accept free-text or model-generated SQL. Each query is independently reconstructed in pandas and reconciled before its output and CSV download are displayed. If execution or reconciliation fails, the app does not publish the result as verified.

## 4. Prepare a stakeholder snapshot

Choose a supported cost, readmission or outcome focus and build a Markdown report. The report includes scope/reference identifiers, selected and reference population sizes, observed cohort composition (not a reconstruction of filter settings), metric definitions, the actual SQL, checked results, limitations and next analytical questions. It is deterministic except for its generated UTC timestamp; no API key or generative model is needed.

Reports and query outputs are cleared when the scope or selected focus/question changes. The full reference cannot be substituted for the selected data; altered or unrelated selected records are rejected. Small cohorts are flagged for cautious interpretation.

## 5. Create a decision record

The **Decision** step uses the validated selected cohort to model administrative review hours and costs under explicit assumptions. It reconciles selected cost-by-condition SQL against pandas, exports a JSON proposal and optionally includes a user-entered unverified follow-up. It does not select patients, calculate clinical benefit or persist a case history. See [BUSINESS_VALUE_DECISION_ENGINE.md](BUSINESS_VALUE_DECISION_ENGINE.md).

## Assistant and model boundaries

The existing AI Assistant supports bounded computed Q&A and optional Gemini selection of existing aggregate evidence cards; see [ASSISTANT_GUIDE.md](ASSISTANT_GUIDE.md). A provider connection or a benchmark score is not proof of clinical validity. Individual model scores and SHAP are synthetic demonstrations; their costs, readmission flags and outcomes are not real patient-care evidence.

## Reproduce and test

```bash
python -m pip install -r requirements.txt
python -m pytest tests/test_analyst_workbench.py tests/test_workbench_ui.py -q
streamlit run app/dashboard/Home.py
```

For a reproducible sample snapshot: `python scripts/export_analyst_example.py`. The sample uses the committed synthetic data, selects Diabetes and writes aggregate results and the executed SQL to `reports/analyst_workbench_example.md`. It does not contain individual patient identifiers.

## Known limits

No 30-day readmission window, observed admission timeline, causal treatment effect, real hospital feed or productivity savings are established. The selected/full comparison is descriptive and unadjusted. Automated checks cover authored cases, not every possible production condition. For real data, governance, a clinical data model, independent evaluation, accessibility review, security and production-performance checks would be required.
