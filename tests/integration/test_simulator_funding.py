from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.signal_chain_lab.domain.enums import ChainInputMode, EventSource, EventType, TradeStatus
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent
from src.signal_chain_lab.engine.simulator import simulate_chain
from src.signal_chain_lab.market.data_models import Candle, FundingEvent, MarketMetadata
from src.signal_chain_lab.policies.base import IntrabarReplayConfig, PolicyConfig


def _utc(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def _candle(ts: datetime, *, close: float = 100.0, timeframe: str = "1h") -> Candle:
    return Candle(
        timestamp=ts,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=1.0,
        symbol="BTCUSDT",
        timeframe=timeframe,
    )


def _open_signal(ts: datetime, *, side: str = "BUY") -> CanonicalEvent:
    return CanonicalEvent(
        signal_id="sig-funding",
        trader_id="trader-a",
        symbol="BTCUSDT",
        side=side,
        timestamp=ts,
        event_type=EventType.OPEN_SIGNAL,
        source=EventSource.TRADER,
        payload={"entry_prices": [100.0], "sl_price": 90.0, "tp_levels": [130.0]},
        sequence=0,
    )


class _MarketProvider:
    def __init__(
        self,
        parent_candles: list[Candle],
        *,
        child_candles_by_parent: dict[datetime, list[Candle]] | None = None,
    ) -> None:
        self._parents = sorted(parent_candles, key=lambda candle: candle.timestamp)
        self._children = child_candles_by_parent or {}

    def has_symbol(self, symbol: str) -> bool:
        return symbol == "BTCUSDT"

    def get_candle(self, symbol: str, timeframe: str, ts: datetime) -> Candle | None:
        for candle in self._parents:
            if candle.symbol == symbol and candle.timeframe == timeframe and candle.timestamp == ts:
                return candle
        return None

    def get_range(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Candle]:
        return [
            candle
            for candle in self._parents
            if candle.symbol == symbol and candle.timeframe == timeframe and start <= candle.timestamp <= end
        ]

    def get_intrabar_range(
        self,
        symbol: str,
        parent_timeframe: str,
        child_timeframe: str,
        ts: datetime,
    ) -> list[Candle]:
        return list(self._children.get(ts, []))

    def get_metadata(self, symbol: str, timeframe: str) -> MarketMetadata | None:
        if not self._parents:
            return None
        return MarketMetadata(
            symbol=symbol,
            timeframe=timeframe,
            provider_name="funding-test-provider",
            timezone="UTC",
            start=self._parents[0].timestamp,
            end=self._parents[-1].timestamp + timedelta(hours=1),
        )


class _FundingProvider:
    def __init__(self, events: list[FundingEvent]) -> None:
        self._events = sorted(events, key=lambda item: item.funding_ts_utc)

    def get_funding_rate(self, symbol: str, ts: datetime) -> float | None:
        del symbol, ts
        return None

    def get_funding_events(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[FundingEvent]:
        return [
            event
            for event in self._events
            if event.symbol == symbol and start <= event.funding_ts_utc <= end
        ]


def test_historical_funding_is_applied_once_per_event_for_open_position() -> None:
    chain = CanonicalChain(
        signal_id="sig-funding",
        trader_id="trader-a",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=False,
        created_at=_utc(2026, 1, 1, 0),
        metadata={"timeframe": "1h"},
        events=[_open_signal(_utc(2026, 1, 1, 0), side="BUY")],
    )
    market_provider = _MarketProvider(
        [
            _candle(_utc(2026, 1, 1, 0), close=100.0),
            _candle(_utc(2026, 1, 1, 1), close=105.0),
            _candle(_utc(2026, 1, 1, 2), close=110.0),
        ]
    )
    funding_provider = _FundingProvider(
        [
            FundingEvent(symbol="BTCUSDT", funding_ts_utc=_utc(2026, 1, 1, 1), funding_rate=0.01),
            FundingEvent(symbol="BTCUSDT", funding_ts_utc=_utc(2026, 1, 1, 1), funding_rate=0.01),
            FundingEvent(symbol="BTCUSDT", funding_ts_utc=_utc(2026, 1, 1, 2), funding_rate=0.02),
        ]
    )
    policy = PolicyConfig(name="with-funding", execution={"funding_model": "historical"})

    logs, state = simulate_chain(
        chain,
        policy=policy,
        market_provider=market_provider,
        funding_provider=funding_provider,
    )

    assert state.status == TradeStatus.ACTIVE
    assert state.funding_events_count == 2
    assert state.applied_funding_event_keys == [
        _utc(2026, 1, 1, 1).isoformat(),
        _utc(2026, 1, 1, 2).isoformat(),
    ]
    assert state.funding_paid == -(100.0 * 0.01 + 105.0 * 0.02)
    funding_logs = [entry for entry in logs if entry.event_type == "funding_applied"]
    assert len(funding_logs) == 2


def test_funding_is_not_applied_when_model_is_none() -> None:
    chain = CanonicalChain(
        signal_id="sig-funding-none",
        trader_id="trader-a",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=False,
        created_at=_utc(2026, 1, 1, 0),
        metadata={"timeframe": "1h"},
        events=[_open_signal(_utc(2026, 1, 1, 0), side="BUY")],
    )
    market_provider = _MarketProvider([_candle(_utc(2026, 1, 1, 0), close=100.0), _candle(_utc(2026, 1, 1, 1), close=100.0)])
    funding_provider = _FundingProvider(
        [FundingEvent(symbol="BTCUSDT", funding_ts_utc=_utc(2026, 1, 1, 1), funding_rate=0.01)]
    )

    logs, state = simulate_chain(
        chain,
        policy=PolicyConfig(name="without-funding", execution={"funding_model": "none"}),
        market_provider=market_provider,
        funding_provider=funding_provider,
    )

    assert state.funding_paid == 0.0
    assert state.funding_events_count == 0
    assert all(entry.event_type != "funding_applied" for entry in logs)


def test_funding_logs_are_kept_when_apply_to_pnl_is_disabled() -> None:
    chain = CanonicalChain(
        signal_id="sig-funding-log-only",
        trader_id="trader-a",
        symbol="BTCUSDT",
        side="SELL",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=False,
        created_at=_utc(2026, 1, 1, 0),
        metadata={"timeframe": "1h"},
        events=[_open_signal(_utc(2026, 1, 1, 0), side="SELL")],
    )
    market_provider = _MarketProvider([_candle(_utc(2026, 1, 1, 0), close=100.0), _candle(_utc(2026, 1, 1, 1), close=100.0)])
    funding_provider = _FundingProvider(
        [FundingEvent(symbol="BTCUSDT", funding_ts_utc=_utc(2026, 1, 1, 1), funding_rate=0.01)]
    )
    policy = PolicyConfig(
        name="funding-log-only",
        execution={"funding_model": "historical", "funding_apply_to_pnl": False},
    )

    logs, state = simulate_chain(
        chain,
        policy=policy,
        market_provider=market_provider,
        funding_provider=funding_provider,
    )

    assert state.funding_paid == 0.0
    assert state.funding_events_count == 1
    funding_logs = [entry for entry in logs if entry.event_type == "funding_applied"]
    assert len(funding_logs) == 1
    assert funding_logs[0].reason == "funding_received"


def test_intrabar_replay_applies_funding_on_child_candles() -> None:
    open_event = _open_signal(_utc(2026, 1, 1, 10), side="BUY")
    move_stop = CanonicalEvent(
        signal_id="sig-funding-intrabar",
        trader_id="trader-a",
        symbol="BTCUSDT",
        side="BUY",
        timestamp=_utc(2026, 1, 1, 10, 30),
        event_type=EventType.MOVE_STOP,
        source=EventSource.TRADER,
        payload={"new_sl_price": 99.0},
        sequence=1,
    )
    chain = CanonicalChain(
        signal_id="sig-funding-intrabar",
        trader_id="trader-a",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=True,
        created_at=_utc(2026, 1, 1, 10),
        metadata={"timeframe": "1h"},
        events=[open_event, move_stop],
    )
    market_provider = _MarketProvider(
        [_candle(_utc(2026, 1, 1, 10), close=100.0)],
        child_candles_by_parent={
            _utc(2026, 1, 1, 10): [
                _candle(_utc(2026, 1, 1, 10), close=100.0, timeframe="5m"),
                _candle(_utc(2026, 1, 1, 10, 30), close=102.0, timeframe="5m"),
                _candle(_utc(2026, 1, 1, 10, 35), close=103.0, timeframe="5m"),
            ]
        },
    )
    funding_provider = _FundingProvider(
        [FundingEvent(symbol="BTCUSDT", funding_ts_utc=_utc(2026, 1, 1, 10, 35), funding_rate=0.01)]
    )
    policy = PolicyConfig(
        name="funding-intrabar",
        execution={"funding_model": "historical"},
        intrabar=IntrabarReplayConfig(
            event_aware_replay_enabled=True,
            child_timeframe="5m",
            same_child_event_policy="conservative_pre_event",
            fallback_mode="warn_and_use_parent_logic",
        ),
    )

    logs, state = simulate_chain(
        chain,
        policy=policy,
        market_provider=market_provider,
        funding_provider=funding_provider,
    )

    assert state.funding_events_count == 1
    assert state.funding_paid == -(102.0 * 0.01)
    assert any(entry.event_type == "funding_applied" for entry in logs)
