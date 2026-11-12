"""Bronze layer — raw ingestion.

Responsibilities:
  1. Read source CSV (never modify it).
  2. Compute SHA-256 of the file for idempotency / lineage.
  3. Validate schema: expected columns present, no extra columns.
  4. Load raw rows into bronze_encounters with metadata columns.

Design rule: Bronze stores EXACTLY what arrived — no type coercion,
no cleaning. All transformations happen in the Silver layer.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from pipeline.config import BRONZE_COLUMNS, PipelineConfig
from pipeline.warehouse import managed_connection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# File utilities
# ---------------------------------------------------------------------------

def compute_file_hash(path: Path) -> str:
    """Return hex SHA-256 digest of a file for lineage tracking."""
    sha = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65_536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def read_raw_csv(path: Path) -> pd.DataFrame:
    """Load CSV into a DataFrame.  Raises FileNotFoundError if absent."""
    if not path.exists():
        raise FileNotFoundError(f"Source CSV not found: {path}")
    df = pd.read_csv(path, dtype=str)   # keep everything as str at Bronze
    logger.info("Read %d rows from %s", len(df), path.name)
    return df


# ---------------------------------------------------------------------------
# Schema validation (Bronze gate)
# ---------------------------------------------------------------------------

def validate_schema(df: pd.DataFrame) -> list[str]:
    """Return a list of schema violation strings (empty = pass)."""
    issues: list[str] = []
    actual = set(df.columns.tolist())
    expected = set(BRONZE_COLUMNS)

    missing = expected - actual
    extra = actual - expected

    if missing:
        issues.append(f"Missing columns: {sorted(missing)}")
    if extra:
        issues.append(f"Unexpected columns: {sorted(extra)}")
    return issues


# ---------------------------------------------------------------------------
# Bronze loader
# ---------------------------------------------------------------------------

def load_bronze(cfg: PipelineConfig) -> dict[str, int | str]:
    """Ingest raw CSV into bronze_encounters.

    Returns a result dict with keys: rows_in, rows_loaded, source_hash.
    Raises ValueError on schema violation.
    """
    source_path = cfg.source_csv
    file_hash = compute_file_hash(source_path)
    ingested_at = datetime.now(timezone.utc).isoformat()

    df = read_raw_csv(source_path)
    rows_in = len(df)

    # --- Schema gate ---
    violations = validate_schema(df)
    if violations:
        raise ValueError(f"Bronze schema validation failed: {violations}")

    # --- Attach metadata columns (new immutable DataFrame) ---
    df = df.copy()
    df["_ingested_at"] = ingested_at
    df["_source_file"] = source_path.name
    df["_source_hash"] = file_hash

    # Rename to match DDL (Procedure → Procedure kept as-is, loaded verbatim)
    insert_cols = [
        "_ingested_at", "_source_file", "_source_hash",
        "Patient_ID", "Age", "Gender", "Condition", "Procedure",
        "Cost", "Length_of_Stay", "Readmission", "Outcome", "Satisfaction",
    ]

    with managed_connection(cfg.warehouse_db) as conn:
        # Idempotent: truncate then reload (Bronze is append-safe but we keep
        # one canonical snapshot per pipeline run for simplicity)
        conn.execute("DELETE FROM bronze_encounters")
        df[insert_cols].to_sql(
            "bronze_encounters",
            conn,
            if_exists="append",
            index=False,
            method="multi",
        )
        rows_loaded = conn.execute(
            "SELECT COUNT(*) FROM bronze_encounters"
        ).fetchone()[0]

    logger.info(
        "Bronze: loaded %d / %d rows | hash=%s",
        rows_loaded, rows_in, file_hash[:12],
    )
    return {"rows_in": rows_in, "rows_loaded": rows_loaded, "source_hash": file_hash}
