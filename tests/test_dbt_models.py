"""Tests for Day 7 — dbt Transformation Models & Automated Schema Testing (DE-007).

Verifies:
  AC1: Staging (stg_), intermediate (int_), and mart (fct_/dim_) models exist and compile
  AC2: dbt tests (unique, not_null, accepted_values, relationships)
  AC3: Automated lineage documentation and idempotent incremental materialization
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import duckdb

from pipeline.dbt.compiler import DbtCompiler, DbtModel
from pipeline.dbt.runner import DbtRunner, DbtExecutionResult, DbtTestResult


@pytest.fixture()
def dbt_project_dir() -> Path:
    """Path to the dbt project root."""
    return Path(__file__).resolve().parent.parent / "warehouse" / "dbt_healthguard"


@pytest.fixture()
def duckdb_con() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB connection with raw source tables populated."""
    con = duckdb.connect(":memory:")
    
    # Create raw bronze encounters table for source('raw_hospital', 'bronze_encounters')
    con.execute("""
        CREATE SCHEMA IF NOT EXISTS raw_hospital;
        CREATE TABLE raw_hospital.bronze_encounters (
            _row_id INTEGER,
            _ingested_at VARCHAR,
            _source_file VARCHAR,
            _source_hash VARCHAR,
            Patient_ID INTEGER,
            Age INTEGER,
            Gender VARCHAR,
            Condition VARCHAR,
            Procedure VARCHAR,
            Cost DOUBLE,
            Length_of_Stay INTEGER,
            Readmission VARCHAR,
            Outcome VARCHAR,
            Satisfaction INTEGER
        );
        INSERT INTO raw_hospital.bronze_encounters VALUES
        (1, '2026-03-01', 'hospital_data.csv', 'hash1', 101, 45, 'Male', 'Diabetes', 'Insulin Therapy', 1500.0, 4, 'No', 'Recovered', 8),
        (2, '2026-03-01', 'hospital_data.csv', 'hash1', 102, 68, 'Female', 'Heart Failure', 'Echocardiogram', 5200.0, 7, 'Yes', 'Stable', 7),
        (3, '2026-03-01', 'hospital_data.csv', 'hash1', 103, 29, 'Female', 'Asthma', 'Nebulization', 800.0, 2, 'No', 'Recovered', 9),
        (4, '2026-03-01', 'hospital_data.csv', 'hash1', 104, 72, 'Male', 'Diabetes', 'Insulin Therapy', 2100.0, 5, 'Yes', 'Critical', 5);
    """)

    # Create raw bronze fhir patients table for source('raw_fhir', 'bronze_patients')
    con.execute("""
        CREATE SCHEMA IF NOT EXISTS raw_fhir;
        CREATE TABLE raw_fhir.bronze_patients (
            patient_id VARCHAR,
            native_id VARCHAR,
            gender VARCHAR,
            birth_date VARCHAR,
            region VARCHAR,
            insurance VARCHAR,
            source_system VARCHAR
        );
        INSERT INTO raw_fhir.bronze_patients VALUES
        ('SYNTHEA_FHIR:P001', 'P001', 'female', '1980-05-12', 'Northeast', 'Medicare', 'SYNTHEA_FHIR'),
        ('SYNTHEA_FHIR:P002', 'P002', 'male', '1955-11-23', 'Midwest', 'Medicaid', 'SYNTHEA_FHIR');
    """)

    return con


# ──────────────────────────────────────────────────────────────────────
# AC1: Models exist, are categorized, and compile into executable SQL
# ──────────────────────────────────────────────────────────────────────
class TestDbtModelsStructure:
    """Verify presence and compilation of stg_, int_, and mart models."""

    def test_project_configuration_exists(self, dbt_project_dir: Path) -> None:
        proj_yml = dbt_project_dir / "dbt_project.yml"
        assert proj_yml.exists(), f"Missing {proj_yml}"

    def test_all_model_layers_exist(self, dbt_project_dir: Path) -> None:
        models_dir = dbt_project_dir / "models"
        stg_dir = models_dir / "staging"
        int_dir = models_dir / "intermediate"
        mart_dir = models_dir / "marts"

        assert stg_dir.is_dir(), "Missing models/staging"
        assert int_dir.is_dir(), "Missing models/intermediate"
        assert mart_dir.is_dir(), "Missing models/marts"

        # Check required files
        assert (stg_dir / "stg_hospital_encounters.sql").exists()
        assert (stg_dir / "stg_fhir_patients.sql").exists()
        assert (int_dir / "int_patient_clinical_history.sql").exists()
        assert (int_dir / "int_condition_cost_summary.sql").exists()
        assert (mart_dir / "fct_hospital_admissions.sql").exists()
        assert (mart_dir / "dim_patient_demographics.sql").exists()
        assert (mart_dir / "fct_readmission_analysis.sql").exists()

    def test_compiler_discovers_all_models(self, dbt_project_dir: Path) -> None:
        compiler = DbtCompiler(dbt_project_dir)
        models = compiler.discover_models()
        model_names = {m.name for m in models}

        expected = {
            "stg_hospital_encounters",
            "stg_fhir_patients",
            "int_patient_clinical_history",
            "int_condition_cost_summary",
            "fct_hospital_admissions",
            "dim_patient_demographics",
            "fct_readmission_analysis",
        }
        assert expected.issubset(model_names)

    def test_topological_dag_ordering(self, dbt_project_dir: Path) -> None:
        """Models must be ordered such that dependencies run before dependents."""
        compiler = DbtCompiler(dbt_project_dir)
        ordered_names = compiler.get_execution_order()

        stg_idx = ordered_names.index("stg_hospital_encounters")
        int_idx = ordered_names.index("int_patient_clinical_history")
        fct_idx = ordered_names.index("fct_hospital_admissions")

        assert stg_idx < int_idx, "stg_ must run before int_"
        assert int_idx < fct_idx, "int_ must run before fct_"

    def test_compiler_resolves_refs_and_sources(self, dbt_project_dir: Path) -> None:
        compiler = DbtCompiler(dbt_project_dir)
        compiled_sql = compiler.compile_model("int_patient_clinical_history")
        assert "stg_hospital_encounters" in compiled_sql
        assert "{{ ref(" not in compiled_sql, "Jinja ref must be resolved"


# ──────────────────────────────────────────────────────────────────────
# AC2: Automated dbt Schema Tests (unique, not_null, accepted_values, relationships)
# ──────────────────────────────────────────────────────────────────────
class TestDbtSchemaTests:
    """Verify execution of the 4 core dbt schema tests."""

    def test_test_suite_passes_on_valid_data(
        self, dbt_project_dir: Path, duckdb_con: duckdb.DuckDBPyConnection
    ) -> None:
        runner = DbtRunner(dbt_project_dir, con=duckdb_con)
        # Execute models first
        exec_res = runner.run()
        assert exec_res.success, f"Run failed: {exec_res.errors}"

        # Run dbt tests
        test_res: DbtTestResult = runner.test()
        assert test_res.passed, f"Tests failed: {test_res.failures}"
        assert test_res.total_tests >= 8, f"Expected >= 8 tests, got {test_res.total_tests}"

        # Check all 4 test types are executed
        test_types = {t.test_type for t in test_res.test_runs}
        assert {"unique", "not_null", "accepted_values", "relationships"}.issubset(test_types)

    def test_unique_test_catches_duplicate_keys(
        self, dbt_project_dir: Path, duckdb_con: duckdb.DuckDBPyConnection
    ) -> None:
        runner = DbtRunner(dbt_project_dir, con=duckdb_con)
        runner.run()

        # Inject duplicate patient_id into bronze
        duckdb_con.execute("""
            INSERT INTO raw_hospital.bronze_encounters VALUES
            (5, '2026-03-01', 'dup.csv', 'hash2', 101, 45, 'Male', 'Diabetes', 'Insulin', 1500.0, 4, 'No', 'Recovered', 8);
        """)
        # Re-run staging
        runner.run(models=["stg_hospital_encounters"])

        # Test must fail
        test_res = runner.test(models=["stg_hospital_encounters"])
        assert not test_res.passed
        unique_failures = [t for t in test_res.failures if t.test_type == "unique"]
        assert len(unique_failures) >= 1

    def test_accepted_values_catches_invalid_categorical(
        self, dbt_project_dir: Path, duckdb_con: duckdb.DuckDBPyConnection
    ) -> None:
        # Clear & insert invalid gender
        duckdb_con.execute("DELETE FROM raw_hospital.bronze_encounters;")
        duckdb_con.execute("""
            INSERT INTO raw_hospital.bronze_encounters VALUES
            (1, '2026-03-01', 'h.csv', 'h', 999, 30, 'Unknown_Gender', 'Asthma', 'Inhaler', 500.0, 1, 'No', 'Recovered', 8);
        """)
        runner = DbtRunner(dbt_project_dir, con=duckdb_con)
        runner.run(models=["stg_hospital_encounters"])

        test_res = runner.test(models=["stg_hospital_encounters"])
        assert not test_res.passed
        val_failures = [t for t in test_res.failures if t.test_type == "accepted_values"]
        assert len(val_failures) >= 1


# ──────────────────────────────────────────────────────────────────────
# AC3: Lineage Documentation & Idempotent Incremental Materialization
# ──────────────────────────────────────────────────────────────────────
class TestDbtLineageAndIncremental:
    """Verify lineage generation and incremental runs."""

    def test_lineage_graph_generation(self, dbt_project_dir: Path) -> None:
        runner = DbtRunner(dbt_project_dir)
        lineage = runner.generate_lineage()

        assert "nodes" in lineage
        assert "edges" in lineage
        # Verify edge from source to stg, stg to int, int to mart
        edge_pairs = {(e["source"], e["target"]) for e in lineage["edges"]}
        assert ("raw_hospital.bronze_encounters", "stg_hospital_encounters") in edge_pairs
        assert ("stg_hospital_encounters", "int_patient_clinical_history") in edge_pairs
        assert ("int_patient_clinical_history", "fct_hospital_admissions") in edge_pairs

    def test_lineage_markdown_table(self, dbt_project_dir: Path) -> None:
        runner = DbtRunner(dbt_project_dir)
        md = runner.render_lineage_markdown()
        assert "| Model | Layer | Materialization | Depends On |" in md
        assert "fct_hospital_admissions" in md
        assert "incremental" in md

    def test_idempotent_incremental_run(
        self, dbt_project_dir: Path, duckdb_con: duckdb.DuckDBPyConnection
    ) -> None:
        runner = DbtRunner(dbt_project_dir, con=duckdb_con)

        # Run 1: Full initial run
        res1 = runner.run(full_refresh=True)
        assert res1.success
        initial_count = duckdb_con.execute(
            "SELECT COUNT(*) FROM fct_hospital_admissions"
        ).fetchone()[0]
        assert initial_count == 4

        # Run 2: Incremental run without new records should produce identical row count
        res2 = runner.run(full_refresh=False)
        assert res2.success
        second_count = duckdb_con.execute(
            "SELECT COUNT(*) FROM fct_hospital_admissions"
        ).fetchone()[0]
        assert second_count == initial_count, "Incremental run must be idempotent"

        # Run 3: Insert new row and run incrementally
        duckdb_con.execute("""
            INSERT INTO raw_hospital.bronze_encounters VALUES
            (5, '2026-03-02', 'h.csv', 'h', 105, 50, 'Female', 'Diabetes', 'Insulin', 1800.0, 3, 'No', 'Recovered', 9);
        """)
        runner.run(models=["stg_hospital_encounters", "int_patient_clinical_history"])
        runner.run(models=["fct_hospital_admissions"], full_refresh=False)
        updated_count = duckdb_con.execute(
            "SELECT COUNT(*) FROM fct_hospital_admissions"
        ).fetchone()[0]
        assert updated_count == 5, "Incremental run must add new record"
