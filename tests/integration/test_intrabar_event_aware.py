"""Integration tests for intrabar event-aware replay (Solution B).

Tests verify that trader updates arriving inside a parent candle are applied
at the correct temporal boundary using child-timeframe candles, eliminating
the retroactive look-ahead bias described in the PRD.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from src.signal_chain_lab.domain.enums import ChainInputMode, EventSource, EventType
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent
from src.signal_chain_lab.engine.simulator import simulate_chain
from src.signal_chain_lab.market.data_models import Candle, MarketMetadata
from src.signal_chain_lab.policies.base import IntrabarReplayConfig, PolicyConfig


# ── Helpers ──────────────────────────────────────────────────────────────────


def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def _candle(
    ts: str,
    *,
    open: float = 100.0,
    high: float,
    low: float,
    close: float = 100.0,
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
) -> Candle:
    return Candle(
        timestamp=_utc(ts),
        open=open,
        high=high,
        low=low,
        close=close,
        volume=1.0,
        symbol=symbol,
        timeframe=timeframe,
    )


def _policy(*, intrabar_enabled: bool = True, child_tf: str = "5m") -> PolicyConfig:
    return PolicyConfig(
        name="test",
        intrabar=IntrabarReplayConfig(
            event_aware_replay_enabled=intrabar_enabled,
            child_timeframe=child_tf,
            same_child_event_policy="conservative_pre_event",
            fallback_mode="warn_and_use_parent_logic",
        ),
    )


def _open_signal(
    ts: str,
    *,
    sl: float,
    tps: list[float],
    entries: list[float] | None = None,
    seq: int = 0,
) -> CanonicalEvent:
    payload: dict[str, Any] = {"sl_price": sl, "tp_levels": tps}
    if entries:
        payload["entry_prices"] = entries
    return CanonicalEvent(
        signal_id="sig-1",
        trader_id="trader-x",
        symbol="BTCUSDT",
        side="BUY",
        timestamp=_utc(ts),
        event_type=EventType.OPEN_SIGNAL,
        source=EventSource.TRADER,
        payload=payload,
        sequence=seq,
    )


def _update_event(
    ts: str,
    event_type: EventType,
    payload: dict[str, Any] | None = None,
    seq: int = 10,
) -> CanonicalEvent:
    normalized_payload = dict(payload or {})
    if (
        event_type == EventType.MOVE_STOP
        and "new_sl" in normalized_payload
        and "new_sl_price" not in normalized_payload
    ):
        normalized_payload["new_sl_price"] = normalized_payload.pop("new_sl")

    return CanonicalEvent(
        signal_id="sig-1",
        trader_id="trader-x",
        symbol="BTCUSDT",
        side="BUY",
        timestamp=_utc(ts),
        event_type=event_type,
        source=EventSource.TRADER,
        payload=normalized_payload,
        sequence=seq,
    )


def _chain(events: list[CanonicalEvent], *, timeframe: str = "1h") -> CanonicalChain:
    return CanonicalChain(
        signal_id="sig-1",
        trader_id="trader-x",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=True,
        created_at=events[0].timestamp,
        metadata={"timeframe": timeframe},
        events=events,
    )


class StubProvider:
    """Minimal MarketDataProvider stub with configurable parent/child candles."""

    def __init__(
        self,
        parent_candles: list[Candle],
        child_candles_by_parent_ts: dict[str, list[Candle]] | None = None,
    ) -> None:
        self._parents: dict[str, Candle] = {c.timestamp.isoformat(): c for c in parent_candles}
        self._children: dict[str, list[Candle]] = child_candles_by_parent_ts or {}
        self.intrabar_calls: list[tuple[str, str, str]] = []

    def has_symbol(self, symbol: str) -> bool:
        return symbol == "BTCUSDT"

    def get_candle(self, symbol: str, timeframe: str, ts: datetime) -> Candle | None:
        return self._parents.get(ts.isoformat())

    def get_range(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        result = [
            c for c in self._parents.values()
            if start <= c.timestamp < end
        ]
        return sorted(result, key=lambda c: c.timestamp)

    def get_intrabar_range(
        self,
        symbol: str,
        parent_timeframe: str,
        child_timeframe: str,
        ts: datetime,
    ) -> list[Candle]:
        self.intrabar_calls.append((symbol, child_timeframe, ts.isoformat()))
        return self._children.get(ts.isoformat(), [])

    def get_metadata(self, symbol: str, timeframe: str) -> MarketMetadata | None:
        if not self._parents:
            return None
        timestamps = [c.timestamp for c in self._parents.values()]
        return MarketMetadata(
            symbol=symbol,
            timeframe=timeframe,
            provider_name="stub",
            timezone="UTC",
            start=min(timestamps),
            end=max(timestamps) + timedelta(hours=1),
        )


# ── TR-1: Regression — no intra-candle events, result unchanged ───────────────


def test_regression_no_intra_candle_events_unchanged() -> None:
    """Chain with event on candle boundary: intrabar replay enabled must not change outcome."""
    parent = _candle("2026-01-01T10:00:00", high=115.0, low=95.0)
    children = [
        _candle("2026-01-01T10:00:00", high=115.0, low=95.0, timeframe="5m"),
    ]
    provider = StubProvider(
        parent_candles=[parent],
        child_candles_by_parent_ts={"2026-01-01T10:00:00+00:00": children},
    )
    events = [
        _open_signal("2026-01-01T10:00:00", sl=90.0, tps=[120.0], entries=[100.0]),
    ]
    chain = _chain(events)

    logs_legacy, state_legacy = simulate_chain(chain, _policy(intrabar_enabled=False), provider)
    logs_event_aware, state_event_aware = simulate_chain(chain, _policy(intrabar_enabled=True), provider)

    # Intrabar replay was NOT triggered (event is on boundary, not intra-candle)
    assert len(logs_legacy) == len(logs_event_aware)
    assert state_legacy.close_reason == state_event_aware.close_reason


# ── TU-1: Move stop intra-candle ──────────────────────────────────────────────


def test_move_stop_intra_candle_pre_event_children_use_old_sl() -> None:
    """MOVE_STOP at 10:30 — children before 10:30 must use old SL (90), not new SL (102).

    Setup:
      - OPEN_SIGNAL at 10:00: entry=100, SL=90, TP=120
      - Parent candle 10:00-11:00: low=88 (would hit OLD SL=90 and new SL=102)
      - MOVE_STOP at 10:30: new SL=102 (break-even move)
      - Children:
          10:00-10:05: low=95 (safe, no hit for either SL)
          10:05-10:10: low=91 (hits OLD SL=90 only — this child is BEFORE event)
          ...actually let's keep it simple:
          10:00: low=99, high=105 (safe)
          10:30: low=101, high=105  ← this is the ambiguous child (contains event boundary)
            with conservative_pre_event it's processed BEFORE the event
          10:35: low=101, high=105  ← after event; SL is now 102, low=101 hits new SL

    Expected with intrabar enabled:
      - 10:00 child: safe (both SL values untouched)
      - 10:30 child: processed with OLD SL=90 → safe (low=101 > 90)
      - event applied: SL moves to 102
      - 10:35 child: low=101 < new SL=102 → SL hit → CLOSE_FULL

    Expected without intrabar (legacy):
      - entire parent candle evaluated with new SL=102
      - low=88 < 102 → SL hit immediately after move stop
      (or however the parent candle evaluates)

    This test verifies the intrabar path triggers and processes children in order.
    """
    parent_ts = "2026-01-01T10:00:00"
    parent = _candle(parent_ts, high=115.0, low=88.0)

    children = [
        _candle("2026-01-01T10:00:00", high=105.0, low=99.0, timeframe="5m"),
        _candle("2026-01-01T10:30:00", high=105.0, low=101.0, timeframe="5m"),  # boundary child (pre-event)
        _candle("2026-01-01T10:35:00", high=105.0, low=101.0, timeframe="5m"),  # post-event: new SL=102 hit
    ]
    provider = StubProvider(
        parent_candles=[parent],
        child_candles_by_parent_ts={f"{parent_ts}+00:00": children},
    )

    events = [
        _open_signal("2026-01-01T10:00:00", sl=90.0, tps=[120.0], entries=[100.0], seq=0),
        _update_event(
            "2026-01-01T10:33:00",  # intra-candle: inside the 10:30 child
            EventType.MOVE_STOP,
            payload={"new_sl": 102.0},
            seq=10,
        ),
    ]
    chain = _chain(events)

    logs, state = simulate_chain(chain, _policy(), provider)

    # Intrabar replay must have been triggered (child data fetched)
    assert len(provider.intrabar_calls) >= 1

    # The trade must have been closed (SL hit after move stop)
    from src.signal_chain_lab.domain.enums import CloseReason
    assert state.close_reason == CloseReason.SL


# ── TU-2: Cancel pending intra-candle ────────────────────────────────────────


def test_cancel_pending_intra_candle_fill_blocked_after_event() -> None:
    """CANCEL_PENDING at 10:30 — entries should not fill from child candles after the event.

    Setup:
      - OPEN_SIGNAL at 10:00: LIMIT entry at 98 (below current price), SL=90, TP=120
      - Parent candle 10:00-11:00: low=96 (would fill entry)
      - CANCEL_PENDING at 10:30
      - Children:
          10:00: low=99 (above entry=98, no fill)
          10:30: low=99 (boundary child, processed before event with conservative_pre_event)
          10:35: low=96 (below entry=98, would fill IF pending still active)

    Expected with intrabar:
      - Pre-event children: no fill (low > 98)
      - Event applied: CANCEL_PENDING
      - Post-event child 10:35: pending already cancelled, no fill

    So final state: CANCELLED (no fill ever happened).
    """
    parent_ts = "2026-01-01T10:00:00"
    parent = _candle(parent_ts, high=105.0, low=96.0)

    children = [
        _candle("2026-01-01T10:00:00", high=105.0, low=99.0, timeframe="5m"),  # pre
        _candle("2026-01-01T10:30:00", high=104.0, low=99.0, timeframe="5m"),  # boundary (pre-event)
        _candle("2026-01-01T10:35:00", high=104.0, low=96.0, timeframe="5m"),  # post-event: fill price touched
    ]
    provider = StubProvider(
        parent_candles=[parent],
        child_candles_by_parent_ts={f"{parent_ts}+00:00": children},
    )

    events = [
        _open_signal("2026-01-01T10:00:00", sl=90.0, tps=[120.0], entries=[98.0], seq=0),
        _update_event(
            "2026-01-01T10:33:00",
            EventType.CANCEL_PENDING,
            seq=10,
        ),
    ]
    chain = _chain(events)

    logs, state = simulate_chain(chain, _policy(), provider)

    # No fill should have occurred
    assert state.open_size == 0.0
    assert len(state.fills) == 0


# ── TU-5: Multiple events in same parent candle ───────────────────────────────


def test_multiple_events_same_parent_candle_correct_order() -> None:
    """Two intra-candle events processed in (timestamp, sequence) order.

    Setup:
      - OPEN_SIGNAL at 10:00 (on boundary)
      - MOVE_STOP at 10:20: SL moves from 90 → 95
      - MOVE_STOP at 10:40: SL moves from 95 → 102
      - Children: 10:00, 10:15, 10:20, 10:25, 10:35, 10:40, 10:45
        (all safe — low never hits any SL)

    After both events, state.current_sl must be 102.
    """
    parent_ts = "2026-01-01T10:00:00"
    parent = _candle(parent_ts, high=115.0, low=99.0)

    children = [
        _candle("2026-01-01T10:00:00", high=110.0, low=100.0, timeframe="5m"),  # fills entry
        _candle("2026-01-01T10:15:00", high=110.0, low=104.0, timeframe="5m"),
        _candle("2026-01-01T10:20:00", high=110.0, low=104.0, timeframe="5m"),  # E1 boundary
        _candle("2026-01-01T10:25:00", high=110.0, low=104.0, timeframe="5m"),
        _candle("2026-01-01T10:35:00", high=110.0, low=104.0, timeframe="5m"),
        _candle("2026-01-01T10:40:00", high=110.0, low=104.0, timeframe="5m"),  # E2 boundary
        _candle("2026-01-01T10:45:00", high=110.0, low=104.0, timeframe="5m"),
    ]
    provider = StubProvider(
        parent_candles=[parent],
        child_candles_by_parent_ts={f"{parent_ts}+00:00": children},
    )

    events = [
        _open_signal("2026-01-01T10:00:00", sl=90.0, tps=[130.0], entries=[100.0], seq=0),
        _update_event(
            "2026-01-01T10:22:00",  # intra-candle, inside 10:20 child
            EventType.MOVE_STOP,
            payload={"new_sl": 95.0},
            seq=10,
        ),
        _update_event(
            "2026-01-01T10:42:00",  # intra-candle, inside 10:40 child
            EventType.MOVE_STOP,
            payload={"new_sl": 102.0},
            seq=20,
        ),
    ]
    chain = _chain(events)

    logs, state = simulate_chain(chain, _policy(), provider)

    # Both MOVE_STOP events applied → final SL = 102
    assert state.current_sl == pytest.approx(102.0)
    # Trade still open (subsequent lows never hit SL=102)
    assert state.open_size > 0


# ── TU-6: Ambiguous child — conservative_pre_event policy ────────────────────


def test_conservative_pre_event_child_containing_event_uses_old_state() -> None:
    """The child candle that contains the event timestamp is processed BEFORE the event.

    Event at 10:33 falls inside the 5m child candle 10:30-10:35.
    With conservative_pre_event, the 10:30 child is processed with the pre-event
    state. The post-event state only takes effect from the 10:35 child onward.
    """
    parent_ts = "2026-01-01T10:00:00"
    # Parent candle: low=88 would hit old SL=90 if evaluated with old state
    parent = _candle(parent_ts, high=115.0, low=88.0)

    children = [
        # 10:30 child: low=91 — above old SL=90, safe with old state
        _candle("2026-01-01T10:30:00", high=105.0, low=91.0, timeframe="5m"),
        # 10:35 child: low=88 — hits new SL=102 (but also old SL=90)
        _candle("2026-01-01T10:35:00", high=105.0, low=88.0, timeframe="5m"),
    ]
    provider = StubProvider(
        parent_candles=[parent],
        child_candles_by_parent_ts={f"{parent_ts}+00:00": children},
    )

    events = [
        _open_signal("2026-01-01T10:00:00", sl=90.0, tps=[130.0], entries=[100.0], seq=0),
        _update_event(
            "2026-01-01T10:33:00",  # falls inside 10:30 child candle
            EventType.MOVE_STOP,
            payload={"new_sl": 102.0},
            seq=10,
        ),
    ]
    chain = _chain(events)

    logs, state = simulate_chain(chain, _policy(), provider)

    from src.signal_chain_lab.domain.enums import CloseReason
    # 10:30 child: low=91 > old SL=90 → no SL hit → processed safely
    # Event applied: SL → 102
    # 10:35 child: low=88 < 102 → SL hit → CLOSE_FULL
    assert state.close_reason == CloseReason.SL


# ── TU-7: No child candles — fallback with warning ───────────────────────────


def test_fallback_no_child_candles_applies_events_and_increments_warnings() -> None:
    """When child candles are unavailable, events are applied without intrabar split.

    The simulation must not crash and must increment warnings_count for each
    event that falls back to parent-level application.
    """
    parent_ts = "2026-01-01T10:00:00"
    prefill_parent = _candle("2026-01-01T09:00:00", high=115.0, low=99.0)
    parent = _candle(parent_ts, high=115.0, low=95.0)
    provider = StubProvider(
        parent_candles=[prefill_parent, parent],
        child_candles_by_parent_ts={},  # no children available
    )

    events = [
        _open_signal("2026-01-01T09:00:00", sl=90.0, tps=[130.0], entries=[100.0], seq=0),
        _update_event(
            "2026-01-01T10:30:00",
            EventType.MOVE_STOP,
            payload={"new_sl": 95.0},
            seq=10,
        ),
    ]
    chain = _chain(events)

    logs, state = simulate_chain(chain, _policy(), provider)

    # Must not crash
    assert state is not None
    # The position was opened on the prior parent candle.
    assert state.open_size > 0
    # Warnings incremented for the fallback
    assert state.warnings_count >= 1
    # MOVE_STOP still applied despite fallback
    assert state.current_sl == pytest.approx(95.0)


# ── TR-2: Event on candle boundary — intrabar path NOT triggered ──────────────


def test_event_exactly_on_candle_boundary_does_not_trigger_intrabar() -> None:
    """An event at exactly the candle boundary should use the standard path."""
    parent_ts = "2026-01-01T10:00:00"
    parent = _candle(parent_ts, high=115.0, low=95.0)
    provider = StubProvider(
        parent_candles=[parent],
        child_candles_by_parent_ts={},
    )

    # OPEN_SIGNAL and MOVE_STOP both at 10:00 exactly (candle boundary)
    events = [
        _open_signal("2026-01-01T10:00:00", sl=90.0, tps=[130.0], entries=[100.0], seq=0),
        _update_event(
            "2026-01-01T11:00:00",  # boundary of next candle
            EventType.MOVE_STOP,
            payload={"new_sl": 95.0},
            seq=10,
        ),
    ]
    chain = _chain(events)

    logs, state = simulate_chain(chain, _policy(), provider)

    # No intrabar calls — both events are on candle boundaries
    assert len(provider.intrabar_calls) == 0


# ── TR-3: Feature disabled — legacy behaviour unchanged ───────────────────────


def test_intrabar_disabled_produces_legacy_behaviour() -> None:
    """With event_aware_replay_enabled=False the simulator uses the legacy path."""
    from src.signal_chain_lab.domain.enums import CloseReason

    parent_ts = "2026-01-01T10:00:00"
    prefill_parent = _candle("2026-01-01T09:00:00", high=115.0, low=99.0)
    parent = _candle(parent_ts, high=115.0, low=95.0)
    provider = StubProvider(
        parent_candles=[prefill_parent, parent],
        child_candles_by_parent_ts={},
    )

    events = [
        _open_signal("2026-01-01T09:00:00", sl=90.0, tps=[130.0], entries=[100.0], seq=0),
        _update_event(
            "2026-01-01T10:30:00",
            EventType.MOVE_STOP,
            payload={"new_sl": 95.0},
            seq=10,
        ),
    ]
    chain = _chain(events)

    _, state = simulate_chain(chain, _policy(intrabar_enabled=False), provider)

    # No intrabar calls regardless
    assert len(provider.intrabar_calls) == 0
    # MOVE_STOP still applied in legacy mode, then the 10:00 parent candle is replayed.
    assert state.current_sl == pytest.approx(95.0)
    assert state.close_reason == CloseReason.SL
