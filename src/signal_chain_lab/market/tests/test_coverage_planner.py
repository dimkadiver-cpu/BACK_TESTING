from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.signal_chain_lab.market.planning.coverage_planner import CoveragePlanner, ManualBuffer
from src.signal_chain_lab.market.planning.demand_scanner import DemandChain
from src.signal_chain_lab.market.runtime_config import runtime_config_from_state
from src.signal_chain_lab.ui.state import MarketState


def _dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def test_coverage_planner_manual_buffer_emits_execution_chart_and_download_windows() -> None:
    chain = DemandChain(
        chain_id="chain-1",
        symbol="BTCUSDT",
        timestamp_open=_dt(2026, 4, 10, 9, 0),
        timestamp_last_relevant_update=_dt(2026, 4, 12, 15, 30),
        chain_status="CLOSED",
    )
    planner = CoveragePlanner(now_provider=lambda: _dt(2026, 4, 20))

    plan = planner.plan([chain], manual_buffer=ManualBuffer(pre_days=7, post_days=3, preset="swing"))
    symbol_windows = plan.windows_by_symbol["BTCUSDT"]

    assert len(symbol_windows.execution_window) == 1
    assert len(symbol_windows.chart_window) == 1
    assert len(symbol_windows.download_window) == 1

    execution = symbol_windows.execution_window[0]
    chart = symbol_windows.chart_window[0]
    download = symbol_windows.download_window[0]

    assert execution.start == _dt(2026, 4, 10, 9, 0)
    assert execution.end == _dt(2026, 4, 12, 15, 30)
    assert chart.start == _dt(2026, 4, 3, 9, 0)
    assert chart.end == _dt(2026, 4, 15, 15, 30)
    assert download.start == chart.start
    assert download.end == chart.end

    serialized = plan.to_dict()["BTCUSDT"]
    assert serialized["required_intervals"] == serialized["download_window"]
    assert serialized["requested_timeframes"] == []


def test_coverage_planner_auto_buffer_keeps_execution_inside_chart_and_download() -> None:
    chain = DemandChain(
        chain_id="chain-2",
        symbol="ETHUSDT",
        timestamp_open=_dt(2026, 4, 10, 8, 0),
        timestamp_last_relevant_update=_dt(2026, 4, 10, 12, 0),
        chain_status="ACTIVE",
    )
    planner = CoveragePlanner(now_provider=lambda: _dt(2026, 4, 30))

    plan = planner.plan([chain])
    symbol_windows = plan.windows_by_symbol["ETHUSDT"]
    execution = symbol_windows.execution_window[0]
    chart = symbol_windows.chart_window[0]
    download = symbol_windows.download_window[0]

    assert chart.start <= execution.start <= execution.end <= chart.end
    assert download.start <= execution.start <= execution.end <= download.end
    assert download.start == chart.start
    assert download.end == chart.end
    assert chart.start == chain.timestamp_open - timedelta(hours=24)
    assert chart.end == chain.timestamp_last_relevant_update + timedelta(days=3)


def test_runtime_config_from_state_maps_market_state_fields() -> None:
    state = MarketState(
        download_tf="15m",
        simulation_tf="15m",
        detail_tf="1m",
        price_basis="mark",
        market_data_source="fixture",
        buffer_mode="manual",
        pre_buffer_days=7,
        post_buffer_days=3,
    )

    config = runtime_config_from_state(state)

    assert config.download_tf == "15m"
    assert config.simulation_tf == "15m"
    assert config.detail_tf == "1m"
    assert config.price_basis == "mark"
    assert config.source == "fixture"
    assert config.buffer_mode == "manual"
    assert config.pre_buffer_days == 7
    assert config.post_buffer_days == 3


def test_coverage_planner_emits_download_windows_for_parent_and_child_timeframes() -> None:
    chain = DemandChain(
        chain_id="chain-3",
        symbol="SOLUSDT",
        timestamp_open=_dt(2026, 4, 10, 8, 0),
        timestamp_last_relevant_update=_dt(2026, 4, 10, 12, 0),
        chain_status="ACTIVE",
    )

    plan = CoveragePlanner(now_provider=lambda: _dt(2026, 4, 30)).plan(
        [chain],
        timeframes=["15m", "1m", "15m"],
    )

    serialized = plan.to_dict()["SOLUSDT"]
    assert serialized["requested_timeframes"] == ["15m", "1m"]
    assert set(serialized["download_windows_by_timeframe"].keys()) == {"15m", "1m"}
    assert serialized["download_windows_by_timeframe"]["15m"] == serialized["download_window"]
    assert serialized["download_windows_by_timeframe"]["1m"] == serialized["download_window"]
