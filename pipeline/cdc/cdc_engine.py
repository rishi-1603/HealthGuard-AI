"""Debezium CDC streaming engine polling WAL events from operational EHR (DE-008)."""

from __future__ import annotations

import json
import logging
from typing import Any

from pipeline.cdc.models import CdcEvent, CdcOp, CdcSource
from pipeline.cdc.operational_db import OperationalEhrDb

logger = logging.getLogger(__name__)


class DebeziumCdcEngine:
    """Simulates a PostgreSQL Debezium connector tailing WAL transaction logs."""

    def __init__(self, ops_db: OperationalEhrDb, connector_name: str = "healthguard_ops_connector") -> None:
        self.ops_db = ops_db
        self.connector_name = connector_name
        self.last_lsn = 0

    def poll_events(self, max_batch_size: int = 100) -> list[CdcEvent]:
        """Poll new WAL entries and emit structured Debezium CDC events."""
        entries = self.ops_db.get_unpolled_wal(since_lsn=self.last_lsn)
        if not entries:
            return []

        if max_batch_size and len(entries) > max_batch_size:
            entries = entries[:max_batch_size]

        events: list[CdcEvent] = []
        for entry in entries:
            op_code = entry["op_type"]
            op = CdcOp(op_code)

            before = json.loads(entry["before_json"]) if entry["before_json"] else None
            after = json.loads(entry["after_json"]) if entry["after_json"] else None

            source = CdcSource(
                connector="postgresql",
                name=self.connector_name,
                table=entry["table_name"],
                tx_id=entry["tx_id"],
                lsn=entry["lsn"],
                ts_ms=entry["ts_ms"],
            )

            event = CdcEvent(
                op=op,
                table=entry["table_name"],
                payload={"before": before, "after": after},
                lsn=entry["lsn"],
                tx_id=entry["tx_id"],
                ts_ms=entry["ts_ms"],
                source=source,
            )
            events.append(event)
            self.last_lsn = max(self.last_lsn, entry["lsn"])

        logger.info("Debezium CDC engine polled %d events up to LSN %d", len(events), self.last_lsn)
        return events
