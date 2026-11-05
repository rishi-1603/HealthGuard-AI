# Business value & decision record — Hospital operations

## Question and scope

What administrative effort might be required to review the selected synthetic cohort's records and definitions? This is a data-quality/operations planning example, not clinical advice, patient prioritization or an intervention recommendation.

In **Analyst Workbench → Decision**, the current cohort and full reference must pass the existing 12-rule contract and subset-integrity check. The selected cohort's cost-by-condition SQL is executed over the selected rows and independently reconciled in pandas before a record is built. That SQL check does not validate an assumed scenario or establish clinical truth. The full reference includes the selection and is not an independent control group. The dataset has no validated admission timeline or 30-day readmission outcome.

## Calculations

Evidence includes selected count, full-reference count, selected/reference recorded readmission-flag rates, mean recorded cost and mean length of stay. Values are descriptive; no causal claim follows.

The user specifies review capacity, minutes per record and an administrative hourly cost. The number planned is capped at the selected-cohort count. Low/base/high cases use 0.5×/1×/1.5× the assumed minutes per record:

```
planned review hours = planned records × assumed minutes per record / 60
modeled administrative cost = planned review hours × assumed hourly cost
```

The record contains **costs only**, not preventable savings, patient benefits or proof that a program improves outcomes. It does not choose individuals for review. The input values are scenarios, not measured staff times or budgets.

## Decision record

A user can enter a proposed/approved/deferred status, administrative action, follow-up KPI, validation plan and optional user-entered outcome note. The versioned JSON export separates source, scope (including effective sidebar filter context), evidence, assumptions, scenarios, decision and `observed_outcome`. The context is recorded from UI selections, not an independent reconstruction of how the data was filtered. The latter is null unless explicitly supplied, and then is labeled unverified. No server persistence, historical case management, import, causal attribution or verified follow-up exists. Changing dashboard scope clears the in-session snapshot; the form must be rebuilt after changing assumptions. Do not enter real patient data in notes.

No LLM calculates the record. The separate AI Assistant has its own bounded question contract and authored benchmark; this scenario is not a clinical model or an unrestricted AI answer.

## Verify

```
python -m pytest tests/test_business_decision_engine.py tests/test_workbench_ui.py -q
```

Tests cover cohort filtering/integrity, scenario arithmetic, invalid assumptions and Streamlit state changes. These are authored checks, not a certification for healthcare use.
