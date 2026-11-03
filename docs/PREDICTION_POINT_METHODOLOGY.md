# Prediction point and feature boundaries

## What the current project establishes

The dashboard dataset contains 984 **synthetic patient records**, one row per patient. It has a Yes/No readmission flag, but **no validated admission and discharge timeline or 30-day target**. The shipped model is an educational demonstration on this synthetic target; it is not a prospective clinical model and is not for diagnosis, triage or treatment. It is not evidence of patient benefit.

Several model inputs—procedure, cost and length of stay—may only become available during or after a stay. The dataset does not establish when they were known or billed. In particular, final cost is not necessarily available at discharge. A high score on this dataset cannot resolve timing leakage or establish prospective performance. See [the model card](../models/readmission/MODEL_CARD.md) and [model honesty audit](../reports/model_honesty.md).

## Hypothetical future study: a discharge-time prediction

The following is a **design checklist**, not a description of the committed dataset or proof that any feature is safe. A real 30-day study would first define the decision, cohort, encounter grain, index discharge, complete follow-up, outcome and observation window with clinical and data-governance experts.

| Candidate input | Hypothetical timing question | Required verification before use |
|---|---|---|
| Age, demographic data | Available at prediction? | Source timestamps, missingness, fairness implications and governance. |
| Condition or diagnosis | Known and recorded by prediction time? | Coding latency, corrections and relation to the outcome. |
| Procedure | Completed and recorded by prediction time? | Confirm timestamp and source; planned or post-discharge procedures are not eligible. |
| Length of stay | Fully observed at prediction time? | Confirm index discharge and timing; unavailable for an admission-time decision. |
| Recorded cost | Known at prediction time? | Billing may arrive or change after discharge; exclude if timing cannot be established. |
| Historical utilization or comorbidities | Strictly prior to prediction? | These fields are not in the dashboard CSV; validate source and look-back window. |
| 30-day readmission outcome | Observed after the index discharge? | It would be the target, never an input. Establish linkage, definition, censoring and follow-up first; current CSV does not provide this. |

Timing is necessary but not sufficient to prevent leakage. A future evaluation also needs representative governed data, independent temporal/external validation, subgroup and calibration analysis, clinical review, and an intervention study before any operational claim. No variable here is certified as leakage-free or clinically suitable.
