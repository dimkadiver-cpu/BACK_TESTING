from __future__ import annotations

from datetime import datetime, timezone
import math

from src.signal_chain_lab.domain.enums import ChainInputMode, EventSource, EventType
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent
from src.signal_chain_lab.engine.simulator import simulate_chain
from src.signal_chain_lab.market.data_models import Candle, MarketMetadata
from src.signal_chain_lab.policies.base import PolicyConfig


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


def _chain_open_market(payload: dict) -> CanonicalChain:
    event = CanonicalEvent(
        signal_id="sig_market_001",
        trader_id="trader_test",
        symbol="BTCUSDT",
        side="BUY",
        timestamp=_utc("2026-01-01T00:00:00"),
        event_type=EventType.OPEN_SIGNAL,
        source=EventSource.TRADER,
        payload={
            "entry_type": "MARKET",
            "sl_price": 50.0,
            "tp_levels": [200.0],
            **payload,
        },
        sequence=1,
    )
    return CanonicalChain(
        signal_id="sig_market_001",
        trader_id="trader_test",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=False,
        created_at=_utc("2026-01-01T00:00:00"),
        metadata={"timeframe": "1h"},
        events=[event],
    )


def _chain_open_limit(payload: dict) -> CanonicalChain:
    event = CanonicalEvent(
        signal_id="sig_limit_001",
        trader_id="trader_test",
        symbol="BTCUSDT",
        side="BUY",
        timestamp=_utc("2026-01-01T00:00:00"),
        event_type=EventType.OPEN_SIGNAL,
        source=EventSource.TRADER,
        payload={
            "entry_type": "LIMIT",
            "entry_prices": [100.0],
            "sl_price": 50.0,
            "tp_levels": [200.0],
            **payload,
        },
        sequence=1,
    )
    return CanonicalChain(
        signal_id="sig_limit_001",
        trader_id="trader_test",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=False,
        created_at=_utc("2026-01-01T00:00:00"),
        metadata={"timeframe": "1h"},
        events=[event],
    )


def test_market_fill_mode_next_open_waits_next_candle() -> None:
    chain = _chain_open_market(payload={})
    policy = PolicyConfig.model_validate(
        {
            "name": "p",
            "execution": {"market_fill_mode": "next_open"},
            "pending": {"pending_timeout_hours": 9999, "chain_timeout_hours": 9999},
        }
    )
    provider = _ListProvider(
        [
            _candle("2026-01-01T00:00:00", open_=100.0, high=110.0, low=90.0, close=105.0),
            _candle("2026-01-01T01:00:00", open_=120.0, high=125.0, low=115.0, close=121.0),
        ]
    )

    _logs, state = simulate_chain(chain, policy, market_provider=provider)

    assert len(state.fills) == 1
    assert state.fills[0].price == 120.0


def test_market_requested_price_reference_ignores_requested_value() -> None:
    chain = _chain_open_market(payload={"entry_prices": [80.0]})
    policy = PolicyConfig.model_validate(
        {
            "name": "p",
            "execution": {
                "market_fill_mode": "next_open",
                "market_requested_price_mode": "reference",
            },
            "pending": {"pending_timeout_hours": 9999, "chain_timeout_hours": 9999},
        }
    )
    provider = _ListProvider(
        [
            _candle("2026-01-01T00:00:00", open_=100.0, high=110.0, low=90.0, close=105.0),
            _candle("2026-01-01T01:00:00", open_=130.0, high=131.0, low=129.0, close=130.5),
        ]
    )

    _logs, state = simulate_chain(chain, policy, market_provider=provider)

    assert len(state.fills) == 1
    assert state.fills[0].price == 130.0


def test_market_requested_price_strict_with_clamp() -> None:
    chain = _chain_open_market(payload={"entry_prices": [999.0]})
    policy = PolicyConfig.model_validate(
        {
            "name": "p",
            "execution": {
                "market_fill_mode": "next_open",
                "market_requested_price_mode": "strict",
                "clamp_requested_to_candle": True,
            },
            "pending": {"pending_timeout_hours": 9999, "chain_timeout_hours": 9999},
        }
    )
    provider = _ListProvider(
        [
            _candle("2026-01-01T00:00:00", open_=100.0, high=110.0, low=90.0, close=105.0),
            _candle("2026-01-01T01:00:00", open_=120.0, high=125.0, low=115.0, close=121.0),
        ]
    )

    _logs, state = simulate_chain(chain, policy, market_provider=provider)

    assert len(state.fills) == 1
    # requested 999 clamped to candle high=125
    assert state.fills[0].price == 125.0


def test_maker_taker_fee_roles_for_entry_and_close() -> None:
    chain = _chain_open_limit(payload={})
    policy = PolicyConfig.model_validate(
        {
            "name": "p",
            "execution": {
                "fee_model": "fixed_bps",
                "fee_bps": 10.0,
                "maker_fee_bps": 2.0,
                "taker_fee_bps": 8.0,
            },
            "pending": {"pending_timeout_hours": 9999, "chain_timeout_hours": 9999},
        }
    )
    provider = _ListProvider(
        [
            _candle("2026-01-01T00:00:00", open_=101.0, high=105.0, low=99.0, close=103.0),
            _candle("2026-01-01T01:00:00", open_=150.0, high=210.0, low=149.0, close=205.0),
        ]
    )

    _logs, state = simulate_chain(chain, policy, market_provider=provider)

    # entry limit fill = maker (100 * 1 * 2bps = 0.02)
    # TP close = maker (200 * 1 * 2bps = 0.04)
    assert math.isclose(state.fees_paid, 0.06, rel_tol=0.0, abs_tol=1e-12)
    assert math.isclose(state.close_fees_paid, 0.04, rel_tol=0.0, abs_tol=1e-12)
