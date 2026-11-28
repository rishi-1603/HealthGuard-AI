"""
Quarantine Engine — Isolates invalid records with reason codes.

Records failing validation are diverted here without crashing the pipeline.
Each quarantined record retains full context for debugging and recovery.
"""

import logging
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class QuarantineReason(str, Enum):
    """Standardized quarantine reason codes."""
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_REFERENCE = "INVALID_REFERENCE"
    INVALID_DATA_TYPE = "INVALID_DATA_TYPE"
    DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"
    MALFORMED_JSON = "MALFORMED_JSON"
    INVALID_ENUM_VALUE = "INVALID_ENUM_VALUE"
    INVALID_DATE_FORMAT = "INVALID_DATE_FORMAT"
    MISSING_SUBJECT = "MISSING_SUBJECT"
    MISSING_CODE = "MISSING_CODE"
    MISSING_STATUS = "MISSING_STATUS"
    SUBJECT_NOT_PATIENT = "SUBJECT_NOT_PATIENT"
    ENCOUNTER_NOT_ENCOUNTER = "ENCOUNTER_NOT_ENCOUNTER"
    REFERENCE_NOT_FOUND = "REFERENCE_NOT_FOUND"


@dataclass
class QuarantineRecord:
    """A single quarantined record with full context."""
    batch_id: str
    resource_type: str
    resource_id: Optional[str]
    source_line: int
    raw_payload: str
    reason: QuarantineReason
    reason_detail: str
    severity: str = "ERROR"  # ERROR, WARNING
    quarantined_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_bronze_record(
        cls,
        bronze_record: dict,
        batch_id: str,
        reason: QuarantineReason,
        reason_detail: str,
        severity: str = "ERROR",
    ) -> "QuarantineRecord":
        """Create quarantine record from Bronze record."""
        return cls(
            batch_id=batch_id,
            resource_type=bronze_record.get("resource_type", "UNKNOWN"),
            resource_id=bronze_record.get("resource_id"),
            source_line=bronze_record.get("source_line", 0),
            raw_payload=bronze_record.get("raw_payload", "")[:5000],  # Truncate
            reason=reason,
            reason_detail=reason_detail,
            severity=severity,
        )


class QuarantineEngine:
    """
    Quarantine Engine — Routes invalid records to quarantine storage.

    Features:
    - In-memory accumulation with periodic flush to Parquet
    - Structured reason codes for analytics
    - Recovery support: re-process quarantined records after fix
    """

    def __init__(
        self,
        quarantine_root: Path,
        batch_size: int = 1000,
    ):
        self.quarantine_root = Path(quarantine_root)
        self.batch_size = batch_size
        self.buffer: list[QuarantineRecord] = []
        self.counts: dict[str, int] = {}  # reason -> count
        self._flush_counter: int = 0
        self.quarantine_root.mkdir(parents=True, exist_ok=True)

    def quarantine(
        self,
        record: QuarantineRecord,
    ) -> None:
        """Add a record to quarantine buffer."""
        self.buffer.append(record)
        reason_key = record.reason.value
        self.counts[reason_key] = self.counts.get(reason_key, 0) + 1

        if len(self.buffer) >= self.batch_size:
            self.flush()

    def quarantine_from_bronze(
        self,
        bronze_record: dict,
        batch_id: str,
        reason: QuarantineReason,
        reason_detail: str,
        severity: str = "ERROR",
    ) -> None:
        """Convenience: quarantine directly from Bronze record."""
        qr = QuarantineRecord.from_bronze_record(
            bronze_record, batch_id, reason, reason_detail, severity
        )
        self.quarantine(qr)

    def flush(self) -> Optional[Path]:
        """Flush buffer to partitioned Parquet file."""
        if not self.buffer:
            return None

        import pyarrow as pa
        import pyarrow.parquet as pq

        # Partition by reason and date
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        output_dir = self.quarantine_root / f"reason={self.buffer[0].reason.value}" / f"date={date_str}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Use counter + timestamp + microsecond for unique filename
        self._flush_counter += 1
        ts = datetime.now(timezone.utc)
        output_file = output_dir / f"quarantine_{ts.strftime('%H%M%S')}_{ts.microsecond:06d}_{self._flush_counter}.parquet"

        # Convert to PyArrow table
        records = [r.to_dict() for r in self.buffer]
        table = pa.Table.from_pylist(records)

        # Staged write
        temp_file = output_dir / f".temp_{output_file.name}"
        pq.write_table(table, str(temp_file))
        temp_file.rename(output_file)

        logger.info(f"Flushed {len(self.buffer)} quarantine records to {output_file}")
        self.buffer.clear()
        return output_file

    def get_summary(self) -> dict:
        """Get quarantine statistics."""
        return {
            "buffered": len(self.buffer),
            "total_quarantined": sum(self.counts.values()),
            "by_reason": self.counts.copy(),
        }

    def close(self) -> None:
        """Flush remaining records on close."""
        self.flush()


def load_quarantine_records(quarantine_root: Path) -> list[dict]:
    """Load all quarantined records for review/reprocessing."""
    import pyarrow.parquet as pq

    records = []
    for parquet_file in Path(quarantine_root).rglob("*.parquet"):
        table = pq.read_table(str(parquet_file))
        records.extend(table.to_pylist())
    return records