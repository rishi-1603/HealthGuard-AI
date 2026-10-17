"""
test_sql_layer.py — the SQL analytics layer must agree with pandas, exactly.
==============================================================================
Pins:
  1. SCHEMA     — the schema builds, constraints bite, indexes exist.
  2. QUERIES    — all seven documented queries execute and return rows.
  3. PARITY     — SQL and pandas produce the same numbers. A mismatch FAILS.
  4. HEADLINES  — the figures the README quotes are reproduced by this layer
                  (264 readmitted / 43.8% of cost / +112.3% premium), so the
                  SQL path cannot silently drift from the published story.
"""
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sql_analytics import (  # noqa: E402
    CSV,
    SCHEMA,
    QUERIES,
    age_band,
    build_db,
    prepare,
    reconcile,
    run_pandas,
    run_sql,
    split_queries,
)


@pytest.fixture(scope="module")
def conn():
    c = build_db()
    yield c
    c.close()


@pytest.fixture(scope="module")
def df():
    return prepare(pd.read_csv(CSV))


@pytest.fixture(scope="module")
def sql_results(conn):
    return run_sql(conn)


@pytest.fixture(scope="module")
def pan_results(df):
    return run_pandas(df)


class TestAgeBand:
    @pytest.mark.parametrize("age,expected", [
        (18, "18-30"), (30, "18-30"), (31, "31-45"), (45, "31-45"),
        (46, "46-60"), (60, "46-60"), (61, "61-75"), (75, "61-75"), (76, "76+"),
    ])
    def test_boundaries(self, age, expected):
        assert age_band(age) == expected

    def test_every_patient_gets_a_band(self, df):
        assert df["age_band"].notna().all()
        assert set(df["age_band"]) <= {"18-30", "31-45", "46-60", "61-75", "76+"}


class TestSchema:
    def test_schema_file_applies_cleanly(self):
        c = sqlite3.connect(":memory:")
        c.executescript(SCHEMA.read_text())
        tables = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "patient_encounters" in tables
        assert "audit_logs" in tables          # the original stub is preserved
        c.close()

    def test_views_exist(self):
        c = sqlite3.connect(":memory:")
        c.executescript(SCHEMA.read_text())
        views = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='view'")}
        assert {"dim_condition", "dim_age_band", "dim_outcome"} <= views
        c.close()

    def test_row_count_matches_csv(self, conn, df):
        n = conn.execute("SELECT COUNT(*) FROM patient_encounters").fetchone()[0]
        assert n == len(df)

    def test_readmission_flag_constraint_bites(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO patient_encounters (patient_id, age, age_band, gender, "
                "condition, procedure_name, cost, length_of_stay, readmitted, "
                "readmission_flag, outcome) VALUES "
                "(99999, 40, '31-45', 'Male', 'X', 'Y', 100, 1, 'Yes', 7, 'Stable')")
            conn.commit()

    def test_negative_cost_rejected(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO patient_encounters (patient_id, age, age_band, gender, "
                "condition, procedure_name, cost, length_of_stay, readmitted, "
                "readmission_flag, outcome) VALUES "
                "(99998, 40, '31-45', 'Male', 'X', 'Y', -5, 1, 'No', 0, 'Stable')")
            conn.commit()


class TestQueriesExecute:
    def test_query_file_splits_into_seven(self):
        assert len(split_queries(QUERIES.read_text())) == 7

    @pytest.mark.parametrize("name", [
        "cost_burden", "cost_premium", "by_condition",
        "by_age_band", "cost_per_day", "by_outcome", "by_gender",
    ])
    def test_query_returns_rows(self, sql_results, name):
        r = sql_results[name]
        assert isinstance(r, pd.DataFrame)
        assert len(r) >= 1, f"{name} returned no rows"

    def test_no_query_returns_nan_everywhere(self, sql_results):
        for name, r in sql_results.items():
            assert not r.isna().all(axis=None), f"{name} is entirely NaN"


class TestParity:
    """SQL and pandas must agree. A mismatch is a failure, never a warning."""

    def test_all_reconciliation_checks_pass(self, sql_results, pan_results):
        checks = reconcile(sql_results, pan_results)
        failures = [c for c in checks if not c["match"]]
        assert failures == [], f"SQL/pandas disagreement: {failures}"

    def test_at_least_fifteen_checks_run(self, sql_results, pan_results):
        assert len(reconcile(sql_results, pan_results)) >= 15

    def test_readmitted_patient_count_agrees(self, sql_results, pan_results):
        s = sql_results["cost_burden"].set_index("readmitted")
        p = pan_results["cost_burden"].set_index("readmitted")
        assert int(s.loc["Yes", "patients"]) == int(p.loc["Yes", "patients"])


class TestPublishedHeadlines:
    """The README narrative must be reproducible from THIS layer."""

    def test_264_readmitted(self, sql_results):
        s = sql_results["cost_burden"].set_index("readmitted")
        assert int(s.loc["Yes", "patients"]) == 264

    def test_readmission_rate_26_8(self, sql_results):
        s = sql_results["cost_burden"].set_index("readmitted")
        rate = float(s.loc["Yes", "patient_share_pct"])
        assert rate == pytest.approx(26.8, abs=0.1)

    def test_cost_share_43_8(self, sql_results):
        s = sql_results["cost_burden"].set_index("readmitted")
        assert float(s.loc["Yes", "cost_share_pct"]) == pytest.approx(43.8, abs=0.2)

    def test_cost_premium_112_3(self, sql_results):
        p = sql_results["cost_premium"].iloc[0]
        assert float(p["cost_premium_pct"]) == pytest.approx(112.3, abs=0.5)

    def test_per_patient_costs_match_readme(self, sql_results):
        p = sql_results["cost_premium"].iloc[0]
        assert float(p["avg_cost_readmitted"]) == pytest.approx(13650, abs=20)
        assert float(p["avg_cost_not_readmitted"]) == pytest.approx(6431, abs=20)

    def test_gender_base_rates_match_the_fairness_disclosure(self, sql_results):
        """HealthGuard's README discloses F 43.9% vs M 7.4%."""
        g = sql_results["by_gender"].set_index("gender")
        assert float(g.loc["Female", "readmission_rate_pct"]) == pytest.approx(43.9, abs=0.5)
        assert float(g.loc["Male", "readmission_rate_pct"]) == pytest.approx(7.4, abs=0.5)


class TestCommittedArtifacts:
    def test_json_report_exists_and_is_consistent(self):
        p = ROOT / "reports" / "sql_analytics.json"
        assert p.exists(), "run scripts/sql_analytics.py to regenerate"
        d = json.loads(p.read_text())
        for key in ("headline", "reconciliation", "queries"):
            assert key in d
        assert d["reconciliation"]["all_passed"] is True

    def test_markdown_report_exists(self):
        assert (ROOT / "reports" / "sql_analytics.md").exists()
