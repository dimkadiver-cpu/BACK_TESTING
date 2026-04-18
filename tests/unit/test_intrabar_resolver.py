from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.market.data_models import Candle
from src.signal_chain_lab.market.intrabar_resolver import IntrabarResolver
from src.signal_chain_lab.market.runtime_config import MarketRuntimeConfig


def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def _candle(ts: str, high: float, low: float, timeframe: str = "5m") -> Candle:
    return Candle(
        timestamp=_utc(ts),
        open=100.0,
        high=high,
        low=low,
        close=100.0,
        volume=1.0,
        symbol="BTCUSDT",
        timeframe=timeframe,
    )


def test_intrabar_resolves_tp_first_with_child_candles() -> None:
    resolver = IntrabarResolver(
        runtime_config=MarketRuntimeConfig(
            download_tf="15m",
            simulation_tf="15m",
            detail_tf="1m",
            price_basis="last",
            source="fixture",
            buffer_mode="auto",
            pre_buffer_days=0,
            post_buffer_days=0,
        )
    )
    parent = _candle("2026-01-01T10:00:00", high=111.0, low=89.0, timeframe="1h")
    child = [
        _candle("2026-01-01T10:00:00", high=110.5, low=99.5),
        _candle("2026-01-01T10:05:00", high=101.0, low=89.5),
    ]

    result = resolver.resolve_sl_tp_collision(
        parent_candle=parent,
        child_candles=child,
        side="BUY",
        sl_price=90.0,
        tp_price=110.0,
    )

    assert result.outcome == "tp_hit"
    assert result.child_timeframe_used is True
    assert result.used_fallback is False
    assert result.candidate_reasons == ["sl_touch_possible", "tp_touch_possible", "sl_tp_collision"]
    assert result.metadata["simulation_tf"] == "15m"
    assert result.metadata["detail_tf"] == "1m"
    assert result.descended_parent_bars == 1


def test_intrabar_fallback_when_child_candles_absent() -> None:
    resolver = IntrabarResolver()
    parent = _candle("2026-01-01T10:00:00", high=111.0, low=89.0, timeframe="1h")

    result = resolver.resolve_sl_tp_collision(
        parent_candle=parent,
        child_candles=[],
        side="BUY",
        sl_price=90.0,
        tp_price=110.0,
    )

    assert result.outcome == "sl_hit"
    assert result.used_fallback is True
    assert result.warning_code == IntrabarResolver.FALLBACK_WARNING_CODE


def test_intrabar_candidate_selection_skips_inert_parent_bar() -> None:
    resolver = IntrabarResolver()
    parent = _candle("2026-01-01T10:00:00", high=105.0, low=95.0, timeframe="15m")

    reasons = resolver.select_candidate_reasons(
        parent_candle=parent,
        side="BUY",
        sl_price=90.0,
        tp_price=110.0,
        entry_prices=[120.0],
    )

    assert reasons == []
    assert resolver.should_descend_to_child_timeframe(
        parent_candle=parent,
        side="BUY",
        sl_price=90.0,
        tp_price=110.0,
        entry_prices=[120.0],
    ) is False


def test_intrabar_no_collision_does_not_need_resolver_invocation() -> None:
    parent = _candle("2026-01-01T10:00:00", high=105.0, low=95.0, timeframe="1h")
    sl_hit = parent.low <= 90.0
    tp_hit = parent.high >= 110.0
    assert sl_hit is False
    assert tp_hit is False
