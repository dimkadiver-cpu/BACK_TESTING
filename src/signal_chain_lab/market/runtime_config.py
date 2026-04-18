"""Runtime configuration for market-data planning and simulation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.signal_chain_lab.ui.state import MarketState


@dataclass(frozen=True, slots=True)
class MarketRuntimeConfig:
    download_tf: str
    simulation_tf: str
    detail_tf: str
    price_basis: str
    source: str
    buffer_mode: str
    pre_buffer_days: int
    post_buffer_days: int


def runtime_config_from_state(market_state: "MarketState") -> MarketRuntimeConfig:
    return MarketRuntimeConfig(
        download_tf=(market_state.download_tf or "1m").strip() or "1m",
        simulation_tf=(market_state.simulation_tf or market_state.download_tf or "1m").strip() or "1m",
        detail_tf=(market_state.detail_tf or market_state.download_tf or "1m").strip() or "1m",
        price_basis=(market_state.price_basis or "last").strip() or "last",
        source=(market_state.market_data_source or "bybit").strip() or "bybit",
        buffer_mode=(market_state.buffer_mode or "auto").strip() or "auto",
        pre_buffer_days=max(0, int(market_state.pre_buffer_days or 0)),
        post_buffer_days=max(0, int(market_state.post_buffer_days or 0)),
    )
