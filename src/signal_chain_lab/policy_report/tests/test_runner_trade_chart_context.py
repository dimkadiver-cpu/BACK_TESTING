from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.signal_chain_lab.domain.enums import ChainInputMode, EventProcessingStatus
from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult
from src.signal_chain_lab.market.data_models import Candle
from src.signal_chain_lab.policy_report.runner import _load_trade_chart_candles_by_timeframe
from src.signal_chain_lab.policy_report.trade_chart_echarts import render_trade_chart_echarts
from src.signal_chain_lab.policy_report.trade_chart_payload import build_trade_chart_payload
from src.signal_chain_lab.policy_report.event_normalizer import ImpactData, ReportCanonicalEvent, EventRelations, EventVisual


class _ProviderStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, datetime, datetime]] = []

    def get_range(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Candle]:
        self.calls.append((symbol, timeframe, start, end))
        return [
            Candle(
                timestamp=start,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=10.0,
                symbol=symbol,
                timeframe=timeframe,
            )
        ]


def test_trade_chart_context_window_extends_by_15_hours_each_side() -> None:
    created_at = datetime(2025, 2, 1, 12, 0, tzinfo=timezone.utc)
    closed_at = created_at + timedelta(hours=2)
    trade = TradeResult(
        signal_id="sig_ctx",
        symbol="BTCUSDT",
        side="LONG",
        status="closed",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        policy_name="policy_x",
        created_at=created_at,
        closed_at=closed_at,
    )
    chain = SimpleNamespace(metadata={"timeframe": "1m"})
    provider = _ProviderStub()

    candles = _load_trade_chart_candles_by_timeframe(
        trade=trade,
        chain=chain,
        market_provider=provider,
        event_log=[],
    )

    assert candles
    assert provider.calls
    _, _, start, end = provider.calls[0]
    assert start == created_at - timedelta(hours=15)
    assert end == closed_at + timedelta(hours=15)


# ---------------------------------------------------------------------------
# Helpers for payload tests
# ---------------------------------------------------------------------------

_TS = datetime(2025, 3, 1, 10, 0, tzinfo=timezone.utc)


def _trade(signal_id: str = "sig_payload") -> TradeResult:
    return TradeResult(
        signal_id=signal_id,
        symbol="BTCUSDT",
        side="LONG",
        status="closed",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        policy_name="test_policy",
        created_at=_TS,
        closed_at=_TS + timedelta(hours=2),
    )


def _entry(event_type: str, **kwargs) -> EventLogEntry:
    return EventLogEntry(
        timestamp=_TS,
        signal_id="sig_payload",
        event_type=event_type,
        source=kwargs.get("source", "engine"),
        processing_status=kwargs.get("processing_status", EventProcessingStatus.APPLIED),
        price_reference=kwargs.get("price_reference", None),
        reason=kwargs.get("reason", None),
        state_before=kwargs.get("state_before", {}),
        state_after=kwargs.get("state_after", {}),
    )


def _build_payload(event_log: list[EventLogEntry]) -> dict:
    return build_trade_chart_payload(
        trade=_trade(),
        event_log=event_log,
        candles_by_timeframe={},
    )


# ---------------------------------------------------------------------------
# Tests — payload contains canonical fields (PRD §14.4)
# ---------------------------------------------------------------------------

def test_payload_event_contains_event_code() -> None:
    """Ogni evento nel payload contiene il campo event_code (PRD §14.4)."""
    payload = _build_payload([_entry("OPEN_SIGNAL")])
    events = payload["events"]
    assert len(events) >= 1
    for ev in events:
        assert "event_code" in ev, f"event_code mancante in {ev}"


def test_payload_event_contains_chart_marker_kind() -> None:
    """Ogni evento nel payload contiene chart_marker_kind (PRD §14.4)."""
    payload = _build_payload([_entry("FILL")])
    events = payload["events"]
    assert len(events) >= 1
    for ev in events:
        assert "chart_marker_kind" in ev


def test_payload_event_contains_geometry_effect() -> None:
    payload = _build_payload([_entry("MOVE_STOP")])
    for ev in payload["events"]:
        assert "geometry_effect" in ev


def test_payload_event_contains_event_list_section() -> None:
    payload = _build_payload([_entry("OPEN_SIGNAL")])
    for ev in payload["events"]:
        assert "event_list_section" in ev


def test_payload_event_contains_rail_label() -> None:
    payload = _build_payload([_entry("OPEN_SIGNAL")])
    setup_event = next(ev for ev in payload["events"] if ev["event_code"] == "SETUP_CREATED")
    assert "rail_label" in setup_event
    assert setup_event["rail_label"]


def test_payload_event_contains_position_effect() -> None:
    payload = _build_payload([_entry("ADD_ENTRY")])
    for ev in payload["events"]:
        assert "position_effect" in ev


def test_payload_event_contains_state_delta_essential() -> None:
    payload = _build_payload([_entry("CLOSE_FULL", reason="sl_hit")])
    for ev in payload["events"]:
        assert "state_delta_essential" in ev


# ---------------------------------------------------------------------------
# Tests — placement by chart_marker_kind (RF-2, RF-4)
# ---------------------------------------------------------------------------

def test_entry_filled_initial_placement_is_chart() -> None:
    """ENTRY_FILLED_INITIAL (REQUIRED) + price → placement = 'chart' (PRD §9)."""
    payload = _build_payload([
        _entry("FILL", state_after={
            "fills": [{"timestamp": "2025-03-01T10:00:00+00:00", "price": 42000.0, "qty": 1.0}]
        })
    ])
    chart_events = [ev for ev in payload["events"] if ev["event_code"] == "ENTRY_FILLED_INITIAL"]
    assert len(chart_events) >= 1
    assert all(ev["placement"] == "chart" for ev in chart_events)


def test_stop_moved_no_chart_marker() -> None:
    """STOP_MOVED (chart_marker_kind=NONE) → placement = 'rail', never 'chart' (RF-4)."""
    payload = _build_payload([_entry("MOVE_STOP", price_reference=41000.0)])
    stop_events = [ev for ev in payload["events"] if ev["event_code"] == "STOP_MOVED"]
    assert len(stop_events) >= 1
    for ev in stop_events:
        assert ev["placement"] == "rail", f"STOP_MOVED deve essere rail, trovato: {ev['placement']}"
        assert ev["chart_marker_kind"] == "NONE"


def test_break_even_activated_no_chart_marker() -> None:
    """BREAK_EVEN_ACTIVATED (chart_marker_kind=NONE) → placement = 'rail' (RF-4)."""
    payload = _build_payload([_entry("MOVE_STOP_TO_BE", price_reference=41500.0)])
    be_events = [ev for ev in payload["events"] if ev["event_code"] == "BREAK_EVEN_ACTIVATED"]
    assert len(be_events) >= 1
    for ev in be_events:
        assert ev["placement"] == "rail"
        assert ev["chart_marker_kind"] == "NONE"


def test_setup_created_no_chart_marker() -> None:
    """SETUP_CREATED (chart_marker_kind=NONE) → placement = 'rail', not chart (RF-2)."""
    payload = _build_payload([_entry("OPEN_SIGNAL")])
    setup_events = [ev for ev in payload["events"] if ev["event_code"] == "SETUP_CREATED"]
    assert len(setup_events) >= 1
    for ev in setup_events:
        assert ev["placement"] == "rail"
        assert ev["chart_marker_kind"] == "NONE"


def test_ignored_event_placement_is_section_b() -> None:
    """IGNORED → placement = 'section_b' (escluso da rail, PRD §5)."""
    payload = _build_payload([
        _entry("ADD_ENTRY", processing_status=EventProcessingStatus.IGNORED)
    ])
    ignored_events = [ev for ev in payload["events"] if ev["event_code"] == "IGNORED"]
    assert len(ignored_events) >= 1
    for ev in ignored_events:
        assert ev["placement"] == "section_b"
        assert ev["event_list_section"] == "B"


def test_exit_final_timeout_placement_is_chart_optional() -> None:
    """EXIT_FINAL_TIMEOUT (REQUIRED) + price → placement = 'chart' (PRD §9)."""
    payload = _build_payload([
        _entry("CLOSE_FULL", reason="chain_timeout", price_reference=41800.0)
    ])
    timeout_events = [ev for ev in payload["events"] if ev["event_code"] == "EXIT_FINAL_TIMEOUT"]
    assert len(timeout_events) >= 1
    for ev in timeout_events:
        assert ev["placement"] == "chart"
        assert ev["chart_marker_kind"] == "REQUIRED"


def test_entry_order_added_no_chart_marker_in_payload(monkeypatch) -> None:
    """ENTRY_ORDER_ADDED (chart_marker_kind=NONE) stays on rail in final payload."""
    planned_event = ReportCanonicalEvent(
        id="sig_payload_rail_entry_order",
        ts=_TS.isoformat(),
        phase="ENTRY",
        event_class="STRUCTURAL",
        subtype="ENTRY_ORDER_ADDED",
        title="ENTRY PLANNED",
        price_anchor=41950.0,
        source="ENGINE",
        impact=ImpactData(),
        summary="ENTRY PLANNED @ 41950",
        raw_text=None,
        details={},
        visual=EventVisual(color_key="entry", lane_key="rail", chart_anchor_mode="exact"),
        relations=EventRelations(sequence_group=_TS.isoformat()),
        event_code="ENTRY_ORDER_ADDED",
        stage="ENTRY",
        position_effect="PLAN_UPDATED",
        display_group="ENTRY_PLAN",
        display_label="ENTRY PLANNED",
        event_list_section="A",
        chart_marker_kind="NONE",
        geometry_effect="ADD_PENDING_LEVEL",
        state_delta_full=[],
        state_delta_essential=[],
        raw_event_ref="sig_payload:0:ENTRY_ORDER_ADDED",
    )

    monkeypatch.setattr(
        "src.signal_chain_lab.policy_report.trade_chart_payload.normalize_events",
        lambda trade, event_log: [planned_event],
    )

    payload = build_trade_chart_payload(
        trade=_trade(),
        event_log=[],
        candles_by_timeframe={},
    )
    events = [ev for ev in payload["events"] if ev["event_code"] == "ENTRY_ORDER_ADDED"]
    assert len(events) == 1
    assert events[0]["placement"] == "rail"
    assert events[0]["chart_marker_kind"] == "NONE"


def test_pending_cancelled_trader_placement_is_chart_optional_when_price_is_known() -> None:
    payload = _build_payload([
        _entry(
            "CANCEL_PENDING",
            source="trader",
            state_before={
                "open_size": 0.0,
                "entries_planned": [{"plan_id": "e1", "price": 41950.0, "order_type": "LIMIT"}],
            },
            state_after={"open_size": 0.0, "entries_planned": []},
        )
    ])
    events = [ev for ev in payload["events"] if ev["event_code"] == "PENDING_CANCELLED_TRADER"]
    assert len(events) == 1
    assert events[0]["placement"] == "chart_optional"
    assert events[0]["chart_marker_kind"] == "OPTIONAL_LIGHT"


def test_trail_keeps_chart_events_in_timeline_payload() -> None:
    payload = _build_payload([
        _entry(
            "OPEN_SIGNAL",
            state_after={
                "open_size": 0.0,
                "entries_planned": [{"plan_id": "e1", "price": 42000.0, "order_type": "LIMIT"}],
                "current_sl": 41500.0,
                "tp_levels": [42500.0],
            },
        ),
        _entry(
            "FILL",
            price_reference=42000.0,
            state_before={
                "open_size": 0.0,
                "entries_planned": [{"plan_id": "e1", "price": 42000.0, "order_type": "LIMIT"}],
                "current_sl": 41500.0,
                "tp_levels": [42500.0],
            },
            state_after={
                "open_size": 1.0,
                "entries_planned": [],
                "current_sl": 41500.0,
                "tp_levels": [42500.0],
                "fills": [{"timestamp": _TS.isoformat(), "price": 42000.0, "qty": 1.0, "plan_id": "e1"}],
            },
        ),
    ])
    events = payload["events"]

    assert len(events) >= 2

    setup_event = next(ev for ev in events if ev["event_code"] == "SETUP_CREATED")
    fill_event = next(ev for ev in events if ev["event_code"] == "ENTRY_FILLED_INITIAL")

    assert setup_event["placement"] == "rail"
    assert fill_event["placement"] == "chart"
    assert setup_event["label"]
    assert fill_event["label"]
    assert setup_event["lane_key"]
    assert fill_event["lane_key"]


def test_echarts_renderer_uses_single_visible_slider_and_hidden_trail_y_labels() -> None:
    payload = {
        "candles_by_timeframe": {
            "1m": [
                [int(_TS.timestamp() * 1000), 100.0, 101.0, 99.0, 102.0, 10.0],
                [int((_TS + timedelta(minutes=1)).timestamp() * 1000), 102.0, 103.0, 101.0, 104.0, 12.0],
            ]
        },
        "events": [],
        "legend_items": [],
        "level_segments": [],
        "meta": {"default_timeframe": "1m", "fills_count": 0},
    }

    html = render_trade_chart_echarts(
        payload,
        chart_id="chart_test",
        asset_path="assets/echarts.min.js",
    )

    assert html.count("type: 'slider'") == 1
    assert "return 'L' + (value + 1);" not in html
    assert "axisLabel: {show: false}" in html
    assert html.count("snapTimestampToVisibleBucket(event.ts, currentTF)") >= 2


def test_prd_lifecycle_story_is_coherent_across_payload_levels() -> None:
    """PRD §16: canonical lifecycle stays coherent across chart, rail, and event list payload."""
    base = _TS
    payload = build_trade_chart_payload(
        trade=_trade(),
        event_log=[
            EventLogEntry(
                timestamp=base,
                signal_id="sig_payload",
                event_type="OPEN_SIGNAL",
                source="trader",
                processing_status=EventProcessingStatus.APPLIED,
                state_before={},
                state_after={
                    "entries_planned": [{"plan_id": "e1", "price": 42000.0, "order_type": "LIMIT"}],
                    "current_sl": 41500.0,
                    "tp_levels": [42500.0, 43000.0],
                },
            ),
            EventLogEntry(
                timestamp=base + timedelta(minutes=5),
                signal_id="sig_payload",
                event_type="ADD_ENTRY",
                source="engine",
                processing_status=EventProcessingStatus.APPLIED,
                state_before={
                    "entries_planned": [{"plan_id": "e1", "price": 42000.0, "order_type": "LIMIT"}],
                    "open_size": 0.0,
                    "current_sl": 41500.0,
                    "tp_levels": [42500.0, 43000.0],
                },
                state_after={
                    "entries_planned": [{"plan_id": "e1", "price": 42000.0, "order_type": "LIMIT"}],
                    "open_size": 0.0,
                    "current_sl": 41500.0,
                    "tp_levels": [42500.0, 43000.0],
                },
            ),
            EventLogEntry(
                timestamp=base + timedelta(minutes=10),
                signal_id="sig_payload",
                event_type="FILL",
                source="engine",
                processing_status=EventProcessingStatus.APPLIED,
                state_before={
                    "entries_planned": [{"plan_id": "e1", "price": 42000.0, "order_type": "LIMIT"}],
                    "open_size": 0.0,
                    "current_sl": 41500.0,
                    "tp_levels": [42500.0, 43000.0],
                },
                state_after={
                    "entries_planned": [{"plan_id": "e1", "price": 42000.0, "order_type": "LIMIT"}],
                    "fills": [{"timestamp": (base + timedelta(minutes=10)).isoformat(), "price": 42000.0, "qty": 1.0, "plan_id": "e1"}],
                    "fills_count": 1,
                    "open_size": 1.0,
                    "current_sl": 41500.0,
                    "tp_levels": [42500.0, 43000.0],
                },
            ),
            EventLogEntry(
                timestamp=base + timedelta(minutes=15),
                signal_id="sig_payload",
                event_type="MOVE_STOP",
                source="engine",
                processing_status=EventProcessingStatus.APPLIED,
                price_reference=42050.0,
                state_before={"open_size": 1.0, "current_sl": 41500.0, "tp_levels": [42500.0, 43000.0]},
                state_after={"open_size": 1.0, "current_sl": 42050.0, "tp_levels": [42500.0, 43000.0]},
            ),
            EventLogEntry(
                timestamp=base + timedelta(minutes=30),
                signal_id="sig_payload",
                event_type="CLOSE_PARTIAL",
                source="engine",
                processing_status=EventProcessingStatus.APPLIED,
                reason="tp_hit",
                price_reference=42500.0,
                state_before={"open_size": 1.0, "current_sl": 42050.0, "realized_pnl": 0.0, "tp_levels": [42500.0, 43000.0]},
                state_after={"open_size": 0.5, "current_sl": 42050.0, "realized_pnl": 125.0, "tp_levels": [43000.0]},
            ),
            EventLogEntry(
                timestamp=base + timedelta(minutes=45),
                signal_id="sig_payload",
                event_type="CLOSE_FULL",
                source="engine",
                processing_status=EventProcessingStatus.APPLIED,
                reason="sl_hit",
                price_reference=42050.0,
                state_before={"open_size": 0.5, "current_sl": 42050.0, "realized_pnl": 125.0, "tp_levels": [43000.0]},
                state_after={"open_size": 0.0, "current_sl": 42050.0, "realized_pnl": 150.0, "tp_levels": []},
            ),
        ],
        candles_by_timeframe={},
    )

    events_by_code = {event["event_code"]: event for event in payload["events"]}
    assert events_by_code["SETUP_CREATED"]["placement"] == "rail"
    assert events_by_code["ENTRY_ORDER_ADDED"]["placement"] == "rail"
    assert events_by_code["ENTRY_FILLED_INITIAL"]["placement"] == "chart"
    assert events_by_code["STOP_MOVED"]["placement"] == "rail"
    assert events_by_code["EXIT_PARTIAL_TP"]["placement"] == "chart"
    assert events_by_code["EXIT_FINAL_SL"]["placement"] == "chart"
    assert all(event["event_list_section"] == "A" for event in events_by_code.values())

    entry_limit_segments = [segment for segment in payload["level_segments"] if segment["kind"] == "ENTRY_LIMIT"]
    assert len(entry_limit_segments) == 1
    assert entry_limit_segments[0]["ts_end"] == (base + timedelta(minutes=10)).isoformat()


def test_pending_entry_added_then_cancelled_updates_level_segments() -> None:
    base = _TS
    payload = build_trade_chart_payload(
        trade=_trade(),
        event_log=[
            EventLogEntry(
                timestamp=base,
                signal_id="sig_payload",
                event_type="OPEN_SIGNAL",
                source="trader",
                processing_status=EventProcessingStatus.APPLIED,
                state_before={},
                state_after={
                    "entries_planned": [{"plan_id": "e1", "price": 42000.0, "order_type": "LIMIT"}],
                    "current_sl": 41500.0,
                    "tp_levels": [42500.0],
                },
            ),
            EventLogEntry(
                timestamp=base + timedelta(minutes=5),
                signal_id="sig_payload",
                event_type="ADD_ENTRY",
                source="engine",
                processing_status=EventProcessingStatus.APPLIED,
                state_before={
                    "entries_planned": [{"plan_id": "e1", "price": 42000.0, "order_type": "LIMIT"}],
                },
                state_after={
                    "entries_planned": [
                        {"plan_id": "e1", "price": 42000.0, "order_type": "LIMIT"},
                        {"plan_id": "e2", "price": 41900.0, "order_type": "LIMIT"},
                    ],
                    "current_sl": 41500.0,
                    "tp_levels": [42500.0],
                },
            ),
            EventLogEntry(
                timestamp=base + timedelta(minutes=8),
                signal_id="sig_payload",
                event_type="CANCEL_PENDING",
                source="engine",
                processing_status=EventProcessingStatus.APPLIED,
                state_before={
                    "open_size": 0.0,
                    "entries_planned": [
                        {"plan_id": "e1", "price": 42000.0, "order_type": "LIMIT"},
                        {"plan_id": "e2", "price": 41900.0, "order_type": "LIMIT"},
                    ],
                },
                state_after={
                    "open_size": 0.0,
                    "entries_planned": [{"plan_id": "e1", "price": 42000.0, "order_type": "LIMIT"}],
                    "current_sl": 41500.0,
                    "tp_levels": [42500.0],
                },
            ),
        ],
        candles_by_timeframe={},
    )
    entry_segments = [segment for segment in payload["level_segments"] if segment["kind"] == "ENTRY_LIMIT"]
    assert len(entry_segments) == 2
    entry2 = next(segment for segment in entry_segments if segment["label"] == "Entry 2")
    assert entry2["ts_start"] == (base + timedelta(minutes=5)).isoformat()
    assert entry2["ts_end"] == (base + timedelta(minutes=8)).isoformat()


def test_cancel_pending_closes_remaining_entry_lines_even_with_stale_snapshot_plans() -> None:
    base = _TS
    payload = build_trade_chart_payload(
        trade=_trade(),
        event_log=[
            EventLogEntry(
                timestamp=base,
                signal_id="sig_payload",
                event_type="OPEN_SIGNAL",
                source="trader",
                processing_status=EventProcessingStatus.APPLIED,
                state_before={},
                state_after={
                    "pending_size": 1.0,
                    "entries_planned": [{"plan_id": "e1", "price": 42000.0, "order_type": "LIMIT"}],
                    "current_sl": 41500.0,
                    "tp_levels": [42500.0],
                },
            ),
            EventLogEntry(
                timestamp=base + timedelta(minutes=8),
                signal_id="sig_payload",
                event_type="CANCEL_PENDING",
                source="engine",
                processing_status=EventProcessingStatus.APPLIED,
                state_before={
                    "open_size": 0.0,
                    "pending_size": 1.0,
                    "entries_planned": [{"plan_id": "e1", "price": 42000.0, "order_type": "LIMIT"}],
                },
                state_after={
                    "open_size": 0.0,
                    "pending_size": 0.0,
                    "entries_planned": [{"plan_id": "e1", "price": 42000.0, "order_type": "LIMIT"}],
                    "current_sl": 41500.0,
                    "tp_levels": [42500.0],
                },
            ),
        ],
        candles_by_timeframe={},
    )
    entry_segments = [segment for segment in payload["level_segments"] if segment["kind"] == "ENTRY_LIMIT"]
    assert len(entry_segments) == 1
    assert entry_segments[0]["ts_end"] == (base + timedelta(minutes=8)).isoformat()
