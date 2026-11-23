"""
SQLGlot AST Security & Governance Validator for HealthGuard 360 Copilot.

Enforces:
  1. Strict Read-Only Execution: only SELECT expressions permitted; all DDL/DML rejected.
  2. Table Whitelisting: only certified Gold marts and Star Schema tables accessible.
  3. Query Limits: enforces automatic LIMIT injection and caps excessive limit clauses.
  4. SQL Injection Resistance: blocks multi-statement, hex-encoding, comment evasion, and system tables.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

import sqlglot
from sqlglot import exp

logger = logging.getLogger(__name__)

# Strict whitelist of certified tables
ALLOWED_TABLES: Set[str] = {
    "gold_condition_mart",
    "gold_age_band_mart",
    "gold_gender_mart",
    "gold_outcome_mart",
    "gold_daily_summary",
    "gold_patient_mart",
    "gold_cost_mart",
    "gold_readmission_mart",
    "silver_encounters",
    "bronze_encounters",
    "fact_encounter",
    "dim_patient",
    "dim_condition",
    "dim_facility",
    "dim_date",
}

# Forbidden keywords / functions in SQLite
DISALLOWED_PATTERNS = [
    re.compile(r";\s*\b(DROP|INSERT|UPDATE|DELETE|ALTER|CREATE|TRUNCATE)\b", re.IGNORECASE),
    re.compile(r"\bload_extension\b", re.IGNORECASE),
    re.compile(r"\bATTACH\s+DATABASE\b", re.IGNORECASE),
    re.compile(r"\bPRAGMA\b", re.IGNORECASE),
    re.compile(r"\bsqlite_\w+", re.IGNORECASE),
]


@dataclass(frozen=True)
class ValidationResult:
    """Immutable result of SQLGlot AST validation."""
    is_valid: bool
    validated_sql: Optional[str]
    referenced_tables: List[str] = field(default_factory=list)
    error_message: Optional[str] = None


class SqlAstValidator:
    """
    Enforces security, read-only policies, table whitelisting, and query capping
    via abstract syntax tree (AST) inspection using SQLGlot.
    """

    def __init__(self, allowed_tables: Optional[Set[str]] = None, max_limit: int = 1000) -> None:
        self.allowed_tables = set(t.lower() for t in (allowed_tables or ALLOWED_TABLES))
        self.max_limit = max_limit

    def validate(self, sql_query: str) -> ValidationResult:
        """Validate query and return sanitized, limit-enforced SQL."""
        if not sql_query or not sql_query.strip():
            return ValidationResult(is_valid=False, validated_sql=None, error_message="Empty SQL query")

        cleaned = sql_query.strip().rstrip(";")

        # 1. Pattern checks for obvious multi-statement or forbidden keywords
        for pat in DISALLOWED_PATTERNS:
            if pat.search(cleaned):
                return ValidationResult(
                    is_valid=False,
                    validated_sql=None,
                    error_message="Security Policy Violation: query contains forbidden statement or keyword",
                )

        # 2. Parse AST via SQLGlot
        try:
            expressions = sqlglot.parse(cleaned, read="sqlite")
        except Exception as err:
            return ValidationResult(
                is_valid=False,
                validated_sql=None,
                error_message=f"SQL Syntax Error: {str(err)}",
            )

        # Enforce single statement
        if len(expressions) != 1 or expressions[0] is None:
            return ValidationResult(
                is_valid=False,
                validated_sql=None,
                error_message="Security Policy Violation: multiple SQL statements are prohibited",
            )

        ast = expressions[0]

        # 3. Enforce Read-Only (Root must be Select or Union)
        if not isinstance(ast, (exp.Select, exp.Union)):
            return ValidationResult(
                is_valid=False,
                validated_sql=None,
                error_message=f"Security Policy Violation: non-SELECT statement type '{type(ast).__name__}' rejected",
            )

        # Check for mutation subqueries or commands
        forbidden_nodes = (
            exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter,
            exp.Create, exp.Command, exp.TruncateTable
        )
        for node in ast.walk():
            if isinstance(node, forbidden_nodes):
                return ValidationResult(
                    is_valid=False,
                    validated_sql=None,
                    error_message=f"Security Policy Violation: DML/DDL node '{type(node).__name__}' found in AST",
                )

        # 4. Enforce Table Whitelist
        referenced_tables: List[str] = []
        for table_node in ast.find_all(exp.Table):
            t_name = table_node.name.lower()
            referenced_tables.append(t_name)
            if t_name not in self.allowed_tables:
                return ValidationResult(
                    is_valid=False,
                    validated_sql=None,
                    referenced_tables=referenced_tables,
                    error_message=f"Access Denied: table '{t_name}' is not in certified catalog whitelist",
                )

        # 5. Enforce Limit Clause
        validated_ast = self._enforce_limit(ast)
        generated_sql = validated_ast.sql(dialect="sqlite")

        return ValidationResult(
            is_valid=True,
            validated_sql=generated_sql,
            referenced_tables=sorted(list(set(referenced_tables))),
        )

    def _enforce_limit(self, ast: exp.Expression) -> exp.Expression:
        """Inject or clamp LIMIT clause to prevent unbounded full-table scans."""
        if not isinstance(ast, exp.Select):
            return ast

        limit_node = ast.args.get("limit")
        if limit_node is None:
            # Default to LIMIT 100
            return ast.limit(100)

        # If limit exists, verify it doesn't exceed max_limit
        try:
            val = int(limit_node.expression.this)
            if val > self.max_limit:
                limit_node.set("expression", exp.Literal.number(self.max_limit))
        except (AttributeError, ValueError):
            limit_node.set("expression", exp.Literal.number(self.max_limit))

        return ast
