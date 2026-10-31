# Hospital outcomes: descriptive findings and limits

The primary dashboard uses 984 synthetic patient records. It supports exploration of recorded costs, outcomes, readmission flags and subgroup differences. It is not a clinical risk assessment or a basis for treatment, triage or insurance decisions.

## Recorded cost and readmission

There are 264 records marked readmitted: 26.83% of the dataset. They hold 43.8% of recorded cost, with a mean of approximately ₹13,650 compared with ₹6,431 for other records.

The 112.3% difference is unadjusted and reflects the supplied synthetic data. It does not show that readmission caused the additional cost or that preventing an event would save that amount. The SQL/pandas reconciliation checks reproduce the headline comparisons independently.

## Model evaluation

The Random Forest's AUC is approximately 0.99, but the condition-only lookup baseline already reaches 0.929. Condition and procedure are closely linked in the generator, and the generated outcome is nearly deterministic for several conditions.

The useful result is the audit explaining this structure—not the headline AUC. No single AUC range establishes clinical validity. A real evaluation would need a defined endpoint, appropriate patient population, leakage checks, calibration and independent validation.

## Intervention scenario

Under assumed program costs, efficacy and event value, enrolling the top-risk quartile produces a modeled net value of about ₹298,298. Enrolling every record produces a modeled loss of ₹1,039,325.

These figures are retrospective scenario calculations. Stratum risk is estimated on the same dataset, and event value is a proxy based on recorded cost rather than a measured causal saving. The sensitivity grid includes settings where no enrollment would be preferable to any of the modeled strategies.

## Subgroups and questions

Synthetic readmission base rates differ substantially by gender. The report measures several error-rate gaps and shows how threshold choices affect recall and precision. An improvement in one fairness metric is not a general fairness conclusion.

The deterministic Q&A layer calculates a bounded set of aggregates and refuses unsupported questions. Optional provider-generated responses require separate review; the authored benchmark does not guarantee unrestricted narration.

## What would be required for operational use

A governed patient/encounter model, an observed admission timeline, a validated readmission window, case-mix information and a suitable independent evaluation are missing. The separate public UCI heart-disease analysis has a different endpoint and does not validate clinical readmission performance.

[SQL reconciliation](sql_analytics.md) · [Model audit](model_honesty.md) · [Program assumptions](program_simulator.md) · [Limitations](assumptions_and_limitations.md)
