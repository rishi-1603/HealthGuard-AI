# Security audit scope

2026-10-30. This is a bounded portfolio audit, not a penetration-test certificate.

- Requirements-based dependency scan and selected historical/current secret signatures were checked in the preceding audit. They do not guarantee absence of every secret or vulnerability.
- No credential is needed for the deterministic dashboard and benchmark paths. External AI-provider checks are blocked when provider credentials are unavailable.
- Credential exposure cannot be repaired by deleting a repository file: rotate/revoke the exposed credential at its issuer.
- Source/configuration and regression checks were rerun after the reviewed PR integration. Main-branch CI remains the release gate.

## Project-specific repairs

- Reviewed Streamlit configuration enables XSRF protection and removes the explicit CORS-disable override.
- Main patient data is synthetic; the separately labelled UCI reference dataset is public clinical research data. Do not add private patient records or identifiers.
- Saved-model loading uses the pinned artifact runtime. Never load untrusted pickle/joblib artifacts.
