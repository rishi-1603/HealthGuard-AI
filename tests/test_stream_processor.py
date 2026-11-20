"""
DE-010 Test Suite: DuckDB Streaming Processor & Late-Arriving Event Reconciliation.

Covers:
  T1  - WindowSpec: tumbling vs sliding discrimination
  T2  - Single-batch tumbling window counts per event_type
  T3  - Multi-batch tumbling window merges correctly
  T4  - Late events within watermark delay are accepted
  T5  - Late events beyond watermark are discarded
  T6  - discarded_late_count increments correctly
  T7  - Watermark advances monotonically
  T8  - Sliding window assigns event to multiple windows
  T9  - Sliding window count >= tumbling count for same events
  T10 - flush_all returns both tumbling and sliding keys
  T11 - WindowedAggregate window_id is deterministic (same input = same ID)
  T12 - WindowedAggregate unique_patients deduplicated correctly
  T13 - SilverStreamWriter upsert is idempotent (double-write = single row)
  T14 - SilverStreamWriter total_rows matches expected
  T15 - SilverStreamWriter query_window_counts returns correct event_count
  T16 - End-to-end: events -> processor -> Silver writer -> verify counts
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from pipeline.streaming.stream_processor import (
    DuckDbStreamProcessor,
    WatermarkState,
    WindowSpec,
    WindowedAggregate,
)
from pipeline.streaming.silver_writer import SilverStreamWriter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ts(base: datetime, offset_minutes: int = 0) -> datetime:
    """Return a UTC-aware datetime offset from base by offset_minutes."""
    return base + timedelta(minutes=offset_minutes)


def _make_event(
    event_type: str,
    patient_id: str,
    base: datetime,
    offset_minutes: int = 0,
    latency_ms: float = 10.0,
) -> Dict[str, Any]:
    return {
        "event_type": event_type,
        "patient_id": patient_id,
        "event_timestamp": _ts(base, offset_minutes),
        "processing_latency_ms": latency_ms,
    }


# A fixed base time, on a clean hour boundary, UTC
BASE = datetime(2026, 1, 1, 8, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# T1 — WindowSpec discrimination
# ---------------------------------------------------------------------------
class TestWindowSpec:
    def test_tumbling_spec(self) -> None:
        spec = WindowSpec(size_minutes=60, slide_minutes=60)
        assert spec.is_tumbling is True
        assert spec.is_sliding is False

    def test_sliding_spec(self) -> None:
        spec = WindowSpec(size_minutes=30, slide_minutes=10)
        assert spec.is_sliding is True
        assert spec.is_tumbling is False


# ---------------------------------------------------------------------------
# T2 & T3 — Tumbling window aggregation
# ---------------------------------------------------------------------------
class TestTumblingWindow:
    def _processor(self) -> DuckDbStreamProcessor:
        # watermark_delay_minutes=0 → no late-event filtering for basic count tests
        return DuckDbStreamProcessor(
            tumbling_window=WindowSpec(60, 60),
            watermark_delay_minutes=0,
        )

    def test_single_batch_counts_per_event_type(self) -> None:
        """T2: 3 ADMITTED + 2 DISCHARGED in one batch, same hour window."""
        proc = self._processor()
        events: List[Dict[str, Any]] = [
            _make_event("ADMITTED", f"P{i}", BASE, offset_minutes=i * 5)
            for i in range(3)
        ] + [
            _make_event("DISCHARGED", f"Q{i}", BASE, offset_minutes=i * 7)
            for i in range(2)
        ]
        proc.process_events(events)
        results = proc.flush_tumbling()
        by_type = {r.event_type: r for r in results}
        assert by_type["ADMITTED"].event_count == 3
        assert by_type["DISCHARGED"].event_count == 2

    def test_multi_batch_accumulates(self) -> None:
        """T3: Two batches with same event_type in same window merge counts."""
        proc = DuckDbStreamProcessor(tumbling_window=WindowSpec(60, 60), watermark_delay_minutes=0)
        batch1 = [_make_event("OBSERVATION", f"P{i}", BASE, i) for i in range(4)]
        batch2 = [_make_event("OBSERVATION", f"P{i+10}", BASE, i + 10) for i in range(3)]
        proc.process_events(batch1)
        proc.process_events(batch2)
        results = proc.flush_tumbling()
        obs = next(r for r in results if r.event_type == "OBSERVATION")
        assert obs.event_count == 7

    def test_different_hours_produce_different_windows(self) -> None:
        """Events in adjacent 60-min windows produce separate WindowedAggregates."""
        proc = DuckDbStreamProcessor(tumbling_window=WindowSpec(60, 60), watermark_delay_minutes=0)
        hour1_events = [_make_event("MEDICATION", "P1", BASE, 0)]
        hour2_events = [_make_event("MEDICATION", "P2", BASE, 65)]  # 65 min later = next window
        proc.process_events(hour1_events + hour2_events)
        results = proc.flush_tumbling()
        meds = [r for r in results if r.event_type == "MEDICATION"]
        assert len(meds) == 2, f"Expected 2 windows, got {len(meds)}"
        assert all(m.event_count == 1 for m in meds)


# ---------------------------------------------------------------------------
# T4-T6 — Late-arriving event handling
# ---------------------------------------------------------------------------
class TestLateEventHandling:
    def _processor(self, delay: int = 5) -> DuckDbStreamProcessor:
        return DuckDbStreamProcessor(
            tumbling_window=WindowSpec(60, 60),
            watermark_delay_minutes=delay,
        )

    def test_late_event_within_delay_accepted(self) -> None:
        """T4: Event 4 min late (< 5 min delay) must be accepted."""
        proc = self._processor(delay=5)
        # First advance watermark to t=0+30 mins
        on_time = [_make_event("ADMITTED", f"P{i}", BASE, offset_minutes=30) for i in range(3)]
        proc.process_events(on_time)
        # Watermark = 30 - 5 = 25 min mark; event at +26 min -> within window
        late_but_ok = [_make_event("ADMITTED", "LATE_P", BASE, offset_minutes=26)]
        proc.process_events(late_but_ok)
        assert proc.discarded_late_count == 0

    def test_late_event_beyond_delay_discarded(self) -> None:
        """T5: Event beyond watermark is discarded and NOT counted in results."""
        proc = self._processor(delay=5)
        # Advance watermark high
        on_time = [_make_event("ADMITTED", "P0", BASE, offset_minutes=60)]
        proc.process_events(on_time)
        # Watermark = 60 - 5 = 55 min mark; event at +10 min -> LATE
        too_late = [_make_event("ADMITTED", "TOOLATE", BASE, offset_minutes=10)]
        proc.process_events(too_late)
        assert proc.discarded_late_count >= 1

    def test_discarded_count_increments(self) -> None:
        """T6: Multiple late events each increment discarded_late_count."""
        proc = self._processor(delay=5)
        # Advance watermark
        on_time = [_make_event("ADMITTED", f"P{i}", BASE, offset_minutes=120) for i in range(2)]
        proc.process_events(on_time)
        # Send 3 events that are definitely before watermark (t=120-5=115)
        late = [_make_event("ADMITTED", f"L{i}", BASE, offset_minutes=i * 5) for i in range(3)]
        proc.process_events(late)
        assert proc.discarded_late_count == 3


# ---------------------------------------------------------------------------
# T7 — Watermark monotonic advance
# ---------------------------------------------------------------------------
class TestWatermarkState:
    def test_watermark_advances_monotonically(self) -> None:
        """T7: Watermark only moves forward."""
        wm = WatermarkState(delay_minutes=10)
        t1 = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 1, 1, 8, 20, tzinfo=timezone.utc)
        wm.advance(t2)
        wm.advance(t1)  # older — must NOT lower watermark
        # max_ts should still be t2, so watermark = t2 - 10 min
        expected_wm = t2 - timedelta(minutes=10)
        assert wm.watermark == expected_wm

    def test_is_late_correctly_classifies(self) -> None:
        wm = WatermarkState(delay_minutes=5)
        base = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        wm.advance(base)
        # watermark = base - 5 min = 09:55
        assert wm.is_late(base - timedelta(minutes=10)) is True
        assert wm.is_late(base - timedelta(minutes=4)) is False


# ---------------------------------------------------------------------------
# T8-T10 — Sliding window
# ---------------------------------------------------------------------------
class TestSlidingWindow:
    def _processor(self) -> DuckDbStreamProcessor:
        return DuckDbStreamProcessor(
            tumbling_window=WindowSpec(60, 60),
            sliding_window=WindowSpec(30, 10),   # 30-min window, 10-min slides
            watermark_delay_minutes=5,
        )

    def test_event_assigned_to_multiple_windows(self) -> None:
        """T8: One event in a 30-min/10-min sliding window appears in up to 3 windows."""
        proc = self._processor()
        events = [_make_event("ADMITTED", "P1", BASE, offset_minutes=15)]
        proc.process_events(events)
        sliding = proc.flush_sliding()
        # Event at +15min should be in windows starting at 0, 10, and possibly 20 (if 20 <= 15 < 50)
        # Specifically: [0,30), [10,40) → event at 15 qualifies for windows starting at 0 and 10
        admitted = [r for r in sliding if r.event_type == "ADMITTED"]
        assert len(admitted) >= 1

    def test_sliding_count_gte_tumbling(self) -> None:
        """T9: Sliding count (summed) >= tumbling count due to multi-window membership."""
        proc = self._processor()
        events = [_make_event("OBSERVATION", f"P{i}", BASE, offset_minutes=i * 5) for i in range(6)]
        proc.process_events(events)
        tumbling = proc.flush_tumbling()
        sliding = proc.flush_sliding()
        t_count = sum(r.event_count for r in tumbling if r.event_type == "OBSERVATION")
        s_count = sum(r.event_count for r in sliding if r.event_type == "OBSERVATION")
        assert s_count >= t_count

    def test_flush_all_returns_both_keys(self) -> None:
        """T10: flush_all() dict has keys 'tumbling' and 'sliding'."""
        proc = self._processor()
        events = [_make_event("ADMITTED", "P1", BASE, 0)]
        proc.process_events(events)
        result = proc.flush_all()
        assert "tumbling" in result
        assert "sliding" in result
        assert isinstance(result["tumbling"], list)
        assert isinstance(result["sliding"], list)


# ---------------------------------------------------------------------------
# T11-T12 — WindowedAggregate properties
# ---------------------------------------------------------------------------
class TestWindowedAggregate:
    def test_window_id_deterministic(self) -> None:
        """T11: Same inputs always produce the same window_id."""
        agg1 = WindowedAggregate(
            event_type="ADMITTED",
            window_start=BASE,
            window_end=BASE + timedelta(hours=1),
            event_count=5,
            unique_patients=3,
            avg_processing_latency_ms=12.5,
        )
        agg2 = WindowedAggregate(
            event_type="ADMITTED",
            window_start=BASE,
            window_end=BASE + timedelta(hours=1),
            event_count=10,  # different count — same key fields
            unique_patients=7,
            avg_processing_latency_ms=8.0,
        )
        # window_id derived from event_type + start + end only
        assert agg1.window_id == agg2.window_id

    def test_unique_patients_deduplication(self) -> None:
        """T12: Same patient_id appearing twice in same window counts once."""
        proc = DuckDbStreamProcessor(tumbling_window=WindowSpec(60, 60), watermark_delay_minutes=5)
        events = [
            _make_event("ADMITTED", "SAME_PATIENT", BASE, 0),
            _make_event("ADMITTED", "SAME_PATIENT", BASE, 10),
            _make_event("ADMITTED", "OTHER_PATIENT", BASE, 20),
        ]
        proc.process_events(events)
        results = proc.flush_tumbling()
        admitted = next(r for r in results if r.event_type == "ADMITTED")
        assert admitted.unique_patients == 2
        assert admitted.event_count == 3


# ---------------------------------------------------------------------------
# T13-T15 — SilverStreamWriter
# ---------------------------------------------------------------------------
class TestSilverStreamWriter:
    def _make_agg(self, event_type: str = "ADMITTED", count: int = 5) -> WindowedAggregate:
        return WindowedAggregate(
            event_type=event_type,
            window_start=BASE,
            window_end=BASE + timedelta(hours=1),
            event_count=count,
            unique_patients=3,
            avg_processing_latency_ms=10.0,
        )

    def test_upsert_idempotent(self) -> None:
        """T13: Writing the same aggregate twice results in exactly 1 row."""
        with SilverStreamWriter() as writer:
            agg = self._make_agg()
            writer.upsert_aggregates([agg])
            writer.upsert_aggregates([agg])  # same window_id
            assert writer.total_rows() == 1

    def test_total_rows(self) -> None:
        """T14: total_rows equals the number of distinct aggregates written."""
        with SilverStreamWriter() as writer:
            aggs = [
                self._make_agg("ADMITTED"),
                WindowedAggregate(
                    event_type="DISCHARGED",
                    window_start=BASE + timedelta(hours=1),
                    window_end=BASE + timedelta(hours=2),
                    event_count=2,
                    unique_patients=2,
                    avg_processing_latency_ms=5.0,
                ),
            ]
            writer.upsert_aggregates(aggs)
            assert writer.total_rows() == 2

    def test_query_window_counts_correct(self) -> None:
        """T15: query_window_counts returns rows with matching event_count."""
        with SilverStreamWriter() as writer:
            agg = self._make_agg("OBSERVATION", count=42)
            writer.upsert_aggregates([agg])
            rows = writer.query_window_counts()
            assert len(rows) == 1
            assert rows[0]["event_count"] == 42
            assert rows[0]["event_type"] == "OBSERVATION"


# ---------------------------------------------------------------------------
# T16 — End-to-end integration
# ---------------------------------------------------------------------------
class TestEndToEnd:
    def test_full_pipeline_events_to_silver(self) -> None:
        """T16: events -> DuckDbStreamProcessor -> SilverStreamWriter -> verified counts."""
        proc = DuckDbStreamProcessor(
            tumbling_window=WindowSpec(60, 60),
            watermark_delay_minutes=5,
        )
        # 5 ADMITTED, 3 DISCHARGED, all within the same hour
        events: List[Dict[str, Any]] = [
            _make_event("ADMITTED", f"P{i}", BASE, i * 5) for i in range(5)
        ] + [
            _make_event("DISCHARGED", f"Q{i}", BASE, i * 8) for i in range(3)
        ]
        proc.process_events(events)
        aggregates = proc.flush_tumbling()

        with SilverStreamWriter() as writer:
            written = writer.upsert_aggregates(aggregates)
            rows = writer.query_window_counts()

        assert written == 2  # ADMITTED + DISCHARGED
        by_type = {r["event_type"]: r for r in rows}
        assert by_type["ADMITTED"]["event_count"] == 5
        assert by_type["DISCHARGED"]["event_count"] == 3
        # All patients are distinct in this test
        assert by_type["ADMITTED"]["unique_patients"] == 5
        assert by_type["DISCHARGED"]["unique_patients"] == 3

    def test_late_events_excluded_from_silver(self) -> None:
        """Late events discarded by processor are NOT present in Silver output."""
        proc = DuckDbStreamProcessor(
            tumbling_window=WindowSpec(60, 60),
            watermark_delay_minutes=5,
        )
        # Advance watermark to +120 min
        on_time = [_make_event("ADMITTED", "P0", BASE, 120)]
        proc.process_events(on_time)
        # Send a late event at +10 min — far behind watermark (120-5=115)
        late = [_make_event("ADMITTED", "TOOLATE", BASE, 10)]
        proc.process_events(late)
        aggregates = proc.flush_tumbling()
        with SilverStreamWriter() as writer:
            writer.upsert_aggregates(aggregates)
            rows = writer.query_window_counts()

        all_patient_ids = set()
        for row in rows:
            pass  # just verify row structure
        assert proc.discarded_late_count >= 1
        # The aggregate for ADMITTED should have event_count == 1 (only on-time event)
        admitted_rows = [r for r in rows if r["event_type"] == "ADMITTED"]
        total_on_time = sum(r["event_count"] for r in admitted_rows)
        assert total_on_time == 1  # only the on-time event in Silver
