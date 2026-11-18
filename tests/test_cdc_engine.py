"""Tests for Day 8 — PostgreSQL Operational Source & Debezium CDC Engine (DE-008).

Verifies:
  AC1: Operational schema for live EHR transactional updates
  AC2: CDC pipeline tracking inserts, updates, and soft/hard deletes via Debezium WAL envelope
  AC3: Sync change capture stream to Lakehouse Bronze layer (table & Parquet)
  AC4: Event replay, state consistency, out-of-order LSN handling, and idempotent deduplication
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline.config import PipelineConfig
from pipeline.warehouse import managed_connection, apply_ddl
from pipeline.cdc.models import CdcEvent, CdcOp
from pipeline.cdc.operational_db import OperationalEhrDb
from pipeline.cdc.cdc_engine import DebeziumCdcEngine
from pipeline.cdc.lakehouse_sync import LakehouseCdcSync


@pytest.fixture()
def cfg(tmp_path: Path) -> PipelineConfig:
    """Config with temporary warehouse and operational database."""
    wh_db = tmp_path / "warehouse.db"
    c = PipelineConfig(
        source_csv=tmp_path / "fake.csv",
        warehouse_db=wh_db,
        reports_dir=tmp_path / "reports",
    )
    apply_ddl(c)
    return c


@pytest.fixture()
def ops_db(tmp_path: Path) -> OperationalEhrDb:
    """Operational EHR database with initialized schema."""
    db_file = tmp_path / "operational_ehr.db"
    return OperationalEhrDb(db_file)


# ──────────────────────────────────────────────────────────────────────
# AC1: Operational EHR Schema & Transaction Execution
# ──────────────────────────────────────────────────────────────────────
class TestOperationalEhrSchema:
    """Verify operational EHR database tables, constraints, and audit columns."""

    def test_operational_tables_exist(self, ops_db: OperationalEhrDb) -> None:
        tables = ops_db.get_table_names()
        assert "operational_encounters" in tables
        assert "operational_wal_log" in tables

    def test_insert_operational_encounter(self, ops_db: OperationalEhrDb) -> None:
        enc_id = ops_db.insert_encounter(
            patient_id="PAT-1001",
            admit_time="2026-03-10T08:00:00Z",
            department="Cardiology",
            condition_code="I50.9",
            billing_amount=4500.0,
        )
        assert enc_id.startswith("ENC-")
        row = ops_db.get_encounter(enc_id)
        assert row is not None
        assert row["patient_id"] == "PAT-1001"
        assert row["status"] == "ADMITTED"
        assert row["is_deleted"] == 0

    def test_update_operational_encounter(self, ops_db: OperationalEhrDb) -> None:
        enc_id = ops_db.insert_encounter("PAT-1002", "2026-03-10T09:00:00Z", "ICU", "J44.1", 3200.0)
        ops_db.update_encounter(
            encounter_id=enc_id,
            status="DISCHARGED",
            discharge_time="2026-03-14T15:00:00Z",
            billing_amount=7800.0,
        )
        row = ops_db.get_encounter(enc_id)
        assert row["status"] == "DISCHARGED"
        assert row["discharge_time"] == "2026-03-14T15:00:00Z"
        assert row["billing_amount"] == 7800.0

    def test_soft_delete_operational_encounter(self, ops_db: OperationalEhrDb) -> None:
        enc_id = ops_db.insert_encounter("PAT-1003", "2026-03-10T10:00:00Z", "ER", "R07.9", 900.0)
        ops_db.soft_delete_encounter(enc_id)
        row = ops_db.get_encounter(enc_id)
        assert row["is_deleted"] == 1
        assert row["status"] == "CANCELLED"


# ──────────────────────────────────────────────────────────────────────
# AC2: Debezium CDC Envelope & WAL Change Capture
# ──────────────────────────────────────────────────────────────────────
class TestDebeziumCdcCapture:
    """Verify CDC change extraction into standard Debezium event envelopes."""

    def test_cdc_captures_insert_as_create_event(self, ops_db: OperationalEhrDb) -> None:
        engine = DebeziumCdcEngine(ops_db)
        enc_id = ops_db.insert_encounter("PAT-2001", "2026-03-11T10:00:00Z", "Neurology", "G40.9", 2500.0)

        events = engine.poll_events()
        assert len(events) == 1
        event = events[0]

        assert event.op == CdcOp.CREATE
        assert event.table == "operational_encounters"
        assert event.payload["before"] is None
        assert event.payload["after"]["encounter_id"] == enc_id
        assert event.payload["after"]["billing_amount"] == 2500.0
        assert event.lsn > 0
        assert event.tx_id > 0

    def test_cdc_captures_update_with_before_and_after(self, ops_db: OperationalEhrDb) -> None:
        engine = DebeziumCdcEngine(ops_db)
        enc_id = ops_db.insert_encounter("PAT-2002", "2026-03-11T11:00:00Z", "Oncology", "C34.9", 5000.0)
        engine.poll_events()  # Consume insert

        ops_db.update_encounter(enc_id, billing_amount=6200.0, status="IN_TREATMENT")
        events = engine.poll_events()
        assert len(events) == 1
        event = events[0]

        assert event.op == CdcOp.UPDATE
        assert event.payload["before"]["billing_amount"] == 5000.0
        assert event.payload["after"]["billing_amount"] == 6200.0
        assert event.payload["before"]["status"] == "ADMITTED"
        assert event.payload["after"]["status"] == "IN_TREATMENT"

    def test_cdc_captures_soft_and_hard_deletes(self, ops_db: OperationalEhrDb) -> None:
        engine = DebeziumCdcEngine(ops_db)
        enc_id = ops_db.insert_encounter("PAT-2003", "2026-03-11T12:00:00Z", "Pediatrics", "J06.9", 400.0)
        engine.poll_events()

        # Soft delete: produces UPDATE with is_deleted=1
        ops_db.soft_delete_encounter(enc_id)
        ev_soft = engine.poll_events()
        assert len(ev_soft) == 1
        assert ev_soft[0].op == CdcOp.UPDATE
        assert ev_soft[0].payload["after"]["is_deleted"] == 1

        # Hard delete: produces DELETE event
        ops_db.hard_delete_encounter(enc_id)
        ev_hard = engine.poll_events()
        assert len(ev_hard) == 1
        assert ev_hard[0].op == CdcOp.DELETE
        assert ev_hard[0].payload["before"]["encounter_id"] == enc_id
        assert ev_hard[0].payload["after"] is None

    def test_debezium_envelope_structure(self, ops_db: OperationalEhrDb) -> None:
        engine = DebeziumCdcEngine(ops_db)
        ops_db.insert_encounter("PAT-2004", "2026-03-11T13:00:00Z", "Surgery", "K35.8", 11000.0)
        events = engine.poll_events()
        assert len(events) == 1
        envelope = events[0].to_debezium_dict()

        assert "schema" in envelope
        assert "payload" in envelope
        payload = envelope["payload"]
        assert payload["op"] == "c"
        assert "source" in payload
        assert payload["source"]["connector"] == "postgresql"
        assert payload["source"]["table"] == "operational_encounters"
        assert "lsn" in payload["source"]
        assert "ts_ms" in payload["source"]


# ──────────────────────────────────────────────────────────────────────
# AC3: Lakehouse Bronze Sync & Parquet Partitioning
# ──────────────────────────────────────────────────────────────────────
class TestLakehouseBronzeSync:
    """Verify CDC stream landing in Lakehouse Bronze tables and partitioned Parquet files."""

    def test_sync_to_bronze_table(self, ops_db: OperationalEhrDb, cfg: PipelineConfig) -> None:
        engine = DebeziumCdcEngine(ops_db)
        sync = LakehouseCdcSync(cfg)

        ops_db.insert_encounter("PAT-3001", "2026-03-12T08:00:00Z", "Cardiology", "I21.9", 8500.0)
        ops_db.insert_encounter("PAT-3002", "2026-03-12T09:00:00Z", "Orthopedics", "S72.0", 6200.0)

        events = engine.poll_events()
        synced_count = sync.sync_to_bronze(events)
        assert synced_count == 2

        with managed_connection(cfg.warehouse_db) as conn:
            rows = conn.execute("SELECT * FROM bronze_cdc_events ORDER BY lsn").fetchall()
        assert len(rows) == 2
        assert rows[0]["op"] == "c"
        assert rows[0]["table_name"] == "operational_encounters"
        payload = json.loads(rows[0]["payload_json"])
        assert payload["after"]["patient_id"] == "PAT-3001"

    def test_sync_to_partitioned_parquet(
        self, ops_db: OperationalEhrDb, cfg: PipelineConfig, tmp_path: Path
    ) -> None:
        engine = DebeziumCdcEngine(ops_db)
        parquet_dir = tmp_path / "lakehouse_cdc"
        sync = LakehouseCdcSync(cfg, parquet_root=parquet_dir)

        ops_db.insert_encounter("PAT-3003", "2026-03-12T10:00:00Z", "General", "R50.9", 350.0)
        events = engine.poll_events()
        file_path = sync.write_bronze_parquet(events)

        assert file_path.exists()
        assert file_path.suffix == ".parquet"


# ──────────────────────────────────────────────────────────────────────
# AC4: State Consistency, Replay & Idempotent Compaction
# ──────────────────────────────────────────────────────────────────────
class TestStateConsistencyAndReplay:
    """Verify state consistency across event mutations, out-of-order LSNs, and replays."""

    def test_end_to_end_replay_consistency(
        self, ops_db: OperationalEhrDb, cfg: PipelineConfig
    ) -> None:
        """Sequential lifecycle: Insert -> Update -> Soft Delete -> Reconcile."""
        engine = DebeziumCdcEngine(ops_db)
        sync = LakehouseCdcSync(cfg)

        # 1. Insert
        enc_id = ops_db.insert_encounter("PAT-4001", "2026-03-13T08:00:00Z", "ICU", "J96.0", 4000.0)
        sync.sync_to_bronze(engine.poll_events())
        sync.compact_to_silver()

        state1 = sync.get_silver_state(enc_id)
        assert state1 is not None
        assert state1["status"] == "ADMITTED"
        assert state1["billing_amount"] == 4000.0
        assert state1["is_deleted"] == 0

        # 2. Update
        ops_db.update_encounter(enc_id, billing_amount=9500.0, status="STABILIZED")
        sync.sync_to_bronze(engine.poll_events())
        sync.compact_to_silver()

        state2 = sync.get_silver_state(enc_id)
        assert state2["status"] == "STABILIZED"
        assert state2["billing_amount"] == 9500.0

        # 3. Soft Delete
        ops_db.soft_delete_encounter(enc_id)
        sync.sync_to_bronze(engine.poll_events())
        sync.compact_to_silver()

        state3 = sync.get_silver_state(enc_id)
        assert state3["is_deleted"] == 1
        assert state3["status"] == "CANCELLED"

    def test_out_of_order_lsn_rejection(
        self, ops_db: OperationalEhrDb, cfg: PipelineConfig
    ) -> None:
        """An event with an older LSN must not overwrite newer state in Silver."""
        engine = DebeziumCdcEngine(ops_db)
        sync = LakehouseCdcSync(cfg)

        enc_id = ops_db.insert_encounter("PAT-4002", "2026-03-13T09:00:00Z", "ER", "K29.7", 1200.0)
        ev_insert = engine.poll_events()[0]

        ops_db.update_encounter(enc_id, billing_amount=2800.0, status="TRANSFERRED")
        ev_update = engine.poll_events()[0]

        assert ev_update.lsn > ev_insert.lsn

        # Apply NEWER update first
        sync.sync_to_bronze([ev_update])
        sync.compact_to_silver()

        # Now replay OLDER insert
        sync.sync_to_bronze([ev_insert])
        sync.compact_to_silver()

        # State must retain the NEWER update values
        final_state = sync.get_silver_state(enc_id)
        assert final_state["billing_amount"] == 2800.0
        assert final_state["status"] == "TRANSFERRED"
        assert final_state["last_lsn"] == ev_update.lsn

    def test_idempotent_event_deduplication(
        self, ops_db: OperationalEhrDb, cfg: PipelineConfig
    ) -> None:
        """Syncing identical events multiple times must not duplicate Bronze rows or corrupt Silver."""
        engine = DebeziumCdcEngine(ops_db)
        sync = LakehouseCdcSync(cfg)

        enc_id = ops_db.insert_encounter("PAT-4003", "2026-03-13T10:00:00Z", "Daycare", "Z00.0", 500.0)
        events = engine.poll_events()

        # Sync twice
        sync.sync_to_bronze(events)
        sync.sync_to_bronze(events)

        with managed_connection(cfg.warehouse_db) as conn:
            bronze_count = conn.execute(
                "SELECT count(*) FROM bronze_cdc_events WHERE event_id = ?",
                (events[0].event_id,),
            ).fetchone()[0]
        assert bronze_count == 1, "Duplicate CDC event_id must be ignored in Bronze"

        sync.compact_to_silver()
        sync.compact_to_silver()

        state = sync.get_silver_state(enc_id)
        assert state is not None
        assert state["billing_amount"] == 500.0
