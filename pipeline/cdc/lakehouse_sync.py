"""Lakehouse CDC synchronization, Bronze landing, and Silver compaction (DE-008)."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from pipeline.config import PipelineConfig
from pipeline.cdc.models import CdcEvent, CdcOp

logger = logging.getLogger(__name__)

_CDC_LAKEHOUSE_DDL = """
-- Bronze raw immutable CDC changelog table
CREATE TABLE IF NOT EXISTS bronze_cdc_events (
    event_id        TEXT PRIMARY KEY,
    lsn             INTEGER NOT NULL,
    tx_id           INTEGER NOT NULL,
    table_name      TEXT NOT NULL,
    op              TEXT NOT NULL,
    ts_ms           INTEGER NOT NULL,
    payload_json    TEXT NOT NULL,
    synced_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cdc_lsn   ON bronze_cdc_events(lsn);
CREATE INDEX IF NOT EXISTS idx_cdc_table ON bronze_cdc_events(table_name);

-- Silver current-state compacted operational table
CREATE TABLE IF NOT EXISTS silver_operational_encounters (
    encounter_id      TEXT PRIMARY KEY,
    patient_id        TEXT NOT NULL,
    admit_time        TEXT NOT NULL,
    discharge_time    TEXT,
    department        TEXT NOT NULL,
    condition_code    TEXT NOT NULL,
    billing_amount    REAL NOT NULL,
    status            TEXT NOT NULL,
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    last_lsn          INTEGER NOT NULL,
    last_updated_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_silver_ops_patient ON silver_operational_encounters(patient_id);
CREATE INDEX IF NOT EXISTS idx_silver_ops_status  ON silver_operational_encounters(status);
"""


class LakehouseCdcSync:
    """Synchronizes Debezium CDC events to Lakehouse Bronze and compacts into Silver."""

    def __init__(self, cfg: PipelineConfig, parquet_root: Path | None = None) -> None:
        self.cfg = cfg
        self.db_path = cfg.warehouse_db
        self.parquet_root = (
            parquet_root or (cfg.warehouse_db.parent / "bronze" / "cdc_events")
        )
        self.parquet_root.mkdir(parents=True, exist_ok=True)
        self._init_ddl()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_ddl(self) -> None:
        conn = self._get_connection()
        try:
            conn.executescript(_CDC_LAKEHOUSE_DDL)
            conn.commit()
        finally:
            conn.close()

    def sync_to_bronze(self, events: list[CdcEvent]) -> int:
        """Insert events into Bronze changelog table idempotently (INSERT OR IGNORE)."""
        if not events:
            return 0

        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        inserted = 0
        try:
            for ev in events:
                op_val = ev.op.value if isinstance(ev.op, CdcOp) else str(ev.op)
                payload_str = json.dumps(ev.payload)

                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO bronze_cdc_events (
                        event_id, lsn, tx_id, table_name, op, ts_ms, payload_json, synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ev.event_id,
                        ev.lsn,
                        ev.tx_id,
                        ev.table,
                        op_val,
                        ev.ts_ms,
                        payload_str,
                        now_iso,
                    ),
                )
                if cur.rowcount > 0:
                    inserted += 1

            conn.commit()
            return inserted
        finally:
            conn.close()

    def write_bronze_parquet(self, events: list[CdcEvent]) -> Path:
        """Write a batch of CDC events to a partitioned Parquet file."""
        if not events:
            raise ValueError("No events to write to Parquet")

        rows = []
        for ev in events:
            rows.append({
                "event_id": ev.event_id,
                "lsn": ev.lsn,
                "tx_id": ev.tx_id,
                "table_name": ev.table,
                "op": ev.op.value if isinstance(ev.op, CdcOp) else str(ev.op),
                "ts_ms": ev.ts_ms,
                "payload_json": json.dumps(ev.payload),
            })

        df = pd.DataFrame(rows)
        batch_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        target_file = self.parquet_root / f"cdc_batch_{batch_ts}.parquet"

        table = pa.Table.from_pandas(df)
        pq.write_table(table, str(target_file), compression="SNAPPY")
        return target_file

    def compact_to_silver(self) -> int:
        """Compact Bronze CDC changelog into Silver current-state table using LSN watermarking.
        
        Guarantees that older LSN records never overwrite newer state.
        """
        conn = self._get_connection()
        compacted_count = 0
        try:
            # Read all CDC events in chronological LSN order
            rows = conn.execute(
                """
                SELECT event_id, lsn, op, payload_json
                FROM bronze_cdc_events
                WHERE table_name = 'operational_encounters'
                ORDER BY lsn ASC
                """
            ).fetchall()

            for r in rows:
                lsn = r["lsn"]
                op = r["op"]
                payload = json.loads(r["payload_json"])

                if op in ("c", "u"):
                    after = payload.get("after")
                    if not after:
                        continue

                    enc_id = after["encounter_id"]

                    # Check current Silver state LSN
                    existing = conn.execute(
                        "SELECT last_lsn FROM silver_operational_encounters WHERE encounter_id = ?",
                        (enc_id,),
                    ).fetchone()

                    # If existing record has a HIGHER or EQUAL LSN, reject this older event
                    if existing is not None and existing["last_lsn"] >= lsn:
                        continue

                    now_iso = datetime.now(timezone.utc).isoformat()
                    conn.execute(
                        """
                        INSERT INTO silver_operational_encounters (
                            encounter_id, patient_id, admit_time, discharge_time,
                            department, condition_code, billing_amount, status,
                            is_deleted, last_lsn, last_updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(encounter_id) DO UPDATE SET
                            patient_id = excluded.patient_id,
                            admit_time = excluded.admit_time,
                            discharge_time = excluded.discharge_time,
                            department = excluded.department,
                            condition_code = excluded.condition_code,
                            billing_amount = excluded.billing_amount,
                            status = excluded.status,
                            is_deleted = excluded.is_deleted,
                            last_lsn = excluded.last_lsn,
                            last_updated_at = excluded.last_updated_at
                        """,
                        (
                            enc_id,
                            after["patient_id"],
                            after["admit_time"],
                            after.get("discharge_time"),
                            after["department"],
                            after["condition_code"],
                            float(after["billing_amount"]),
                            after["status"],
                            int(after.get("is_deleted", 0)),
                            lsn,
                            now_iso,
                        ),
                    )
                    compacted_count += 1

                elif op == "d":
                    before = payload.get("before")
                    if not before:
                        continue
                    enc_id = before["encounter_id"]

                    existing = conn.execute(
                        "SELECT last_lsn FROM silver_operational_encounters WHERE encounter_id = ?",
                        (enc_id,),
                    ).fetchone()

                    if existing is not None and existing["last_lsn"] >= lsn:
                        continue

                    conn.execute(
                        "DELETE FROM silver_operational_encounters WHERE encounter_id = ?",
                        (enc_id,),
                    )
                    compacted_count += 1

            conn.commit()
            return compacted_count
        finally:
            conn.close()

    def get_silver_state(self, encounter_id: str) -> dict[str, Any] | None:
        """Fetch current compacted state of an encounter from Silver."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM silver_operational_encounters WHERE encounter_id = ?",
                (encounter_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
