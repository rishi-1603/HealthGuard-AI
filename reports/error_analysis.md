# Error Analysis — Readmission Model
### The two errors it makes, and what they reveal

> Failure cases extracted from the shipped model's held-out test slice
> (197 patients, random_state=42) — the exact split the dashboard metrics use.

## 1. The confusion at 0.5 (test slice)

| | Predicted readmit | Predicted no-readmit |
|---|---|---|
| **Actually readmitted** | 53 | **1 (FN)** |
| **Actually not** | **1 (FP)** | 142 |

Two errors in 197 patients — and **both errors are the interesting part of this
project.**

## 2. The two failure cases

| Case | Patient | p | Age | Gender | Condition / Procedure | Cost | LOS | Why the model failed |
|---|---|---|---|---|---|---|---|---|
| **FN** | P2 | 0.009 | 60 | Male | Diabetes / Insulin Therapy | ₹2,000 | 3d | Diabetes readmits at **1.5%** in this data — the model learned the condition rate and missed the exception |
| **FP** | P7 | 0.861 | 55 | Female | Appendicitis / Appendectomy | ₹8,000 | 4d | Appendicitis readmits at **exactly 50%** — the model is guessing on a coin flip and lost |

## 3. The determinism map (why these are the ONLY kinds of errors possible)

| Condition | Readmit rate | n |
|---|---|---|
| Allergic Reaction, Childbirth, Fractured Leg, Respiratory Infection, Prostate Cancer, Osteoarthritis, Kidney Stones, Hypertension | **0.0%** | ~65 each |
| Diabetes | 1.5% | 65 |
| Fractured Arm, Appendicitis, Cancer, Stroke | **50.0%** | ~66 each |
| Heart Disease | 98.5% | 65 |
| Heart Attack | **100.0%** | 67 |

The generator makes condition nearly determine the label. The model is — to a
first approximation — a **condition lookup table**: its errors can only occur
where the generator itself is stochastic (the four 50% conditions) or where an
exception exists (the Diabetes readmission).

**This is the sharpest possible demonstration of the honesty audit's point:**
a model with 2 errors in 197 is not a near-perfect predictor; it is a mirror of
the data-generation process. On real patients, error analysis would find case-mix
effects, measurement issues, and care-pathway failures. Here it finds generator
structure.

## 4. What the SHAP layer adds

Per-patient SHAP on P2 and P7 (dashboard → Patient Intelligence) attributes
each score to `Condition_enc` dominating, with `Cost`/`Length_of_Stay` as the
secondary pathway (the audit shows demographics-only models reach AUC 0.985).
The explanation is faithful to the model — and the model is faithful to the
generator. That chain is what the project actually demonstrates.

## 5. What this analysis changes

1. **Presentation:** this report is the answer to *"your model has AUC 0.99 —
   what could possibly go wrong?"* The answer: nothing in-sample, everything
   out-of-distribution. A new condition, a changed procedure pathway, or real
   patient heterogeneity would break the lookup immediately.
2. **Subgroup work (calibration_and_decision_curve.md):** the 18-30 band has
   zero positives and the 31-45 band has two — the error analysis explains
   why: young patients fall almost entirely in the 0% conditions.
3. **Model card:** linked as the failure-case evidence.

## 6. Limitations

1. Synthetic data — these patients do not exist; the *structure* is the lesson.
2. One split analyzed (the shipped one); other seeds move which coin-flip cases
   err but not the pattern.
3. No temporal, treatment, or care-pathway features exist to make errors
   *interesting* — which is itself the limitation worth stating in interviews.
