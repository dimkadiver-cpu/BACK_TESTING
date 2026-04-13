"""Simulation result aggregation models."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.signal_chain_lab.domain.enums import ChainInputMode, EventProcessingStatus


class EventLogEntry(BaseModel):
    timestamp: datetime
    signal_id: str
    event_type: str
    source: str

    requested_action: str | None = None
    executed_action: str | None = None
    processing_status: EventProcessingStatus

    price_reference: float | None = None
    reason: str | None = None

    raw_text: str | None = None

    state_before: dict[str, Any] = Field(default_factory=dict)
    state_after: dict[str, Any] = Field(default_factory=dict)


class TradeResult(BaseModel):
    signal_id: str
    trader_id: str | None = None
    symbol: str
    side: str
    status: str
    input_mode: ChainInputMode
    policy_name: str
    close_reason: str | None = None

    created_at: datetime | None = None
    first_fill_at: datetime | None = None
    closed_at: datetime | None = None
    duration_seconds: float | None = None

    entries_count: int = 0
    avg_entry_price: float | None = None
    max_position_size: float = 0.0
    final_position_size: float = 0.0

    # --- raw PnL (internal / debug) ---
    realized_pnl: float = 0.0        # price_delta - close_fees (engine internal value)
    unrealized_pnl: float = 0.0
    fees_paid: float = 0.0           # DEPRECATED alias → use fees_total_raw

    # --- new canonical raw metrics ---
    invested_notional: float | None = None          # Σ(fill_price * fill_qty)
    pnl_gross_raw: float | None = None              # pure price delta (no fees, no funding)
    pnl_net_raw: float | None = None                # price delta - all fees + funding
    fees_total_raw: float = 0.0                     # total fees paid (entry + close)
    funding_total_raw_net: float = 0.0              # net funding (positive = received)

    # --- primary % metrics (normalized on invested_notional, always available) ---
    trade_return_pct_gross: float | None = None     # pnl_gross_raw / invested_notional * 100
    trade_return_pct_net: float | None = None       # pnl_net_raw  / invested_notional * 100
    cost_drag_pct: float | None = None              # gross - net (always >= 0 when funding=0)

    # --- quality metrics ---
    initial_r_pct: float | None = None              # |entry - initial_sl| / entry * 100
    r_multiple: float | None = None                 # trade_return_pct_net / initial_r_pct

    mae: float | None = None
    mfe: float | None = None

    # --- % metrics ---
    trade_impact_pct: float | None = None           # DEPRECATED: pnl / initial_capital * 100
    cum_equity_after_trade_pct: float | None = None # cumulative net return % (chronological)
    mae_pct: float | None = None                    # mae / invested_notional * 100
    mfe_pct: float | None = None                    # mfe / invested_notional * 100
    capture_ratio_pct: float | None = None          # pnl_net_raw / mfe * 100

    # --- execution detail ---
    time_to_fill_seconds: float | None = None
    bars_in_trade: int | None = None
    first_fill_price: float | None = None
    final_exit_price: float | None = None
    updates_applied_count: int = 0
    fills_count: int = 0
    partial_closes_count: int = 0

    warnings_count: int = 0
    ignored_events_count: int = 0


class ScenarioResult(BaseModel):
    policy_name: str
    # --- net primary metrics ---
    win_rate_net: float = 0.0
    avg_trade_return_pct_net: float = 0.0
    expectancy_pct_net: float = 0.0
    profit_factor_net: float = 0.0
    avg_r_multiple: float | None = None
    # --- raw aggregates (debug/internal) ---
    total_pnl_raw: float = 0.0
    gross_profit_raw: float = 0.0
    gross_loss_raw: float = 0.0
    max_drawdown: float = 0.0
    trades_count: int = 0
    simulated_chains_count: int = 0
    excluded_chains_count: int = 0
    avg_warnings_per_trade: float = 0.0
    # Run-level metadata (same for all policies in a run)
    price_basis: str = "last"       # "last" | "mark"
    exchange_faithful: bool = True  # True = Bybit official run; False = comparative

    # ── Backward-compatibility aliases (deprecated) ───────────────────────────
    # These map to the new canonical fields so downstream code keeps working.
    @property
    def total_pnl(self) -> float:
        return self.total_pnl_raw

    @property
    def return_pct(self) -> float:
        return self.avg_trade_return_pct_net

    @property
    def win_rate(self) -> float:
        return self.win_rate_net

    @property
    def profit_factor(self) -> float:
        return self.profit_factor_net

    @property
    def expectancy(self) -> float:
        return self.expectancy_pct_net


class ScenarioComparison(BaseModel):
    base_policy_name: str
    target_policy_name: str
    delta_pnl: float = 0.0
    delta_drawdown: float = 0.0
    delta_win_rate: float = 0.0
    delta_expectancy: float = 0.0
