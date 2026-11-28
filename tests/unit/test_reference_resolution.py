"""
Unit tests for Silver reference resolution.
"""

import pytest
from src.healthguard.silver.references import (
    resolve_patient_ref,
    resolve_encounter_ref,
    extract_reference_id,
    build_patient_lookup,
    build_encounter_lookup,
    resolve_references_in_record,
)


class TestResolvePatientRef:
    """Tests for resolve_patient_ref function."""

    def test_valid_reference(self):
        """Valid Patient reference resolves correctly."""
        lookup = {"123": "SYNTHEA_FHIR:123", "456": "SYNTHEA_FHIR:456"}
        assert resolve_patient_ref("Patient/123", lookup) == "SYNTHEA_FHIR:123"

    def test_reference_with_history(self):
        """Reference with _history suffix resolves correctly."""
        lookup = {"123": "SYNTHEA_FHIR:123"}
        assert resolve_patient_ref("Patient/123/_history/1", lookup) == "SYNTHEA_FHIR:123"

    def test_reference_not_found(self):
        """Missing reference returns None."""
        lookup = {"123": "SYNTHEA_FHIR:123"}
        assert resolve_patient_ref("Patient/999", lookup) is None

    def test_invalid_format(self):
        """Invalid reference format returns None."""
        lookup = {"123": "SYNTHEA_FHIR:123"}
        assert resolve_patient_ref("Patient/", lookup) is None
        assert resolve_patient_ref("Encounter/123", lookup) is None
        assert resolve_patient_ref("", lookup) is None
        assert resolve_patient_ref(None, lookup) is None


class TestResolveEncounterRef:
    """Tests for resolve_encounter_ref function."""

    def test_valid_reference(self):
        """Valid Encounter reference resolves correctly."""
        lookup = {"ENC001": "SYNTHEA_FHIR:ENC001"}
        assert resolve_encounter_ref("Encounter/ENC001", lookup) == "SYNTHEA_FHIR:ENC001"

    def test_reference_not_found(self):
        """Missing reference returns None."""
        lookup = {"ENC001": "SYNTHEA_FHIR:ENC001"}
        assert resolve_encounter_ref("Encounter/ENC999", lookup) is None

    def test_invalid_format(self):
        """Invalid format returns None."""
        lookup = {"ENC001": "SYNTHEA_FHIR:ENC001"}
        assert resolve_encounter_ref("Patient/ENC001", lookup) is None
        assert resolve_encounter_ref("Encounter/", lookup) is None


class TestExtractReferenceId:
    """Tests for extract_reference_id function."""

    def test_from_string(self):
        """Extract ID from reference string."""
        assert extract_reference_id("Patient/123", "Patient") == "123"
        assert extract_reference_id("Encounter/456", "Encounter") == "456"

    def test_from_object(self):
        """Extract ID from reference object."""
        assert extract_reference_id({"reference": "Patient/123"}, "Patient") == "123"
        assert extract_reference_id({"reference": "Encounter/456"}, "Encounter") == "456"

    def test_wrong_type(self):
        """Wrong reference type returns None."""
        assert extract_reference_id("Patient/123", "Encounter") is None
        assert extract_reference_id({"reference": "Patient/123"}, "Encounter") is None

    def test_invalid_input(self):
        """Invalid input returns None."""
        assert extract_reference_id(None, "Patient") is None
        assert extract_reference_id("invalid", "Patient") is None
        assert extract_reference_id({"not": "reference"}, "Patient") is None


class TestBuildLookups:
    """Tests for build_patient_lookup and build_encounter_lookup."""

    def test_build_patient_lookup(self):
        """Build lookup from Bronze Patient records."""
        records = [
            {"resource_id": "PAT001"},
            {"resource_id": "PAT002"},
            {"resource_id": None},
            {"resource_id": "PAT003"},
        ]
        lookup = build_patient_lookup(records)
        assert lookup == {
            "PAT001": "SYNTHEA_FHIR:PAT001",
            "PAT002": "SYNTHEA_FHIR:PAT002",
            "PAT003": "SYNTHEA_FHIR:PAT003",
        }

    def test_build_encounter_lookup(self):
        """Build lookup from Bronze Encounter records."""
        records = [
            {"resource_id": "ENC001"},
            {"resource_id": "ENC002"},
        ]
        lookup = build_encounter_lookup(records)
        assert lookup == {
            "ENC001": "SYNTHEA_FHIR:ENC001",
            "ENC002": "SYNTHEA_FHIR:ENC002",
        }

    def test_empty_records(self):
        """Empty records produce empty lookup."""
        assert build_patient_lookup([]) == {}
        assert build_encounter_lookup([]) == {}


class TestResolveReferencesInRecord:
    """Tests for resolve_references_in_record function."""

    def test_patient_no_references(self):
        """Patient record has no external references to resolve."""
        record = {"patient_id": "PAT001", "gender": "male"}
        patient_lookup = {"PAT001": "SYNTHEA_FHIR:PAT001"}
        encounter_lookup = {}

        resolved = resolve_references_in_record(record, "Patient", patient_lookup, encounter_lookup)
        assert resolved == record  # No change expected

    def test_encounter_subject_resolution(self):
        """Encounter subject reference resolves to Patient."""
        record = {"encounter_id": "ENC001", "subject": {"reference": "Patient/PAT001"}}
        patient_lookup = {"PAT001": "SYNTHEA_FHIR:PAT001"}
        encounter_lookup = {}

        resolved = resolve_references_in_record(record, "Encounter", patient_lookup, encounter_lookup)
        assert resolved["subject_id"] == "SYNTHEA_FHIR:PAT001"

    def test_condition_subject_and_encounter_resolution(self):
        """Condition subject and encounter references resolve."""
        record = {
            "condition_id": "COND001",
            "subject": {"reference": "Patient/PAT001"},
            "encounter": {"reference": "Encounter/ENC001"},
        }
        patient_lookup = {"PAT001": "SYNTHEA_FHIR:PAT001"}
        encounter_lookup = {"ENC001": "SYNTHEA_FHIR:ENC001"}

        resolved = resolve_references_in_record(record, "Condition", patient_lookup, encounter_lookup)
        assert resolved["subject_id"] == "SYNTHEA_FHIR:PAT001"
        assert resolved["encounter_id"] == "SYNTHEA_FHIR:ENC001"

    def test_optional_encounter_missing(self):
        """Optional Encounter reference missing -> None."""
        record = {"observation_id": "OBS001", "subject": {"reference": "Patient/PAT001"}}
        patient_lookup = {"PAT001": "SYNTHEA_FHIR:PAT001"}
        encounter_lookup = {}

        resolved = resolve_references_in_record(record, "Observation", patient_lookup, encounter_lookup)
        assert resolved["subject_id"] == "SYNTHEA_FHIR:PAT001"
        assert resolved["encounter_id"] is None

    def test_other_reference_types_preserved(self):
        """Non-Patient/Encounter references preserved as-is."""
        record = {"device": {"reference": "Device/DEV001"}}
        patient_lookup = {}
        encounter_lookup = {}

        resolved = resolve_references_in_record(record, "Observation", patient_lookup, encounter_lookup)
        # Device reference not in our lookups, but should be handled
        assert "device_id" in resolved