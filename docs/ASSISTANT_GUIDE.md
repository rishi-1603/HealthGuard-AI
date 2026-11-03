# Analyst assistant: behavior and verification

## What it does

The AI Assistant tab supports bounded analytical questions over the **current dashboard cohort**. It can report counts, readmission/recovery rates, average or total recorded cost, average stay, satisfaction and age. It supports named conditions, gender and simple age ranges, with comparisons by condition, gender, age band, outcome or readmission status.

Examples:

- How many patients were readmitted?
- What is the total cost for male patients with diabetes?
- Compare average cost by readmission.
- Compare readmission rate by gender.
- What is the average cost for patients older than 60?

The input language is deliberately bounded. Unknown filters, ambiguous multi-metric requests, missing conditions, unavailable time windows and clinical requests are refused rather than silently reinterpreted. The service cannot expand a filtered DataFrame back to the full patient population.

## Numerical answer path

```text
Question + filtered cohort
  -> bounded question plan
  -> filter/column validation
  -> pandas computation
  -> answer + scope + formula + source columns + evidence table
```

`assistant_service.py` does not call a model or execute generated SQL/code. `simple_qa.answer()` remains a compatibility entry point. Missing or invalid metric values are excluded with denominator disclosure; an empty cohort is not reported as a zero rate. Absent cost-comparison groups are not assigned zero cost.

The assistant is isolated in a Streamlit fragment so a question does not need to rebuild unrelated charts. Conversation and brief state are keyed to a content-based cohort fingerprint and cleared when the cohort changes. A maximum of six recent question results is retained per session, with the last three displayed.

## What Gemini contributes

The optional provider receives a small catalog of already computed aggregate fact cards and a supported focus. It may return only JSON containing three to five unique allowed card IDs. The app renders the corresponding **backend-computed text**, not provider-authored clinical or numerical prose. Extra fields, unknown IDs, duplicate selections, invalid JSON and empty responses are rejected.

Unsupported questions are **not automatically forwarded** to the provider. There is no arbitrary SQL, tool execution, external browsing, diagnosis or treatment recommendation in this interface.

No raw patient rows, patient identifiers or patient codes are sent. Cohorts smaller than five records remain local. These controls are not a claim of anonymization, HIPAA compliance or suitability for real clinical data.

## Configuration and availability

- Set `GOOGLE_API_KEY` through deployment secrets or the environment. Never paste a credential into the app or commit it.
- Optional `GEMINI_MODEL` selects a text model returned by this account's model catalog. Otherwise the adapter prefers an available stable lightweight Flash text model for this small selection task, with one bounded alternative from a distinct model family.
- A configured key is not a verified connection. **Check Gemini connection** performs a small generation request with no patient data.
- Requests have bounded timeouts/retries. In automatic mode, a transient/model-availability error may try one alternative catalog model. Authentication/quota errors do not trigger repeated requests.
- A small process-local budget allows four optional provider flows per minute. It reduces accidental quota use but is not distributed rate limiting or authentication. Local analytical questions are not subject to it.
- User messages contain safe status descriptions, never raw SDK exception bodies. Provider failures leave the computed assistant and evidence available.
- Streamlit and google-genai minimum versions reflect the native fragment/form and bounded-request adapter tested for this release.

## Evaluation

Run:

```bash
python scripts/qa_eval.py
python scripts/assistant_reliability_eval.py
python -m pytest -q
```

The original benchmark remains 8/8 answerable, 3/3 unsupported refusals and 3/3 false-premise cases. The new benchmark independently checks 14 numerical/scope cases, 12 refusals and one grouped comparison. Tests also cover provider JSON contracts, transient failover, quota/authentication failures, redaction, small-cohort handling and real Streamlit form/scope workflows.

CI does not use an actual provider credential. Live provider availability, selected model and exact release commit are separate deployment evidence in the delivery report; mocked provider tests do not establish provider uptime.

## Limits

These are authored cases, not universal natural-language understanding. The primary dataset is synthetic and has no validated 30-day admissions timeline. The predictive risk model and SHAP views are demonstrations, not clinical validation. Neither a successful connection check nor a selected brief establishes patient benefit, causality or production-scale reliability.
