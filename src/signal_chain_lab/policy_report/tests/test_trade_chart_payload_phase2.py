from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.signal_chain_lab.domain.enums import ChainInputMode, EventProcessingStatus
from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult
from src.signal_chain_lab.policy_report.trade_chart_payload import build_trade_chart_payload


_BASE_TS = datetime(2025, 2, 1, 12, 0, tzinfo=timezone.utc)


def _trade(*, fills_count: int, avg_entry_price: float | None = None, closed_at_offset_min: int = 30) -> TradeResult:
    return TradeResult(
        signal_id="sig_phase2",
        symbol="BTCUSDT",
        side="LONG",
        status="closed",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        policy_name="policy_x",
        fills_count=fills_count,
        avg_entry_price=avg_entry_price,
        created_at=_BASE_TS,
        closed_at=_BASE_TS + timedelta(minutes=closed_at_offset_min),
    )


def _ev(
    offset_min: int,
    event_type: str,
    *,
    state_after: dict | None = None,
    reason: str | None = None,
) -> EventLogEntry:
    return EventLogEntry(
        timestamp=_BASE_TS + timedelta(minutes=offset_min),
        signal_id="sig_phase2",
        event_type=event_type,
        source="engine",
        processing_status=EventProcessingStatus.APPLIED,
        reason=reason,
        state_before={},
        state_after=state_after or {},
    )


def test_sl_moved_creates_two_sl_segments() -> None:
    trade = _trade(fills_count=1)
    event_log = [
        _ev(0, "OPEN_SIGNAL", state_after={"current_sl": 95.0, "tp_levels": [110.0]}),
        _ev(10, "MOVE_STOP", state_after={"current_sl": 98.0, "tp_levels": [110.0]}),
        _ev(20, "CLOSE_FULL", state_after={"current_sl": 98.0, "tp_levels": [110.0]}),
    ]

    payload = build_trade_chart_payload(trade, event_log, candles_by_timeframe={})
    sl_segments = [s for s in payload["level_segments"] if s["kind"] == "SL"]

    assert len(sl_segments) == 2
    assert sl_segments[0]["price"] == 95.0
    assert sl_segments[1]["price"] == 98.0
    assert sl_segments[0]["ts_end"] == (_BASE_TS + timedelta(minutes=10)).isoformat()


def test_avg_entry_hidden_when_single_fill() -> None:
    trade = _trade(fills_count=1, avg_entry_price=100.0)
    event_log = [_ev(0, "OPEN_SIGNAL", state_after={"current_sl": 95.0, "tp_levels": [110.0]})]

    payload = build_trade_chart_payload(trade, event_log, candles_by_timeframe={})
    avg_segments = [s for s in payload["level_segments"] if s["kind"] == "AVG_ENTRY"]

    assert avg_segments == []


def test_avg_entry_present_when_multiple_fills() -> None:
    trade = _trade(fills_count=2, avg_entry_price=101.5)
    event_log = [
        _ev(
            0,
            "OPEN_SIGNAL",
            state_after={
                "current_sl": 95.0,
                "tp_levels": [110.0],
                "entries_planned": [
                    {"plan_id": "e1", "price": 100.0, "order_type": "LIMIT"},
                    {"plan_id": "e2", "price": 103.0, "order_type": "LIMIT"},
                ],
            },
        ),
        EventLogEntry(
            timestamp=_BASE_TS + timedelta(minutes=5),
            signal_id="sig_phase2",
            event_type="FILL",
            source="engine",
            processing_status=EventProcessingStatus.APPLIED,
            reason=None,
            state_before={"entries_planned": [{"plan_id": "e1", "price": 100.0, "order_type": "LIMIT"}], "open_size": 0.0},
            state_after={
                "entries_planned": [{"plan_id": "e2", "price": 103.0, "order_type": "LIMIT"}],
                "open_size": 1.0,
                "fills": [{"timestamp": (_BASE_TS + timedelta(minutes=5)).isoformat(), "price": 100.0, "qty": 1.0, "plan_id": "e1"}],
            },
        ),
        EventLogEntry(
            timestamp=_BASE_TS + timedelta(minutes=10),
            signal_id="sig_phase2",
            event_type="FILL",
            source="engine",
            processing_status=EventProcessingStatus.APPLIED,
            reason=None,
            state_before={"entries_planned": [{"plan_id": "e2", "price": 103.0, "order_type": "LIMIT"}], "open_size": 1.0},
            state_after={
                "entries_planned": [],
                "open_size": 2.0,
                "fills": [
                    {"timestamp": (_BASE_TS + timedelta(minutes=5)).isoformat(), "price": 100.0, "qty": 1.0, "plan_id": "e1"},
                    {"timestamp": (_BASE_TS + timedelta(minutes=10)).isoformat(), "price": 103.0, "qty": 1.0, "plan_id": "e2"},
                ],
            },
        ),
    ]

    payload = build_trade_chart_payload(trade, event_log, candles_by_timeframe={})
    avg_segments = [s for s in payload["level_segments"] if s["kind"] == "AVG_ENTRY"]

    assert len(avg_segments) == 1
    assert avg_segments[0]["price"] == 101.5
    assert avg_segments[0]["ts_start"] == (_BASE_TS + timedelta(minutes=10)).isoformat()


def test_avg_entry_resegments_when_third_fill_changes_average() -> None:
    trade = _trade(fills_count=3, avg_entry_price=102.0, closed_at_offset_min=40)
    event_log = [
        EventLogEntry(
            timestamp=_BASE_TS,
            signal_id="sig_phase2",
            event_type="OPEN_SIGNAL",
            source="engine",
            processing_status=EventProcessingStatus.APPLIED,
            reason=None,
            state_before={},
            state_after={
                "entries_planned": [
                    {"plan_id": "e1", "price": 100.0, "order_type": "LIMIT"},
                    {"plan_id": "e2", "price": 101.0, "order_type": "LIMIT"},
                    {"plan_id": "e3", "price": 105.0, "order_type": "LIMIT"},
                ],
                "current_sl": 95.0,
                "tp_levels": [110.0],
            },
        ),
        EventLogEntry(
            timestamp=_BASE_TS + timedelta(minutes=5),
            signal_id="sig_phase2",
            event_type="FILL",
            source="engine",
            processing_status=EventProcessingStatus.APPLIED,
            reason=None,
            state_before={"entries_planned": [{"plan_id": "e1", "price": 100.0, "order_type": "LIMIT"}], "open_size": 0.0},
            state_after={
                "entries_planned": [
                    {"plan_id": "e2", "price": 101.0, "order_type": "LIMIT"},
                    {"plan_id": "e3", "price": 105.0, "order_type": "LIMIT"},
                ],
                "open_size": 1.0,
                "fills": [{"timestamp": (_BASE_TS + timedelta(minutes=5)).isoformat(), "price": 100.0, "qty": 1.0, "plan_id": "e1"}],
            },
        ),
        EventLogEntry(
            timestamp=_BASE_TS + timedelta(minutes=10),
            signal_id="sig_phase2",
            event_type="FILL",
            source="engine",
            processing_status=EventProcessingStatus.APPLIED,
            reason=None,
            state_before={"entries_planned": [{"plan_id": "e2", "price": 101.0, "order_type": "LIMIT"}], "open_size": 1.0},
            state_after={
                "entries_planned": [{"plan_id": "e3", "price": 105.0, "order_type": "LIMIT"}],
                "open_size": 2.0,
                "fills": [
                    {"timestamp": (_BASE_TS + timedelta(minutes=5)).isoformat(), "price": 100.0, "qty": 1.0, "plan_id": "e1"},
                    {"timestamp": (_BASE_TS + timedelta(minutes=10)).isoformat(), "price": 101.0, "qty": 1.0, "plan_id": "e2"},
                ],
            },
        ),
        EventLogEntry(
            timestamp=_BASE_TS + timedelta(minutes=20),
            signal_id="sig_phase2",
            event_type="FILL",
            source="engine",
            processing_status=EventProcessingStatus.APPLIED,
            reason=None,
            state_before={"entries_planned": [{"plan_id": "e3", "price": 105.0, "order_type": "LIMIT"}], "open_size": 2.0},
            state_after={
                "entries_planned": [],
                "open_size": 3.0,
                "fills": [
                    {"timestamp": (_BASE_TS + timedelta(minutes=5)).isoformat(), "price": 100.0, "qty": 1.0, "plan_id": "e1"},
                    {"timestamp": (_BASE_TS + timedelta(minutes=10)).isoformat(), "price": 101.0, "qty": 1.0, "plan_id": "e2"},
                    {"timestamp": (_BASE_TS + timedelta(minutes=20)).isoformat(), "price": 105.0, "qty": 1.0, "plan_id": "e3"},
                ],
            },
        ),
    ]

    payload = build_trade_chart_payload(trade, event_log, candles_by_timeframe={})
    avg_segments = [s for s in payload["level_segments"] if s["kind"] == "AVG_ENTRY"]

    assert len(avg_segments) == 2
    assert avg_segments[0]["price"] == 100.5
    assert avg_segments[0]["ts_start"] == (_BASE_TS + timedelta(minutes=10)).isoformat()
    assert avg_segments[0]["ts_end"] == (_BASE_TS + timedelta(minutes=20)).isoformat()
    assert avg_segments[1]["price"] == 102.0
    assert avg_segments[1]["ts_start"] == (_BASE_TS + timedelta(minutes=20)).isoformat()


def test_multi_tp_segments_close_on_hit_or_trade_end() -> None:
    trade = _trade(fills_count=1)
    event_log = [
        _ev(0, "OPEN_SIGNAL", state_after={"current_sl": 95.0, "tp_levels": [110.0, 120.0]}),
        _ev(12, "CLOSE_PARTIAL", reason="tp_hit", state_after={"current_sl": 95.0, "tp_levels": [120.0]}),
        _ev(25, "CLOSE_FULL", reason="manual", state_after={"current_sl": 95.0, "tp_levels": [120.0]}),
    ]

    payload = build_trade_chart_payload(trade, event_log, candles_by_timeframe={})
    tp_segments = [s for s in payload["level_segments"] if s["kind"] == "TP"]

    assert len(tp_segments) == 2

    tp1 = next(seg for seg in tp_segments if seg["label"] == "TP1")
    tp2 = next(seg for seg in tp_segments if seg["label"] == "TP2")

    assert tp1["ts_end"] == (_BASE_TS + timedelta(minutes=12)).isoformat()
    assert tp2["ts_end"] == (_BASE_TS + timedelta(minutes=25)).isoformat()


def test_chart_events_include_stable_event_id_for_sidebar_sync() -> None:
    trade = _trade(fills_count=1)
    event_log = [
        _ev(0, "OPEN_SIGNAL", state_after={"current_sl": 95.0, "tp_levels": [110.0], "avg_entry_price": 100.0}),
        _ev(5, "MOVE_STOP", state_after={"current_sl": 97.0, "tp_levels": [110.0], "avg_entry_price": 100.0}),
    ]

    payload = build_trade_chart_payload(trade, event_log, candles_by_timeframe={})
    events = payload["events"]

    assert len(events) == 2
    assert events[0]["event_id"] == "sig_phase2_0"
    assert events[1]["event_id"] == "sig_phase2_1"
    assert "summary" in events[0]


def test_entry_line_closes_on_fill_when_plan_id_is_missing_but_price_matches() -> None:
    trade = _trade(fills_count=1)
    event_log = [
        _ev(
            0,
            "OPEN_SIGNAL",
            state_after={
                "entries_planned": [
                    {"plan_id": "e1", "price": 100.0, "order_type": "LIMIT"},
                    {"plan_id": "e2", "price": 103.0, "order_type": "LIMIT"},
                ],
                "current_sl": 95.0,
                "tp_levels": [110.0],
            },
        ),
        EventLogEntry(
            timestamp=_BASE_TS + timedelta(minutes=5),
            signal_id="sig_phase2",
            event_type="FILL",
            source="engine",
            processing_status=EventProcessingStatus.APPLIED,
            reason=None,
            state_before={
                "entries_planned": [
                    {"plan_id": "e1", "price": 100.0, "order_type": "LIMIT"},
                    {"plan_id": "e2", "price": 103.0, "order_type": "LIMIT"},
                    ],
                "open_size": 0.0,
            },
            state_after={
                "entries_planned": [
                    {"plan_id": "e1", "price": 100.0, "order_type": "LIMIT"},
                    {"plan_id": "e2", "price": 103.0, "order_type": "LIMIT"},
                ],
                "open_size": 1.0,
                "fills": [{"timestamp": (_BASE_TS + timedelta(minutes=5)).isoformat(), "price": 100.0, "qty": 1.0}],
            },
        ),
    ]

    payload = build_trade_chart_payload(trade, event_log, candles_by_timeframe={})
    entry_segments = [s for s in payload["level_segments"] if s["kind"] == "ENTRY_LIMIT"]

    entry1 = next(seg for seg in entry_segments if seg["label"] == "Entry 1")
    entry2 = next(seg for seg in entry_segments if seg["label"] == "Entry 2")

    assert entry1["ts_end"] == (_BASE_TS + timedelta(minutes=5)).isoformat()
    assert entry2["ts_end"] == (_BASE_TS + timedelta(minutes=30)).isoformat()


def test_avg_entry_starts_after_second_fill_even_with_fractional_quantities() -> None:
    trade = _trade(fills_count=2, avg_entry_price=101.5)
    event_log = [
        _ev(
            0,
            "OPEN_SIGNAL",
            state_after={
                "current_sl": 95.0,
                "tp_levels": [110.0],
                "entries_planned": [
                    {"plan_id": "e1", "price": 100.0, "order_type": "LIMIT"},
                    {"plan_id": "e2", "price": 103.0, "order_type": "LIMIT"},
                ],
            },
        ),
        EventLogEntry(
            timestamp=_BASE_TS + timedelta(minutes=5),
            signal_id="sig_phase2",
            event_type="FILL",
            source="engine",
            processing_status=EventProcessingStatus.APPLIED,
            reason=None,
            state_before={"entries_planned": [{"plan_id": "e1", "price": 100.0, "order_type": "LIMIT"}], "open_size": 0.0},
            state_after={
                "entries_planned": [{"plan_id": "e2", "price": 103.0, "order_type": "LIMIT"}],
                "open_size": 0.5,
                "fills": [{"timestamp": (_BASE_TS + timedelta(minutes=5)).isoformat(), "price": 100.0, "qty": 0.5, "plan_id": "e1"}],
            },
        ),
        EventLogEntry(
            timestamp=_BASE_TS + timedelta(minutes=10),
            signal_id="sig_phase2",
            event_type="FILL",
            source="engine",
            processing_status=EventProcessingStatus.APPLIED,
            reason=None,
            state_before={"entries_planned": [{"plan_id": "e2", "price": 103.0, "order_type": "LIMIT"}], "open_size": 0.5},
            state_after={
                "entries_planned": [],
                "open_size": 1.0,
                "fills": [
                    {"timestamp": (_BASE_TS + timedelta(minutes=5)).isoformat(), "price": 100.0, "qty": 0.5, "plan_id": "e1"},
                    {"timestamp": (_BASE_TS + timedelta(minutes=10)).isoformat(), "price": 103.0, "qty": 0.5, "plan_id": "e2"},
                ],
            },
        ),
    ]

    payload = build_trade_chart_payload(trade, event_log, candles_by_timeframe={})
    avg_segments = [s for s in payload["level_segments"] if s["kind"] == "AVG_ENTRY"]

    assert len(avg_segments) == 1
    assert avg_segments[0]["price"] == 101.5
    assert avg_segments[0]["ts_start"] == (_BASE_TS + timedelta(minutes=10)).isoformat()


def test_entry_line_closes_on_open_size_increase_when_fill_snapshot_is_missing() -> None:
    trade = _trade(fills_count=1)
    event_log = [
        _ev(
            0,
            "OPEN_SIGNAL",
            state_after={
                "entries_planned": [{"plan_id": "e1", "price": 100.0, "order_type": "LIMIT"}],
                "current_sl": 95.0,
                "tp_levels": [110.0],
            },
        ),
        EventLogEntry(
            timestamp=_BASE_TS + timedelta(minutes=5),
            signal_id="sig_phase2",
            event_type="FILL",
            source="engine",
            processing_status=EventProcessingStatus.APPLIED,
            price_reference=100.0,
            reason=None,
            state_before={
                "entries_planned": [{"plan_id": "e1", "price": 100.0, "order_type": "LIMIT"}],
                "open_size": 0.0,
            },
            state_after={
                "entries_planned": [{"plan_id": "e1", "price": 100.0, "order_type": "LIMIT"}],
                "open_size": 1.0,
                "current_sl": 95.0,
                "tp_levels": [110.0],
            },
        ),
    ]

    payload = build_trade_chart_payload(trade, event_log, candles_by_timeframe={})
    entry_segments = [s for s in payload["level_segments"] if s["kind"] == "ENTRY_LIMIT"]

    assert len(entry_segments) == 1
    assert entry_segments[0]["label"] == "Entry 1"
    assert entry_segments[0]["ts_end"] == (_BASE_TS + timedelta(minutes=5)).isoformat()


def test_entry_line_uses_fill_timestamp_when_fill_first_appears_in_next_event_state_before() -> None:
    trade = _trade(fills_count=2, avg_entry_price=101.2, closed_at_offset_min=60)
    fill1_ts = _BASE_TS
    fill2_ts = _BASE_TS + timedelta(minutes=7)
    event_log = [
        _ev(
            0,
            "OPEN_SIGNAL",
            state_after={
                "entries_planned": [
                    {"plan_id": "e1", "price": 100.0, "order_type": "MARKET"},
                    {"plan_id": "e2", "price": 104.0, "order_type": "LIMIT"},
                ],
                "current_sl": 95.0,
                "tp_levels": [110.0],
            },
        ),
        EventLogEntry(
            timestamp=_BASE_TS + timedelta(minutes=30),
            signal_id="sig_phase2",
            event_type="MOVE_STOP_TO_BE",
            source="trader",
            processing_status=EventProcessingStatus.APPLIED,
            reason=None,
            state_before={
                "entries_planned": [
                    {"plan_id": "e1", "price": 100.0, "order_type": "MARKET"},
                    {"plan_id": "e2", "price": 104.0, "order_type": "LIMIT"},
                ],
                "fills": [
                    {"timestamp": fill1_ts.isoformat(), "price": 100.0, "qty": 0.7, "plan_id": "e1"},
                    {"timestamp": fill2_ts.isoformat(), "price": 104.0, "qty": 0.3, "plan_id": "e2"},
                ],
                "open_size": 1.0,
                "avg_entry_price": 101.2,
                "current_sl": 95.0,
                "tp_levels": [110.0],
            },
            state_after={
                "entries_planned": [
                    {"plan_id": "e1", "price": 100.0, "order_type": "MARKET"},
                    {"plan_id": "e2", "price": 104.0, "order_type": "LIMIT"},
                ],
                "fills": [
                    {"timestamp": fill1_ts.isoformat(), "price": 100.0, "qty": 0.7, "plan_id": "e1"},
                    {"timestamp": fill2_ts.isoformat(), "price": 104.0, "qty": 0.3, "plan_id": "e2"},
                ],
                "open_size": 1.0,
                "avg_entry_price": 101.2,
                "current_sl": 101.2,
                "tp_levels": [110.0],
            },
        ),
    ]

    payload = build_trade_chart_payload(trade, event_log, candles_by_timeframe={})
    entry_segments = [s for s in payload["level_segments"] if s["kind"] == "ENTRY_LIMIT"]
    avg_segments = [s for s in payload["level_segments"] if s["kind"] == "AVG_ENTRY"]

    assert len(entry_segments) == 1
    assert entry_segments[0]["ts_end"] == fill2_ts.isoformat()
    assert len(avg_segments) == 1
    assert avg_segments[0]["ts_start"] == fill2_ts.isoformat()


def test_market_fill_without_drawn_segment_does_not_close_other_pending_entry() -> None:
    trade = _trade(fills_count=2, avg_entry_price=101.2, closed_at_offset_min=60)
    fill1_ts = _BASE_TS
    fill2_ts = _BASE_TS + timedelta(minutes=7)
    event_log = [
        _ev(
            0,
            "OPEN_SIGNAL",
            state_after={
                "entries_planned": [
                    {"plan_id": "e1", "price": 100.0, "order_type": "MARKET"},
                    {"plan_id": "e2", "price": 104.0, "order_type": "LIMIT"},
                ],
                "current_sl": 95.0,
                "tp_levels": [110.0],
            },
        ),
        EventLogEntry(
            timestamp=_BASE_TS + timedelta(minutes=30),
            signal_id="sig_phase2",
            event_type="MOVE_STOP_TO_BE",
            source="trader",
            processing_status=EventProcessingStatus.APPLIED,
            reason=None,
            state_before={
                "entries_planned": [
                    {"plan_id": "e1", "price": 100.0, "order_type": "MARKET"},
                    {"plan_id": "e2", "price": 104.0, "order_type": "LIMIT"},
                ],
                "fills": [
                    {"timestamp": fill1_ts.isoformat(), "price": 100.0, "qty": 0.7, "plan_id": "e1"},
                    {"timestamp": fill2_ts.isoformat(), "price": 104.0, "qty": 0.3, "plan_id": "e2"},
                ],
                "open_size": 1.0,
                "avg_entry_price": 101.2,
                "current_sl": 95.0,
                "tp_levels": [110.0],
            },
            state_after={
                "entries_planned": [
                    {"plan_id": "e1", "price": 100.0, "order_type": "MARKET"},
                    {"plan_id": "e2", "price": 104.0, "order_type": "LIMIT"},
                ],
                "fills": [
                    {"timestamp": fill1_ts.isoformat(), "price": 100.0, "qty": 0.7, "plan_id": "e1"},
                    {"timestamp": fill2_ts.isoformat(), "price": 104.0, "qty": 0.3, "plan_id": "e2"},
                ],
                "open_size": 1.0,
                "avg_entry_price": 101.2,
                "current_sl": 101.2,
                "tp_levels": [110.0],
            },
        ),
    ]

    payload = build_trade_chart_payload(trade, event_log, candles_by_timeframe={})
    entry_segments = [s for s in payload["level_segments"] if s["kind"] == "ENTRY_LIMIT"]

    assert len(entry_segments) == 1
    assert entry_segments[0]["ts_end"] == fill2_ts.isoformat()
