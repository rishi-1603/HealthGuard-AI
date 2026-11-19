"""Kafka Schema Registry validation for clinical streaming events (DE-009)."""

from __future__ import annotations

import logging
from typing import Any

from pipeline.streaming.models import ClinicalEvent, ClinicalEventType

logger = logging.getLogger(__name__)


class SchemaValidationError(ValueError):
    """Raised when a streaming event fails schema registry contract checks."""


class SchemaRegistry:
    """Manages event schemas and validates payloads against versioned contracts."""

    # Schema field specifications: field_name -> expected_types (or tuple of types)
    _SCHEMAS: dict[str, dict[str, type | tuple[type, ...]]] = {
        ClinicalEventType.ADMITTED.value: {
            "department": str,
            "admit_reason": str,
        },
        ClinicalEventType.OBSERVATION.value: {
            "observation_code": str,
            "observation_name": str,
            "value": (int, float),
            "unit": str,
        },
        ClinicalEventType.MEDICATION.value: {
            "medication_name": str,
            "dose": str,
        },
        ClinicalEventType.DISCHARGED.value: {
            "disposition": str,
            "outcome": str,
            "length_of_stay": int,
        },
    }

    def __init__(self, version: str = "1.0.0") -> None:
        self.version = version

    def validate(self, event: ClinicalEvent) -> bool:
        """Validate clinical event against registered schema definition."""
        op_key = event.event_type.value if isinstance(event.event_type, ClinicalEventType) else str(event.event_type)

        if op_key not in self._SCHEMAS:
            raise SchemaValidationError(f"Unknown event type '{op_key}' in schema registry")

        # Top-level required attributes
        for top_attr in ("event_id", "event_type", "event_timestamp", "patient_id", "encounter_id"):
            val = getattr(event, top_attr, None)
            if not val:
                raise SchemaValidationError(f"Missing required top-level event attribute: '{top_attr}'")

        # Payload validations
        spec = self._SCHEMAS[op_key]
        payload = event.payload or {}

        for req_field, expected_type in spec.items():
            if req_field not in payload or payload[req_field] is None:
                raise SchemaValidationError(
                    f"Event '{op_key}' payload missing required field '{req_field}'"
                )

            val = payload[req_field]
            if not isinstance(val, expected_type):
                raise SchemaValidationError(
                    f"Field '{req_field}' expected type {expected_type}, got {type(val).__name__} ({val!r})"
                )

        return True
