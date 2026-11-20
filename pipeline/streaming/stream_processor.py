"""
DE-010: DuckDB Streaming Processor with Windowed Aggregations & Late Event Reconciliation.

Implements event-time tumbling and sliding window aggregations over healthcare
streaming events with watermark-based late-arriving event handling.
Idempotent upserts push windowed results into the Silver lakehouse layer.
"""
from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Window key type alias
# ---------------------------------------------------------------------------
WindowKey = Tuple[str, datetime, datetime]  # (event_type, window_start, window_end)


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class WindowSpec:
    """Immutable window specification."""

    size_minutes: int
    slide_minutes: int  # equals size_minutes for tumbling; < size_minutes for sliding

    @property
    def is_tumbling(self) -> bool:
        return self.slide_minutes == self.size_minutes

    @property
    def is_sliding(self) -> bool:
        return self.slide_minutes < self.size_minutes


@dataclass(frozen=True)
class WindowedAggregate:
    """Immutable result of a windowed aggregation over one event-type bucket."""

    event_type: str
    window_start: datetime
    window_end: datetime
    event_count: int
    unique_patients: int
    avg_processing_latency_ms: float
    window_id: str = field(default="")

    def __post_init__(self) -> None:
        # Derive stable deterministic ID after init (frozen, use object.__setattr__)
        if not self.window_id:
            raw = f"{self.event_type}|{self.window_start.isoformat()}|{self.window_end.isoformat()}"
            wid = hashlib.md5(raw.encode()).hexdigest()
            object.__setattr__(self, "window_id", wid)


@dataclass
class WatermarkState:
    """Tracks maximum observed event timestamp (high-water mark)."""

    _max_ts: datetime = field(
        default_factory=lambda: datetime.min.replace(tzinfo=timezone.utc)
    )
    delay_minutes: int = 5

    def advance(self, event_ts: datetime) -> None:
        if event_ts > self._max_ts:
            self._max_ts = event_ts

    @property
    def watermark(self) -> datetime:
        if self._max_ts == datetime.min.replace(tzinfo=timezone.utc):
            return datetime.min.replace(tzinfo=timezone.utc)
        return self._max_ts - timedelta(minutes=self.delay_minutes)

    def is_late(self, event_ts: datetime) -> bool:
        """Return True if event is older than the current watermark."""
        return event_ts < self.watermark


# ---------------------------------------------------------------------------
# Core stream processor
# ---------------------------------------------------------------------------
class DuckDbStreamProcessor:
    """
    In-process streaming processor that:
    - Consumes a list of streaming events (simulating a Kafka consumer)
    - Applies tumbling and/or sliding window aggregations with event-time semantics
    - Handles late-arriving events (up to watermark delay, discards beyond)
    - Produces idempotent WindowedAggregate records

    No actual DuckDB I/O happens here — this is the pure aggregation engine.
    Silver writes are delegated to SilverStreamWriter.
    """

    def __init__(
        self,
        tumbling_window: Optional[WindowSpec] = None,
        sliding_window: Optional[WindowSpec] = None,
        watermark_delay_minutes: int = 5,
    ) -> None:
        self._tumbling = tumbling_window or WindowSpec(size_minutes=60, slide_minutes=60)
        self._sliding = sliding_window
        self._watermark = WatermarkState(delay_minutes=watermark_delay_minutes)
        # Accumulation buffers: window_key -> {metric accumulators}
        self._tumbling_buf: Dict[WindowKey, _WindowBuffer] = {}
        self._sliding_buf: Dict[WindowKey, _WindowBuffer] = {}
        self.discarded_late_count: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def process_events(self, events: List[Dict[str, Any]]) -> None:
        """Ingest a micro-batch of raw events into internal window buffers.

        Watermark advancement uses the micro-batch maximum timestamp so that
        events within the same batch are never classified as late relative to
        each other.  Late-event detection only applies across batch boundaries.
        """
        if not events:
            return

        # Phase 1: parse all timestamps first
        parsed: List[tuple[datetime, Dict[str, Any]]] = [
            (self._parse_ts(evt.get("event_timestamp", "")), evt) for evt in events
        ]

        # Phase 2: accumulate events using the CURRENT watermark (pre-batch)
        # so intra-batch events are not penalised by their siblings
        for ts, evt in parsed:
            if self._watermark.is_late(ts):
                self.discarded_late_count += 1
                logger.debug(
                    "Discarded late event at %s (watermark=%s)", ts, self._watermark.watermark
                )
                continue
            self._accumulate(ts, evt, self._tumbling, self._tumbling_buf)
            if self._sliding:
                self._accumulate(ts, evt, self._sliding, self._sliding_buf)

        # Phase 3: advance watermark using the batch maximum
        batch_max = max(ts for ts, _ in parsed)
        self._watermark.advance(batch_max)

    def flush_tumbling(self) -> List[WindowedAggregate]:
        """Finalise all tumbling windows and return aggregated results."""
        return self._flush(self._tumbling_buf)

    def flush_sliding(self) -> List[WindowedAggregate]:
        """Finalise all sliding windows and return aggregated results."""
        if not self._sliding:
            return []
        return self._flush(self._sliding_buf)

    def flush_all(self) -> Dict[str, List[WindowedAggregate]]:
        return {
            "tumbling": self.flush_tumbling(),
            "sliding": self.flush_sliding(),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_ts(raw: Any) -> datetime:
        if isinstance(raw, datetime):
            if raw.tzinfo is None:
                return raw.replace(tzinfo=timezone.utc)
            return raw
        try:
            dt = datetime.fromisoformat(str(raw))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return datetime.now(timezone.utc)

    @staticmethod
    def _window_start(ts: datetime, spec: WindowSpec) -> datetime:
        """Align timestamp to the nearest window boundary."""
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        slide_secs = spec.slide_minutes * 60
        offset = int((ts - epoch).total_seconds())
        aligned = (offset // slide_secs) * slide_secs
        return epoch + timedelta(seconds=aligned)

    def _accumulate(
        self,
        ts: datetime,
        evt: Dict[str, Any],
        spec: WindowSpec,
        buf: Dict[WindowKey, "_WindowBuffer"],
    ) -> None:
        """Route event into all windows that contain it."""
        w_start = self._window_start(ts, spec)
        # For sliding windows an event may belong to multiple windows
        candidates: List[datetime] = []
        if spec.is_sliding:
            # Walk back enough slide steps to cover the full window size
            steps = spec.size_minutes // spec.slide_minutes
            for i in range(steps):
                cs = w_start - timedelta(minutes=spec.slide_minutes * i)
                ce = cs + timedelta(minutes=spec.size_minutes)
                if cs <= ts < ce:
                    candidates.append(cs)
        else:
            candidates.append(w_start)

        event_type = str(evt.get("event_type", "UNKNOWN"))
        patient_id = str(evt.get("patient_id", ""))
        latency = float(evt.get("processing_latency_ms", 0.0))

        for c_start in candidates:
            c_end = c_start + timedelta(minutes=spec.size_minutes)
            key: WindowKey = (event_type, c_start, c_end)
            if key not in buf:
                buf[key] = _WindowBuffer(event_type=event_type, start=c_start, end=c_end)
            buf[key].add(patient_id, latency)

    @staticmethod
    def _flush(buf: Dict[WindowKey, "_WindowBuffer"]) -> List[WindowedAggregate]:
        results = []
        for _key, wb in buf.items():
            results.append(wb.to_aggregate())
        # Sort deterministically: event_type then window_start
        results.sort(key=lambda a: (a.event_type, a.window_start))
        return results


@dataclass
class _WindowBuffer:
    """Mutable accumulator for one (event_type, window) bucket."""

    event_type: str
    start: datetime
    end: datetime
    _count: int = field(default=0, init=False)
    _patients: set = field(default_factory=set, init=False)
    _latency_sum: float = field(default=0.0, init=False)

    def add(self, patient_id: str, latency_ms: float) -> None:
        self._count += 1
        self._patients.add(patient_id)
        self._latency_sum += latency_ms

    def to_aggregate(self) -> WindowedAggregate:
        avg_lat = self._latency_sum / self._count if self._count else 0.0
        return WindowedAggregate(
            event_type=self.event_type,
            window_start=self.start,
            window_end=self.end,
            event_count=self._count,
            unique_patients=len(self._patients),
            avg_processing_latency_ms=round(avg_lat, 3),
        )
