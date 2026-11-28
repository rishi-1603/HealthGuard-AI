"""
Silver Layer — FHIR R4 Resource Normalization, Validation, Quarantine & Reconciliation.

Transforms Bronze raw payloads into clean, referentially-intact Silver tables.
"""

from src.healthguard.silver.references import resolve_patient_ref, resolve_encounter_ref, build_patient_lookup, build_encounter_lookup
from src.healthguard.silver.quality import DQEngine, QualityReport
from src.healthguard.silver.quarantine import QuarantineEngine, QuarantineRecord, QuarantineReason
from src.healthguard.silver.reconciliation import ReconciliationEngine, ReconciliationReport

__all__ = [
    "resolve_patient_ref",
    "resolve_encounter_ref",
    "build_patient_lookup",
    "build_encounter_lookup",
    "DQEngine",
    "QualityReport",
    "QuarantineEngine",
    "QuarantineRecord",
    "QuarantineReason",
    "ReconciliationEngine",
    "ReconciliationReport",
]