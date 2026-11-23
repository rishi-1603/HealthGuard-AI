"""
Governed Healthcare AI Data Copilot for HealthGuard 360.

Translates natural language clinical questions into audited, validated SQL queries.
Executes queries against the lakehouse warehouse and synthesizes grounded answers
citing exact executed SQL and table provenance. Rejects out-of-scope, false-premise,
or injection queries without hallucinating.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from pipeline.config import PipelineConfig
from pipeline.copilot.catalog import KNOWN_CONDITIONS, MetricCatalog, MetricDefinition
from pipeline.copilot.validator import SqlAstValidator, ValidationResult
from pipeline.warehouse import managed_connection

logger = logging.getLogger(__name__)

# Questions with false clinical premises or unmapped entities that must be refused
FALSE_PREMISE_PATTERNS = [
    "lung cancer",
    "brain transplant",
    "covid",
    "covid-19",
    "ebola",
    "alzheimer",
    "leukemia",
]

# Non-healthcare out-of-scope topics
OUT_OF_SCOPE_PATTERNS = [
    "capital of france",
    "poem",
    "weather",
    "stock market",
    "recipe",
    "football",
    "who won",
]

# Obvious direct SQL injection attempts
INJECTION_KEYWORDS = [
    "drop table",
    "insert into",
    "delete from",
    "update ",
    "alter table",
    "truncate ",
    ";--",
    "--",
    ";",
    "union select",
    "or 1=1",
    "1=1",
    "'1'='1",
    "' or '",
    "'='",
    "attach database",
    "sqlite_master",
    "admin_users",
]


@dataclass(frozen=True)
class CopilotResponse:
    """Immutable response from the Governed Healthcare AI Copilot."""
    question: str
    answer: str
    sql_query: Optional[str]
    referenced_tables: List[str]
    provenance: Dict[str, Any]
    confidence: float
    is_refusal: bool = False
    refusal_reason: Optional[str] = None
    execution_latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "sql_query": self.sql_query,
            "referenced_tables": list(self.referenced_tables),
            "provenance": dict(self.provenance),
            "confidence": self.confidence,
            "is_refusal": self.is_refusal,
            "refusal_reason": self.refusal_reason,
            "execution_latency_ms": self.execution_latency_ms,
        }


class HealthcareDataCopilot:
    """
    Governed NL-to-SQL copilot for clinical and operational healthcare intelligence.
    """

    def __init__(
        self,
        db_path: Optional[Path | str] = None,
        catalog: Optional[MetricCatalog] = None,
        validator: Optional[SqlAstValidator] = None,
    ) -> None:
        cfg = PipelineConfig()
        self.db_path = Path(db_path or cfg.warehouse_db)
        self.catalog = catalog or MetricCatalog()
        self.validator = validator or SqlAstValidator()

    def ask(self, question: str) -> CopilotResponse:
        """
        Process a natural language question and return a governed, grounded answer.
        """
        t0 = time.perf_counter()
        q_clean = question.strip()

        # 1. Guardrail: Security & Injection Check
        if self._is_security_threat(q_clean):
            t_ms = (time.perf_counter() - t0) * 1000.0
            return CopilotResponse(
                question=q_clean,
                answer="Refusal: query blocked by Security Governance. Disallowed keywords or SQL injection patterns detected.",
                sql_query=None,
                referenced_tables=[],
                provenance={"status": "BLOCKED_BY_SECURITY_POLICY"},
                confidence=1.0,
                is_refusal=True,
                refusal_reason="SECURITY_POLICY_VIOLATION",
                execution_latency_ms=round(t_ms, 2),
            )

        # 2. Guardrail: False Premises & Out-of-Scope Checks
        refusal = self._check_refusal(q_clean)
        if refusal:
            t_ms = (time.perf_counter() - t0) * 1000.0
            return CopilotResponse(
                question=q_clean,
                answer=f"Refusal: {refusal}",
                sql_query=None,
                referenced_tables=[],
                provenance={"status": "OUT_OF_SCOPE_OR_FALSE_PREMISE"},
                confidence=0.95,
                is_refusal=True,
                refusal_reason=refusal,
                execution_latency_ms=round(t_ms, 2),
            )

        # 3. Match against Metric Catalog
        match_result = self.catalog.match(q_clean)
        if not match_result:
            t_ms = (time.perf_counter() - t0) * 1000.0
            return CopilotResponse(
                question=q_clean,
                answer="I could not match your question to any certified clinical or financial metric in the governance catalog.",
                sql_query=None,
                referenced_tables=[],
                provenance={"status": "UNMATCHED_METRIC"},
                confidence=0.5,
                is_refusal=True,
                refusal_reason="UNMATCHED_METRIC",
                execution_latency_ms=round(t_ms, 2),
            )

        metric, params = match_result
        raw_sql = metric.sql_template.format(**params)

        # 4. Validate SQL AST via SQLGlot
        val_res: ValidationResult = self.validator.validate(raw_sql)
        if not val_res.is_valid or not val_res.validated_sql:
            t_ms = (time.perf_counter() - t0) * 1000.0
            return CopilotResponse(
                question=q_clean,
                answer=f"Refusal: generated SQL failed AST governance check: {val_res.error_message}",
                sql_query=raw_sql,
                referenced_tables=val_res.referenced_tables,
                provenance={"status": "VALIDATION_FAILED", "error": val_res.error_message},
                confidence=0.0,
                is_refusal=True,
                refusal_reason=val_res.error_message,
                execution_latency_ms=round(t_ms, 2),
            )

        # 5. Execute Validated SQL
        try:
            df = self._execute_sql(val_res.validated_sql)
        except Exception as err:
            t_ms = (time.perf_counter() - t0) * 1000.0
            return CopilotResponse(
                question=q_clean,
                answer=f"Database execution error: {str(err)}",
                sql_query=val_res.validated_sql,
                referenced_tables=val_res.referenced_tables,
                provenance={"status": "EXECUTION_ERROR", "error": str(err)},
                confidence=0.0,
                is_refusal=True,
                refusal_reason=str(err),
                execution_latency_ms=round(t_ms, 2),
            )

        # 6. Synthesize Grounded Response
        answer_text = self._synthesize_answer(metric, df, params)
        t_ms = (time.perf_counter() - t0) * 1000.0

        provenance = {
            "source_tables": val_res.referenced_tables,
            "extracted_parameters": params,
            "metric_name": metric.name,
            "target_table": metric.target_table,
            "row_count": len(df),
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }

        return CopilotResponse(
            question=q_clean,
            answer=answer_text,
            sql_query=val_res.validated_sql,
            referenced_tables=val_res.referenced_tables,
            provenance=provenance,
            confidence=0.99,
            is_refusal=False,
            execution_latency_ms=round(t_ms, 2),
        )

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _is_security_threat(question: str) -> bool:
        q_lower = question.lower()
        return any(pat in q_lower for pat in INJECTION_KEYWORDS)

    @staticmethod
    def _check_refusal(question: str) -> Optional[str]:
        q_lower = question.lower()
        for fp in FALSE_PREMISE_PATTERNS:
            if fp in q_lower:
                return f"Condition '{fp}' is not tracked in the clinical warehouse dataset."
        for oos in OUT_OF_SCOPE_PATTERNS:
            if oos in q_lower:
                return "The question is outside the scope of hospital clinical and financial operations."
        return None

    def _execute_sql(self, sql: str) -> pd.DataFrame:
        with managed_connection(self.db_path) as conn:
            return pd.read_sql(sql, conn)

    def _synthesize_answer(
        self, metric: MetricDefinition, df: pd.DataFrame, params: Dict[str, Any]
    ) -> str:
        """Formulate a deterministic, citation-grounded clinical response."""
        if df.empty:
            return f"No records found for {metric.display_name} with parameters {params}."

        row = df.iloc[0]

        if metric.name == "readmission_rate_overall":
            rate = row["readmission_rate"]
            pts = int(row.get("total_patients", 0))
            return f"The overall 30-day hospital readmission rate is {rate:.1f}% across {pts:,} total patients."

        if metric.name == "readmission_rate_by_condition":
            cond = row["condition"]
            rate = row["readmission_rate"]
            readmitted = int(row.get("readmitted_count", 0))
            total = int(row.get("total_patients", 0))
            return f"The readmission rate for {cond} is {rate:.1f}% ({readmitted:,} of {total:,} patients readmitted)."

        if metric.name == "avg_cost_overall":
            cost = row["avg_cost"]
            tot = row.get("total_expenditure", 0)
            return f"The average treatment cost is ${cost:,.2f} across all encounters (total expenditure: ${tot:,.2f})."

        if metric.name == "avg_cost_by_condition":
            cond = row["condition"]
            avg_c = row["avg_cost"]
            min_c = row.get("min_cost", 0)
            max_c = row.get("max_cost", 0)
            return f"The average cost for {cond} is ${avg_c:,.2f} (range: ${min_c:,.2f} – ${max_c:,.2f})."

        if metric.name == "top_expensive_conditions":
            items = [f"{r['condition']} (${r['avg_cost']:,.2f})" for _, r in df.iterrows()]
            return f"The most expensive conditions by average treatment cost are: {', '.join(items)}."

        if metric.name == "avg_length_of_stay":
            los = row["avg_los"]
            return f"The average patient length of stay is {los:.1f} days."

        if metric.name == "patient_count_by_condition":
            cond = row["condition"]
            cnt = int(row["patient_count"])
            avg_c = row.get("avg_cost", 0)
            return f"There are {cnt:,} patients diagnosed with {cond} (average cost: ${avg_c:,.2f})."

        if metric.name == "gender_analytics":
            summary = [f"{r['gender']}: {int(r['patient_count']):,} patients (avg cost ${r['avg_cost']:,.2f})" for _, r in df.iterrows()]
            return f"Patient volume and costs by gender: {'; '.join(summary)}."

        if metric.name == "patient_satisfaction":
            sat = row["avg_satisfaction"]
            tot = int(row.get("total_ratings", 0))
            return f"The average patient satisfaction rating is {sat:.2f} out of 5 across {tot:,} responses."

        if metric.name == "discharge_outcomes":
            summary = [f"{r['outcome']}: {int(r['patient_count']):,} patients" for _, r in df.iterrows()]
            return f"Discharge clinical outcomes breakdown: {'; '.join(summary)}."

        return f"{metric.display_name} result: {df.to_dict(orient='records')}."
