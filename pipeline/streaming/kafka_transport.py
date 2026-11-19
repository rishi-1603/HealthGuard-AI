"""Kafka streaming transport, consistent partition routing, and idempotent producer (DE-009)."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from pipeline.streaming.models import ClinicalEvent
from pipeline.streaming.schema_registry import SchemaRegistry

logger = logging.getLogger(__name__)


@dataclass
class RecordMetadata:
    """Metadata returned upon successful produce."""

    topic: str
    partition: int
    offset: int
    sequence_number: int
    timestamp_ms: int
    delivered: bool = True
    duplicate: bool = False


@dataclass
class KafkaMessage:
    """Message stored on the broker topic partition."""

    topic: str
    partition: int
    offset: int
    key: str
    value: dict[str, Any]
    timestamp_ms: int


class KafkaPartitionRouter:
    """Calculates partition index using consistent hashing on patient_id."""

    def __init__(self, num_partitions: int = 4) -> None:
        self.num_partitions = max(1, num_partitions)

    def get_partition(self, topic: str, partition_key: str) -> int:
        """Route partition key deterministically via MD5 hash modulo num_partitions."""
        h = hashlib.md5(partition_key.encode("utf-8")).hexdigest()
        return int(h, 16) % self.num_partitions


class InMemoryKafkaBroker:
    """In-memory multi-partition Kafka broker simulating distributed cluster semantics."""

    def __init__(self, num_partitions: int = 4) -> None:
        self.num_partitions = num_partitions
        # topic -> partition -> list[KafkaMessage]
        self._topics: dict[str, dict[int, list[KafkaMessage]]] = {}
        # consumer_group -> topic -> partition -> last_committed_offset
        self._committed_offsets: dict[str, dict[str, dict[int, int]]] = {}

    def _ensure_topic(self, topic: str) -> None:
        if topic not in self._topics:
            self._topics[topic] = {p: [] for p in range(self.num_partitions)}

    def append(self, topic: str, partition: int, key: str, value: dict[str, Any]) -> int:
        """Append message to partition and return assigned offset."""
        self._ensure_topic(topic)
        p_queue = self._topics[topic][partition]
        offset = len(p_queue)
        msg = KafkaMessage(
            topic=topic,
            partition=partition,
            offset=offset,
            key=key,
            value=value,
            timestamp_ms=int(time.time() * 1000),
        )
        p_queue.append(msg)
        return offset

    def get_messages(self, topic: str, partition: int) -> list[KafkaMessage]:
        self._ensure_topic(topic)
        return list(self._topics[topic].get(partition, []))

    def fetch(
        self, topic: str, partition: int, start_offset: int, max_records: int
    ) -> list[KafkaMessage]:
        self._ensure_topic(topic)
        msgs = self._topics[topic].get(partition, [])
        return msgs[start_offset : start_offset + max_records]

    def commit_offset(self, group_id: str, topic: str, partition: int, offset: int) -> None:
        if group_id not in self._committed_offsets:
            self._committed_offsets[group_id] = {}
        if topic not in self._committed_offsets[group_id]:
            self._committed_offsets[group_id][topic] = {}
        self._committed_offsets[group_id][topic][partition] = offset

    def get_committed_offset(self, group_id: str, topic: str, partition: int) -> int:
        return self._committed_offsets.get(group_id, {}).get(topic, {}).get(partition, 0)


class IdempotentKafkaProducer:
    """Kafka producer enforcing schema validation, partition routing, and deduplication."""

    def __init__(
        self,
        broker: InMemoryKafkaBroker,
        schema_registry: SchemaRegistry | None = None,
        router: KafkaPartitionRouter | None = None,
    ) -> None:
        self.broker = broker
        self.schema_registry = schema_registry or SchemaRegistry()
        self.router = router or KafkaPartitionRouter(num_partitions=broker.num_partitions)

        # Tracks seen event_ids for exactly-once deduplication: event_id -> RecordMetadata
        self._dedup_cache: dict[str, RecordMetadata] = {}
        # Tracks monotonic sequence numbers per (topic, partition)
        self._seq_numbers: dict[tuple[str, int], int] = {}

    def send(self, topic: str, event: ClinicalEvent) -> RecordMetadata:
        """Validate and produce event to topic partition idempotently."""
        # 1. Schema registry validation
        self.schema_registry.validate(event)

        # 2. Idempotency check: if event_id already acknowledged, return cached metadata
        if event.event_id in self._dedup_cache:
            prev = self._dedup_cache[event.event_id]
            logger.info("Duplicate event %s dropped by idempotent producer", event.event_id)
            return RecordMetadata(
                topic=prev.topic,
                partition=prev.partition,
                offset=prev.offset,
                sequence_number=prev.sequence_number,
                timestamp_ms=prev.timestamp_ms,
                delivered=True,
                duplicate=True,
            )

        # 3. Partition routing
        partition = self.router.get_partition(topic, event.partition_key)

        # 4. Monotonic sequence number per partition
        seq_key = (topic, partition)
        seq_num = self._seq_numbers.get(seq_key, 0)
        self._seq_numbers[seq_key] = seq_num + 1

        # 5. Append to broker
        offset = self.broker.append(
            topic=topic,
            partition=partition,
            key=event.partition_key,
            value=event.to_dict(),
        )

        now_ms = int(time.time() * 1000)
        meta = RecordMetadata(
            topic=topic,
            partition=partition,
            offset=offset,
            sequence_number=seq_num,
            timestamp_ms=now_ms,
            delivered=True,
            duplicate=False,
        )

        self._dedup_cache[event.event_id] = meta
        return meta


class KafkaConsumer:
    """Consumer group polling partitions in order with offset commits."""

    def __init__(self, broker: InMemoryKafkaBroker, topic: str, group_id: str) -> None:
        self.broker = broker
        self.topic = topic
        self.group_id = group_id

    def poll(self, max_records: int = 100) -> list[KafkaMessage]:
        """Poll messages across assigned topic partitions and advance committed offsets."""
        messages: list[KafkaMessage] = []
        records_left = max_records

        for p in range(self.broker.num_partitions):
            if records_left <= 0:
                break

            current_offset = self.broker.get_committed_offset(self.group_id, self.topic, p)
            fetched = self.broker.fetch(self.topic, p, current_offset, records_left)

            if fetched:
                messages.extend(fetched)
                new_offset = fetched[-1].offset + 1
                self.broker.commit_offset(self.group_id, self.topic, p, new_offset)
                records_left -= len(fetched)

        return messages
