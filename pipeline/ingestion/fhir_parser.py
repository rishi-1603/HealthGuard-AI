"""FHIR R4 resource parser for Synthea synthetic healthcare bundles.

Parses Patient, Encounter, Condition, and Observation resources with normalized
source-scoped identifiers to prevent cross-system key collisions.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import pandas as pd

logger = logging.getLogger(__name__)


def normalize_source_id(source_system: str, raw_id: Any) -> str:
    """Create a globally unique, collision-proof identifier scoped by source system.
    
    Examples:
        normalize_source_id('HG_CSV', 101) -> 'HG_CSV:101'
        normalize_source_id('SYNTHEA_FHIR', 'P0001') -> 'SYNTHEA_FHIR:P0001'
    """
    clean_raw = str(raw_id).strip()
    return f"{source_system}:{clean_raw}"


@dataclass(frozen=True)
class ParsedFHIRDataset:
    """Immutable container for parsed FHIR entity DataFrames."""
    patients: pd.DataFrame
    encounters: pd.DataFrame
    conditions: pd.DataFrame
    observations: pd.DataFrame


class FHIRBundleParser:
    """Parser for FHIR R4 JSON bundles."""

    def __init__(self, bundle_path: Path | str, source_tag: str = "SYNTHEA_FHIR") -> None:
        self.bundle_path = Path(bundle_path)
        self.source_tag = source_tag

    def parse(self, max_entries: int | None = None) -> ParsedFHIRDataset:
        """Parse bundle into structured DataFrames."""
        if not self.bundle_path.exists():
            raise FileNotFoundError(f"FHIR bundle not found at {self.bundle_path}")

        patients_list: list[dict[str, Any]] = []
        encounters_list: list[dict[str, Any]] = []
        conditions_list: list[dict[str, Any]] = []
        observations_list: list[dict[str, Any]] = []

        with open(self.bundle_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        entries = data.get("entry", [])
        if max_entries is not None:
            entries = entries[:max_entries]

        for item in entries:
            res = item.get("resource", {})
            rt = res.get("resourceType")

            if rt == "Patient":
                patients_list.append(self._parse_patient(res))
            elif rt == "Encounter":
                encounters_list.append(self._parse_encounter(res))
            elif rt == "Condition":
                conditions_list.append(self._parse_condition(res))
            elif rt == "Observation":
                observations_list.append(self._parse_observation(res))

        return ParsedFHIRDataset(
            patients=pd.DataFrame(patients_list) if patients_list else pd.DataFrame(columns=["patient_id", "gender", "birth_date", "region", "insurance", "source_system"]),
            encounters=pd.DataFrame(encounters_list) if encounters_list else pd.DataFrame(columns=["encounter_id", "patient_id", "status", "start_date", "source_system"]),
            conditions=pd.DataFrame(conditions_list) if conditions_list else pd.DataFrame(columns=["condition_id", "patient_id", "condition_text", "source_system"]),
            observations=pd.DataFrame(observations_list) if observations_list else pd.DataFrame(columns=["observation_id", "patient_id", "observation_name", "value", "unit", "effective_date", "source_system"]),
        )

    def _parse_patient(self, res: dict[str, Any]) -> dict[str, Any]:
        raw_id = res.get("id", "")
        extensions = res.get("extension", [])
        
        region = None
        insurance = None
        for ext in extensions:
            url = ext.get("url", "")
            if "region" in url:
                region = ext.get("valueString")
            elif "insurance" in url:
                insurance = ext.get("valueString")

        return {
            "patient_id": normalize_source_id(self.source_tag, raw_id),
            "native_id": raw_id,
            "gender": res.get("gender"),
            "birth_date": res.get("birthDate"),
            "region": region,
            "insurance": insurance,
            "source_system": self.source_tag,
        }

    def _parse_encounter(self, res: dict[str, Any]) -> dict[str, Any]:
        raw_id = res.get("id", "")
        subj_ref = res.get("subject", {}).get("reference", "")
        patient_native_id = subj_ref.split("/")[-1] if "/" in subj_ref else subj_ref

        period = res.get("period", {})
        return {
            "encounter_id": normalize_source_id(self.source_tag, raw_id),
            "native_id": raw_id,
            "patient_id": normalize_source_id(self.source_tag, patient_native_id),
            "status": res.get("status"),
            "start_date": period.get("start"),
            "source_system": self.source_tag,
        }

    def _parse_condition(self, res: dict[str, Any]) -> dict[str, Any]:
        raw_id = res.get("id", "")
        subj_ref = res.get("subject", {}).get("reference", "")
        patient_native_id = subj_ref.split("/")[-1] if "/" in subj_ref else subj_ref

        code_obj = res.get("code", {})
        condition_text = code_obj.get("text")
        if not condition_text and "coding" in code_obj and code_obj["coding"]:
            condition_text = code_obj["coding"][0].get("display")

        return {
            "condition_id": normalize_source_id(self.source_tag, raw_id),
            "native_id": raw_id,
            "patient_id": normalize_source_id(self.source_tag, patient_native_id),
            "condition_text": condition_text or "Unknown",
            "source_system": self.source_tag,
        }

    def _parse_observation(self, res: dict[str, Any]) -> dict[str, Any]:
        raw_id = res.get("id", "")
        subj_ref = res.get("subject", {}).get("reference", "")
        patient_native_id = subj_ref.split("/")[-1] if "/" in subj_ref else subj_ref

        code_text = res.get("code", {}).get("text")
        qty = res.get("valueQuantity", {})

        return {
            "observation_id": normalize_source_id(self.source_tag, raw_id),
            "native_id": raw_id,
            "patient_id": normalize_source_id(self.source_tag, patient_native_id),
            "observation_name": code_text or "unspecified",
            "value": qty.get("value"),
            "unit": qty.get("unit"),
            "effective_date": res.get("effectiveDateTime"),
            "source_system": self.source_tag,
        }
