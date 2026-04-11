"""Integration tests for multi-TP policy support in the simulator.

Covers:
- Equal distribution across 3 TPs
- tp_50_30_20 distribution across 3 TPs
- use_tp_count=1 closes full at TP1
- use_tp_count=2 with 4 signal TPs
- No double PnL counting across partial TP hits
- be_trigger=tp1 moves SL to BE after first partial close
- cancel_averaging_pending_after_tp1 cancels pending after TP1
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
from src.signal_chain_lab.engine.simulator import simulate_chain
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
            provider_name="list-provider",
            timezone="UTC",
            start=matching[0].timestamp,
            end=matching[-1].timestamp,
        )


def _make_chain(tp_levels: list[float], entry_price: float = 100.0, sl_price: float = 80.0) -> CanonicalChain:
    return CanonicalChain(
        signal_id="sig-multi-tp",
        trader_id="trader-x",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=False,
        created_at=_utc("2026-01-01T00:00:00"),
        metadata={"timeframe": "1h"},
        events=[
            CanonicalEvent(
                signal_id="sig-multi-tp",
                trader_id="trader-x",
                symbol="BTCUSDT",
                side="BUY",
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
    use_tp_count: int | None = None,
    be_trigger: str | None = None,
    cancel_avg_after_tp1: bool = False,
) -> PolicyConfig:
    data: dict = {
        "name": "test_multi_tp",
        "tp": {"use_original_tp": True, "tp_distribution": tp_distribution},
        "pending": {
            "pending_timeout_hours": 200,
            "chain_timeout_hours": 400,
            "cancel_averaging_pending_after_tp1": cancel_avg_after_tp1,
        },
    }
    if use_tp_count is not None:
        data["tp"]["use_tp_count"] = use_tp_count
    if be_trigger is not None:
        data["sl"] = {"break_even_mode": "auto", "be_trigger": be_trigger}
    return PolicyConfig.from_dict(data)


# ---------------------------------------------------------------------------
# Tests: TP distribution — equal
# ---------------------------------------------------------------------------

def test_three_tp_equal_closes_in_three_steps() -> None:
    """Equal distribution: position is closed in three equal chunks at TP1, TP2, TP3."""
    chain = _make_chain(tp_levels=[110.0, 120.0, 130.0])
    policy = _policy(tp_distribution="equal")

    # Candle 1: fills entry at 100 (low touches 100)
    # Candle 2: hits TP1 at 110 (high ≥ 110, low > SL)
    # Candle 3: hits TP2 at 120
    # Candle 4: hits TP3 at 130 → full close
    provider = _ListProvider([
        _candle("2026-01-01T00:00:00", 101, 102, 99, 101),   # fills limit @100
        _candle("2026-01-01T01:00:00", 105, 112, 104, 110),  # TP1 hit
        _candle("2026-01-01T02:00:00", 115, 122, 113, 120),  # TP2 hit
        _candle("2026-01-01T03:00:00", 125, 132, 123, 130),  # TP3 hit
    ])

    logs, state = simulate_chain(chain, policy, provider)

    assert state.status == TradeStatus.CLOSED
    assert state.close_reason == CloseReason.TP
    assert state.open_size == pytest.approx(0.0, abs=1e-9)

    # Count engine-generated partial TP events
    partial_events = [log for log in logs if log.event_type == "CLOSE_PARTIAL" and log.source == "engine"]
    full_tp_events = [
        log for log in logs
        if log.event_type == "CLOSE_FULL" and log.source == "engine"
        and log.state_after.get("close_reason") == "tp"
    ]
    assert len(partial_events) == 2, f"Expected 2 partial TP closes, got {len(partial_events)}"
    assert len(full_tp_events) == 1, f"Expected 1 final TP close, got {len(full_tp_events)}"

    # PnL: 1/3*(110-100) + 1/3*(120-100) + 1/3*(130-100) = 3.33 + 6.67 + 10 = 20.0
    expected_pnl = (1 / 3) * (110 - 100) + (1 / 3) * (120 - 100) + (1 / 3) * (130 - 100)
    assert state.realized_pnl == pytest.approx(expected_pnl, rel=1e-6)


def test_three_tp_equal_position_size_reduces_step_by_step() -> None:
    """After each partial TP close, open_size decreases by 1/3 of original."""
    chain = _make_chain(tp_levels=[110.0, 120.0, 130.0])
    policy = _policy(tp_distribution="equal")

    provider = _ListProvider([
        _candle("2026-01-01T00:00:00", 101, 102, 99, 101),
        _candle("2026-01-01T01:00:00", 105, 112, 104, 110),
        _candle("2026-01-01T02:00:00", 115, 122, 113, 120),
        _candle("2026-01-01T03:00:00", 125, 132, 123, 130),
    ])

    logs, state = simulate_chain(chain, policy, provider)

    # Verify open_size progression from partial close logs
    partial_events = [log for log in logs if log.event_type == "CLOSE_PARTIAL" and log.source == "engine"]
    assert len(partial_events) == 2

    # After TP1 partial close: open_size should be ~2/3
    after_tp1 = partial_events[0].state_after
    assert after_tp1["open_size"] == pytest.approx(2 / 3, rel=1e-6)

    # After TP2 partial close: open_size should be ~1/3
    after_tp2 = partial_events[1].state_after
    assert after_tp2["open_size"] == pytest.approx(1 / 3, rel=1e-6)


# ---------------------------------------------------------------------------
# Tests: TP distribution — tp_50_30_20
# ---------------------------------------------------------------------------

def test_three_tp_50_30_20_closes_with_correct_pnl() -> None:
    """tp_50_30_20: close 50 % at TP1, 30 % at TP2, 20 % at TP3."""
    chain = _make_chain(tp_levels=[110.0, 120.0, 130.0])
    policy = _policy(tp_distribution="tp_50_30_20")

    provider = _ListProvider([
        _candle("2026-01-01T00:00:00", 101, 102, 99, 101),
        _candle("2026-01-01T01:00:00", 105, 112, 104, 110),  # TP1
        _candle("2026-01-01T02:00:00", 115, 122, 113, 120),  # TP2
        _candle("2026-01-01T03:00:00", 125, 132, 123, 130),  # TP3
    ])

    logs, state = simulate_chain(chain, policy, provider)

    assert state.status == TradeStatus.CLOSED
    assert state.close_reason == CloseReason.TP

    # PnL: 0.5*(110-100) + 0.3*(120-100) + 0.2*(130-100) = 5 + 6 + 6 = 17.0
    expected_pnl = 0.5 * (110 - 100) + 0.3 * (120 - 100) + 0.2 * (130 - 100)
    assert state.realized_pnl == pytest.approx(expected_pnl, rel=1e-6)

    # 2 partial + 1 final TP close
    partial_events = [log for log in logs if log.event_type == "CLOSE_PARTIAL" and log.source == "engine"]
    assert len(partial_events) == 2


def test_three_tp_50_30_20_open_size_correct_after_tp1() -> None:
    """After TP1 (50 %), 50 % of position remains open."""
    chain = _make_chain(tp_levels=[110.0, 120.0, 130.0])
    policy = _policy(tp_distribution="tp_50_30_20")

    provider = _ListProvider([
        _candle("2026-01-01T00:00:00", 101, 102, 99, 101),
        _candle("2026-01-01T01:00:00", 105, 112, 104, 110),
        _candle("2026-01-01T02:00:00", 115, 122, 113, 120),
        _candle("2026-01-01T03:00:00", 125, 132, 123, 130),
    ])

    logs, state = simulate_chain(chain, policy, provider)

    partial_events = [log for log in logs if log.event_type == "CLOSE_PARTIAL" and log.source == "engine"]
    assert partial_events[0].state_after["open_size"] == pytest.approx(0.5, rel=1e-6)
    assert partial_events[1].state_after["open_size"] == pytest.approx(0.2, rel=1e-6)


# ---------------------------------------------------------------------------
# Tests: use_tp_count
# ---------------------------------------------------------------------------

def test_use_tp_count_1_closes_full_at_tp1() -> None:
    """use_tp_count=1: use only the first TP and close the full position there."""
    # Signal has 3 TPs, but policy limits to 1
    chain = _make_chain(tp_levels=[110.0, 120.0, 130.0])
    policy = _policy(tp_distribution="equal", use_tp_count=1)

    provider = _ListProvider([
        _candle("2026-01-01T00:00:00", 101, 102, 99, 101),
        _candle("2026-01-01T01:00:00", 105, 112, 104, 110),  # TP1 → should close full
    ])

    logs, state = simulate_chain(chain, policy, provider)

    assert state.status == TradeStatus.CLOSED
    assert state.close_reason == CloseReason.TP
    assert state.open_size == pytest.approx(0.0, abs=1e-9)

    # Only 1 effective TP → CLOSE_FULL, no partials
    partial_events = [log for log in logs if log.event_type == "CLOSE_PARTIAL" and log.source == "engine"]
    assert len(partial_events) == 0

    # PnL: 1.0 * (110 - 100) = 10.0
    assert state.realized_pnl == pytest.approx(10.0, rel=1e-6)


def test_use_tp_count_2_with_four_signal_tps() -> None:
    """use_tp_count=2: only the first 2 signal TPs are used; trade closes at TP2."""
    chain = _make_chain(tp_levels=[110.0, 120.0, 130.0, 140.0])
    policy = _policy(tp_distribution="equal", use_tp_count=2)

    provider = _ListProvider([
        _candle("2026-01-01T00:00:00", 101, 102, 99, 101),
        _candle("2026-01-01T01:00:00", 105, 112, 104, 110),  # TP1 partial
        _candle("2026-01-01T02:00:00", 115, 125, 113, 120),  # TP2 final close
    ])

    logs, state = simulate_chain(chain, policy, provider)

    assert state.status == TradeStatus.CLOSED
    assert state.close_reason == CloseReason.TP
    assert state.open_size == pytest.approx(0.0, abs=1e-9)
    assert state.next_tp_index == 2  # consumed both effective TPs

    # 1 partial (TP1) + 1 final (TP2)
    partial_events = [log for log in logs if log.event_type == "CLOSE_PARTIAL" and log.source == "engine"]
    assert len(partial_events) == 1

    # tp_levels in state should only have 2 entries
    assert state.tp_levels == [110.0, 120.0]

    # PnL: 0.5*(110-100) + 0.5*(120-100) = 5 + 10 = 15.0
    expected_pnl = 0.5 * (110 - 100) + 0.5 * (120 - 100)
    assert state.realized_pnl == pytest.approx(expected_pnl, rel=1e-6)


# ---------------------------------------------------------------------------
# Tests: no double PnL counting
# ---------------------------------------------------------------------------

def test_no_double_pnl_single_tp() -> None:
    """For a single-TP trade, PnL equals exactly (tp_price - entry) * position_size."""
    chain = _make_chain(tp_levels=[110.0])
    policy = _policy(tp_distribution="equal")

    provider = _ListProvider([
        _candle("2026-01-01T00:00:00", 101, 102, 99, 101),
        _candle("2026-01-01T01:00:00", 105, 112, 104, 110),
    ])

    logs, state = simulate_chain(chain, policy, provider)

    assert state.realized_pnl == pytest.approx(10.0, rel=1e-6)
    assert state.unrealized_pnl == pytest.approx(0.0, abs=1e-9)
    assert state.status == TradeStatus.CLOSED


def test_no_double_pnl_multi_tp_cumulative() -> None:
    """Cumulative PnL across 3 partial TP closes equals sum of individual contributions."""
    chain = _make_chain(tp_levels=[110.0, 120.0, 130.0])
    policy = _policy(tp_distribution="equal")

    provider = _ListProvider([
        _candle("2026-01-01T00:00:00", 101, 102, 99, 101),
        _candle("2026-01-01T01:00:00", 105, 112, 104, 110),
        _candle("2026-01-01T02:00:00", 115, 122, 113, 120),
        _candle("2026-01-01T03:00:00", 125, 132, 123, 130),
    ])

    logs, state = simulate_chain(chain, policy, provider)

    # Sum up realized_pnl deltas from event log
    pnl_deltas: list[float] = []
    prev_pnl = 0.0
    for log in logs:
        cur_pnl = log.state_after.get("realized_pnl", 0.0)
        delta = cur_pnl - prev_pnl
        if delta > 1e-10:
            pnl_deltas.append(delta)
        prev_pnl = cur_pnl

    assert len(pnl_deltas) == 3, f"Expected 3 PnL increments, got {len(pnl_deltas)}: {pnl_deltas}"
    assert sum(pnl_deltas) == pytest.approx(state.realized_pnl, rel=1e-9)


def test_pnl_after_partial_tp_then_sl_hit() -> None:
    """Trade partially closes at TP1 then SL is hit: PnL reflects both events."""
    chain = _make_chain(tp_levels=[110.0, 120.0, 130.0])
    policy = _policy(tp_distribution="equal")

    provider = _ListProvider([
        _candle("2026-01-01T00:00:00", 101, 102, 99, 101),   # fill @100
        _candle("2026-01-01T01:00:00", 105, 112, 104, 110),  # TP1 partial
        _candle("2026-01-01T02:00:00", 90, 92, 78, 80),      # SL @80 hit
    ])

    logs, state = simulate_chain(chain, policy, provider)

    assert state.status == TradeStatus.CLOSED
    assert state.close_reason == CloseReason.SL

    # After TP1: closed 1/3 @ 110, PnL += (110-100)*(1/3) ≈ 3.33
    # After SL: closed 2/3 @ 80, PnL += (80-100)*(2/3) ≈ -13.33
    tp1_pnl = (1 / 3) * (110 - 100)
    sl_pnl = (2 / 3) * (80 - 100)
    expected_pnl = tp1_pnl + sl_pnl
    assert state.realized_pnl == pytest.approx(expected_pnl, rel=1e-6)


# ---------------------------------------------------------------------------
# Tests: be_trigger
# ---------------------------------------------------------------------------

def test_be_trigger_tp1_moves_sl_to_entry_after_tp1() -> None:
    """be_trigger=tp1: SL is moved to avg_entry_price after TP1 partial close."""
    chain = _make_chain(tp_levels=[110.0, 120.0, 130.0])
    policy = _policy(tp_distribution="equal", be_trigger="tp1")

    provider = _ListProvider([
        _candle("2026-01-01T00:00:00", 101, 102, 99, 101),
        _candle("2026-01-01T01:00:00", 105, 112, 104, 110),  # TP1 + BE trigger
        _candle("2026-01-01T02:00:00", 115, 125, 113, 120),  # TP2
        _candle("2026-01-01T03:00:00", 125, 135, 123, 130),  # TP3
    ])

    logs, state = simulate_chain(chain, policy, provider)

    be_events = [log for log in logs if log.event_type == "MOVE_STOP_TO_BE" and log.source == "engine"]
    assert len(be_events) == 1, f"Expected 1 BE event, got {len(be_events)}"

    after_be = be_events[0].state_after
    assert after_be["current_sl"] == pytest.approx(after_be["avg_entry_price"], rel=1e-9)


# ---------------------------------------------------------------------------
# Tests: cancel_averaging_pending_after_tp1
# ---------------------------------------------------------------------------

def test_cancel_averaging_pending_after_tp1() -> None:
    """When cancel_averaging_pending_after_tp1=True, averaging pending entry is cancelled at TP1."""
    chain = CanonicalChain(
        signal_id="sig-avg-cancel",
        trader_id="trader-x",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=False,
        created_at=_utc("2026-01-01T00:00:00"),
        metadata={"timeframe": "1h"},
        events=[
            CanonicalEvent(
                signal_id="sig-avg-cancel",
                trader_id="trader-x",
                symbol="BTCUSDT",
                side="BUY",
                timestamp=_utc("2026-01-01T00:00:00"),
                event_type=EventType.OPEN_SIGNAL,
                source=EventSource.TRADER,
                payload={
                    "entry_type": "LIMIT",
                    "entry_plan_entries": [
                        {"role": "primary", "order_type": "limit", "price": 100.0},
                        {"role": "averaging", "order_type": "limit", "price": 95.0},
                    ],
                    "sl_price": 80.0,
                    "tp_levels": [110.0, 120.0, 130.0],
                },
                sequence=0,
            )
        ],
    )
    policy = _policy(tp_distribution="equal", cancel_avg_after_tp1=True)

    provider = _ListProvider([
        _candle("2026-01-01T00:00:00", 101, 102, 99, 101),   # fills primary @100; NOT averaging (low=99 > 95)
        _candle("2026-01-01T01:00:00", 105, 112, 104, 110),  # TP1 → partial close + cancel pending
    ])

    logs, state = simulate_chain(chain, policy, provider)

    cancel_events = [
        log for log in logs
        if log.event_type == "CANCEL_PENDING" and log.source == "engine"
        and log.state_before.get("pending_size", 0) > 0
    ]
    assert len(cancel_events) == 1

    # After cancellation, pending_size should be 0
    assert state.pending_size == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Tests: tp_close_fractions computed at signal open
# ---------------------------------------------------------------------------

def test_tp_close_fractions_computed_at_signal_open_equal() -> None:
    """tp_close_fractions is populated correctly at OPEN_SIGNAL with equal distribution."""
    from src.signal_chain_lab.engine.state_machine import apply_event
    from src.signal_chain_lab.domain.trade_state import TradeState

    state = TradeState(
        signal_id="s",
        symbol="BTCUSDT",
        side="BUY",
        status=__import__("src.signal_chain_lab.domain.enums", fromlist=["TradeStatus"]).TradeStatus.NEW,
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        policy_name="test",
    )
    event = CanonicalEvent(
        signal_id="s",
        symbol="BTCUSDT",
        side="BUY",
        timestamp=_utc("2026-01-01T00:00:00"),
        event_type=EventType.OPEN_SIGNAL,
        source=EventSource.TRADER,
        payload={"entry_prices": [100.0], "sl_price": 90.0, "tp_levels": [110.0, 120.0, 130.0]},
        sequence=0,
    )
    policy = _policy(tp_distribution="equal")
    apply_event(state, event, policy=policy)

    assert len(state.tp_close_fractions) == 3
    assert state.tp_close_fractions[0] == pytest.approx(1 / 3, rel=1e-6)
    assert state.tp_close_fractions[1] == pytest.approx(0.5, rel=1e-6)
    assert state.tp_close_fractions[2] == pytest.approx(1.0, rel=1e-6)


def test_tp_close_fractions_computed_at_signal_open_50_30_20() -> None:
    """tp_close_fractions computed correctly for tp_50_30_20 with 3 TPs."""
    from src.signal_chain_lab.engine.state_machine import apply_event
    from src.signal_chain_lab.domain.trade_state import TradeState
    from src.signal_chain_lab.domain.enums import TradeStatus

    state = TradeState(
        signal_id="s",
        symbol="BTCUSDT",
        side="BUY",
        status=TradeStatus.NEW,
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        policy_name="test",
    )
    event = CanonicalEvent(
        signal_id="s",
        symbol="BTCUSDT",
        side="BUY",
        timestamp=_utc("2026-01-01T00:00:00"),
        event_type=EventType.OPEN_SIGNAL,
        source=EventSource.TRADER,
        payload={"entry_prices": [100.0], "sl_price": 90.0, "tp_levels": [110.0, 120.0, 130.0]},
        sequence=0,
    )
    policy = _policy(tp_distribution="tp_50_30_20")
    apply_event(state, event, policy=policy)

    # f0=0.5, f1=0.3/0.5=0.6, f2=1.0
    assert state.tp_close_fractions[0] == pytest.approx(0.5, rel=1e-6)
    assert state.tp_close_fractions[1] == pytest.approx(0.6, rel=1e-6)
    assert state.tp_close_fractions[2] == pytest.approx(1.0, rel=1e-6)


def test_use_tp_count_limits_tp_levels_in_state() -> None:
    """use_tp_count truncates tp_levels stored in state."""
    from src.signal_chain_lab.engine.state_machine import apply_event
    from src.signal_chain_lab.domain.trade_state import TradeState
    from src.signal_chain_lab.domain.enums import TradeStatus

    state = TradeState(
        signal_id="s",
        symbol="BTCUSDT",
        side="BUY",
        status=TradeStatus.NEW,
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        policy_name="test",
    )
    event = CanonicalEvent(
        signal_id="s",
        symbol="BTCUSDT",
        side="BUY",
        timestamp=_utc("2026-01-01T00:00:00"),
        event_type=EventType.OPEN_SIGNAL,
        source=EventSource.TRADER,
        payload={"entry_prices": [100.0], "sl_price": 90.0, "tp_levels": [110.0, 120.0, 130.0, 140.0]},
        sequence=0,
    )
    policy = _policy(tp_distribution="equal", use_tp_count=2)
    apply_event(state, event, policy=policy)

    assert state.tp_levels == [110.0, 120.0]
    assert len(state.tp_close_fractions) == 2
    assert state.tp_close_fractions[0] == pytest.approx(0.5, rel=1e-6)
    assert state.tp_close_fractions[1] == pytest.approx(1.0, rel=1e-6)
