"""Real-time healthcare clinical event simulation and Kafka streaming transport (DE-009)."""

from pipeline.streaming.models import (
    ClinicalEvent,
    ClinicalEventType,
    generate_deterministic_event_id,
)
from pipeline.streaming.schema_registry import SchemaRegistry, SchemaValidationError
from pipeline.streaming.event_generator import ClinicalEventGenerator
from pipeline.streaming.kafka_transport import (
    KafkaPartitionRouter,
    InMemoryKafkaBroker,
    IdempotentKafkaProducer,
    KafkaConsumer,
    KafkaMessage,
    RecordMetadata,
)

__all__ = [
    "ClinicalEvent",
    "ClinicalEventType",
    "generate_deterministic_event_id",
    "SchemaRegistry",
    "SchemaValidationError",
    "ClinicalEventGenerator",
    "KafkaPartitionRouter",
    "InMemoryKafkaBroker",
    "IdempotentKafkaProducer",
    "KafkaConsumer",
    "KafkaMessage",
    "RecordMetadata",
]
