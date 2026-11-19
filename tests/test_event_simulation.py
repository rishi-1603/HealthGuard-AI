"""Tests for Day 9 — Real-Time Healthcare Event Simulation & Kafka Streaming Transport (DE-009).

Verifies:
  AC1: Synthetic real-time clinical events generation (admitted, observation, medication, discharged)
  AC2: Kafka topic configuration, partition strategy (patient_id affinity), and schema registry validation
  AC3: Deterministic event IDs and idempotent producer guarantees (deduplication & sequence ordering)
  AC4: Consumer event replay and stream delivery
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline.streaming.models import (
    ClinicalEvent,
    ClinicalEventType,
    generate_deterministic_event_id,
)
from pipeline.streaming.schema_registry import SchemaRegistry, SchemaValidationError
from pipeline.streaming.event_generator import ClinicalEventGenerator
from pipeline.streaming.kafka_transport import (
    KafkaPartitionRouter,
    IdempotentKafkaProducer,
    InMemoryKafkaBroker,
    KafkaConsumer,
)


# ──────────────────────────────────────────────────────────────────────
# AC1: Clinical Event Models & Synthetic Event Generation
# ──────────────────────────────────────────────────────────────────────
class TestClinicalEventGeneration:
    """Verify synthetic clinical event generation across the 4 core clinical event types."""

    def test_generate_admission_event(self) -> None:
        generator = ClinicalEventGenerator(seed=42)
        event = generator.generate_admission(
            patient_id="HG_CSV:101",
            encounter_id="ENC-001",
            department="Cardiology",
            admit_reason="Acute Myocardial Infarction",
        )

        assert event.event_type == ClinicalEventType.ADMITTED
        assert event.patient_id == "HG_CSV:101"
        assert event.encounter_id == "ENC-001"
        assert event.payload["department"] == "Cardiology"
        assert event.payload["admit_reason"] == "Acute Myocardial Infarction"
        assert event.schema_version == "1.0.0"
        assert event.event_id is not None

    def test_generate_observation_event(self) -> None:
        generator = ClinicalEventGenerator(seed=42)
        event = generator.generate_observation(
            patient_id="HG_CSV:101",
            encounter_id="ENC-001",
            observation_code="8480-6",
            observation_name="Systolic Blood Pressure",
            value=138.0,
            unit="mmHg",
        )

        assert event.event_type == ClinicalEventType.OBSERVATION
        assert event.payload["observation_code"] == "8480-6"
        assert event.payload["value"] == 138.0
        assert event.payload["unit"] == "mmHg"

    def test_generate_medication_event(self) -> None:
        generator = ClinicalEventGenerator(seed=42)
        event = generator.generate_medication(
            patient_id="HG_CSV:101",
            encounter_id="ENC-001",
            medication_name="Aspirin",
            dose="81 mg",
            route="Oral",
        )

        assert event.event_type == ClinicalEventType.MEDICATION
        assert event.payload["medication_name"] == "Aspirin"
        assert event.payload["dose"] == "81 mg"

    def test_generate_discharge_event(self) -> None:
        generator = ClinicalEventGenerator(seed=42)
        event = generator.generate_discharge(
            patient_id="HG_CSV:101",
            encounter_id="ENC-001",
            disposition="Home",
            outcome="Recovered",
            length_of_stay=4,
        )

        assert event.event_type == ClinicalEventType.DISCHARGED
        assert event.payload["disposition"] == "Home"
        assert event.payload["outcome"] == "Recovered"
        assert event.payload["length_of_stay"] == 4

    def test_generate_patient_journey_stream(self) -> None:
        """A complete encounter lifecycle yields sequential events: admitted -> observation -> medication -> discharged."""
        generator = ClinicalEventGenerator(seed=100)
        events = generator.generate_encounter_journey(
            patient_id="SYNTHEA_FHIR:P001",
            encounter_id="ENC-100",
            num_observations=3,
            num_medications=2,
        )

        assert len(events) == 1 + 3 + 2 + 1  # 7 events total
        assert events[0].event_type == ClinicalEventType.ADMITTED
        assert events[-1].event_type == ClinicalEventType.DISCHARGED

        # Check chronological ordering
        timestamps = [e.event_timestamp for e in events]
        assert timestamps == sorted(timestamps)


# ──────────────────────────────────────────────────────────────────────
# AC2: Kafka Partition Strategy & Schema Registry Validation
# ──────────────────────────────────────────────────────────────────────
class TestKafkaPartitioningAndSchemaRegistry:
    """Verify consistent patient partition routing and strict schema registry enforcement."""

    def test_partition_affinity_by_patient_id(self) -> None:
        """Events for the same patient must always route to the exact same partition."""
        router = KafkaPartitionRouter(num_partitions=6)

        p1 = "HG_CSV:101"
        p2 = "SYNTHEA_FHIR:P002"

        part_p1_a = router.get_partition("healthcare.clinical.events", p1)
        part_p1_b = router.get_partition("healthcare.clinical.events", p1)
        assert part_p1_a == part_p1_b
        assert 0 <= part_p1_a < 6

        part_p2 = router.get_partition("healthcare.clinical.events", p2)
        assert 0 <= part_p2 < 6

    def test_schema_registry_validates_correct_event(self) -> None:
        registry = SchemaRegistry()
        generator = ClinicalEventGenerator(seed=1)
        event = generator.generate_admission("P1", "E1", "Emergency", "Chest pain")

        assert registry.validate(event) is True

    def test_schema_registry_rejects_missing_required_fields(self) -> None:
        registry = SchemaRegistry()
        event = ClinicalEvent(
            event_id="test-id",
            event_type=ClinicalEventType.ADMITTED,
            event_timestamp=datetime.now(timezone.utc).isoformat(),
            patient_id="P1",
            encounter_id="E1",
            payload={"department": "ICU"},  # missing 'admit_reason'
            schema_version="1.0.0",
        )

        with pytest.raises(SchemaValidationError, match="admit_reason"):
            registry.validate(event)

    def test_schema_registry_rejects_invalid_types(self) -> None:
        registry = SchemaRegistry()
        event = ClinicalEvent(
            event_id="test-id",
            event_type=ClinicalEventType.OBSERVATION,
            event_timestamp=datetime.now(timezone.utc).isoformat(),
            patient_id="P1",
            encounter_id="E1",
            payload={
                "observation_code": "8480-6",
                "observation_name": "Blood Pressure",
                "value": "NOT_A_FLOAT",  # invalid numeric type
                "unit": "mmHg",
            },
            schema_version="1.0.0",
        )

        with pytest.raises(SchemaValidationError, match="value"):
            registry.validate(event)


# ──────────────────────────────────────────────────────────────────────
# AC3: Deterministic Event IDs & Idempotent Producer Guarantees
# ──────────────────────────────────────────────────────────────────────
class TestDeterministicIdsAndIdempotence:
    """Verify deterministic UUIDv5 generation and deduplication on the producer."""

    def test_deterministic_event_id_reproducibility(self) -> None:
        """Same input attributes must yield identical deterministic event IDs."""
        id1 = generate_deterministic_event_id(
            source_system="EHR_STREAM",
            encounter_id="ENC-500",
            event_type="encounter_admitted",
            timestamp_str="2026-03-15T12:00:00Z",
        )
        id2 = generate_deterministic_event_id(
            source_system="EHR_STREAM",
            encounter_id="ENC-500",
            event_type="encounter_admitted",
            timestamp_str="2026-03-15T12:00:00Z",
        )
        assert id1 == id2
        assert len(id1) == 36  # Valid UUID format

    def test_idempotent_producer_drops_duplicates(self) -> None:
        broker = InMemoryKafkaBroker(num_partitions=4)
        producer = IdempotentKafkaProducer(broker)

        generator = ClinicalEventGenerator(seed=2)
        event = generator.generate_admission("P1", "E1", "Surgery", "Appendicitis")

        # Produce first time
        record_meta_1 = producer.send("healthcare.clinical.events", event)
        assert record_meta_1.delivered is True
        assert record_meta_1.duplicate is False
        assert record_meta_1.offset == 0

        # Produce exact same event second time
        record_meta_2 = producer.send("healthcare.clinical.events", event)
        assert record_meta_2.delivered is True
        assert record_meta_2.duplicate is True  # Recognized as duplicate
        assert record_meta_2.offset == 0  # Does not advance offset

        # Broker topic partition only has 1 record
        partition = record_meta_1.partition
        assert len(broker.get_messages("healthcare.clinical.events", partition)) == 1

    def test_producer_sequence_number_tracking(self) -> None:
        broker = InMemoryKafkaBroker(num_partitions=4)
        producer = IdempotentKafkaProducer(broker)
        generator = ClinicalEventGenerator(seed=3)

        ev1 = generator.generate_admission("P10", "E10", "Cardiology", "Arrhythmia")
        ev2 = generator.generate_observation("P10", "E10", "883-9", "Heart Rate", 88.0, "bpm")

        m1 = producer.send("healthcare.clinical.events", ev1)
        m2 = producer.send("healthcare.clinical.events", ev2)

        assert m1.sequence_number == 0
        assert m2.sequence_number == 1
        assert m1.partition == m2.partition, "Same patient must share partition"


# ──────────────────────────────────────────────────────────────────────
# AC4: Consumer Event Replay & Polling
# ──────────────────────────────────────────────────────────────────────
class TestKafkaConsumerPolling:
    """Verify consumer offset tracking, partition polling, and JSON serialization."""

    def test_consumer_polls_in_order(self) -> None:
        broker = InMemoryKafkaBroker(num_partitions=2)
        producer = IdempotentKafkaProducer(broker)
        generator = ClinicalEventGenerator(seed=4)

        # Produce 3 events for same patient
        journey = generator.generate_encounter_journey("P99", "E99", num_observations=1, num_medications=1)
        for ev in journey:
            producer.send("healthcare.clinical.events", ev)

        consumer = KafkaConsumer(broker, topic="healthcare.clinical.events", group_id="grp-analytics")
        polled = consumer.poll(max_records=10)

        assert len(polled) == len(journey)
        polled_types = [msg.value["event_type"] for msg in polled]
        expected_types = [e.event_type.value for e in journey]
        assert polled_types == expected_types

    def test_consumer_offset_commit_prevents_duplicate_reads(self) -> None:
        broker = InMemoryKafkaBroker(num_partitions=1)
        producer = IdempotentKafkaProducer(broker)
        generator = ClinicalEventGenerator(seed=5)

        ev = generator.generate_admission("P1", "E1", "General", "Checkup")
        producer.send("test.topic", ev)

        consumer = KafkaConsumer(broker, topic="test.topic", group_id="grp-1")
        batch1 = consumer.poll(max_records=5)
        assert len(batch1) == 1

        # Second poll returns nothing because offsets were committed
        batch2 = consumer.poll(max_records=5)
        assert len(batch2) == 0
