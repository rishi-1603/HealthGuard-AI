# Release checklist

Audit date: 2026-10-30. See the external delivery report for final commit IDs and exact-commit CI results.

- [x] Existing work preserved on recoverable branches.
- [x] Related audit PR changes reviewed and integrated; unrelated PR left alone.
- [x] Independent raw-data recomputation and SQL execution documented.
- [x] Direct deterministic benchmarks executed.
- [x] Full regression: 133 tests passed.
- [x] Selected lint checks pass without deleting analytical assertions.
- [x] Measured accessibility defects repaired; screenshots refreshed.
- [x] README source/image paths checked; descriptions no longer contain drifting test counts.
- [ ] Final normal push, exact remote commit, CI and live release markers confirmed in the delivery report.
- [ ] Manual screen-reader/assistive-technology review.
- [ ] External LLM-provider adversarial/outage tests with authorized provider credentials.
- [ ] Production-scale sustained load/cold-start service-level validation.
- [ ] Whole-commit Streamlit deployment attestation where platform metadata/access is unavailable.

A checkbox is not evidence by itself. The data, feature, issue and security documents define the checked scope. Do not describe the release as literally perfect or completely tested.
