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

    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    fees_paid: float = 0.0

    mae: float | None = None
    mfe: float | None = None
    warnings_count: int = 0
    ignored_events_count: int = 0


class ScenarioResult(BaseModel):
    policy_name: str
    total_pnl: float = 0.0
    return_pct: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    trades_count: int = 0
    simulated_chains_count: int = 0
    excluded_chains_count: int = 0
    avg_warnings_per_trade: float = 0.0


class ScenarioComparison(BaseModel):
    base_policy_name: str
    target_policy_name: str
    delta_pnl: float = 0.0
    delta_drawdown: float = 0.0
    delta_win_rate: float = 0.0
    delta_expectancy: float = 0.0
