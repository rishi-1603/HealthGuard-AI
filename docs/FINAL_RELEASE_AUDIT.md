# Final publication audit — HealthGuard AI — Hospital Outcomes Analytics

Audit date: 2026-10-30. Scope: targeted publication repair, not a certification of literal perfection.
Baseline GitHub main: `ebde3ea2a0bf6331e1ceda973234c041f6631061`. Recoverable branch: `audit/publication-review`.

## Execution and ownership
No autonomous subagents were available. One assistant performed sequential data/SQL, code, QA, security, browser and documentation workstreams. Tests and tool checks are evidence; there was no independent human or separately spawned QA agent.

## Changes and issue register
| Severity | File/screen | Evidence | Root cause | Repair | Verification |
|---|---|---|---|---|---|
| HIGH | requirements.txt; committed readmission artifacts | Loading scikit-learn 1.9.0 artifacts under 1.6.1 emits InconsistentVersionWarning. | Unbounded scikit-learn minimum permits a different serialization runtime. | Pin scikit-learn==1.9.0, the original artifact version. Preserve existing model bytes. | FIXED: 132 tests pass with no version warnings; vulnerability scan clean for resolved requirements. |
| MEDIUM | scripts/fairness_tradeoff.py; reports/fairness_tradeoff.*; README.md | Claims unequal base rates necessarily prevent simultaneous TPR/FPR parity. | An empirical threshold trade-off overstated as a general theorem. | Distinguish observed trade-off from impossibility results requiring additional conditions. Regenerate report with numbers unchanged. | FIXED: suite 132 passes; no numerical pins weakened. |
| MEDIUM | README.md | States no real clinical data anywhere, despite separate public UCI external reference file. | Primary synthetic dashboard scope confused with whole-repository scope. | Clarify primary synthetic data and separate public clinical reference track. | FIXED. |
| LOW | models/readmission/MODEL_CARD.md | Claims 100 trees and CI retrains shipped model on every push. | Stale model/CI documentation. | Document 200 trees and actual audit-only CI behavior. | FIXED against training source and workflow. |
| LOW | app/dashboard/Home.py | Rendered 98.46153846153847% and causal-sounding drives readmissions. | Unformatted rate and overstated descriptive wording. | Round to one decimal; say highest observed readmission rates. | FIXED; existing AppTest and full suite pass. |

## Data and metric verification
984 records; 264 readmitted (26.83%); readmitted cost share 43.8%; mean cost 13,650 vs 6,431 (+112.3%). SQL and pandas independently reconciled. No real clinical effectiveness claimed.

PASS for actual SQLite analytics layer: 15/15 reconciliation checks executed.

## Feature verification matrix
Production app woke successfully. Executive Overview, Clinical Analytics, Root-Cause Drill, Patient Intelligence and AI Assistant tabs clicked without displayed Streamlit exceptions. Four requested viewports captured. Local render tests pass; all patient selections, downloads and external AI-provider paths are not exhaustively verified.

- Production browser checks were separate from local tests.
- Initial Streamlit sleep screens were not counted as application success; apps were woken and actual embedded app frames inspected.
- Screenshot captures were genuine browser images, not generated mockups. Baseline production captures are retained in the external audit evidence pack, not represented as post-repair screenshots.
- No independent LLM provider test, exhaustive state-space check, accessibility-tool audit or production load test was completed.

## Source, structure and security checks
- 129 tracked files inventoried; 108 relevant text files pattern-scanned. This is not a claim of exhaustive semantic line-by-line review.
- Fatal syntax/undefined-name static check: `ruff check . --select E9,F63,F7,F82` passed. Broad style/type cleanup was not performed.
- README local link/image paths: no missing targets detected at baseline.
- Known GitHub token, Google-key and private-key signature scan over selected current text files and reachable historical text blobs: no matches. Heuristic only; screenshots/binary secrets and all possible credential formats are unverified.
- No tracked .env, credentials.json or secrets.toml found by the targeted filename check.
- pip-audit requirements resolution: no known vulnerabilities reported at scan time. This is not a guarantee of secure deployment or a replacement for a lockfile.
- The token supplied in chat is exposed and should be revoked/rotated. It must never enter repository content.

## Release scorecard
| Area | Status | Evidence / boundary |
|---|---|---|
| Repository structure | PARTIAL | Targeted evidence above; comprehensive requirement coverage not established. |
| Code quality | PARTIAL | Targeted evidence above; comprehensive requirement coverage not established. |
| Data cleaning | PARTIAL | Targeted evidence above; comprehensive requirement coverage not established. |
| Metric correctness | PARTIAL | Executed reconciliation/tests for covered metrics; not every displayed calculation independently re-derived. |
| SQL validation | PASS | PASS for actual SQLite analytics layer: 15/15 reconciliation checks executed. |
| Feature functionality | PARTIAL | Targeted evidence above; comprehensive requirement coverage not established. |
| UI/UX | PARTIAL | Four viewports captured; tab/navigation smoke checks only. |
| Accessibility | BLOCKED | No complete keyboard/screen-reader/contrast audit; viewport checks do not establish accessibility. |
| Security | PARTIAL | Requirements scan and selected secret signatures only. |
| Performance | PARTIAL | Targeted evidence above; comprehensive requirement coverage not established. |
| Automated tests | PASS | 132 passed; see external final test log. |
| Build and CI | PARTIAL | Local checks recorded; pushed-commit CI is verified separately in the delivery report. |
| README and documentation | PARTIAL | Targeted evidence above; comprehensive requirement coverage not established. |
| GitHub presentation | PARTIAL | Targeted evidence above; comprehensive requirement coverage not established. |
| Live deployment | PARTIAL | Baseline production rendered; repaired-commit deployment must be confirmed separately. |
| Recruiter readiness | PARTIAL | Targeted evidence above; comprehensive requirement coverage not established. |

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

## Release checklist
- [x] Fresh public clone; old workspaces left untouched.
- [x] Recoverable branch and scoped diff.
- [x] Targeted fixes tested; no test weakened or deleted.
- [x] Selected SQL/data, security and browser evidence recorded.
- [ ] Pushed commit CI and repaired deployment verified (see delivery report).
- [ ] Complete accessibility, filter/export/provider and performance coverage.

## Remaining verification
Verify pinned environment on deployed Streamlit app after rebuild. All provider/API behaviors, accessibility and load testing remain incomplete. Intervention targeting is a retrospective scenario, not an out-of-sample clinical effectiveness estimate.

## Verdict
**NOT READY for an unconditional all-features final-release claim.** Targeted source repairs pass their local acceptance tests. Publication as an analytics demonstration must retain the listed limitations; release completion depends on the pushed-commit CI and deployment follow-up.
