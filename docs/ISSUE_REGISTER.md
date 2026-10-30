# Issue register

2026-10-30 follow-up. All listed repairs require full regression; deployment checks are separate.

| Severity | Exact location | Evidence | Root cause | Repair | Verification |
|---|---|---|---|---|---|
| Medium | app/dashboard/Home.py | axe found toolbar contrast around 1.04:1. | Dark toolbar label inherited on dark header. | Set toolbar text to the existing light foreground. | Browser patch scan clears violation at desktop/mobile. |
| High | scripts/realdata_validation.py; reports/realdata_validation.*; tests/test_realdata_validation.py | Direct external-report regeneration disagreed with stale pins under sklearn 1.9.0; unconstrained minimax favored a low-recall policy. | Prior artifact generated with a different runtime; search lacked a utility constraint. | Record runtime and protocol; require at least 90% of baseline recall; pin independently reproduced results. | Independent implementation agrees: F=.25/M=.35, recall=.9209, worst gap=.0085. No metric edited just to improve appearance. |
| Medium | .streamlit/config.toml | Reviewed audit PR enables Streamlit XSRF protection. | XSRF had been explicitly disabled. | Merge reviewed protection setting and remove CORS-disable override. | TOML validated; AppTest/regression passes; recheck actual cloud startup. |
| Low | app/dashboard/Home.py | Single-condition view showed unrounded rates, +− LOS text and rounded small costs to 0.0L. | Formatting paths did not cover filtered cohorts. | One-decimal descriptive rate, signed difference formatting and exact recorded cost display. | Filtered-cohort tests and browser workflow checks. |
| Low | Python/test modules | 12 selected lint findings at baseline. | Unused imports/locals and unnecessary f prefixes. | Remove dead imports; strengthen the existing tier test to assert WATCH as well as HIGH/LOW. | Selected Ruff rules clean; full suite pass. |

## Remaining boundaries
- No real parallel subagent facility was available; sequential specialist workstreams were used.
- Optional external LLM providers require separate credentials and evaluation; deterministic tests are not unrestricted narration tests.
- No complete manual screen-reader/contrast review or production stress certification.
- Revoke any credential exposed in chat or elsewhere. Repository cleanup cannot revoke that credential.
