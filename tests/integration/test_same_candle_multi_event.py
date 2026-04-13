"""Integration tests for same-candle multi-event handling in the simulator.

Covers the scenarios described in PRD_fix_same_candle_multi_event.md:

- Caso A: Multiple TPs hit in the same candle (LONG)
- Caso B: TP1 + break-even SL move + SL hit all in the same candle (LONG)
- Caso C: Multiple TPs hit in the same candle (SHORT — symmetric behaviour)
- Caso D: Final TP hit in the same candle as a preceding partial TP
- Caso E: No-progress guard raises SimulationInvariantError
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from src.signal_chain_lab.domain.enums import (
    ChainInputMode,
    CloseReason,
    EventSource,
    EventType,
    TradeStatus,
)
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent
from src.signal_chain_lab.engine.simulator import SimulationInvariantError, simulate_chain
from src.signal_chain_lab.market.data_models import Candle, MarketMetadata
from src.signal_chain_lab.policies.base import PolicyConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def _candle(ts: str, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        timestamp=_utc(ts),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1.0,
        symbol="BTCUSDT",
        timeframe="1h",
    )


class _ListProvider:
    """Minimal market provider backed by a flat list of 1h candles."""

    def __init__(self, candles: list[Candle]) -> None:
        self._candles = sorted(candles, key=lambda c: c.timestamp)

    def has_symbol(self, symbol: str) -> bool:
        return True

    def get_candle(self, symbol: str, timeframe: str, ts: datetime) -> Candle | None:
        for c in self._candles:
            if c.symbol == symbol and c.timeframe == timeframe and c.timestamp == ts:
                return c
        return None

    def get_range(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Candle]:
        return [
            c for c in self._candles
            if c.symbol == symbol and c.timeframe == timeframe and start <= c.timestamp <= end
        ]

    def get_intrabar_range(self, symbol: str, parent_tf: str, child_tf: str, ts: datetime) -> list[Candle]:
        return []

    def get_metadata(self, symbol: str, timeframe: str) -> MarketMetadata | None:
        matching = [c for c in self._candles if c.symbol == symbol and c.timeframe == timeframe]
        if not matching:
            return None
        return MarketMetadata(
            symbol=symbol,
            timeframe=timeframe,
            provider_name="list-provider",
            timezone="UTC",
            start=matching[0].timestamp,
            end=matching[-1].timestamp,
        )


def _make_chain(
    tp_levels: list[float],
    side: str = "BUY",
    entry_price: float = 100.0,
    sl_price: float = 80.0,
) -> CanonicalChain:
    return CanonicalChain(
        signal_id="sig-same-candle",
        trader_id="trader-x",
        symbol="BTCUSDT",
        side=side,
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=False,
        created_at=_utc("2026-01-01T00:00:00"),
        metadata={"timeframe": "1h"},
        events=[
            CanonicalEvent(
                signal_id="sig-same-candle",
                trader_id="trader-x",
                symbol="BTCUSDT",
                side=side,
                timestamp=_utc("2026-01-01T00:00:00"),
                event_type=EventType.OPEN_SIGNAL,
                source=EventSource.TRADER,
                payload={
                    "entry_prices": [entry_price],
                    "entry_type": "LIMIT",
                    "sl_price": sl_price,
                    "tp_levels": tp_levels,
                },
                sequence=0,
            )
        ],
    )


def _policy(
    tp_distribution: str = "equal",
    be_trigger: str | None = None,
) -> PolicyConfig:
    data: dict = {
        "name": "test_same_candle",
        "tp": {"use_original_tp": True, "tp_distribution": tp_distribution},
        "pending": {
            "pending_timeout_hours": 200,
            "chain_timeout_hours": 400,
        },
    }
    if be_trigger is not None:
        data["sl"] = {"break_even_mode": "auto", "be_trigger": be_trigger}
    return PolicyConfig.from_dict(data)


# ---------------------------------------------------------------------------
# Caso A — Multi-TP same candle (LONG)
# ---------------------------------------------------------------------------

def test_long_multi_tp_same_candle() -> None:
    """All three TPs are hit in a single candle: simulator processes all three."""
    chain = _make_chain(tp_levels=[110.0, 120.0, 130.0])
    policy = _policy()

    provider = _ListProvider([
        _candle("2026-01-01T00:00:00", 101, 102, 99, 101),   # fills LONG limit @100 (low=99<100)
        _candle("2026-01-01T01:00:00", 105, 135, 103, 130),  # TP1=110, TP2=120, TP3=130 all in range
    ])

    logs, state = simulate_chain(chain, policy, provider)

    assert state.status == TradeStatus.CLOSED
    assert state.close_reason == CloseReason.TP
    assert state.open_size == pytest.approx(0.0, abs=1e-9)

    partial_events = [l for l in logs if l.event_type == "CLOSE_PARTIAL" and l.source == "engine"]
    full_tp_events = [
        l for l in logs
        if l.event_type == "CLOSE_FULL" and l.source == "engine"
        and l.state_after.get("close_reason") == "tp"
    ]
    assert len(partial_events) == 2, f"Expected 2 partial TP closes, got {len(partial_events)}"
    assert len(full_tp_events) == 1, f"Expected 1 final TP close, got {len(full_tp_events)}"

    # Equal distribution: 1/3*(110-100) + 1/3*(120-100) + 1/3*(130-100) = 20.0
    expected_pnl = (1 / 3) * 10 + (1 / 3) * 20 + (1 / 3) * 30
    assert state.realized_pnl == pytest.approx(expected_pnl, rel=1e-6)


# ---------------------------------------------------------------------------
# Caso B — TP1 + break-even SL move + SL hit in same candle (LONG)
# ---------------------------------------------------------------------------

def test_long_tp1_be_sl_same_candle() -> None:
    """After TP1 the SL is moved to break-even; the same candle then hits the new SL."""
    # TP2=140 is well above candle.high=115 — it is never hit
    chain = _make_chain(tp_levels=[110.0, 140.0], entry_price=100.0, sl_price=80.0)
    policy = _policy(be_trigger="tp1")

    provider = _ListProvider([
        _candle("2026-01-01T00:00:00", 101, 102, 99, 101),  # fills @100
        _candle("2026-01-01T01:00:00", 105, 115, 97, 100),  # TP1=110 hit → BE→SL=100 → low=97<100 → SL
    ])

    logs, state = simulate_chain(chain, policy, provider)

    assert state.status == TradeStatus.CLOSED
    assert state.close_reason == CloseReason.SL

    be_events = [l for l in logs if l.event_type == "MOVE_STOP_TO_BE" and l.source == "engine"]
    assert len(be_events) == 1, f"Expected 1 BE event, got {len(be_events)}"

    # PnL: (1/2)*(110-100) + (1/2)*(100-100) = 5.0  (BE close at entry = zero loss)
    assert state.realized_pnl == pytest.approx(5.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Caso C — Multi-TP same candle (SHORT — symmetric)
# ---------------------------------------------------------------------------

def test_short_multi_tp_same_candle() -> None:
    """SHORT: two TPs are both hit in a single candle; behaviour is symmetric with LONG."""
    # SHORT LIMIT entry at 50.  Fills when candle.high >= 50 (sell limit).
    chain = _make_chain(tp_levels=[44.0, 38.0], side="SELL", entry_price=50.0, sl_price=60.0)
    policy = _policy()

    provider = _ListProvider([
        _candle("2026-01-01T00:00:00", 55, 56, 47, 48),  # fills SHORT @50 (high=56 >= 50)
        _candle("2026-01-01T01:00:00", 47, 55, 36, 40),  # TP1=44 hit, TP2=38 hit; SL=60 not hit (high<60)
    ])

    logs, state = simulate_chain(chain, policy, provider)

    assert state.status == TradeStatus.CLOSED
    assert state.close_reason == CloseReason.TP
    assert state.open_size == pytest.approx(0.0, abs=1e-9)

    partial_events = [l for l in logs if l.event_type == "CLOSE_PARTIAL" and l.source == "engine"]
    full_tp_events = [
        l for l in logs
        if l.event_type == "CLOSE_FULL" and l.source == "engine"
        and l.state_after.get("close_reason") == "tp"
    ]
    assert len(partial_events) == 1, f"Expected 1 partial TP close, got {len(partial_events)}"
    assert len(full_tp_events) == 1, f"Expected 1 final TP close, got {len(full_tp_events)}"

    # SHORT PnL: (50-44)*(1/2) + (50-38)*(1/2) = 3.0 + 6.0 = 9.0
    assert state.realized_pnl == pytest.approx(9.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Caso D — Final TP hit in the same candle as a preceding partial TP
# ---------------------------------------------------------------------------

def test_long_final_tp_same_candle_after_partial() -> None:
    """After partial TP1, TP2 (last TP) is also hit in the same candle → full close."""
    chain = _make_chain(tp_levels=[110.0, 120.0])
    policy = _policy()

    provider = _ListProvider([
        _candle("2026-01-01T00:00:00", 101, 102, 99, 101),   # fills @100
        _candle("2026-01-01T01:00:00", 105, 125, 103, 120),  # TP1=110 and TP2=120 both in range
    ])

    logs, state = simulate_chain(chain, policy, provider)

    assert state.status == TradeStatus.CLOSED
    assert state.close_reason == CloseReason.TP
    assert state.open_size == pytest.approx(0.0, abs=1e-9)

    partial_events = [l for l in logs if l.event_type == "CLOSE_PARTIAL" and l.source == "engine"]
    full_tp_events = [
        l for l in logs
        if l.event_type == "CLOSE_FULL" and l.source == "engine"
        and l.state_after.get("close_reason") == "tp"
    ]
    assert len(partial_events) == 1, f"Expected 1 partial TP close, got {len(partial_events)}"
    assert len(full_tp_events) == 1, f"Expected 1 final TP close, got {len(full_tp_events)}"

    # PnL: (1/2)*(110-100) + (1/2)*(120-100) = 5.0 + 10.0 = 15.0
    assert state.realized_pnl == pytest.approx(15.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Caso E — No-progress guard raises SimulationInvariantError
# ---------------------------------------------------------------------------

def test_no_progress_guard_raises_invariant_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """If a collision is detected but state does not advance, SimulationInvariantError is raised."""
    import src.signal_chain_lab.engine.simulator as sim_module
    from src.signal_chain_lab.domain.enums import EventProcessingStatus
    from src.signal_chain_lab.domain.results import EventLogEntry

    original_apply_event = sim_module.apply_event

    def _selective_apply_event(state, event, *, policy=None):
        # Let trader events (OPEN_SIGNAL etc.) run normally so state is set up.
        # Freeze all ENGINE-generated events so no state fields change.
        if event.source == EventSource.ENGINE:
            return EventLogEntry(
                timestamp=event.timestamp,
                signal_id=state.signal_id,
                event_type=event.event_type.value,
                source=event.source.value,
                processing_status=EventProcessingStatus.APPLIED,
            )
        return original_apply_event(state, event, policy=policy)

    def _frozen_close_resolution(state, resolution):
        # Return without touching next_tp_index, open_size, current_sl, or status.
        return False, 0.5, 0.0, 0.0

    monkeypatch.setattr(sim_module, "_apply_close_resolution", _frozen_close_resolution)
    monkeypatch.setattr(sim_module, "apply_event", _selective_apply_event)

    chain = _make_chain(tp_levels=[110.0, 120.0])
    policy = _policy()

    provider = _ListProvider([
        _candle("2026-01-01T00:00:00", 101, 102, 99, 101),   # fills @100
        _candle("2026-01-01T01:00:00", 105, 125, 103, 115),  # TP1 detected → frozen → no progress
    ])

    with pytest.raises(SimulationInvariantError):
        simulate_chain(chain, policy, provider)
