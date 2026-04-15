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
        _ev(0, "OPEN_SIGNAL", state_after={"current_sl": 95.0, "tp_levels": [110.0]}),
        _ev(5, "ADD_ENTRY", state_after={"current_sl": 95.0, "tp_levels": [110.0], "avg_entry_price": 101.5}),
    ]

    payload = build_trade_chart_payload(trade, event_log, candles_by_timeframe={})
    avg_segments = [s for s in payload["level_segments"] if s["kind"] == "AVG_ENTRY"]

    assert len(avg_segments) == 1
    assert avg_segments[0]["price"] == 101.5


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
    assert tp2["ts_end"] == trade.closed_at.isoformat()
