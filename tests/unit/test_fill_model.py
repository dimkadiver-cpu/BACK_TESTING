from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.engine.fill_model import fill_market_order, try_fill_limit_order_touch
from src.signal_chain_lab.market.data_models import Candle
from src.signal_chain_lab.policies.base import PolicyConfig


def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def test_fill_market_order_applies_latency() -> None:
    policy = PolicyConfig(name="p", execution={"latency_ms": 250})
    fill = fill_market_order(
        qty=1.5,
        reference_price=100.0,
        event_timestamp=_utc("2026-01-01T10:00:00"),
        policy=policy,
        source_event_sequence=7,
    )
    assert fill.price == 100.0
    assert fill.qty == 1.5
    assert fill.timestamp == _utc("2026-01-01T10:00:00.250000")
    assert fill.source_event_sequence == 7


def test_fill_limit_touch_for_long() -> None:
    policy = PolicyConfig(name="p")
    candle = Candle(
        open=101.0,
        high=103.0,
        low=99.0,
        close=102.0,
        volume=10.0,
        timestamp=_utc("2026-01-01T10:00:00"),
        symbol="BTCUSDT",
        timeframe="1m",
    )
    fill = try_fill_limit_order_touch(
        qty=1.0,
        limit_price=100.0,
        candle=candle,
        side="LONG",
        policy=policy,
    )
    assert fill is not None
    assert fill.price == 100.0


def test_fill_limit_no_touch_returns_none() -> None:
    policy = PolicyConfig(name="p")
    candle = Candle(
        open=101.0,
        high=103.0,
        low=100.5,
        close=102.0,
        volume=10.0,
        timestamp=_utc("2026-01-01T10:00:00"),
        symbol="BTCUSDT",
        timeframe="1m",
    )
    fill = try_fill_limit_order_touch(
        qty=1.0,
        limit_price=100.0,
        candle=candle,
        side="LONG",
        policy=policy,
    )
    assert fill is None
