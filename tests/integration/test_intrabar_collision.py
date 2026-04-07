from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.domain.enums import ChainInputMode, EventSource, EventType
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent
from src.signal_chain_lab.engine.simulator import simulate_chain
from src.signal_chain_lab.market.data_models import Candle, MarketMetadata
from src.signal_chain_lab.policies.base import PolicyConfig


def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


class StubMarketProvider:
    def __init__(self, parent: Candle, children: list[Candle]) -> None:
        self.parent = parent
        self.children = children
        self.intrabar_calls = 0

    def has_symbol(self, symbol: str) -> bool:
        return symbol == "BTCUSDT"

    def get_candle(self, symbol: str, timeframe: str, ts: datetime) -> Candle | None:
        if symbol == self.parent.symbol and timeframe == self.parent.timeframe and ts == self.parent.timestamp:
            return self.parent
        return None

    def get_range(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Candle]:
        del start, end
        if symbol == self.parent.symbol and timeframe == self.parent.timeframe:
            return [self.parent]
        return []

    def get_intrabar_range(
        self,
        symbol: str,
        parent_timeframe: str,
        child_timeframe: str,
        ts: datetime,
    ) -> list[Candle]:
        del parent_timeframe
        self.intrabar_calls += 1
        if symbol == "BTCUSDT" and child_timeframe == "5m" and ts == self.parent.timestamp:
            return self.children
        return []

    def get_metadata(self, symbol: str, timeframe: str) -> MarketMetadata | None:
        del symbol
        return MarketMetadata(
            symbol="BTCUSDT",
            timeframe=timeframe,
            provider_name="stub",
            timezone="UTC",
            start=self.parent.timestamp,
            end=self.parent.timestamp,
        )


def _build_chain(metadata: dict[str, str] | None = None) -> CanonicalChain:
    return CanonicalChain(
        signal_id="sig-6",
        trader_id="trader-a",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=False,
        created_at=_utc("2026-01-01T10:00:00"),
        metadata=metadata or {"timeframe": "1h", "intrabar_child_timeframe": "5m"},
        events=[
            CanonicalEvent(
                signal_id="sig-6",
                trader_id="trader-a",
                symbol="BTCUSDT",
                side="BUY",
                timestamp=_utc("2026-01-01T10:00:00"),
                event_type=EventType.OPEN_SIGNAL,
                source=EventSource.TRADER,
                payload={"entry_prices": [100.0], "sl_price": 90.0, "tp_levels": [110.0]},
                sequence=0,
            )
        ],
    )


def test_intrabar_collision_uses_child_timeframe() -> None:
    parent = Candle(
        timestamp=_utc("2026-01-01T10:00:00"),
        open=100.0,
        high=111.0,
        low=89.0,
        close=100.0,
        volume=1.0,
        symbol="BTCUSDT",
        timeframe="1h",
    )
    children = [
        Candle(
            timestamp=_utc("2026-01-01T10:00:00"),
            open=100.0,
            high=110.5,
            low=99.0,
            close=110.0,
            volume=1.0,
            symbol="BTCUSDT",
            timeframe="5m",
        )
    ]
    provider = StubMarketProvider(parent, children)

    logs, state = simulate_chain(_build_chain(), PolicyConfig(name="original_chain"), provider)

    assert provider.intrabar_calls == 1
    assert len(logs) == 2
    assert logs[-1].source == "engine"
    assert state.close_reason is not None
    assert state.close_reason.value == "tp"


def test_intrabar_collision_fallback_with_warning_when_child_missing() -> None:
    parent = Candle(
        timestamp=_utc("2026-01-01T10:00:00"),
        open=100.0,
        high=111.0,
        low=89.0,
        close=100.0,
        volume=1.0,
        symbol="BTCUSDT",
        timeframe="1h",
    )
    provider = StubMarketProvider(parent, children=[])

    logs, state = simulate_chain(_build_chain(), PolicyConfig(name="original_chain"), provider)

    assert provider.intrabar_calls == 1
    assert len(logs) == 2
    assert state.close_reason is not None
    assert state.close_reason.value == "sl"
    assert state.warnings_count == 1


def test_no_collision_does_not_call_intrabar_provider() -> None:
    parent = Candle(
        timestamp=_utc("2026-01-01T10:00:00"),
        open=100.0,
        high=108.0,
        low=92.0,
        close=100.0,
        volume=1.0,
        symbol="BTCUSDT",
        timeframe="1h",
    )
    provider = StubMarketProvider(parent, children=[])

    logs, state = simulate_chain(_build_chain(), PolicyConfig(name="original_chain"), provider)

    assert provider.intrabar_calls == 0
    assert len(logs) == 1
    assert state.close_reason is None
