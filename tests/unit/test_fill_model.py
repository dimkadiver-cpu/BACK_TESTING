from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.engine.fill_model import compute_close_fee, fill_market_order, try_fill_limit_order_touch
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


def test_fee_uses_taker_for_market_and_maker_for_limit() -> None:
    policy = PolicyConfig(
        name="p",
        execution={
            "fee_model": "fixed_bps",
            "fee_bps": 10.0,
            "maker_fee_bps": 2.0,
            "taker_fee_bps": 8.0,
        },
    )

    market_fill = fill_market_order(
        qty=1.0,
        reference_price=100.0,
        event_timestamp=_utc("2026-01-01T10:00:00"),
        policy=policy,
    )
    assert market_fill.fee_paid == 0.08  # 100 * 1 * 8 / 10_000

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
    limit_fill = try_fill_limit_order_touch(
        qty=1.0,
        limit_price=100.0,
        candle=candle,
        side="LONG",
        policy=policy,
    )
    assert limit_fill is not None
    assert limit_fill.fee_paid == 0.02  # 100 * 1 * 2 / 10_000


def test_close_fee_uses_role_specific_bps_and_falls_back_to_fee_bps() -> None:
    policy = PolicyConfig(
        name="p",
        execution={
            "fee_model": "fixed_bps",
            "fee_bps": 10.0,
            "maker_fee_bps": 2.0,
            "taker_fee_bps": 8.0,
        },
    )
    assert compute_close_fee(100.0, 1.0, policy, liquidity_role="maker") == 0.02
    assert compute_close_fee(100.0, 1.0, policy, liquidity_role="taker") == 0.08
    assert compute_close_fee(100.0, 1.0, policy, liquidity_role=None) == 0.1
