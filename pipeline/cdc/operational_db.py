"""Operational PostgreSQL / SQLite EHR database with transaction WAL logging (DE-008)."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_OPERATIONAL_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS operational_encounters (
    encounter_id      TEXT PRIMARY KEY,
    patient_id        TEXT NOT NULL,
    admit_time        TEXT NOT NULL,
    discharge_time    TEXT,
    department        TEXT NOT NULL,
    condition_code    TEXT NOT NULL,
    billing_amount    REAL NOT NULL,
    status            TEXT NOT NULL DEFAULT 'ADMITTED',
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operational_wal_log (
    wal_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    lsn               INTEGER NOT NULL,
    tx_id             INTEGER NOT NULL,
    ts_ms             INTEGER NOT NULL,
    op_type           TEXT NOT NULL,
    table_name        TEXT NOT NULL,
    record_id         TEXT NOT NULL,
    before_json       TEXT,
    after_json        TEXT
);

CREATE INDEX IF NOT EXISTS idx_wal_lsn ON operational_wal_log(lsn);
"""


class OperationalEhrDb:
    """Operational transactional EHR database managing live patient encounter operations."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        try:
            conn.executescript(_OPERATIONAL_SCHEMA_DDL)
            conn.commit()
        finally:
            conn.close()

    def get_table_names(self) -> list[str]:
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            return [r[0] for r in rows]
        finally:
            conn.close()

    def _next_lsn(self, conn: sqlite3.Connection) -> tuple[int, int]:
        """Return (next_lsn, next_tx_id)."""
        row = conn.execute(
            "SELECT coalesce(max(lsn), 1000) as max_lsn, coalesce(max(tx_id), 100) as max_tx FROM operational_wal_log"
        ).fetchone()
        next_lsn = row["max_lsn"] + 1
        next_tx = row["max_tx"] + 1
        return next_lsn, next_tx

    def insert_encounter(
        self,
        patient_id: str,
        admit_time: str,
        department: str,
        condition_code: str,
        billing_amount: float,
        encounter_id: str | None = None,
    ) -> str:
        """Insert a new clinical encounter and append to transaction WAL."""
        enc_id = encounter_id or f"ENC-{uuid.uuid4().hex[:8].upper()}"
        now_iso = datetime.now(timezone.utc).isoformat()
        ts_ms = int(time.time() * 1000)

        conn = self._get_connection()
        try:
            lsn, tx_id = self._next_lsn(conn)
            record = {
                "encounter_id": enc_id,
                "patient_id": patient_id,
                "admit_time": admit_time,
                "discharge_time": None,
                "department": department,
                "condition_code": condition_code,
                "billing_amount": float(billing_amount),
                "status": "ADMITTED",
                "is_deleted": 0,
                "created_at": now_iso,
                "updated_at": now_iso,
            }

            conn.execute(
                """
                INSERT INTO operational_encounters (
                    encounter_id, patient_id, admit_time, discharge_time,
                    department, condition_code, billing_amount, status,
                    is_deleted, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["encounter_id"],
                    record["patient_id"],
                    record["admit_time"],
                    record["discharge_time"],
                    record["department"],
                    record["condition_code"],
                    record["billing_amount"],
                    record["status"],
                    record["is_deleted"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )

            # Log to WAL
            conn.execute(
                """
                INSERT INTO operational_wal_log (
                    lsn, tx_id, ts_ms, op_type, table_name, record_id, before_json, after_json
                ) VALUES (?, ?, ?, 'c', 'operational_encounters', ?, NULL, ?)
                """,
                (lsn, tx_id, ts_ms, enc_id, json.dumps(record)),
            )

            conn.commit()
            return enc_id
        finally:
            conn.close()

    def update_encounter(
        self,
        encounter_id: str,
        status: str | None = None,
        discharge_time: str | None = None,
        billing_amount: float | None = None,
        department: str | None = None,
    ) -> None:
        """Update an operational encounter and record before/after in WAL."""
        now_iso = datetime.now(timezone.utc).isoformat()
        ts_ms = int(time.time() * 1000)

        conn = self._get_connection()
        try:
            curr = conn.execute(
                "SELECT * FROM operational_encounters WHERE encounter_id = ?",
                (encounter_id,),
            ).fetchone()
            if not curr:
                raise ValueError(f"Encounter {encounter_id} not found")

            before_dict = dict(curr)
            after_dict = dict(before_dict)

            if status is not None:
                after_dict["status"] = status
            if discharge_time is not None:
                after_dict["discharge_time"] = discharge_time
            if billing_amount is not None:
                after_dict["billing_amount"] = float(billing_amount)
            if department is not None:
                after_dict["department"] = department
            after_dict["updated_at"] = now_iso

            lsn, tx_id = self._next_lsn(conn)

            conn.execute(
                """
                UPDATE operational_encounters
                SET status = ?, discharge_time = ?, billing_amount = ?,
                    department = ?, updated_at = ?
                WHERE encounter_id = ?
                """,
                (
                    after_dict["status"],
                    after_dict["discharge_time"],
                    after_dict["billing_amount"],
                    after_dict["department"],
                    after_dict["updated_at"],
                    encounter_id,
                ),
            )

            conn.execute(
                """
                INSERT INTO operational_wal_log (
                    lsn, tx_id, ts_ms, op_type, table_name, record_id, before_json, after_json
                ) VALUES (?, ?, ?, 'u', 'operational_encounters', ?, ?, ?)
                """,
                (lsn, tx_id, ts_ms, encounter_id, json.dumps(before_dict), json.dumps(after_dict)),
            )

            conn.commit()
        finally:
            conn.close()

    def soft_delete_encounter(self, encounter_id: str) -> None:
        """Mark an encounter as is_deleted=1, status='CANCELLED' and log a single atomic update to WAL."""
        now_iso = datetime.now(timezone.utc).isoformat()
        ts_ms = int(time.time() * 1000)
        conn = self._get_connection()
        try:
            curr = conn.execute(
                "SELECT * FROM operational_encounters WHERE encounter_id = ?",
                (encounter_id,),
            ).fetchone()
            if not curr:
                raise ValueError(f"Encounter {encounter_id} not found")

            before_dict = dict(curr)
            after_dict = dict(before_dict)
            after_dict["is_deleted"] = 1
            after_dict["status"] = "CANCELLED"
            after_dict["updated_at"] = now_iso

            lsn, tx_id = self._next_lsn(conn)
            conn.execute(
                "UPDATE operational_encounters SET is_deleted = 1, status = 'CANCELLED', updated_at = ? WHERE encounter_id = ?",
                (now_iso, encounter_id),
            )
            conn.execute(
                """
                INSERT INTO operational_wal_log (
                    lsn, tx_id, ts_ms, op_type, table_name, record_id, before_json, after_json
                ) VALUES (?, ?, ?, 'u', 'operational_encounters', ?, ?, ?)
                """,
                (lsn, tx_id, ts_ms, encounter_id, json.dumps(before_dict), json.dumps(after_dict)),
            )
            conn.commit()
        finally:
            conn.close()

    def hard_delete_encounter(self, encounter_id: str) -> None:
        """Delete encounter row permanently and log 'd' delete event to WAL."""
        now_iso = datetime.now(timezone.utc).isoformat()
        ts_ms = int(time.time() * 1000)

        conn = self._get_connection()
        try:
            curr = conn.execute(
                "SELECT * FROM operational_encounters WHERE encounter_id = ?",
                (encounter_id,),
            ).fetchone()
            if not curr:
                return

            before_dict = dict(curr)
            lsn, tx_id = self._next_lsn(conn)

            conn.execute(
                "DELETE FROM operational_encounters WHERE encounter_id = ?",
                (encounter_id,),
            )
            conn.execute(
                """
                INSERT INTO operational_wal_log (
                    lsn, tx_id, ts_ms, op_type, table_name, record_id, before_json, after_json
                ) VALUES (?, ?, ?, 'd', 'operational_encounters', ?, ?, NULL)
                """,
                (lsn, tx_id, ts_ms, encounter_id, json.dumps(before_dict)),
            )
            conn.commit()
        finally:
            conn.close()

    def get_encounter(self, encounter_id: str) -> dict[str, Any] | None:
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM operational_encounters WHERE encounter_id = ?",
                (encounter_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_unpolled_wal(self, since_lsn: int = 0) -> list[dict[str, Any]]:
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM operational_wal_log WHERE lsn > ? ORDER BY lsn ASC",
                (since_lsn,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
