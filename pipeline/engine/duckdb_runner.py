"""DuckDB high-performance analytical OLAP engine.

Provides in-memory and persistent columnar execution, parameterized queries,
DataFrame registrations, and pre-computed analytical healthcare aggregations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
import duckdb
import pandas as pd

logger = logging.getLogger(__name__)


class DuckDBEngine:
    """Wrapper around DuckDB for high-speed analytical queries."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = str(db_path) if db_path else ":memory:"
        self._con: duckdb.DuckDBPyConnection | None = duckdb.connect(self.db_path)
        logger.debug(f"DuckDBEngine connected to {self.db_path}")

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        if self._con is None:
            raise RuntimeError("DuckDB connection is closed.")
        return self._con

    def execute_query(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> pd.DataFrame:
        """Execute SQL query and return immutable pandas DataFrame."""
        if params is not None:
            return self.connection.execute(sql, params).df()
        return self.connection.execute(sql).df()

    def query_scalar(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> Any:
        """Execute SQL query and return a single scalar value."""
        if params is not None:
            result = self.connection.execute(sql, params).fetchone()
        else:
            result = self.connection.execute(sql).fetchone()
        return result[0] if result else None

    def register_df(self, view_name: str, df: pd.DataFrame) -> None:
        """Register a pandas DataFrame as a virtual view in DuckDB."""
        self.connection.register(view_name, df)

    def unregister_df(self, view_name: str) -> None:
        """Unregister a virtual view in DuckDB."""
        self.connection.unregister(view_name)

    def _resolve_col(self, view_name: str, candidates: list[str]) -> str:
        """Find the matching column name in view from a list of candidates."""
        schema_df = self.connection.execute(f"DESCRIBE {view_name}").df()
        cols = set(schema_df["column_name"].str.lower())
        for c in candidates:
            if c.lower() in cols:
                # Return the actual casing in table
                for actual in schema_df["column_name"]:
                    if actual.lower() == c.lower():
                        return actual
        return candidates[0]

    def compute_condition_metrics(self, view_name: str = "silver") -> pd.DataFrame:
        """Calculate condition-level metrics matching Gold mart definitions."""
        cond_col = self._resolve_col(view_name, ["condition", "Condition"])
        cost_col = self._resolve_col(view_name, ["cost", "Cost"])
        los_col = self._resolve_col(view_name, ["length_of_stay", "Length_of_Stay"])
        readmit_col = self._resolve_col(view_name, ["readmission_flag", "readmission"])

        sql = f"""
            SELECT
                {cond_col} AS Condition,
                COUNT(*) AS patient_count,
                ROUND(AVG({cost_col}), 2) AS avg_cost,
                ROUND(AVG({los_col}), 2) AS avg_los,
                SUM(CAST({readmit_col} AS INT)) AS readmission_count,
                ROUND(SUM(CAST({readmit_col} AS INT)) * 100.0 / COUNT(*), 2) AS readmission_rate_pct
            FROM {view_name}
            GROUP BY {cond_col}
            ORDER BY patient_count DESC
        """
        return self.execute_query(sql)

    def compute_age_band_metrics(self, view_name: str = "silver") -> pd.DataFrame:
        """Calculate age-band metrics matching Gold mart definitions."""
        age_col = self._resolve_col(view_name, ["age_band", "Age_Band"])
        cost_col = self._resolve_col(view_name, ["cost", "Cost"])
        los_col = self._resolve_col(view_name, ["length_of_stay", "Length_of_Stay"])
        readmit_col = self._resolve_col(view_name, ["readmission_flag", "readmission"])

        sql = f"""
            SELECT
                {age_col} AS age_band,
                COUNT(*) AS patient_count,
                ROUND(AVG({cost_col}), 2) AS avg_cost,
                ROUND(AVG({los_col}), 2) AS avg_los,
                SUM(CAST({readmit_col} AS INT)) AS readmission_count,
                ROUND(SUM(CAST({readmit_col} AS INT)) * 100.0 / COUNT(*), 2) AS readmission_rate_pct
            FROM {view_name}
            GROUP BY {age_col}
            ORDER BY patient_count DESC
        """
        return self.execute_query(sql)

    def compute_cost_percentiles(self, view_name: str = "silver") -> dict[str, float]:
        """Compute key cost distribution percentiles (p25, p50, p75, p90)."""
        cost_col = self._resolve_col(view_name, ["cost", "Cost"])
        sql = f"""
            SELECT
                ROUND(QUANTILE_CONT({cost_col}, 0.25), 2) AS p25,
                ROUND(QUANTILE_CONT({cost_col}, 0.50), 2) AS p50,
                ROUND(QUANTILE_CONT({cost_col}, 0.75), 2) AS p75,
                ROUND(QUANTILE_CONT({cost_col}, 0.90), 2) AS p90
            FROM {view_name}
        """
        df = self.execute_query(sql)
        row = df.iloc[0]
        return {
            "p25": float(row["p25"]),
            "p50": float(row["p50"]),
            "p75": float(row["p75"]),
            "p90": float(row["p90"]),
        }

    def close(self) -> None:
        """Close connection and free resources."""
        if self._con is not None:
            self._con.close()
            self._con = None

    def __enter__(self) -> DuckDBEngine:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
