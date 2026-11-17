"""dbt executor, schema test runner, and automated lineage generator (DE-007)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import yaml

from pipeline.dbt.compiler import DbtCompiler, DbtModel

logger = logging.getLogger(__name__)


@dataclass
class DbtTestRun:
    """Result of an individual dbt schema test execution."""

    model_name: str
    column_name: str
    test_type: str  # 'unique', 'not_null', 'accepted_values', 'relationships'
    passed: bool
    error_count: int
    details: str


@dataclass
class DbtTestResult:
    """Summary of all dbt schema test runs."""

    passed: bool
    total_tests: int
    test_runs: list[DbtTestRun] = field(default_factory=list)

    @property
    def failures(self) -> list[DbtTestRun]:
        return [t for t in self.test_runs if not t.passed]


@dataclass
class DbtExecutionResult:
    """Result of model materialization run."""

    success: bool
    models_executed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class DbtRunner:
    """Executes dbt models and schema tests against an analytical DuckDB instance."""

    def __init__(
        self,
        project_dir: Path | str,
        con: duckdb.DuckDBPyConnection | None = None,
        db_path: Path | str | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.compiler = DbtCompiler(self.project_dir)
        if con is not None:
            self.con = con
        elif db_path is not None:
            self.con = duckdb.connect(str(db_path))
        else:
            self.con = duckdb.connect(":memory:")

    def run(
        self,
        models: list[str] | None = None,
        full_refresh: bool = False,
    ) -> DbtExecutionResult:
        """Execute dbt models in topological order with incremental support."""
        all_ordered = self.compiler.get_execution_order()
        target_models = (
            [m for m in all_ordered if m in models] if models is not None else all_ordered
        )

        executed: list[str] = []
        errors: list[str] = []

        for name in target_models:
            model = self.compiler.get_model(name)
            try:
                # Check if target table already exists in DuckDB
                table_check = self.con.execute(
                    "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
                    [name],
                ).fetchone()
                table_exists = table_check is not None and table_check[0] > 0

                is_inc = (
                    model.materialized == "incremental"
                    and not full_refresh
                    and table_exists
                )

                compiled_sql = self.compiler.compile_model(name, is_incremental=is_inc)

                if model.materialized == "view":
                    self.con.execute(f"CREATE OR REPLACE VIEW {name} AS {compiled_sql}")
                elif model.materialized == "table":
                    self.con.execute(f"CREATE OR REPLACE TABLE {name} AS {compiled_sql}")
                elif model.materialized == "incremental":
                    if not is_inc:
                        self.con.execute(f"CREATE OR REPLACE TABLE {name} AS {compiled_sql}")
                    else:
                        if model.unique_key:
                            self.con.execute(
                                f"CREATE TEMP TABLE _stg_{name} AS {compiled_sql}"
                            )
                            self.con.execute(
                                f"DELETE FROM {name} WHERE {model.unique_key} IN "
                                f"(SELECT {model.unique_key} FROM _stg_{name})"
                            )
                            self.con.execute(
                                f"INSERT INTO {name} SELECT * FROM _stg_{name}"
                            )
                            self.con.execute(f"DROP TABLE _stg_{name}")
                        else:
                            self.con.execute(f"INSERT INTO {name} {compiled_sql}")

                executed.append(name)
            except Exception as e:
                logger.exception("Failed materializing dbt model %s", name)
                errors.append(f"{name}: {e}")
                return DbtExecutionResult(success=False, models_executed=executed, errors=errors)

        return DbtExecutionResult(success=True, models_executed=executed)

    def test(self, models: list[str] | None = None) -> DbtTestResult:
        """Discover and execute all schema tests defined in schema.yml files."""
        test_runs: list[DbtTestRun] = []

        for yml_file in (self.project_dir / "models").rglob("*.yml"):
            if yml_file.name == "sources.yml":
                continue

            try:
                content = yaml.safe_load(yml_file.read_text(encoding="utf-8"))
            except Exception:
                continue

            if not content or "models" not in content:
                continue

            for m_entry in content["models"]:
                m_name = m_entry.get("name")
                if not m_name or (models is not None and m_name not in models):
                    continue

                columns = m_entry.get("columns", [])
                for col in columns:
                    c_name = col.get("name")
                    tests = col.get("tests", [])

                    for t_def in tests:
                        run = self._execute_test(m_name, c_name, t_def)
                        test_runs.append(run)

        passed = all(t.passed for t in test_runs)
        return DbtTestResult(passed=passed, total_tests=len(test_runs), test_runs=test_runs)

    def _execute_test(self, model: str, column: str, test_def: Any) -> DbtTestRun:
        """Run an individual test definition against DuckDB."""
        if isinstance(test_def, str):
            test_type = test_def
            params: dict[str, Any] = {}
        elif isinstance(test_def, dict):
            test_type = next(iter(test_def.keys()))
            params = test_def[test_type] or {}
        else:
            return DbtTestRun(model, column, "unknown", False, 1, f"Invalid test def: {test_def}")

        try:
            if test_type == "unique":
                query = (
                    f"SELECT {column}, count(*) FROM {model} "
                    f"GROUP BY {column} HAVING count(*) > 1"
                )
                res = self.con.execute(query).fetchall()
                passed = len(res) == 0
                return DbtTestRun(model, column, test_type, passed, len(res), f"{len(res)} duplicate keys found")

            elif test_type == "not_null":
                query = f"SELECT count(*) FROM {model} WHERE {column} IS NULL"
                val = self.con.execute(query).fetchone()[0]
                passed = val == 0
                return DbtTestRun(model, column, test_type, passed, val, f"{val} null rows found")

            elif test_type == "accepted_values":
                allowed = params.get("values", [])
                formatted = ", ".join(
                    f"'{v}'" if isinstance(v, str) else str(v) for v in allowed
                )
                query = f"SELECT count(*) FROM {model} WHERE {column} NOT IN ({formatted})"
                val = self.con.execute(query).fetchone()[0]
                passed = val == 0
                return DbtTestRun(model, column, test_type, passed, val, f"{val} unacceptable values found")

            elif test_type == "relationships":
                to_ref = params.get("to", "")
                to_field = params.get("field", "")
                # resolve ref('target') -> target
                m = re.search(r"ref\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", to_ref)
                target_table = m.group(1) if m else to_ref

                query = (
                    f"SELECT count(*) FROM {model} "
                    f"WHERE {column} IS NOT NULL AND {column} NOT IN "
                    f"(SELECT {to_field} FROM {target_table})"
                )
                val = self.con.execute(query).fetchone()[0]
                passed = val == 0
                return DbtTestRun(
                    model,
                    column,
                    test_type,
                    passed,
                    val,
                    f"{val} orphaned records without parent {target_table}.{to_field}",
                )

            else:
                return DbtTestRun(model, column, test_type, False, 1, f"Unsupported test {test_type}")
        except Exception as e:
            return DbtTestRun(model, column, test_type, False, 1, f"Test execution error: {e}")

    def generate_lineage(self) -> dict[str, list[dict[str, Any]]]:
        """Generate dependency lineage graph of sources, staging, intermediate, and marts."""
        models = self.compiler.discover_models()
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []

        seen_sources: set[str] = set()

        for m in models:
            nodes.append({
                "id": m.name,
                "layer": m.layer,
                "materialization": m.materialized,
                "type": "model",
            })
            for s_source, s_table in m.sources:
                src_id = f"{s_source}.{s_table}"
                if src_id not in seen_sources:
                    nodes.append({
                        "id": src_id,
                        "layer": "source",
                        "materialization": "source",
                        "type": "source",
                    })
                    seen_sources.add(src_id)
                edges.append({"source": src_id, "target": m.name})

            for dep in m.depends_on:
                edges.append({"source": dep, "target": m.name})

        return {"nodes": nodes, "edges": edges}

    def render_lineage_markdown(self) -> str:
        """Render markdown documentation table for the automated lineage."""
        models = self.compiler.discover_models()
        lines = [
            "### HealthGuard 360 dbt Model Lineage & Transformation Spec",
            "",
            "| Model | Layer | Materialization | Depends On |",
            "| :--- | :--- | :--- | :--- |",
        ]

        for m in sorted(models, key=lambda x: (x.layer, x.name)):
            deps = ", ".join(m.depends_on + [f"{s[0]}.{s[1]}" for s in m.sources]) or "None"
            lines.append(f"| `{m.name}` | **{m.layer}** | `{m.materialized}` | {deps} |")

        return "\n".join(lines)
