"""Warehouse connection and DDL management.

Provides a single connection factory and applies all CREATE TABLE / VIEW
statements for Bronze, Silver, and Gold layers.  Using SQLite here — the
same DDL works against PostgreSQL by swapping the connection string.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Generator
from contextlib import contextmanager

from pipeline.config import PipelineConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DDL — Bronze layer (raw, immutable copy of source)
# ---------------------------------------------------------------------------
_BRONZE_DDL = """
CREATE TABLE IF NOT EXISTS bronze_encounters (
    _row_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    _ingested_at     TEXT NOT NULL,
    _source_file     TEXT NOT NULL,
    _source_hash     TEXT NOT NULL,
    Patient_ID       INTEGER,
    Age              INTEGER,
    Gender           TEXT,
    Condition        TEXT,
    Procedure        TEXT,
    Cost             INTEGER,
    Length_of_Stay   INTEGER,
    Readmission      TEXT,
    Outcome          TEXT,
    Satisfaction     INTEGER
);

CREATE INDEX IF NOT EXISTS idx_bronze_patient_id ON bronze_encounters(Patient_ID);
CREATE INDEX IF NOT EXISTS idx_bronze_ingested   ON bronze_encounters(_ingested_at);
"""

# ---------------------------------------------------------------------------
# DDL — Silver layer (cleaned, validated, derived columns)
# ---------------------------------------------------------------------------
_SILVER_DDL = """
CREATE TABLE IF NOT EXISTS silver_encounters (
    patient_id          INTEGER PRIMARY KEY,
    age                 INTEGER NOT NULL CHECK(age BETWEEN 0 AND 120),
    age_band            TEXT    NOT NULL,
    gender              TEXT    NOT NULL,
    condition           TEXT    NOT NULL,
    procedure_name      TEXT    NOT NULL,
    cost                REAL    NOT NULL CHECK(cost >= 0),
    length_of_stay      INTEGER NOT NULL CHECK(length_of_stay >= 0),
    readmission         TEXT    NOT NULL CHECK(readmission IN ('Yes','No')),
    readmission_flag    INTEGER NOT NULL CHECK(readmission_flag IN (0,1)),
    outcome             TEXT    NOT NULL,
    satisfaction        INTEGER CHECK(satisfaction BETWEEN 1 AND 10),
    cost_per_day        REAL,
    _silver_loaded_at   TEXT NOT NULL,
    _dq_passed          INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_silver_condition ON silver_encounters(condition);
CREATE INDEX IF NOT EXISTS idx_silver_age_band  ON silver_encounters(age_band);
CREATE INDEX IF NOT EXISTS idx_silver_readmit   ON silver_encounters(readmission_flag);
CREATE INDEX IF NOT EXISTS idx_silver_gender    ON silver_encounters(gender);
"""

# ---------------------------------------------------------------------------
# DDL — Gold layer (pre-aggregated analytics marts)
# ---------------------------------------------------------------------------
_GOLD_DDL = """
CREATE TABLE IF NOT EXISTS gold_condition_mart (
    condition               TEXT PRIMARY KEY,
    total_patients          INTEGER NOT NULL,
    readmitted_count        INTEGER NOT NULL,
    readmission_rate_pct    REAL    NOT NULL,
    total_cost              REAL    NOT NULL,
    avg_cost                REAL    NOT NULL,
    avg_length_of_stay      REAL    NOT NULL,
    avg_satisfaction        REAL,
    _gold_loaded_at         TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS gold_age_band_mart (
    age_band                TEXT PRIMARY KEY,
    total_patients          INTEGER NOT NULL,
    readmitted_count        INTEGER NOT NULL,
    readmission_rate_pct    REAL    NOT NULL,
    avg_cost                REAL    NOT NULL,
    avg_length_of_stay      REAL    NOT NULL,
    _gold_loaded_at         TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS gold_gender_mart (
    gender                  TEXT PRIMARY KEY,
    total_patients          INTEGER NOT NULL,
    readmitted_count        INTEGER NOT NULL,
    readmission_rate_pct    REAL    NOT NULL,
    avg_cost                REAL    NOT NULL,
    avg_satisfaction        REAL,
    _gold_loaded_at         TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS gold_outcome_mart (
    outcome                 TEXT PRIMARY KEY,
    total_patients          INTEGER NOT NULL,
    share_pct               REAL    NOT NULL,
    avg_cost                REAL    NOT NULL,
    readmission_rate_pct    REAL    NOT NULL,
    _gold_loaded_at         TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS gold_daily_summary (
    summary_date            TEXT PRIMARY KEY,
    total_patients          INTEGER NOT NULL,
    total_cost              REAL    NOT NULL,
    readmitted_count        INTEGER NOT NULL,
    readmission_rate_pct    REAL    NOT NULL,
    avg_cost                REAL    NOT NULL,
    avg_length_of_stay      REAL    NOT NULL,
    avg_satisfaction        REAL,
    _gold_loaded_at         TEXT    NOT NULL
);
"""

# ---------------------------------------------------------------------------
# Pipeline audit log
# ---------------------------------------------------------------------------
_AUDIT_DDL = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id              TEXT PRIMARY KEY,
    stage               TEXT NOT NULL,
    status              TEXT NOT NULL CHECK(status IN ('running','success','failed')),
    rows_in             INTEGER,
    rows_out            INTEGER,
    rows_rejected       INTEGER,
    started_at          TEXT NOT NULL,
    finished_at         TEXT,
    error_message       TEXT,
    metadata_json       TEXT
);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Return a SQLite connection with WAL mode and foreign-key enforcement."""
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def managed_connection(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Context manager: yields a connection that auto-commits on success."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply_ddl(cfg: PipelineConfig) -> None:
    """Create all tables and indexes if they do not already exist."""
    with managed_connection(cfg.warehouse_db) as conn:
        conn.executescript(_BRONZE_DDL)
        conn.executescript(_SILVER_DDL)
        conn.executescript(_GOLD_DDL)
        conn.executescript(_AUDIT_DDL)
    logger.info("DDL applied to %s", cfg.warehouse_db)
