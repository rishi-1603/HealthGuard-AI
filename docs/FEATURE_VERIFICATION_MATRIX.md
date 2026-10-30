# Feature verification matrix

2026-10-30. PASS applies to the stated workflow, not every combination of inputs. Fresh production screenshots are genuine browser captures.

| Feature | Check | Status / boundary |
|---|---|---|
| Five tabs | Overview, Clinical Analytics, Root-Cause Drill, Patient Intelligence, AI Assistant | PASS in browser |
| Condition filter | Diabetes cohort=65, matches independent CSV count | PASS in browser |
| Patient export | Downloaded 65-row CSV; every Condition=Diabetes | PASS in browser |
| Grounded question | Diabetes readmission answer=1.5% | PASS in browser |
| Empty cohort | Male + Childbirth, no displayed exception | PASS in browser |
| Direct QA benchmark | 8 answers + 3 refusals + 3 traps | PASS within authored scope |

## Accessibility
axe scans use WCAG2A/AA and WCAG2.1AA tags. Measured patch verification has zero detected violations at 1440×900 and 390×844, with 1 incomplete rule groups still requiring manual review. A live post-push scan is recorded in the delivery report.
Keyboard focus smoke checks are not a screen-reader walkthrough. Not all chart semantics, every hidden state or assistive-technology behavior is certified.

## Performance
Warm browser rendering was observed; fixed waits used for UI screenshots are not latency measurements. A local API test used 50 read-only requests at concurrency 5: 0 errors, median 54.295 ms, p95 103.5 ms in this sandbox. This does not establish Streamlit session capacity, production cold-start bounds or real-user service levels.

## Not tested exhaustively
Every filter permutation, provider outage/rate-limit scenario and arbitrary question; unrestricted LLM narration; sustained production stress and real screen-reader behavior.
