"""Real-time clinical event models and deterministic identifier generation (DE-009)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# Namespace UUID for deterministic UUIDv5 event ID generation
_HEALTHGUARD_NAMESPACE = uuid.UUID("a2345678-1234-5678-1234-567812345678")


class ClinicalEventType(str, Enum):
    """Core real-time healthcare clinical event types."""

    ADMITTED = "encounter_admitted"
    OBSERVATION = "observation_recorded"
    MEDICATION = "medication_ordered"
    DISCHARGED = "encounter_discharged"


def generate_deterministic_event_id(
    source_system: str,
    encounter_id: str,
    event_type: str,
    timestamp_str: str,
) -> str:
    """Generate a collision-proof, deterministic UUIDv5 from event attributes.
    
    Guarantees exact reproducibility for identical event attempts.
    """
    composite_key = f"{source_system}:{encounter_id}:{event_type}:{timestamp_str}"
    return str(uuid.uuid5(_HEALTHGUARD_NAMESPACE, composite_key))


@dataclass
class ClinicalEvent:
    """Canonical real-time streaming clinical event."""

    event_id: str
    event_type: ClinicalEventType
    event_timestamp: str
    patient_id: str
    encounter_id: str
    payload: dict[str, Any]
    schema_version: str = "1.0.0"
    source_system: str = "HEALTHGUARD_STREAM"
    partition_key: str = field(default="")

    def __post_init__(self) -> None:
        if not self.partition_key:
            self.partition_key = self.patient_id

    def to_dict(self) -> dict[str, Any]:
        """Convert clinical event to transport dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value if isinstance(self.event_type, ClinicalEventType) else str(self.event_type),
            "event_timestamp": self.event_timestamp,
            "patient_id": self.patient_id,
            "encounter_id": self.encounter_id,
            "payload": self.payload,
            "schema_version": self.schema_version,
            "source_system": self.source_system,
            "partition_key": self.partition_key,
        }
