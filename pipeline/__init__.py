"""HealthGuard AI — Data Engineering Pipeline (Medallion Architecture).

Layers:
  Bronze  — raw ingestion: CSV → warehouse, schema-validated, immutable.
  Silver  — cleaned, normalised, derived columns, quality-gate enforced.
  Gold    — aggregated analytics mart tables ready for BI consumption.
"""

__version__ = "1.0.0"
