# DEPLOYMENT VERIFICATION — HealthGuard
### Verified 2026-10-18

## Targets
| Component | Where | URL |
|---|---|---|
| Dashboard | Streamlit Community Cloud | https://healthguard-ai-cyl2viwrsdrrff7pig7u6c.streamlit.app/ |
| Container | Dockerfile | local run supported |
| Repository + CI | GitHub Actions | rishi-1603/HealthGuard-AI |

## Machine-verified (2026-10-18)
- HTTP check on the demo URL: **303 (app reachable, Streamlit redirect)**.
- CI latest run: **success** (calibration + temporal scripts -> pytest, 132 tests).

## Manual click-through checklist (owner)
1. Score a sample patient; open the SHAP view.
2. Ask the Q&A one grounded and one ungroundable question (expect refusal).
3. `python scripts/calibration_decision_curve.py && python -m pytest tests/`.

## Redeployment
Streamlit Cloud rebuilds on push (root requirements.txt). Set google API key via
Streamlit secrets if using Q&A; app remains usable without it (feature degrades).

## Rollback
Git revert on main. Model artifacts are versioned in-repo; the app never writes
to source data.
