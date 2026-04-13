"""Regression tests for plan_id-based entry-to-fill mapping (PRD fix problema 3).

Covers:
- CA-1/CA-2: older pending entry not hidden after out-of-order ADD_ENTRY fill
- CA-3: FillRecord carries the plan_id of the executed entry
- CA-4: plan_ids are unique and deterministic
- CA-5: sequential fill behaviour unchanged
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.signal_chain_lab.domain.enums import (
    ChainInputMode,
    EventSource,
    EventType,
    TradeStatus,
)
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent
from src.signal_chain_lab.domain.trade_state import TradeState
from src.signal_chain_lab.engine.simulator import simulate_chain
from src.signal_chain_lab.engine.state_machine import apply_event
from src.signal_chain_lab.market.data_models import Candle, MarketMetadata
from src.signal_chain_lab.policies.base import PolicyConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def _candle(ts: str, low: float, high: float) -> Candle:
    return Candle(
        timestamp=_utc(ts),
        open=high,
        high=high,
        low=low,
        close=low,
        volume=1.0,
        symbol="BTCUSDT",
        timeframe="1h",
    )


class _ListProvider:
    """Minimal market provider backed by a flat list of candles."""

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
            provider_name="test-provider",
            timezone="UTC",
            start=matching[0].timestamp,
            end=matching[-1].timestamp,
        )


def _minimal_policy() -> PolicyConfig:
    """Policy with cancellations disabled and long timeouts to not interfere with fills."""
    return PolicyConfig.model_validate(
        {
            "name": "test_policy",
            "pending": {
                "cancel_pending_by_engine": False,
                "pending_timeout_hours": 9999,
                "chain_timeout_hours": 9999,
            },
        }
    )


def _open_signal_event(
    *,
    signal_id: str,
    seq: int,
    ts: str,
    entry_prices: list[float],
    sl: float,
    tp: float,
) -> CanonicalEvent:
    return CanonicalEvent(
        signal_id=signal_id,
        symbol="BTCUSDT",
        side="BUY",
        timestamp=_utc(ts),
        event_type=EventType.OPEN_SIGNAL,
        source=EventSource.TRADER,
        payload={
            "entry_prices": entry_prices,
            "entry_type": "LIMIT",
            "sl_price": sl,
            "tp_levels": [tp],
        },
        sequence=seq,
    )


def _add_entry_event(
    *,
    signal_id: str,
    seq: int,
    ts: str,
    price: float,
    size_ratio: float = 0.5,
) -> CanonicalEvent:
    return CanonicalEvent(
        signal_id=signal_id,
        symbol="BTCUSDT",
        side="BUY",
        timestamp=_utc(ts),
        event_type=EventType.ADD_ENTRY,
        source=EventSource.TRADER,
        payload={
            "price": price,
            "order_type": "limit",
            "size_ratio": size_ratio,
        },
        sequence=seq,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_add_entry_fill_does_not_hide_older_pending_plan() -> None:
    """CA-1, CA-2: E2 must still fill even after ADD_ENTRY E3 fills before it.

    Scenario:
      OPEN_SIGNAL: E1=100, E2=90 (LONG, each size_ratio=0.5)
      Candle 1 (low=99): E1 fills, E2 does not
      ADD_ENTRY: E3=98 (size_ratio=0.5)
      Candle 2 (low=97): E3 fills, E2 does not
      Candle 3 (low=89): E2 fills

    Old bug: len(fills)==2 after candle 2, E2 has index 1 → 1 < 2 → excluded from pending.
    Fix: plan_id-based selection finds E2 still unfilled.
    """
    signal_id = "btc_001"
    policy = _minimal_policy()

    chain = CanonicalChain(
        signal_id=signal_id,
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=True,
        created_at=_utc("2026-01-01T00:00:00"),
        metadata={"timeframe": "1h"},
        events=[
            _open_signal_event(
                signal_id=signal_id, seq=1,
                ts="2026-01-01T00:00:00",
                entry_prices=[100.0, 90.0],
                sl=80.0, tp=120.0,
            ),
            _add_entry_event(
                signal_id=signal_id, seq=2,
                ts="2026-01-01T01:00:00",
                price=98.0,
                size_ratio=0.5,
            ),
        ],
    )

    market = _ListProvider([
        # Candle 1: E1 touches (low=99 ≤ 100), E2 does not (99 > 90)
        _candle("2026-01-01T00:00:00", low=99.0, high=102.0),
        # Candle 2: E3 touches (low=97 ≤ 98), E2 does not (97 > 90)
        _candle("2026-01-01T01:00:00", low=97.0, high=100.0),
        # Candle 3: E2 touches (low=89 ≤ 90)
        _candle("2026-01-01T02:00:00", low=89.0, high=91.0),
    ])

    _logs, state = simulate_chain(chain, policy, market_provider=market)

    assert len(state.fills) == 3, (
        f"Expected 3 fills (E1, E3, E2) but got {len(state.fills)}. "
        "E2 was likely hidden by the old index-based pending selection."
    )

    filled_ids = [f.plan_id for f in state.fills]
    assert f"{signal_id}:1:E1" in filled_ids
    assert f"{signal_id}:1:E2" in filled_ids
    assert f"{signal_id}:2:E3" in filled_ids


def test_open_signal_assigns_unique_deterministic_plan_ids() -> None:
    """CA-4: plan_ids must be unique within a chain and deterministically formatted."""
    from src.signal_chain_lab.domain.enums import ChainInputMode, TradeStatus
    from src.signal_chain_lab.domain.trade_state import TradeState

    state = TradeState(
        signal_id="btc_002",
        symbol="BTCUSDT",
        side="BUY",
        status=TradeStatus.NEW,
        input_mode=ChainInputMode.SIGNAL_ONLY_NATIVE,
        policy_name="test_policy",
    )
    event = CanonicalEvent(
        signal_id="btc_002",
        symbol="BTCUSDT",
        side="BUY",
        timestamp=_utc("2026-01-01T00:00:00"),
        event_type=EventType.OPEN_SIGNAL,
        source=EventSource.TRADER,
        payload={
            "entry_prices": [100.0, 90.0, 80.0],
            "entry_type": "LIMIT",
            "sl_price": 70.0,
            "tp_levels": [120.0],
        },
        sequence=5,
    )

    apply_event(state, event)

    plan_ids = [plan.plan_id for plan in state.entries_planned]

    # All plans must have a plan_id
    assert all(pid is not None for pid in plan_ids), f"Some plans missing plan_id: {plan_ids}"

    # IDs must be unique
    assert len(plan_ids) == len(set(plan_ids)), f"Duplicate plan_ids: {plan_ids}"

    # IDs must follow the deterministic format signal_id:sequence:E{ordinal}
    assert plan_ids == ["btc_002:5:E1", "btc_002:5:E2", "btc_002:5:E3"], (
        f"Unexpected plan_ids: {plan_ids}"
    )


def test_fill_record_carries_plan_id_of_filled_entry() -> None:
    """CA-3: each FillRecord must report the plan_id of the entry that was executed."""
    signal_id = "btc_003"
    policy = _minimal_policy()

    chain = CanonicalChain(
        signal_id=signal_id,
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=False,
        created_at=_utc("2026-01-01T00:00:00"),
        metadata={"timeframe": "1h"},
        events=[
            _open_signal_event(
                signal_id=signal_id, seq=1,
                ts="2026-01-01T00:00:00",
                entry_prices=[100.0, 90.0],
                sl=80.0, tp=120.0,
            ),
        ],
    )

    market = _ListProvider([
        # Both entries touch in this candle
        _candle("2026-01-01T00:00:00", low=88.0, high=102.0),
    ])

    _logs, state = simulate_chain(chain, policy, market_provider=market)

    assert len(state.fills) == 2

    fill_plan_ids = {f.plan_id for f in state.fills}
    assert fill_plan_ids == {f"{signal_id}:1:E1", f"{signal_id}:1:E2"}, (
        f"Fill plan_ids do not match entry plan_ids: {fill_plan_ids}"
    )

    # Each fill's plan_id must correspond to the correct entry
    for fill in state.fills:
        matching_plan = next(
            (p for p in state.entries_planned if p.plan_id == fill.plan_id), None
        )
        assert matching_plan is not None, f"No entry found for fill.plan_id={fill.plan_id}"
        assert fill.price == matching_plan.price, (
            f"Fill price {fill.price} does not match plan price {matching_plan.price} "
            f"for plan_id={fill.plan_id}"
        )


def test_sequential_fill_order_behaviour_remains_unchanged() -> None:
    """CA-5: linear fill scenario (no ADD_ENTRY) must behave identically to before the fix."""
    signal_id = "btc_004"
    policy = _minimal_policy()

    chain = CanonicalChain(
        signal_id=signal_id,
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=False,
        created_at=_utc("2026-01-01T00:00:00"),
        metadata={"timeframe": "1h"},
        events=[
            _open_signal_event(
                signal_id=signal_id, seq=1,
                ts="2026-01-01T00:00:00",
                entry_prices=[100.0, 90.0],
                sl=80.0, tp=120.0,
            ),
        ],
    )

    market = _ListProvider([
        # Candle 1: only E1 fills (low=99 ≤ 100, not 90)
        _candle("2026-01-01T00:00:00", low=99.0, high=102.0),
        # Candle 2: E2 fills (low=88 ≤ 90)
        _candle("2026-01-01T01:00:00", low=88.0, high=92.0),
    ])

    _logs, state = simulate_chain(chain, policy, market_provider=market)

    assert len(state.fills) == 2

    fill_prices = [f.price for f in state.fills]
    assert 100.0 in fill_prices, "E1 (price=100) should have filled"
    assert 90.0 in fill_prices, "E2 (price=90) should have filled"

    assert state.open_size == pytest.approx(1.0)
    assert state.pending_size == pytest.approx(0.0)
    assert state.status == TradeStatus.ACTIVE
