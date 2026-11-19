"""Synthetic real-time clinical event stream generator (DE-009)."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any

from pipeline.streaming.models import (
    ClinicalEvent,
    ClinicalEventType,
    generate_deterministic_event_id,
)


class ClinicalEventGenerator:
    """Generates synthetic, clinically realistic streaming events."""

    DEPARTMENTS = ["Cardiology", "Emergency", "Internal Medicine", "Oncology", "Neurology", "Pediatrics", "ICU"]
    ADMIT_REASONS = [
        "Acute Myocardial Infarction",
        "Congestive Heart Failure",
        "Chronic Obstructive Pulmonary Disease",
        "Type 2 Diabetes with Ketoacidosis",
        "Pneumonia",
        "Acute Appendicitis",
        "Ischemic Stroke",
    ]
    OBSERVATIONS = [
        ("8480-6", "Systolic Blood Pressure", (100.0, 160.0), "mmHg"),
        ("8462-4", "Diastolic Blood Pressure", (60.0, 100.0), "mmHg"),
        ("883-9", "Heart Rate", (55.0, 115.0), "bpm"),
        ("8310-5", "Body Temperature", (36.2, 38.8), "Cel"),
        ("2339-0", "Blood Glucose", (70.0, 240.0), "mg/dL"),
        ("59408-5", "Oxygen Saturation", (91.0, 99.0), "%"),
    ]
    MEDICATIONS = [
        ("Aspirin", "81 mg", "Oral"),
        ("Metformin", "500 mg", "Oral"),
        ("Lisinopril", "10 mg", "Oral"),
        ("Albuterol", "2.5 mg", "Inhalation"),
        ("Furosemide", "40 mg", "IV"),
        ("Heparin", "5000 units", "Subcutaneous"),
    ]
    OUTCOMES = ["Recovered", "Stable", "Critical"]
    DISPOSITIONS = ["Home", "Skilled Nursing Facility", "Rehabilitation", "Home Healthcare"]

    def __init__(self, seed: int | None = None, source_system: str = "HEALTHGUARD_STREAM") -> None:
        self.rng = random.Random(seed)
        self.source_system = source_system

    def _now_iso(self, offset_seconds: int = 0) -> str:
        base = datetime(2026, 3, 15, 8, 0, 0, tzinfo=timezone.utc)
        target = base + timedelta(seconds=offset_seconds)
        return target.isoformat()

    def generate_admission(
        self,
        patient_id: str,
        encounter_id: str,
        department: str | None = None,
        admit_reason: str | None = None,
        timestamp: str | None = None,
    ) -> ClinicalEvent:
        """Generate an admission event."""
        ts = timestamp or self._now_iso(0)
        dept = department or self.rng.choice(self.DEPARTMENTS)
        reason = admit_reason or self.rng.choice(self.ADMIT_REASONS)

        ev_id = generate_deterministic_event_id(
            self.source_system, encounter_id, ClinicalEventType.ADMITTED.value, ts
        )

        return ClinicalEvent(
            event_id=ev_id,
            event_type=ClinicalEventType.ADMITTED,
            event_timestamp=ts,
            patient_id=patient_id,
            encounter_id=encounter_id,
            payload={
                "department": dept,
                "admit_reason": reason,
            },
            source_system=self.source_system,
        )

    def generate_observation(
        self,
        patient_id: str,
        encounter_id: str,
        observation_code: str | None = None,
        observation_name: str | None = None,
        value: float | None = None,
        unit: str | None = None,
        timestamp: str | None = None,
    ) -> ClinicalEvent:
        """Generate an observation / vitals event."""
        ts = timestamp or self._now_iso(self.rng.randint(600, 3600))
        if not observation_code or not observation_name:
            code, name, (min_v, max_v), u = self.rng.choice(self.OBSERVATIONS)
            val = round(self.rng.uniform(min_v, max_v), 1)
        else:
            code = observation_code
            name = observation_name
            val = float(value) if value is not None else 120.0
            u = unit or "unit"

        ev_id = generate_deterministic_event_id(
            self.source_system, encounter_id, f"{ClinicalEventType.OBSERVATION.value}:{code}", ts
        )

        return ClinicalEvent(
            event_id=ev_id,
            event_type=ClinicalEventType.OBSERVATION,
            event_timestamp=ts,
            patient_id=patient_id,
            encounter_id=encounter_id,
            payload={
                "observation_code": code,
                "observation_name": name,
                "value": val,
                "unit": u,
            },
            source_system=self.source_system,
        )

    def generate_medication(
        self,
        patient_id: str,
        encounter_id: str,
        medication_name: str | None = None,
        dose: str | None = None,
        route: str | None = None,
        timestamp: str | None = None,
    ) -> ClinicalEvent:
        """Generate a medication order event."""
        ts = timestamp or self._now_iso(self.rng.randint(3600, 7200))
        if not medication_name:
            name, d, r = self.rng.choice(self.MEDICATIONS)
        else:
            name = medication_name
            d = dose or "10 mg"
            r = route or "Oral"

        ev_id = generate_deterministic_event_id(
            self.source_system, encounter_id, f"{ClinicalEventType.MEDICATION.value}:{name}", ts
        )

        return ClinicalEvent(
            event_id=ev_id,
            event_type=ClinicalEventType.MEDICATION,
            event_timestamp=ts,
            patient_id=patient_id,
            encounter_id=encounter_id,
            payload={
                "medication_name": name,
                "dose": d,
                "route": r,
            },
            source_system=self.source_system,
        )

    def generate_discharge(
        self,
        patient_id: str,
        encounter_id: str,
        disposition: str | None = None,
        outcome: str | None = None,
        length_of_stay: int | None = None,
        timestamp: str | None = None,
    ) -> ClinicalEvent:
        """Generate a discharge event."""
        los = length_of_stay if length_of_stay is not None else self.rng.randint(1, 10)
        ts = timestamp or self._now_iso(los * 86400)
        disp = disposition or self.rng.choice(self.DISPOSITIONS)
        out = outcome or self.rng.choice(self.OUTCOMES)

        ev_id = generate_deterministic_event_id(
            self.source_system, encounter_id, ClinicalEventType.DISCHARGED.value, ts
        )

        return ClinicalEvent(
            event_id=ev_id,
            event_type=ClinicalEventType.DISCHARGED,
            event_timestamp=ts,
            patient_id=patient_id,
            encounter_id=encounter_id,
            payload={
                "disposition": disp,
                "outcome": out,
                "length_of_stay": los,
            },
            source_system=self.source_system,
        )

    def generate_encounter_journey(
        self,
        patient_id: str,
        encounter_id: str,
        num_observations: int = 3,
        num_medications: int = 2,
    ) -> list[ClinicalEvent]:
        """Generate a complete patient journey with guaranteed chronological ordering."""
        events: list[ClinicalEvent] = []

        # 1. Admission at T=0
        events.append(self.generate_admission(patient_id, encounter_id, timestamp=self._now_iso(0)))

        # 2. Observations spaced every 2 hours
        for i in range(1, num_observations + 1):
            ts = self._now_iso(i * 7200)
            events.append(self.generate_observation(patient_id, encounter_id, timestamp=ts))

        # 3. Medications spaced after observations
        med_start = (num_observations + 1) * 7200
        for j in range(num_medications):
            ts = self._now_iso(med_start + j * 3600)
            events.append(self.generate_medication(patient_id, encounter_id, timestamp=ts))

        # 4. Discharge after all clinical activities
        discharge_ts = self._now_iso(med_start + num_medications * 3600 + 7200)
        events.append(
            self.generate_discharge(patient_id, encounter_id, length_of_stay=3, timestamp=discharge_ts)
        )

        return events
