"""dbt model compiler, dependency graph builder, and DAG sorter (DE-007)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DbtModel:
    """Represents a discovered dbt model and its metadata."""

    name: str
    path: Path
    layer: str  # 'staging', 'intermediate', 'marts'
    raw_sql: str
    materialized: str = "table"
    unique_key: str | None = None
    depends_on: list[str] = field(default_factory=list)
    sources: list[tuple[str, str]] = field(default_factory=list)


class DbtCompiler:
    """Discovers, parses, and compiles dbt SQL models into executable queries."""

    def __init__(self, project_dir: Path | str) -> None:
        self.project_dir = Path(project_dir)
        self.models_dir = self.project_dir / "models"
        self._models_cache: dict[str, DbtModel] | None = None

    def discover_models(self) -> list[DbtModel]:
        """Scan models directory and parse all model metadata."""
        if self._models_cache is not None:
            return list(self._models_cache.values())

        models: dict[str, DbtModel] = {}
        for sql_file in self.models_dir.rglob("*.sql"):
            raw_sql = sql_file.read_text(encoding="utf-8")
            model_name = sql_file.stem

            # Determine layer
            rel_parts = sql_file.relative_to(self.models_dir).parts
            layer = rel_parts[0] if len(rel_parts) > 1 else "default"

            # Parse {{ config(...) }}
            materialized = "table"
            unique_key = None
            config_match = re.search(r"\{\{\s*config\s*\((.*?)\)\s*\}\}", raw_sql, re.DOTALL)
            if config_match:
                cfg_str = config_match.group(1)
                mat_m = re.search(r"materialized\s*=\s*['\"]([^'\"]+)['\"]", cfg_str)
                if mat_m:
                    materialized = mat_m.group(1)
                uk_m = re.search(r"unique_key\s*=\s*['\"]([^'\"]+)['\"]", cfg_str)
                if uk_m:
                    unique_key = uk_m.group(1)

            # Parse {{ ref('...') }}
            refs = re.findall(r"\{\{\s*ref\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}", raw_sql)

            # Parse {{ source('...', '...') }}
            sources = re.findall(
                r"\{\{\s*source\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}",
                raw_sql,
            )

            models[model_name] = DbtModel(
                name=model_name,
                path=sql_file,
                layer=layer,
                raw_sql=raw_sql,
                materialized=materialized,
                unique_key=unique_key,
                depends_on=list(dict.fromkeys(refs)),  # deduplicate preserving order
                sources=sources,
            )

        self._models_cache = models
        return list(models.values())

    def get_model(self, name: str) -> DbtModel:
        """Fetch a single model by name."""
        self.discover_models()
        assert self._models_cache is not None
        if name not in self._models_cache:
            raise KeyError(f"dbt model '{name}' not found in {self.models_dir}")
        return self._models_cache[name]

    def get_execution_order(self) -> list[str]:
        """Perform topological sort on model dependency DAG (Kahn's algorithm)."""
        models = self.discover_models()
        graph: dict[str, set[str]] = {m.name: set(m.depends_on) for m in models}
        in_degree: dict[str, int] = {m.name: 0 for m in models}

        # Calculate in-degrees (number of dependencies within the models)
        for m in models:
            for dep in m.depends_on:
                if dep in graph:
                    pass  # m depends on dep
            in_degree[m.name] = len([dep for dep in m.depends_on if dep in graph])

        queue = [name for name, deg in in_degree.items() if deg == 0]
        # Sort queue deterministically
        queue.sort()
        ordered: list[str] = []

        while queue:
            current = queue.pop(0)
            ordered.append(current)

            # Find all models that depend on current
            for m in models:
                if current in m.depends_on and m.name not in ordered:
                    in_degree[m.name] -= 1
                    if in_degree[m.name] == 0:
                        queue.append(m.name)
                        queue.sort()

        if len(ordered) != len(models):
            unresolved = set(graph.keys()) - set(ordered)
            raise ValueError(f"Cyclic dependency detected among dbt models: {unresolved}")

        return ordered

    def compile_model(
        self,
        name: str,
        is_incremental: bool = False,
        this_table: str | None = None,
    ) -> str:
        """Compile a model's Jinja templates into valid ANSI / DuckDB SQL."""
        model = self.get_model(name)
        sql = model.raw_sql

        # 1. Remove {{ config(...) }}
        sql = re.sub(r"\{\{\s*config\s*\([^)]*\)\s*\}\}", "", sql, flags=re.DOTALL)

        # 2. Handle {% if is_incremental() %} ... {% endif %}
        def _replace_inc(match: re.Match) -> str:
            body = match.group(1)
            return body if is_incremental else ""

        sql = re.sub(
            r"\{%\s*if\s+is_incremental\(\)\s*%\}(.*?)\{%\s*endif\s*%\}",
            _replace_inc,
            sql,
            flags=re.DOTALL,
        )

        # 3. Replace {{ this }}
        target = this_table or name
        sql = re.sub(r"\{\{\s*this\s*\}\}", target, sql)

        # 4. Replace {{ ref('...') }} -> model_name
        sql = re.sub(r"\{\{\s*ref\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}", r"\1", sql)

        # 5. Replace {{ source('s', 't') }} -> s.t
        sql = re.sub(
            r"\{\{\s*source\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}",
            r"\1.\2",
            sql,
        )

        return sql.strip()
