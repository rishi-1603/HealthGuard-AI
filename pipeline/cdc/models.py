"""Debezium CDC data models and standard envelope schemas (DE-008)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CdcOp(str, Enum):
    """Debezium operation codes."""

    CREATE = "c"
    UPDATE = "u"
    DELETE = "d"
    READ = "r"


@dataclass
class CdcSource:
    """Debezium source connector metadata block."""

    version: str = "2.4.0.Final"
    connector: str = "postgresql"
    name: str = "healthguard_operational_server"
    ts_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    snapshot: str = "false"
    db: str = "healthguard_ops"
    schema: str = "public"
    table: str = "operational_encounters"
    tx_id: int = 1
    lsn: int = 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "connector": self.connector,
            "name": self.name,
            "ts_ms": self.ts_ms,
            "snapshot": self.snapshot,
            "db": self.db,
            "schema": self.schema,
            "table": self.table,
            "txId": self.tx_id,
            "lsn": self.lsn,
        }


@dataclass
class CdcEvent:
    """Full Debezium CDC change event."""

    op: CdcOp
    table: str
    payload: dict[str, Any]  # contains 'before' and 'after'
    lsn: int
    tx_id: int
    ts_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: CdcSource | None = None

    def __post_init__(self) -> None:
        if self.source is None:
            self.source = CdcSource(
                table=self.table,
                tx_id=self.tx_id,
                lsn=self.lsn,
                ts_ms=self.ts_ms,
            )

    def to_debezium_dict(self) -> dict[str, Any]:
        """Convert into canonical Debezium JSON envelope."""
        assert self.source is not None
        return {
            "schema": {
                "type": "struct",
                "fields": [
                    {"type": "struct", "field": "before", "optional": True},
                    {"type": "struct", "field": "after", "optional": True},
                    {"type": "struct", "field": "source", "optional": False},
                    {"type": "string", "field": "op", "optional": False},
                    {"type": "int64", "field": "ts_ms", "optional": True},
                ],
                "optional": False,
                "name": f"{self.source.name}.{self.source.schema}.{self.table}.Envelope",
            },
            "payload": {
                "before": self.payload.get("before"),
                "after": self.payload.get("after"),
                "source": self.source.to_dict(),
                "op": self.op.value if isinstance(self.op, CdcOp) else str(self.op),
                "ts_ms": self.ts_ms,
                "transaction": None,
            },
        }
