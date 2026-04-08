from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.domain.enums import ChainInputMode, EventSource, EventType, TradeStatus
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent
from src.signal_chain_lab.market.data_models import Candle, MarketDataProvider, MarketMetadata
from src.signal_chain_lab.engine.simulator import simulate_chain
from src.signal_chain_lab.policies.base import PolicyConfig


def _utc(y: int, mo: int, d: int, h: int = 0, mi: int = 0, sec: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, sec, tzinfo=timezone.utc)


class _MinuteBucketProvider(MarketDataProvider):
    def __init__(self) -> None:
        self._candle = Candle(
            timestamp=_utc(2026, 4, 1, 0, 0, 0),
            open=100.0,
            high=102.0,
            low=99.0,
            close=101.0,
            volume=1.0,
            symbol="BTCUSDT",
            timeframe="1m",
        )

    def get_candle(self, symbol: str, timeframe: str, ts: datetime) -> Candle | None:
        if symbol == "BTCUSDT" and timeframe == "1m" and ts == self._candle.timestamp:
            return self._candle
        return None

    def get_range(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Candle]:
        if start <= self._candle.timestamp <= end:
            return [self._candle]
        return []

    def get_intrabar_range(
        self,
        symbol: str,
        parent_timeframe: str,
        child_timeframe: str,
        ts: datetime,
    ) -> list[Candle]:
        return []

    def get_metadata(self, symbol: str, timeframe: str) -> MarketMetadata | None:
        return None


def test_market_order_uses_signal_timestamp_bucket_for_fill() -> None:
    chain = CanonicalChain(
        signal_id="sig-market-bucket",
        trader_id="trader-a",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.SIGNAL_ONLY_NATIVE,
        has_updates_in_dataset=False,
        created_at=_utc(2026, 4, 1, 0, 0, 43),
        events=[
            CanonicalEvent(
                signal_id="sig-market-bucket",
                trader_id="trader-a",
                symbol="BTCUSDT",
                side="BUY",
                timestamp=_utc(2026, 4, 1, 0, 0, 43),
                event_type=EventType.OPEN_SIGNAL,
                source=EventSource.TRADER,
                payload={
                    "entry_prices": [],
                    "sl_price": 95.0,
                    "tp_levels": [110.0],
                    "entry_type": "market",
                },
                sequence=0,
            )
        ],
        metadata={"timeframe": "1m"},
    )

    logs, state = simulate_chain(
        chain=chain,
        policy=PolicyConfig(name="original_chain"),
        market_provider=_MinuteBucketProvider(),
    )

    assert logs
    assert state.status == TradeStatus.ACTIVE
    assert state.first_fill_at == _utc(2026, 4, 1, 0, 0, 43)
    assert state.avg_entry_price == 100.0
    assert len(state.fills) == 1
