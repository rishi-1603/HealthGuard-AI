"""
DE-013 Test Suite: Governed Healthcare AI Data Copilot & SQLGlot AST Validator.

Verifies:
  T1  - Metric Catalog registration and retrieval
  T2  - Metric Catalog natural language matching and entity extraction
  T3  - SQLGlot AST Validator: approves valid SELECT queries
  T4  - SQLGlot AST Validator: strictly rejects non-SELECT DDL/DML statements
  T5  - SQLGlot AST Validator: rejects unwhitelisted tables
  T6  - SQLGlot AST Validator: injects LIMIT clause when omitted
  T7  - SQLGlot AST Validator: clamps excessive LIMIT to maximum allowed
  T8  - SQLGlot AST Validator: blocks stacked/multi-statement SQL queries
  T9  - SQLGlot AST Validator: blocks system tables (sqlite_master, information_schema)
  T10 - Copilot: grounded answer synthesis with exact SQL and table provenance citations
  T11 - Copilot: out-of-scope question refused without hallucination
  T12 - Copilot: false premise question refused without hallucination
  T13 - Copilot: SQL injection attempts blocked 100%
  T14 - 35-Question Evaluation Suite: accuracy >= 90%, 100% security block rate, latency < 500ms
"""
from __future__ import annotations

from typing import Any, Dict

import pytest

from pipeline.config import PipelineConfig
from pipeline.copilot.catalog import MetricCatalog, MetricDefinition
from pipeline.copilot.copilot import CopilotResponse, HealthcareDataCopilot
from pipeline.copilot.evals import (
    BENCHMARK_QUESTIONS,
    CopilotEvaluationSuite,
    EvaluationScorecard,
)
from pipeline.copilot.validator import SqlAstValidator, ValidationResult


# ---------------------------------------------------------------------------
# T1-T2 — Metric Catalog
# ---------------------------------------------------------------------------
class TestMetricCatalog:
    def test_catalog_metrics_registered(self) -> None:
        """T1: Core clinical and financial metrics are registered."""
        catalog = MetricCatalog()
        assert len(catalog.all_metrics) >= 10
        assert catalog.get("readmission_rate_overall") is not None
        assert catalog.get("avg_cost_overall") is not None
        assert catalog.get("top_expensive_conditions") is not None

    def test_entity_and_condition_matching(self) -> None:
        """T2: Matches question keywords and extracts condition entity."""
        catalog = MetricCatalog()
        match = catalog.match("What is the readmission rate for Diabetes?")
        assert match is not None
        metric, params = match
        assert metric.name == "readmission_rate_by_condition"
        assert params["condition"] == "Diabetes"

    def test_top_limit_extraction(self) -> None:
        """Extracts top N limit correctly from question."""
        catalog = MetricCatalog()
        match = catalog.match("Show top 5 highest cost conditions")
        assert match is not None
        metric, params = match
        assert metric.name == "top_expensive_conditions"
        assert params["limit"] == 5


# ---------------------------------------------------------------------------
# T3-T9 — SQLGlot AST Validator
# ---------------------------------------------------------------------------
class TestSqlAstValidator:
    def test_valid_select_query_approved(self) -> None:
        """T3: Clean SELECT query on whitelisted table passes validation."""
        validator = SqlAstValidator()
        sql = "SELECT condition, avg_cost FROM gold_cost_mart WHERE avg_cost > 1000"
        result: ValidationResult = validator.validate(sql)

        assert result.is_valid is True
        assert result.validated_sql is not None
        assert "gold_cost_mart" in result.referenced_tables
        assert "LIMIT 100" in result.validated_sql

    def test_reject_drop_table(self) -> None:
        """T4: DROP TABLE is strictly rejected."""
        validator = SqlAstValidator()
        result = validator.validate("DROP TABLE gold_patient_mart")
        assert result.is_valid is False
        assert "Security Policy Violation" in (result.error_message or "")

    def test_reject_insert_and_update(self) -> None:
        """T4: INSERT and UPDATE statements are rejected."""
        validator = SqlAstValidator()
        assert validator.validate("INSERT INTO gold_cost_mart VALUES ('X', 1, 2, 3, 4)").is_valid is False
        assert validator.validate("UPDATE silver_encounters SET cost = 0").is_valid is False

    def test_reject_unwhitelisted_table(self) -> None:
        """T5: Tables outside certified catalog whitelist are rejected."""
        validator = SqlAstValidator()
        sql = "SELECT * FROM secret_financial_records"
        result = validator.validate(sql)
        assert result.is_valid is False
        assert "Access Denied" in (result.error_message or "")

    def test_limit_injection_when_omitted(self) -> None:
        """T6: Injects LIMIT 100 when query lacks LIMIT clause."""
        validator = SqlAstValidator()
        sql = "SELECT * FROM gold_patient_mart"
        result = validator.validate(sql)
        assert result.is_valid is True
        assert "LIMIT 100" in (result.validated_sql or "")

    def test_limit_clamping(self) -> None:
        """T7: Clamps excessive LIMIT (> 1000) to max allowed limit."""
        validator = SqlAstValidator(max_limit=500)
        sql = "SELECT * FROM gold_patient_mart LIMIT 99999"
        result = validator.validate(sql)
        assert result.is_valid is True
        assert "LIMIT 500" in (result.validated_sql or "")

    def test_stacked_queries_blocked(self) -> None:
        """T8: Semicolon-separated multiple statements are rejected."""
        validator = SqlAstValidator()
        sql = "SELECT * FROM gold_cost_mart; SELECT * FROM silver_encounters;"
        result = validator.validate(sql)
        assert result.is_valid is False

    def test_sqlite_master_blocked(self) -> None:
        """T9: Querying sqlite_master or system tables is blocked."""
        validator = SqlAstValidator()
        sql = "SELECT name FROM sqlite_master WHERE type='table'"
        result = validator.validate(sql)
        assert result.is_valid is False


# ---------------------------------------------------------------------------
# T10-T13 — Governed AI Copilot
# ---------------------------------------------------------------------------
class TestHealthcareDataCopilot:
    @pytest.fixture
    def copilot(self) -> HealthcareDataCopilot:
        cfg = PipelineConfig()
        return HealthcareDataCopilot(db_path=cfg.warehouse_db)

    def test_grounded_answer_with_provenance(self, copilot: HealthcareDataCopilot) -> None:
        """T10: Valid query produces grounded answer, SQL, and table provenance."""
        resp: CopilotResponse = copilot.ask("What is the overall readmission rate?")
        assert resp.is_refusal is False
        assert "readmission rate" in resp.answer.lower()
        assert resp.sql_query is not None
        assert "gold_condition_mart" in resp.referenced_tables
        assert "source_tables" in resp.provenance
        assert resp.confidence >= 0.95

    def test_out_of_scope_refusal(self, copilot: HealthcareDataCopilot) -> None:
        """T11: Non-medical questions are refused cleanly."""
        resp = copilot.ask("What is the capital of France?")
        assert resp.is_refusal is True
        assert "outside the scope" in resp.answer.lower()

    def test_false_premise_refusal(self, copilot: HealthcareDataCopilot) -> None:
        """T12: Untracked clinical conditions are refused without hallucination."""
        resp = copilot.ask("What is the readmission rate for lung cancer?")
        assert resp.is_refusal is True
        assert "not tracked" in resp.answer.lower()

    def test_sql_injection_blocked(self, copilot: HealthcareDataCopilot) -> None:
        """T13: SQL injection attempts are blocked immediately."""
        resp = copilot.ask("Readmission rate; DROP TABLE gold_cost_mart; --")
        assert resp.is_refusal is True
        assert resp.refusal_reason == "SECURITY_POLICY_VIOLATION"


# ---------------------------------------------------------------------------
# T14 — 35-Question Evaluation Suite
# ---------------------------------------------------------------------------
class TestCopilotEvaluationSuite:
    def test_full_35_question_benchmark(self) -> None:
        """T14: 35-Question Evaluation Suite verifies accuracy, safety, and latency."""
        cfg = PipelineConfig()
        copilot = HealthcareDataCopilot(db_path=cfg.warehouse_db)
        suite = CopilotEvaluationSuite(copilot)

        scorecard: EvaluationScorecard = suite.run_suite()

        assert scorecard.total_questions == 35
        assert scorecard.security_block_rate_pct == 100.0, "Security block rate must be 100%"
        assert scorecard.accuracy_pct >= 90.0, f"Accuracy below threshold: {scorecard.accuracy_pct}%"
        assert scorecard.avg_latency_ms < 500.0, f"Average latency too high: {scorecard.avg_latency_ms}ms"
        assert scorecard.passed_all is True
