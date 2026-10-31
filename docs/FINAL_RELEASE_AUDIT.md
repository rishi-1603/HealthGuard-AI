# Publication verification — HealthGuard AI — Hospital Outcomes Analytics

Audit date: 2026-10-30. This follow-up supersedes the earlier snapshot that treated PostgreSQL, fresh screenshots and accessibility tooling as wholly unperformed.

## What was executed

- Fresh-source branch with recoverable commits; no unrelated changes overwritten.
- Independent raw-data calculations and actual PostgreSQL execution, with dialect boundaries documented.
- Actual anonymous browser rendering, tab/navigation actions, representative filters, downloads and deterministic assistant workflows.
- Fresh screenshots stored in `docs/screenshots/publication_*.png` and referenced by the README.
- axe-core WCAG 2 A/AA and 2.1 AA checks at desktop/mobile, with measured defects repaired. Automated scans do not certify screen-reader usability.
- Direct deterministic AI benchmark execution, selected static checks and full regression: **133 tests**.
- Reviewed integration of the related publication-audit PR. The unrelated E-Commerce revenue PR remains outside this release.

## Evidence by area

| Area | Result and boundary |
|---|---|
| Structure/documentation | PASS for corrected links, fresh screenshot references and this separated audit set |
| Metrics/data quality | PASS for independently recomputed figures in [data validation](DATA_AND_METRIC_VALIDATION.md); not every future metric |
| SQL | PASS: native SQLite checks; original SELECTs also executed on an explicitly ported PostgreSQL schema |
| Code/static checks | PASS for Ruff E9/F63/F7/F82/F401/F541/F841; not an exhaustive proof of correctness |
| Regression | 133 tests pass; tests not weakened or skipped |
| Functionality | Representative workflows recorded in [feature matrix](FEATURE_VERIFICATION_MATRIX.md); combinatorial coverage remains partial |
| Accessibility | Automated tested scope repaired; incomplete axe checks and manual assistive-technology review remain PARTIAL |
| Security | [Security scope](SECURITY_AUDIT.md); no blanket security certification |
| Performance | Bounded local API concurrency and warm browser checks, not production capacity/stress certification |
| CI/release | Exact published commit and its Actions result must be checked at [GitHub Actions](https://github.com/rishi-1603/HealthGuard-AI/actions) |
| Deployment identity | Changed behavior checked separately; no whole-commit Streamlit attestation without platform build metadata |

## Documents

[Issues](ISSUE_REGISTER.md) · [Data/SQL/statistics](DATA_AND_METRIC_VALIDATION.md) · [Features](FEATURE_VERIFICATION_MATRIX.md) · [Security](SECURITY_AUDIT.md) · [Release checklist](RELEASE_CHECKLIST.md)

## Verdict

**READY WITH DISCLOSED LIMITATIONS for the checked portfolio-demonstration scope**, contingent on the final pushed commit passing CI. Not a claim of clinical validity, real fraud detection, realized savings, exhaustive accessibility, or production-scale reliability.

## Recruiter notes

### 15-second summary
Synthetic hospital-outcomes case study using SQL reconciliation, cost/readmission comparisons, model-honesty checks and scenario-based intervention analysis. Not clinical decision support.

### One-minute technical overview
Synthetic hospital-outcomes case study using SQL reconciliation, cost/readmission comparisons, model-honesty checks and scenario-based intervention analysis. Not clinical decision support. The workflow defines entities and denominators, validates selected calculations independently, and presents findings with reproducible Python/SQL evidence. Statistical results are framed as descriptive or scenario-based where causal evidence is absent. Review the limitations before interpreting any model, risk score or financial estimate. Tests support reproducibility but do not prove production performance.

### Three analytical achievements
- Executed SQL/pandas reconciliation: 15/15 checks over 984 synthetic records.
- 264 readmitted records account for 43.8% of recorded cost; +112.3% unadjusted cost association, not causal avoided cost.
- Fairness trade-offs, grounded-QA refusals and external-data transfer limits are explicitly documented.

### Three technical challenges
- Keeping serialized artifacts and dependency runtime compatible.
- Separating illustrative labels from real readmission-window evidence.
- Avoiding causal savings claims from cost associations and in-sample risk targeting.

### Five interview questions
- What does one patient row represent?
- Is there a validated 30-day readmission window?
- Why is high AUC not proof of clinical validity?
- What assumptions determine intervention economics?
- Can differing base rates alone prove equalized odds impossible?

## Extended accessibility follow-up — 2026-10-31

All main pages/tabs were keyboard-activated and scanned after animations settled. The extended scan found additional contrast defects beyond the earlier default-page scan. E-Commerce retention heatmap text now uses contrast-based black/white selection on solid computed backgrounds; HealthGuard native theme settings now match the existing dark CSS so widget labels remain readable. This expands automated coverage but does not certify real screen-reader use or every possible UI state.

## Language and claim-scope review — 2026-10-31

Removed an uncited universal clinical-AUC range from active UI, registry commentary and reports. Replaced promotional conclusions with endpoint-specific limitations and conditional scenario interpretation. The corresponding regression now guards against reintroducing that uncited claim while retaining all numerical assertions. Full suite: 133 tests.

Numerical findings were not increased or relabelled as real-world outcomes. Synthetic-data, AI-use, evaluation-scope and deployment limitations remain explicit.
