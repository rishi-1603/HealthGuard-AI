"""Tests for Day 6 — Enterprise Star Schema & Dimensional Modeling (DE-006).

Verifies:
  AC1: dim_patient (SCD Type 2), dim_condition, dim_facility, dim_date
  AC2: fact_encounter, fact_observation, fact_pipeline_run, fact_data_quality
  AC3: Surrogate keys, composite indices, cross-DB ANSI DDL
  AC4: Star schema referential integrity
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, date
from pathlib import Path

import pytest

from pipeline.config import PipelineConfig
from pipeline.warehouse import managed_connection, apply_ddl
from pipeline.warehouse.star_schema import (
    apply_star_schema_ddl,
    DimensionLoader,
    FactLoader,
    DIMENSION_TABLES,
    FACT_TABLES,
    populate_star_schema_from_silver,
)


@pytest.fixture()
def cfg(tmp_path: Path) -> PipelineConfig:
    """Temp warehouse for star schema tests."""
    return PipelineConfig(
        source_csv=tmp_path / "fake.csv",
        warehouse_db=tmp_path / "test_star.db",
        reports_dir=tmp_path / "reports",
    )


@pytest.fixture()
def schema_db(cfg: PipelineConfig) -> Path:
    """Apply all DDL (core + star schema) and return db path."""
    apply_ddl(cfg)
    apply_star_schema_ddl(cfg)
    return cfg.warehouse_db


# ──────────────────────────────────────────────────────────────────────
# AC1: Dimension tables exist with correct columns
# ──────────────────────────────────────────────────────────────────────
class TestDimensionTablesDDL:
    """Verify dimension table structures."""

    def test_dim_patient_columns(self, schema_db: Path) -> None:
        with managed_connection(schema_db) as conn:
            cols = _column_names(conn, "dim_patient")
        expected = {
            "patient_sk", "patient_id", "source_system", "gender",
            "birth_date", "age_band", "region", "insurance",
            "effective_from", "effective_to", "is_current",
            "row_hash",
        }
        assert expected.issubset(cols), f"Missing: {expected - cols}"

    def test_dim_patient_scd2_columns(self, schema_db: Path) -> None:
        """SCD Type 2 tracking columns must exist."""
        with managed_connection(schema_db) as conn:
            cols = _column_names(conn, "dim_patient")
        for scd_col in ("effective_from", "effective_to", "is_current"):
            assert scd_col in cols, f"SCD2 column '{scd_col}' missing"

    def test_dim_condition_columns(self, schema_db: Path) -> None:
        with managed_connection(schema_db) as conn:
            cols = _column_names(conn, "dim_condition")
        expected = {
            "condition_sk", "condition_code", "condition_text",
            "condition_category",
        }
        assert expected.issubset(cols), f"Missing: {expected - cols}"

    def test_dim_facility_columns(self, schema_db: Path) -> None:
        with managed_connection(schema_db) as conn:
            cols = _column_names(conn, "dim_facility")
        expected = {
            "facility_sk", "facility_code", "facility_name",
            "facility_type", "region",
        }
        assert expected.issubset(cols), f"Missing: {expected - cols}"

    def test_dim_date_columns(self, schema_db: Path) -> None:
        with managed_connection(schema_db) as conn:
            cols = _column_names(conn, "dim_date")
        expected = {
            "date_sk", "full_date", "year", "quarter", "month",
            "day_of_week", "is_weekend",
        }
        assert expected.issubset(cols), f"Missing: {expected - cols}"

    def test_all_dimension_tables_registered(self) -> None:
        assert set(DIMENSION_TABLES) == {
            "dim_patient", "dim_condition", "dim_facility", "dim_date",
        }


# ──────────────────────────────────────────────────────────────────────
# AC2: Fact tables exist with correct columns
# ──────────────────────────────────────────────────────────────────────
class TestFactTablesDDL:
    """Verify fact table structures."""

    def test_fact_encounter_columns(self, schema_db: Path) -> None:
        with managed_connection(schema_db) as conn:
            cols = _column_names(conn, "fact_encounter")
        expected = {
            "encounter_sk", "patient_sk", "condition_sk",
            "facility_sk", "admit_date_sk", "discharge_date_sk",
            "cost", "length_of_stay", "readmission_flag",
            "satisfaction", "outcome",
        }
        assert expected.issubset(cols), f"Missing: {expected - cols}"

    def test_fact_observation_columns(self, schema_db: Path) -> None:
        with managed_connection(schema_db) as conn:
            cols = _column_names(conn, "fact_observation")
        expected = {
            "observation_sk", "patient_sk", "date_sk",
            "observation_name", "value", "unit",
        }
        assert expected.issubset(cols), f"Missing: {expected - cols}"

    def test_fact_pipeline_run_columns(self, schema_db: Path) -> None:
        with managed_connection(schema_db) as conn:
            cols = _column_names(conn, "fact_pipeline_run")
        expected = {
            "run_sk", "run_id", "stage", "status",
            "rows_in", "rows_out", "rows_rejected",
            "started_at", "finished_at", "date_sk",
        }
        assert expected.issubset(cols), f"Missing: {expected - cols}"

    def test_fact_data_quality_columns(self, schema_db: Path) -> None:
        with managed_connection(schema_db) as conn:
            cols = _column_names(conn, "fact_data_quality")
        expected = {
            "dq_sk", "date_sk", "table_name", "rule_name",
            "records_checked", "records_passed", "records_failed",
            "pass_rate",
        }
        assert expected.issubset(cols), f"Missing: {expected - cols}"

    def test_all_fact_tables_registered(self) -> None:
        assert set(FACT_TABLES) == {
            "fact_encounter", "fact_observation",
            "fact_pipeline_run", "fact_data_quality",
        }


# ──────────────────────────────────────────────────────────────────────
# AC3: Surrogate keys and indices
# ──────────────────────────────────────────────────────────────────────
class TestSurrogateKeysAndIndices:
    """Verify surrogate key auto-generation and index presence."""

    def test_dim_patient_surrogate_autoincrement(self, schema_db: Path) -> None:
        with managed_connection(schema_db) as conn:
            conn.execute(
                "INSERT INTO dim_patient "
                "(patient_id, source_system, gender, birth_date, age_band, "
                "effective_from, is_current, row_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("P001", "HG_CSV", "Male", "1990-01-01", "31-45",
                 "2026-01-01", 1, "hash1"),
            )
            row = conn.execute(
                "SELECT patient_sk FROM dim_patient WHERE patient_id = ?",
                ("P001",),
            ).fetchone()
        assert row is not None
        assert isinstance(row[0], int)
        assert row[0] >= 1

    def test_fact_encounter_surrogate_autoincrement(self, schema_db: Path) -> None:
        """Fact tables also use integer surrogate keys."""
        with managed_connection(schema_db) as conn:
            # Insert dimension dependencies first
            conn.execute(
                "INSERT INTO dim_patient "
                "(patient_id, source_system, gender, birth_date, age_band, "
                "effective_from, is_current, row_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("P001", "HG_CSV", "Male", "1990-01-01", "31-45",
                 "2026-01-01", 1, "hash1"),
            )
            pat_sk = conn.execute(
                "SELECT patient_sk FROM dim_patient WHERE patient_id='P001'"
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO dim_condition "
                "(condition_code, condition_text, condition_category) "
                "VALUES (?, ?, ?)",
                ("C001", "Diabetes", "Chronic"),
            )
            cond_sk = conn.execute(
                "SELECT condition_sk FROM dim_condition WHERE condition_code='C001'"
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO dim_facility "
                "(facility_code, facility_name, facility_type, region) "
                "VALUES (?, ?, ?, ?)",
                ("F001", "General Hospital", "Hospital", "East"),
            )
            fac_sk = conn.execute(
                "SELECT facility_sk FROM dim_facility WHERE facility_code='F001'"
            ).fetchone()[0]

            conn.execute(
                "INSERT INTO dim_date "
                "(date_sk, full_date, year, quarter, month, day_of_week, is_weekend) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (20260101, "2026-01-01", 2026, 1, 1, 3, 0),
            )

            conn.execute(
                "INSERT INTO fact_encounter "
                "(patient_sk, condition_sk, facility_sk, admit_date_sk, "
                "cost, length_of_stay, readmission_flag, satisfaction, outcome) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (pat_sk, cond_sk, fac_sk, 20260101, 1500.0, 5, 0, 8, "Recovered"),
            )
            row = conn.execute(
                "SELECT encounter_sk FROM fact_encounter"
            ).fetchone()
        assert row is not None
        assert isinstance(row[0], int)

    def test_composite_index_on_dim_patient(self, schema_db: Path) -> None:
        """Composite index on (patient_id, is_current) for SCD2 lookups."""
        with managed_connection(schema_db) as conn:
            indexes = _index_names(conn, "dim_patient")
        assert any("patient_id" in idx and "current" in idx for idx in indexes), \
            f"Expected composite index on dim_patient, found: {indexes}"

    def test_index_on_fact_encounter_patient_sk(self, schema_db: Path) -> None:
        with managed_connection(schema_db) as conn:
            indexes = _index_names(conn, "fact_encounter")
        assert any("patient_sk" in idx for idx in indexes), \
            f"Expected index on fact_encounter.patient_sk, found: {indexes}"


# ──────────────────────────────────────────────────────────────────────
# AC4: Referential integrity — ETL loaders
# ──────────────────────────────────────────────────────────────────────
class TestDimensionLoader:
    """Verify dimension ETL loading."""

    def test_load_dim_date_generates_date_range(self, schema_db: Path) -> None:
        loader = DimensionLoader(schema_db)
        count = loader.load_dim_date(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )
        assert count == 31
        with managed_connection(schema_db) as conn:
            row = conn.execute(
                "SELECT * FROM dim_date WHERE full_date = '2026-01-15'"
            ).fetchone()
        assert row is not None
        assert dict(row)["year"] == 2026
        assert dict(row)["month"] == 1
        assert dict(row)["is_weekend"] in (0, 1)

    def test_load_dim_date_idempotent(self, schema_db: Path) -> None:
        loader = DimensionLoader(schema_db)
        loader.load_dim_date(date(2026, 1, 1), date(2026, 1, 10))
        loader.load_dim_date(date(2026, 1, 1), date(2026, 1, 10))
        with managed_connection(schema_db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM dim_date").fetchone()[0]
        assert count == 10

    def test_load_dim_patient_scd2_insert(self, schema_db: Path) -> None:
        loader = DimensionLoader(schema_db)
        sk = loader.upsert_dim_patient(
            patient_id="HG_CSV:101",
            source_system="HG_CSV",
            gender="Male",
            birth_date="1985-03-15",
            age_band="31-45",
            region=None,
            insurance=None,
        )
        assert isinstance(sk, int) and sk >= 1
        with managed_connection(schema_db) as conn:
            row = conn.execute(
                "SELECT is_current, effective_to FROM dim_patient "
                "WHERE patient_sk = ?", (sk,)
            ).fetchone()
        assert dict(row)["is_current"] == 1
        assert dict(row)["effective_to"] is None  # current row has no end

    def test_load_dim_patient_scd2_update(self, schema_db: Path) -> None:
        """Updating a patient attribute should close the old row and insert new."""
        loader = DimensionLoader(schema_db)
        sk1 = loader.upsert_dim_patient(
            patient_id="HG_CSV:201", source_system="HG_CSV",
            gender="Female", birth_date="1970-06-01", age_band="46-60",
        )
        # Now region changed
        sk2 = loader.upsert_dim_patient(
            patient_id="HG_CSV:201", source_system="HG_CSV",
            gender="Female", birth_date="1970-06-01", age_band="46-60",
            region="West",
        )
        assert sk2 != sk1  # new surrogate key for the new version
        with managed_connection(schema_db) as conn:
            rows = conn.execute(
                "SELECT is_current, effective_to FROM dim_patient "
                "WHERE patient_id = 'HG_CSV:201' ORDER BY patient_sk"
            ).fetchall()
        assert len(rows) == 2
        old, new = [dict(r) for r in rows]
        assert old["is_current"] == 0
        assert old["effective_to"] is not None
        assert new["is_current"] == 1
        assert new["effective_to"] is None

    def test_load_dim_condition(self, schema_db: Path) -> None:
        loader = DimensionLoader(schema_db)
        sk = loader.upsert_dim_condition("DM", "Diabetes Mellitus", "Chronic")
        assert isinstance(sk, int) and sk >= 1
        with managed_connection(schema_db) as conn:
            text = conn.execute(
                "SELECT condition_text FROM dim_condition WHERE condition_sk = ?",
                (sk,),
            ).fetchone()[0]
        assert text == "Diabetes Mellitus"

    def test_load_dim_facility(self, schema_db: Path) -> None:
        loader = DimensionLoader(schema_db)
        sk = loader.upsert_dim_facility("F01", "Metro Hospital", "Hospital", "East")
        assert isinstance(sk, int) and sk >= 1


class TestFactLoader:
    """Verify fact table ETL loading with referential integrity."""

    def test_insert_fact_encounter(self, schema_db: Path) -> None:
        dim = DimensionLoader(schema_db)
        dim.load_dim_date(date(2026, 1, 1), date(2026, 1, 31))
        pat_sk = dim.upsert_dim_patient(
            "P1", "HG_CSV", "Male", "1990-01-01", "31-45",
        )
        cond_sk = dim.upsert_dim_condition("C1", "Asthma", "Respiratory")
        fac_sk = dim.upsert_dim_facility("F1", "City Hospital", "Hospital", "North")

        fact = FactLoader(schema_db)
        enc_sk = fact.insert_fact_encounter(
            patient_sk=pat_sk,
            condition_sk=cond_sk,
            facility_sk=fac_sk,
            admit_date=date(2026, 1, 10),
            discharge_date=date(2026, 1, 15),
            cost=2500.0,
            length_of_stay=5,
            readmission_flag=0,
            satisfaction=9,
            outcome="Recovered",
        )
        assert isinstance(enc_sk, int) and enc_sk >= 1

    def test_insert_fact_observation(self, schema_db: Path) -> None:
        dim = DimensionLoader(schema_db)
        dim.load_dim_date(date(2026, 3, 1), date(2026, 3, 31))
        pat_sk = dim.upsert_dim_patient(
            "P2", "SYNTHEA_FHIR", "Female", "1980-05-20", "46-60",
        )

        fact = FactLoader(schema_db)
        obs_sk = fact.insert_fact_observation(
            patient_sk=pat_sk,
            observation_date=date(2026, 3, 15),
            observation_name="Blood Pressure",
            value=120.0,
            unit="mmHg",
        )
        assert isinstance(obs_sk, int) and obs_sk >= 1

    def test_insert_fact_pipeline_run(self, schema_db: Path) -> None:
        dim = DimensionLoader(schema_db)
        dim.load_dim_date(date(2026, 2, 1), date(2026, 2, 28))

        fact = FactLoader(schema_db)
        run_sk = fact.insert_fact_pipeline_run(
            run_id="run-abc-123",
            stage="bronze",
            status="success",
            rows_in=1000,
            rows_out=990,
            rows_rejected=10,
            started_at="2026-02-15T10:00:00",
            finished_at="2026-02-15T10:05:00",
            run_date=date(2026, 2, 15),
        )
        assert isinstance(run_sk, int) and run_sk >= 1

    def test_insert_fact_data_quality(self, schema_db: Path) -> None:
        dim = DimensionLoader(schema_db)
        dim.load_dim_date(date(2026, 4, 1), date(2026, 4, 30))

        fact = FactLoader(schema_db)
        dq_sk = fact.insert_fact_data_quality(
            check_date=date(2026, 4, 10),
            table_name="silver_encounters",
            rule_name="not_null_patient_id",
            records_checked=984,
            records_passed=984,
            records_failed=0,
        )
        assert isinstance(dq_sk, int) and dq_sk >= 1
        with managed_connection(schema_db) as conn:
            row = conn.execute(
                "SELECT pass_rate FROM fact_data_quality WHERE dq_sk = ?",
                (dq_sk,),
            ).fetchone()
        assert abs(dict(row)["pass_rate"] - 100.0) < 0.01

    def test_referential_integrity_fact_to_dim(self, schema_db: Path) -> None:
        """Fact insertion with non-existent dimension FK should fail."""
        fact = FactLoader(schema_db)
        with pytest.raises(sqlite3.IntegrityError):
            fact.insert_fact_encounter(
                patient_sk=99999,  # does not exist
                condition_sk=99999,
                facility_sk=99999,
                admit_date=date(2026, 1, 1),
                cost=100.0,
                length_of_stay=1,
                readmission_flag=0,
                satisfaction=5,
                outcome="Stable",
            )

    def test_populate_star_schema_from_silver(self, cfg: PipelineConfig, schema_db: Path) -> None:
        """Integration test: populate dimensions and facts directly from Silver encounters."""
        # Insert a sample silver row
        with managed_connection(schema_db) as conn:
            conn.execute(
                """
                INSERT INTO silver_encounters (
                    patient_id, age, age_band, gender, condition, procedure_name,
                    cost, length_of_stay, readmission, readmission_flag, outcome,
                    satisfaction, cost_per_day, _silver_loaded_at, _dq_passed
                )
                VALUES (
                    101, 55, '46-60', 'Female', 'Hypertension', 'ECG',
                    1200.0, 3, 'No', 0, 'Recovered', 9, 400.0, '2026-03-01T12:00:00', 1
                )
                """
            )

        counts = populate_star_schema_from_silver(cfg)
        assert counts["dim_patient"] >= 1
        assert counts["dim_condition"] >= 1
        assert counts["fact_encounter"] >= 1

        with managed_connection(schema_db) as conn:
            enc = conn.execute(
                """
                SELECT f.encounter_sk, f.cost, f.outcome, p.patient_id, p.gender, c.condition_text
                FROM fact_encounter f
                JOIN dim_patient p ON f.patient_sk = p.patient_sk
                JOIN dim_condition c ON f.condition_sk = c.condition_sk
                """
            ).fetchone()
            assert enc is not None
            assert enc["patient_id"] == "HG_CSV:101"
            assert enc["condition_text"] == "Hypertension"
            assert enc["cost"] == 1200.0



# ──────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────
def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return the set of column names for a table."""
    info = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in info}


def _index_names(conn: sqlite3.Connection, table: str) -> list[str]:
    """Return index names for a table."""
    rows = conn.execute(f"PRAGMA index_list({table})").fetchall()
    return [row[1] for row in rows]
