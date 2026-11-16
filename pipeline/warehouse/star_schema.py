"""Enterprise Star Schema & Dimensional Modeling (DE-006).

Defines ANSI DDL, surrogate keys, composite indices, and ETL loaders for:
  Dimensions:
    - dim_patient (SCD Type 2 tracking with effective_from/effective_to/is_current)
    - dim_condition
    - dim_facility
    - dim_date
  Facts:
    - fact_encounter
    - fact_observation
    - fact_pipeline_run
    - fact_data_quality
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from pipeline.config import PipelineConfig

logger = logging.getLogger(__name__)

DIMENSION_TABLES: list[str] = [
    "dim_patient",
    "dim_condition",
    "dim_facility",
    "dim_date",
]

FACT_TABLES: list[str] = [
    "fact_encounter",
    "fact_observation",
    "fact_pipeline_run",
    "fact_data_quality",
]

_STAR_SCHEMA_DDL = """
-- ---------------------------------------------------------------------------
-- DIMENSIONS
-- ---------------------------------------------------------------------------

-- Dimension: Patient with SCD Type 2 tracking
CREATE TABLE IF NOT EXISTS dim_patient (
    patient_sk          INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id          TEXT    NOT NULL,
    source_system       TEXT    NOT NULL,
    gender              TEXT,
    birth_date          TEXT,
    age_band            TEXT,
    region              TEXT,
    insurance           TEXT,
    effective_from      TEXT    NOT NULL,
    effective_to        TEXT,
    is_current          INTEGER NOT NULL DEFAULT 1 CHECK(is_current IN (0, 1)),
    row_hash            TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dim_patient_id_current ON dim_patient(patient_id, is_current);
CREATE INDEX IF NOT EXISTS idx_dim_patient_source     ON dim_patient(source_system);

-- Dimension: Clinical Condition / Diagnosis
CREATE TABLE IF NOT EXISTS dim_condition (
    condition_sk        INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_code      TEXT    NOT NULL UNIQUE,
    condition_text      TEXT    NOT NULL,
    condition_category  TEXT
);

CREATE INDEX IF NOT EXISTS idx_dim_condition_code ON dim_condition(condition_code);

-- Dimension: Healthcare Facility
CREATE TABLE IF NOT EXISTS dim_facility (
    facility_sk         INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_code       TEXT    NOT NULL UNIQUE,
    facility_name       TEXT    NOT NULL,
    facility_type       TEXT,
    region              TEXT
);

CREATE INDEX IF NOT EXISTS idx_dim_facility_code ON dim_facility(facility_code);

-- Dimension: Calendar Date
CREATE TABLE IF NOT EXISTS dim_date (
    date_sk             INTEGER PRIMARY KEY,
    full_date           TEXT    NOT NULL UNIQUE,
    year                INTEGER NOT NULL,
    quarter             INTEGER NOT NULL,
    month               INTEGER NOT NULL,
    day_of_week         INTEGER NOT NULL,
    is_weekend          INTEGER NOT NULL CHECK(is_weekend IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_dim_date_full_date ON dim_date(full_date);

-- ---------------------------------------------------------------------------
-- FACTS
-- ---------------------------------------------------------------------------

-- Fact: Clinical Encounters
CREATE TABLE IF NOT EXISTS fact_encounter (
    encounter_sk        INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_sk          INTEGER NOT NULL REFERENCES dim_patient(patient_sk),
    condition_sk        INTEGER NOT NULL REFERENCES dim_condition(condition_sk),
    facility_sk         INTEGER NOT NULL REFERENCES dim_facility(facility_sk),
    admit_date_sk       INTEGER NOT NULL REFERENCES dim_date(date_sk),
    discharge_date_sk   INTEGER REFERENCES dim_date(date_sk),
    cost                REAL    NOT NULL CHECK(cost >= 0),
    length_of_stay      INTEGER NOT NULL CHECK(length_of_stay >= 0),
    readmission_flag    INTEGER NOT NULL CHECK(readmission_flag IN (0, 1)),
    satisfaction        INTEGER CHECK(satisfaction BETWEEN 1 AND 10),
    outcome             TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fact_encounter_patient_sk   ON fact_encounter(patient_sk);
CREATE INDEX IF NOT EXISTS idx_fact_encounter_condition_sk ON fact_encounter(condition_sk);
CREATE INDEX IF NOT EXISTS idx_fact_encounter_facility_sk  ON fact_encounter(facility_sk);
CREATE INDEX IF NOT EXISTS idx_fact_encounter_admit_date   ON fact_encounter(admit_date_sk);

-- Fact: Patient Observations / Labs
CREATE TABLE IF NOT EXISTS fact_observation (
    observation_sk      INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_sk          INTEGER NOT NULL REFERENCES dim_patient(patient_sk),
    date_sk             INTEGER NOT NULL REFERENCES dim_date(date_sk),
    observation_name    TEXT    NOT NULL,
    value               REAL,
    unit                TEXT
);

CREATE INDEX IF NOT EXISTS idx_fact_obs_patient_sk ON fact_observation(patient_sk);
CREATE INDEX IF NOT EXISTS idx_fact_obs_date_sk    ON fact_observation(date_sk);

-- Fact: Pipeline Orchestration Audit Runs
CREATE TABLE IF NOT EXISTS fact_pipeline_run (
    run_sk              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              TEXT    NOT NULL,
    stage               TEXT    NOT NULL,
    status              TEXT    NOT NULL CHECK(status IN ('running', 'success', 'failed')),
    rows_in             INTEGER,
    rows_out            INTEGER,
    rows_rejected       INTEGER,
    started_at          TEXT    NOT NULL,
    finished_at         TEXT,
    date_sk             INTEGER NOT NULL REFERENCES dim_date(date_sk)
);

CREATE INDEX IF NOT EXISTS idx_fact_pipeline_run_date_sk ON fact_pipeline_run(date_sk);
CREATE INDEX IF NOT EXISTS idx_fact_pipeline_run_id      ON fact_pipeline_run(run_id);

-- Fact: Data Quality Rule Audits
CREATE TABLE IF NOT EXISTS fact_data_quality (
    dq_sk               INTEGER PRIMARY KEY AUTOINCREMENT,
    date_sk             INTEGER NOT NULL REFERENCES dim_date(date_sk),
    table_name          TEXT    NOT NULL,
    rule_name           TEXT    NOT NULL,
    records_checked     INTEGER NOT NULL,
    records_passed      INTEGER NOT NULL,
    records_failed      INTEGER NOT NULL,
    pass_rate           REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fact_dq_date_sk ON fact_data_quality(date_sk);
CREATE INDEX IF NOT EXISTS idx_fact_dq_table   ON fact_data_quality(table_name);
"""


def _get_connection(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def apply_star_schema_ddl(cfg: PipelineConfig) -> None:
    """Create all star schema dimensional tables and indexes."""
    conn = _get_connection(cfg.warehouse_db)
    try:
        conn.executescript(_STAR_SCHEMA_DDL)
        conn.commit()
    finally:
        conn.close()
    logger.info("Star schema DDL applied to %s", cfg.warehouse_db)


def _to_date_sk(val: Any) -> int:
    """Convert a date, datetime, or ISO string to integer YYYYMMDD surrogate key."""
    if isinstance(val, (date, datetime)):
        return int(val.strftime("%Y%m%d"))
    if isinstance(val, str):
        cleaned = val[:10].replace("-", "")
        return int(cleaned)
    if isinstance(val, int):
        return val
    raise ValueError(f"Cannot convert {val} of type {type(val)} to date_sk")


class DimensionLoader:
    """ETL loader for dimension tables with SCD Type 2 tracking."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    def load_dim_date(self, start_date: date, end_date: date) -> int:
        """Populate dim_date over a date range [start_date, end_date] idempotently."""
        conn = _get_connection(self.db_path)
        count = 0
        curr = start_date
        try:
            while curr <= end_date:
                date_sk = int(curr.strftime("%Y%m%d"))
                full_date = curr.isoformat()
                year = curr.year
                quarter = (curr.month - 1) // 3 + 1
                month = curr.month
                day_of_week = curr.weekday()
                is_weekend = 1 if curr.weekday() >= 5 else 0

                conn.execute(
                    """
                    INSERT OR REPLACE INTO dim_date
                    (date_sk, full_date, year, quarter, month, day_of_week, is_weekend)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (date_sk, full_date, year, quarter, month, day_of_week, is_weekend),
                )
                count += 1
                curr += timedelta(days=1)
            conn.commit()
            return count
        finally:
            conn.close()

    def upsert_dim_patient(
        self,
        patient_id: str,
        source_system: str,
        gender: str | None = None,
        birth_date: str | None = None,
        age_band: str | None = None,
        region: str | None = None,
        insurance: str | None = None,
        effective_date: str | None = None,
    ) -> int:
        """Upsert a patient into dim_patient applying SCD Type 2 logic.
        
        Returns the active patient_sk.
        """
        raw_hash_src = f"{gender}|{birth_date}|{age_band}|{region}|{insurance}"
        row_hash = hashlib.sha256(raw_hash_src.encode("utf-8")).hexdigest()[:16]
        now_iso = effective_date or datetime.now().date().isoformat()

        conn = _get_connection(self.db_path)
        try:
            cur = conn.execute(
                """
                SELECT patient_sk, row_hash
                FROM dim_patient
                WHERE patient_id = ? AND is_current = 1
                """,
                (str(patient_id),),
            )
            existing = cur.fetchone()

            if existing is not None:
                if existing["row_hash"] == row_hash:
                    return int(existing["patient_sk"])
                
                # SCD2 update: expire current version
                conn.execute(
                    """
                    UPDATE dim_patient
                    SET is_current = 0, effective_to = ?
                    WHERE patient_sk = ?
                    """,
                    (now_iso, existing["patient_sk"]),
                )

            # Insert new current record
            insert_cur = conn.execute(
                """
                INSERT INTO dim_patient (
                    patient_id, source_system, gender, birth_date, age_band,
                    region, insurance, effective_from, effective_to, is_current, row_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 1, ?)
                """,
                (
                    str(patient_id),
                    source_system,
                    gender,
                    birth_date,
                    age_band,
                    region,
                    insurance,
                    now_iso,
                    row_hash,
                ),
            )
            conn.commit()
            return int(insert_cur.lastrowid)
        finally:
            conn.close()

    def upsert_dim_condition(
        self,
        condition_code: str,
        condition_text: str,
        condition_category: str | None = None,
    ) -> int:
        """Upsert into dim_condition by condition_code. Returns condition_sk."""
        conn = _get_connection(self.db_path)
        try:
            cur = conn.execute(
                "SELECT condition_sk FROM dim_condition WHERE condition_code = ?",
                (condition_code,),
            )
            row = cur.fetchone()
            if row is not None:
                return int(row["condition_sk"])

            insert_cur = conn.execute(
                """
                INSERT INTO dim_condition (condition_code, condition_text, condition_category)
                VALUES (?, ?, ?)
                """,
                (condition_code, condition_text, condition_category),
            )
            conn.commit()
            return int(insert_cur.lastrowid)
        finally:
            conn.close()

    def upsert_dim_facility(
        self,
        facility_code: str,
        facility_name: str,
        facility_type: str | None = None,
        region: str | None = None,
    ) -> int:
        """Upsert into dim_facility by facility_code. Returns facility_sk."""
        conn = _get_connection(self.db_path)
        try:
            cur = conn.execute(
                "SELECT facility_sk FROM dim_facility WHERE facility_code = ?",
                (facility_code,),
            )
            row = cur.fetchone()
            if row is not None:
                return int(row["facility_sk"])

            insert_cur = conn.execute(
                """
                INSERT INTO dim_facility (facility_code, facility_name, facility_type, region)
                VALUES (?, ?, ?, ?)
                """,
                (facility_code, facility_name, facility_type, region),
            )
            conn.commit()
            return int(insert_cur.lastrowid)
        finally:
            conn.close()


class FactLoader:
    """ETL loader for fact tables enforcing foreign key referential integrity."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    def insert_fact_encounter(
        self,
        patient_sk: int,
        condition_sk: int,
        facility_sk: int,
        admit_date: Any,
        cost: float,
        length_of_stay: int,
        readmission_flag: int,
        satisfaction: int | None,
        outcome: str,
        discharge_date: Any | None = None,
    ) -> int:
        """Insert a row into fact_encounter with referential integrity."""
        admit_sk = _to_date_sk(admit_date)
        discharge_sk = _to_date_sk(discharge_date) if discharge_date is not None else None

        conn = _get_connection(self.db_path)
        try:
            cur = conn.execute(
                """
                INSERT INTO fact_encounter (
                    patient_sk, condition_sk, facility_sk, admit_date_sk, discharge_date_sk,
                    cost, length_of_stay, readmission_flag, satisfaction, outcome
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    patient_sk,
                    condition_sk,
                    facility_sk,
                    admit_sk,
                    discharge_sk,
                    float(cost),
                    int(length_of_stay),
                    int(readmission_flag),
                    satisfaction,
                    outcome,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def insert_fact_observation(
        self,
        patient_sk: int,
        observation_date: Any,
        observation_name: str,
        value: float | None = None,
        unit: str | None = None,
    ) -> int:
        """Insert a row into fact_observation with referential integrity."""
        date_sk = _to_date_sk(observation_date)
        conn = _get_connection(self.db_path)
        try:
            cur = conn.execute(
                """
                INSERT INTO fact_observation (
                    patient_sk, date_sk, observation_name, value, unit
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (patient_sk, date_sk, observation_name, value, unit),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def insert_fact_pipeline_run(
        self,
        run_id: str,
        stage: str,
        status: str,
        rows_in: int | None,
        rows_out: int | None,
        rows_rejected: int | None,
        started_at: str,
        finished_at: str | None,
        run_date: Any,
    ) -> int:
        """Insert a row into fact_pipeline_run with referential integrity."""
        date_sk = _to_date_sk(run_date)
        conn = _get_connection(self.db_path)
        try:
            cur = conn.execute(
                """
                INSERT INTO fact_pipeline_run (
                    run_id, stage, status, rows_in, rows_out, rows_rejected,
                    started_at, finished_at, date_sk
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    stage,
                    status,
                    rows_in,
                    rows_out,
                    rows_rejected,
                    started_at,
                    finished_at,
                    date_sk,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def insert_fact_data_quality(
        self,
        check_date: Any,
        table_name: str,
        rule_name: str,
        records_checked: int,
        records_passed: int,
        records_failed: int,
    ) -> int:
        """Insert a row into fact_data_quality with pass_rate calculation."""
        date_sk = _to_date_sk(check_date)
        pass_rate = (
            (float(records_passed) / float(records_checked)) * 100.0
            if records_checked > 0
            else 0.0
        )
        conn = _get_connection(self.db_path)
        try:
            cur = conn.execute(
                """
                INSERT INTO fact_data_quality (
                    date_sk, table_name, rule_name, records_checked,
                    records_passed, records_failed, pass_rate
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date_sk,
                    table_name,
                    rule_name,
                    records_checked,
                    records_passed,
                    records_failed,
                    pass_rate,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()


def populate_star_schema_from_silver(cfg: PipelineConfig) -> dict[str, int]:
    """ETL job to populate Star Schema dimensions and facts from Silver encounters and audit tables.
    
    Returns a dictionary of loaded record counts per dimension/fact.
    """
    conn = _get_connection(cfg.warehouse_db)
    dim_loader = DimensionLoader(cfg.warehouse_db)
    fact_loader = FactLoader(cfg.warehouse_db)

    counts: dict[str, int] = {
        "dim_date": 0,
        "dim_patient": 0,
        "dim_condition": 0,
        "dim_facility": 0,
        "fact_encounter": 0,
        "fact_pipeline_run": 0,
    }

    try:
        # 1. Populate dim_date for standard historical + current range (2020 to 2030)
        counts["dim_date"] = dim_loader.load_dim_date(date(2025, 1, 1), date(2026, 12, 31))

        # 2. Populate default facilities
        fac_sk = dim_loader.upsert_dim_facility(
            facility_code="HG_MAIN",
            facility_name="HealthGuard Central Medical Center",
            facility_type="General Hospital",
            region="Midwest",
        )
        counts["dim_facility"] = 1

        # 3. Read silver encounters
        silver_rows = conn.execute(
            """
            SELECT patient_id, age, age_band, gender, condition, procedure_name,
                   cost, length_of_stay, readmission_flag, outcome, satisfaction,
                   _silver_loaded_at
            FROM silver_encounters
            """
        ).fetchall()

        cond_sk_map: dict[str, int] = {}
        patient_sk_map: dict[str, int] = {}

        for row in silver_rows:
            cond_name = row["condition"]
            if cond_name not in cond_sk_map:
                c_sk = dim_loader.upsert_dim_condition(
                    condition_code=f"COND_{cond_name.upper().replace(' ', '_')}",
                    condition_text=cond_name,
                    condition_category="General Clinical",
                )
                cond_sk_map[cond_name] = c_sk
                counts["dim_condition"] += 1

            p_id = f"HG_CSV:{row['patient_id']}"
            if p_id not in patient_sk_map:
                # estimate birth year based on age in 2026
                birth_year = 2026 - int(row["age"])
                p_sk = dim_loader.upsert_dim_patient(
                    patient_id=p_id,
                    source_system="HG_CSV",
                    gender=row["gender"],
                    birth_date=f"{birth_year}-01-01",
                    age_band=row["age_band"],
                )
                patient_sk_map[p_id] = p_sk
                counts["dim_patient"] += 1

            loaded_at_str = row["_silver_loaded_at"] or "2026-01-01"
            admit_date_val = loaded_at_str[:10]

            fact_loader.insert_fact_encounter(
                patient_sk=patient_sk_map[p_id],
                condition_sk=cond_sk_map[cond_name],
                facility_sk=fac_sk,
                admit_date=admit_date_val,
                cost=row["cost"],
                length_of_stay=row["length_of_stay"],
                readmission_flag=row["readmission_flag"],
                satisfaction=row["satisfaction"],
                outcome=row["outcome"],
            )
            counts["fact_encounter"] += 1

        # 4. Populate fact_pipeline_run from pipeline_runs if available
        runs = conn.execute(
            """
            SELECT run_id, stage, status, rows_in, rows_out, rows_rejected,
                   started_at, finished_at
            FROM pipeline_runs
            """
        ).fetchall()

        for r in runs:
            start_date_val = (r["started_at"] or "2026-01-01")[:10]
            fact_loader.insert_fact_pipeline_run(
                run_id=r["run_id"],
                stage=r["stage"],
                status=r["status"],
                rows_in=r["rows_in"],
                rows_out=r["rows_out"],
                rows_rejected=r["rows_rejected"],
                started_at=r["started_at"],
                finished_at=r["finished_at"],
                run_date=start_date_val,
            )
            counts["fact_pipeline_run"] += 1

        return counts
    finally:
        conn.close()

