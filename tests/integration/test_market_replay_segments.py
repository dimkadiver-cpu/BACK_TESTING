from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.domain.enums import ChainInputMode, EventSource, EventType, TradeStatus
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent
from src.signal_chain_lab.engine.simulator import simulate_chain
from src.signal_chain_lab.market.data_models import Candle, MarketMetadata
from src.signal_chain_lab.policies.base import PolicyConfig


def _utc(y: int, mo: int, d: int, h: int = 0, mi: int = 0, sec: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, sec, tzinfo=timezone.utc)


class _SegmentProvider:
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

    def has_symbol(self, symbol: str) -> bool:
        return symbol == "BTCUSDT"

    def get_candle(self, symbol: str, timeframe: str, ts: datetime) -> Candle | None:
        for candle in self._candles:
            if candle.symbol == symbol and candle.timeframe == timeframe and candle.timestamp == ts:
                return candle
        return None

    def get_range(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Candle]:
        return [
            candle
            for candle in self._candles
            if candle.symbol == symbol and candle.timeframe == timeframe and start <= candle.timestamp <= end
        ]

    def get_intrabar_range(
        self,
        symbol: str,
        parent_timeframe: str,
        child_timeframe: str,
        ts: datetime,
    ) -> list[Candle]:
        return []

    def get_metadata(self, symbol: str, timeframe: str) -> MarketMetadata | None:
        matching = [c for c in self._candles if c.symbol == symbol and c.timeframe == timeframe]
        if not matching:
            return None
        return MarketMetadata(
            symbol=symbol,
            timeframe=timeframe,
            provider_name="segment-provider",
            timezone="UTC",
            start=matching[0].timestamp,
            end=matching[-1].timestamp,
        )


class _SegmentProviderWithMetadataEnd(_SegmentProvider):
    def __init__(self, candles: list[Candle], metadata_end: datetime) -> None:
        super().__init__(candles)
        self._metadata_end = metadata_end

    def get_metadata(self, symbol: str, timeframe: str) -> MarketMetadata | None:
        metadata = super().get_metadata(symbol, timeframe)
        if metadata is None:
            return None
        metadata.end = self._metadata_end
        return metadata


def test_replays_market_between_events_and_fills_limit_before_manual_close() -> None:
    chain = CanonicalChain(
        signal_id="sig-segment-fill",
        trader_id="trader-a",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=True,
        created_at=_utc(2026, 1, 1, 10, 0, 20),
        metadata={"timeframe": "1m"},
        events=[
            CanonicalEvent(
                signal_id="sig-segment-fill",
                trader_id="trader-a",
                symbol="BTCUSDT",
                side="BUY",
                timestamp=_utc(2026, 1, 1, 10, 0, 20),
                event_type=EventType.OPEN_SIGNAL,
                source=EventSource.TRADER,
                payload={"entry_prices": [100.0], "sl_price": 95.0, "tp_levels": [110.0]},
                sequence=0,
            ),
            CanonicalEvent(
                signal_id="sig-segment-fill",
                trader_id="trader-a",
                symbol="BTCUSDT",
                side="BUY",
                timestamp=_utc(2026, 1, 1, 10, 3, 0),
                event_type=EventType.CLOSE_FULL,
                source=EventSource.TRADER,
                payload={"close_price": 103.0},
                sequence=1,
            ),
        ],
    )
    provider = _SegmentProvider(
        [
            Candle(
                timestamp=_utc(2026, 1, 1, 10, 0, 0),
                open=101.0,
                high=101.5,
                low=100.5,
                close=101.0,
                volume=1.0,
                symbol="BTCUSDT",
                timeframe="1m",
            ),
            Candle(
                timestamp=_utc(2026, 1, 1, 10, 1, 0),
                open=100.8,
                high=101.2,
                low=99.8,
                close=100.2,
                volume=1.0,
                symbol="BTCUSDT",
                timeframe="1m",
            ),
            Candle(
                timestamp=_utc(2026, 1, 1, 10, 2, 0),
                open=102.0,
                high=103.5,
                low=101.8,
                close=103.0,
                volume=1.0,
                symbol="BTCUSDT",
                timeframe="1m",
            ),
        ]
    )

    logs, state = simulate_chain(chain=chain, policy=PolicyConfig(name="original_chain"), market_provider=provider)

    assert len(logs) == 2
    assert state.first_fill_at == _utc(2026, 1, 1, 10, 1, 0)
    assert state.status == TradeStatus.CLOSED
    assert state.realized_pnl == 3.0
    assert state.close_reason is not None
    assert state.close_reason.value == "manual"


def test_tp_sl_collision_requires_open_position_not_pending_only() -> None:
    chain = CanonicalChain(
        signal_id="sig-pending-no-close",
        trader_id="trader-a",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.SIGNAL_ONLY_NATIVE,
        has_updates_in_dataset=False,
        created_at=_utc(2026, 1, 1, 10, 0, 0),
        metadata={"timeframe": "1m"},
        events=[
            CanonicalEvent(
                signal_id="sig-pending-no-close",
                trader_id="trader-a",
                symbol="BTCUSDT",
                side="BUY",
                timestamp=_utc(2026, 1, 1, 10, 0, 0),
                event_type=EventType.OPEN_SIGNAL,
                source=EventSource.TRADER,
                payload={"entry_prices": [100.0], "sl_price": 95.0, "tp_levels": [110.0]},
                sequence=0,
            )
        ],
    )
    provider = _SegmentProvider(
        [
            Candle(
                timestamp=_utc(2026, 1, 1, 10, 0, 0),
                open=105.0,
                high=109.0,
                low=101.0,
                close=106.0,
                volume=1.0,
                symbol="BTCUSDT",
                timeframe="1m",
            )
        ]
    )

    logs, state = simulate_chain(chain=chain, policy=PolicyConfig(name="original_chain"), market_provider=provider)

    assert len(logs) == 1
    assert state.status == TradeStatus.PENDING
    assert state.first_fill_at is None
    assert state.realized_pnl == 0.0


def test_chain_timeout_triggers_even_when_it_falls_between_candle_buckets() -> None:
    chain = CanonicalChain(
        signal_id="sig-timeout-between-buckets",
        trader_id="trader-a",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=False,
        created_at=_utc(2026, 1, 1, 0, 30, 30),
        metadata={"timeframe": "1h"},
        events=[
            CanonicalEvent(
                signal_id="sig-timeout-between-buckets",
                trader_id="trader-a",
                symbol="BTCUSDT",
                side="BUY",
                timestamp=_utc(2026, 1, 1, 0, 30, 30),
                event_type=EventType.OPEN_SIGNAL,
                source=EventSource.TRADER,
                payload={"entry_prices": [100.0], "sl_price": 95.0, "tp_levels": [120.0]},
                sequence=0,
            )
        ],
    )
    provider = _SegmentProviderWithMetadataEnd(
        [
            Candle(
                timestamp=_utc(2026, 1, 1, 0, 0, 0),
                open=101.0,
                high=101.0,
                low=101.0,
                close=101.0,
                volume=1.0,
                symbol="BTCUSDT",
                timeframe="1h",
            ),
            Candle(
                timestamp=_utc(2026, 1, 1, 1, 0, 0),
                open=100.5,
                high=101.0,
                low=99.0,
                close=100.2,
                volume=1.0,
                symbol="BTCUSDT",
                timeframe="1h",
            ),
            Candle(
                timestamp=_utc(2026, 1, 1, 2, 0, 0),
                open=100.2,
                high=100.8,
                low=99.8,
                close=100.1,
                volume=1.0,
                symbol="BTCUSDT",
                timeframe="1h",
            ),
        ],
        metadata_end=_utc(2026, 1, 1, 2, 30, 30),
    )
    policy = PolicyConfig(name="original_chain", pending={"chain_timeout_hours": 2.0})

    logs, state = simulate_chain(chain=chain, policy=policy, market_provider=provider)

    assert state.first_fill_at == _utc(2026, 1, 1, 1, 0, 0)
    assert state.status == TradeStatus.EXPIRED
    assert state.closed_at == _utc(2026, 1, 1, 2, 30, 30)
    assert state.close_reason is not None
    assert state.close_reason.value == "expired"
    assert logs[-1].reason == "chain_timeout"
