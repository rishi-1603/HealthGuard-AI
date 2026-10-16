# SECURITY & DEPENDENCY AUDIT — HealthGuard
### Audit date: 2026-10-17

## Dependencies (requirements.txt — intentionally lean)
streamlit>=1.35 · pandas>=2 · numpy>=1.24 · scikit-learn>=1.3 · joblib>=1.3 ·
plotly>=5.20 · pytest>=8 · shap>=0.44 · google-genai>=1.0
- Lean set for Streamlit Cloud; matplotlib deliberately EXCLUDED (optional
  figures). google-api-key comes from the platform's secrets UI, never committed.

## Secrets
- Token-pattern scan of all tracked files: **CLEAN** (2026-10-17).
- Q&A service credentials: environment/Streamlit secrets only.
- Maintainer GitHub PAT: env var only; rotation scheduled; never in repo.

## Supply chain / CI
GitHub-hosted runners; official actions only. Dockerfile for local parity.

## Data ethics
Fully synthetic patients; the README and model card state this before any metric.
The product refuses clinical claims and ungroundable questions by design.

## Residual risks
Broad version bounds can drift (CI catches breakage per push); real Google API
usage must stay inside free quotas; account security is the owner's job.
