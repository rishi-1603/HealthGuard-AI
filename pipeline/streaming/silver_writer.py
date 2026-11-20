"""
DE-010: Silver Streaming Writer — idempotent upserts of windowed aggregates into DuckDB Silver tables.

Design goals:
  - Idempotent: re-running the same WindowedAggregate produces identical rows (upsert by window_id).
  - In-process DuckDB connection (no external DB server required).
  - Zero external dependencies beyond duckdb (already installed).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import duckdb

from pipeline.streaming.stream_processor import WindowedAggregate

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS silver_streaming_windows (
    window_id               VARCHAR PRIMARY KEY,
    event_type              VARCHAR NOT NULL,
    window_start            VARCHAR NOT NULL,
    window_end              VARCHAR NOT NULL,
    event_count             INTEGER NOT NULL,
    unique_patients         INTEGER NOT NULL,
    avg_processing_latency_ms DOUBLE NOT NULL,
    written_at              VARCHAR DEFAULT CAST(now() AS VARCHAR)
);
"""


class SilverStreamWriter:
    """
    Writes WindowedAggregate records to a DuckDB-backed Silver table.
    Accepts an optional `db_path`; if None, opens an in-memory DuckDB instance.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path
        self._conn: Optional[duckdb.DuckDBPyConnection] = None

    # ------------------------------------------------------------------
    # Context manager interface
    # ------------------------------------------------------------------
    def __enter__(self) -> "SilverStreamWriter":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def connect(self) -> None:
        path = self._db_path or ":memory:"
        self._conn = duckdb.connect(path)
        self._conn.execute(_DDL)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------
    def upsert_aggregates(self, aggregates: List[WindowedAggregate]) -> int:
        """
        Idempotently insert or replace windowed aggregates.
        Returns the number of records written.
        """
        if not self._conn:
            raise RuntimeError("SilverStreamWriter is not connected. Call connect() first.")
        written = 0
        for agg in aggregates:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO silver_streaming_windows (
                    window_id, event_type, window_start, window_end,
                    event_count, unique_patients, avg_processing_latency_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    agg.window_id,
                    agg.event_type,
                    agg.window_start.isoformat(),
                    agg.window_end.isoformat(),
                    agg.event_count,
                    agg.unique_patients,
                    agg.avg_processing_latency_ms,
                ],
            )
            written += 1
        logger.info("Upserted %d windowed aggregates to silver_streaming_windows", written)
        return written

    def query_window_counts(self) -> List[Dict[str, object]]:
        """Return all rows ordered by event_type, window_start for verification."""
        if not self._conn:
            raise RuntimeError("Not connected.")
        rows = self._conn.execute(
            "SELECT * FROM silver_streaming_windows ORDER BY event_type, window_start"
        ).fetchall()
        cols = [d[0] for d in self._conn.description]
        return [dict(zip(cols, row)) for row in rows]

    def total_rows(self) -> int:
        if not self._conn:
            return 0
        result = self._conn.execute(
            "SELECT COUNT(*) FROM silver_streaming_windows"
        ).fetchone()
        return int(result[0]) if result else 0
