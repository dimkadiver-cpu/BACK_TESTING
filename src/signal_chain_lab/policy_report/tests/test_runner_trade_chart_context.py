from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.signal_chain_lab.domain.enums import ChainInputMode
from src.signal_chain_lab.domain.results import TradeResult
from src.signal_chain_lab.market.data_models import Candle
from src.signal_chain_lab.policy_report.runner import _load_trade_chart_candles_by_timeframe


class _ProviderStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, datetime, datetime]] = []

    def get_range(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Candle]:
        self.calls.append((symbol, timeframe, start, end))
        return [
            Candle(
                timestamp=start,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=10.0,
                symbol=symbol,
                timeframe=timeframe,
            )
        ]


def test_trade_chart_context_window_extends_by_15_hours_each_side() -> None:
    created_at = datetime(2025, 2, 1, 12, 0, tzinfo=timezone.utc)
    closed_at = created_at + timedelta(hours=2)
    trade = TradeResult(
        signal_id="sig_ctx",
        symbol="BTCUSDT",
        side="LONG",
        status="closed",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        policy_name="policy_x",
        created_at=created_at,
        closed_at=closed_at,
    )
    chain = SimpleNamespace(metadata={"timeframe": "1m"})
    provider = _ProviderStub()

    candles = _load_trade_chart_candles_by_timeframe(
        trade=trade,
        chain=chain,
        market_provider=provider,
        event_log=[],
    )

    assert candles
    assert provider.calls
    _, _, start, end = provider.calls[0]
    assert start == created_at - timedelta(hours=15)
    assert end == closed_at + timedelta(hours=15)
