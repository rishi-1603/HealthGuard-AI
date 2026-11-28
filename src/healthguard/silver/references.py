"""
Reference Resolution — Resolves FHIR references to source-scoped IDs.

Handles Patient, Encounter, and other reference types with proper
source system prefixing (SYNTHEA_FHIR:...).
"""

import json
import logging
import re
from typing import Optional

# Lazy import to avoid circular dependency
def _get_load_contract():
    from src.healthguard.ingestion.source_validator import load_contract
    return load_contract

def load_contract(resource_type: str):
    """Lazy proxy to load_contract."""
    return _get_load_contract()(resource_type)

logger = logging.getLogger(__name__)


def resolve_patient_ref(ref: str, patient_lookup: dict) -> Optional[str]:
    """
    Resolve a Patient reference to a source-scoped ID.

    Args:
        ref: FHIR reference string, e.g. "Patient/123" or "Patient/123/_history/1"
        patient_lookup: Dict mapping native ID -> source-scoped ID

    Returns:
        Source-scoped ID (e.g., "SYNTHEA_FHIR:123") or None if not found
    """
    if not ref or not isinstance(ref, str):
        return None

    # Handle "Patient/123" or "Patient/123/_history/1"
    if not ref.startswith("Patient/"):
        logger.debug(f"Reference does not start with 'Patient/': {ref}")
        return None

    # Extract native ID: "Patient/123/_history/1" -> "123"
    parts = ref.split("/")
    if len(parts) < 2:
        return None

    native_id = parts[1]
    if not native_id:
        return None

    # Look up in patient lookup (maps native_id -> scoped_id)
    return patient_lookup.get(native_id)


def resolve_encounter_ref(ref: str, encounter_lookup: dict) -> Optional[str]:
    """
    Resolve an Encounter reference to a source-scoped ID.

    Args:
        ref: FHIR reference string, e.g. "Encounter/456"
        encounter_lookup: Dict mapping native ID -> source-scoped ID

    Returns:
        Source-scoped ID or None if not found
    """
    if not ref or not isinstance(ref, str):
        return None

    if not ref.startswith("Encounter/"):
        logger.debug(f"Reference does not start with 'Encounter/': {ref}")
        return None

    parts = ref.split("/")
    if len(parts) < 2:
        return None

    native_id = parts[1]
    if not native_id:
        return None

    return encounter_lookup.get(native_id)


def extract_reference_id(ref: dict | str, expected_type: str) -> Optional[str]:
    """
    Extract native ID from a FHIR reference object or string.

    Args:
        ref: Reference object {"reference": "Patient/123"} or string "Patient/123"
             or JSON string '{"reference": "Patient/123"}'
        expected_type: Expected resource type (e.g., "Patient", "Encounter")

    Returns:
        Native ID string or None
    """
    if isinstance(ref, str):
        # Try to parse as JSON first (in case it's a serialized reference object)
        try:
            parsed = json.loads(ref)
            if isinstance(parsed, dict) and "reference" in parsed:
                ref_str = parsed["reference"]
            else:
                ref_str = ref
        except json.JSONDecodeError:
            ref_str = ref
    elif isinstance(ref, dict) and "reference" in ref:
        ref_str = ref["reference"]
    else:
        return None

    if not ref_str.startswith(f"{expected_type}/"):
        return None

    return ref_str.split("/")[1] if len(ref_str.split("/")) > 1 else None


def build_patient_lookup(patient_records: list[dict]) -> dict[str, str]:
    """
    Build lookup dict: native_id -> source_scoped_id for Patients.

    Args:
        patient_records: List of Bronze Patient records with 'resource_id'

    Returns:
        Dict mapping native ID -> "SYNTHEA_FHIR:<native_id>"
    """
    lookup = {}
    for record in patient_records:
        native_id = record.get("resource_id")
        if native_id:
            # Source-scoped ID format: SYSTEM:native_id
            lookup[native_id] = f"SYNTHEA_FHIR:{native_id}"
    return lookup


def build_encounter_lookup(encounter_records: list[dict]) -> dict[str, str]:
    """
    Build lookup dict: native_id -> source_scoped_id for Encounters.

    Args:
        encounter_records: List of Bronze Encounter records with 'resource_id'

    Returns:
        Dict mapping native ID -> "SYNTHEA_FHIR:<native_id>"
    """
    lookup = {}
    for record in encounter_records:
        native_id = record.get("resource_id")
        if native_id:
            lookup[native_id] = f"SYNTHEA_FHIR:{native_id}"
    return lookup


def resolve_references_in_record(
    record: dict,
    resource_type: str,
    patient_lookup: dict,
    encounter_lookup: dict,
) -> dict:
    """
    Resolve all references in a Silver record using contracts.

    Args:
        record: Raw FHIR resource dict
        resource_type: FHIR resource type (Patient, Encounter, Condition, Observation)
        patient_lookup: native_id -> scoped_id mapping
        encounter_lookup: native_id -> scoped_id mapping

    Returns:
        Record with resolved reference fields added
    """
    contract = load_contract(resource_type)
    ref_resolution = contract.reference_resolution
    resolved = record.copy()

    for ref_field, ref_spec in ref_resolution.items():
        if ref_field not in record or not record[ref_field]:
            # Optional reference not present
            target_field = f"{ref_field}_id"
            resolved[target_field] = None
            continue

        ref_obj = record[ref_field]
        expected_type = ref_spec.get("target_resource", "Patient")

        if expected_type == "Patient":
            native_id = extract_reference_id(ref_obj, "Patient")
            resolved[f"{ref_field}_id"] = patient_lookup.get(native_id) if native_id else None
        elif expected_type == "Encounter":
            native_id = extract_reference_id(ref_obj, "Encounter")
            resolved[f"{ref_field}_id"] = encounter_lookup.get(native_id) if native_id else None
        else:
            # Other reference types (Organization, Practitioner, etc.) - preserve as-is
            native_id = extract_reference_id(ref_obj, expected_type)
            resolved[f"{ref_field}_id"] = f"{expected_type.upper()}:{native_id}" if native_id else None

    return resolved