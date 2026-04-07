"""Trade state machine data model."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.signal_chain_lab.domain.enums import ChainInputMode, CloseReason, TradeStatus


class EntryPlan(BaseModel):
    role: Literal["primary", "averaging"]
    order_type: Literal["market", "limit", "unknown"]
    price: float | None = None
    size_ratio: float
    label: str | None = None
    sequence: int | None = None


class FillRecord(BaseModel):
    price: float
    qty: float
    timestamp: datetime
    source_event_sequence: int | None = None
    fee_paid: float = 0.0


class TradeState(BaseModel):
    signal_id: str
    trader_id: str | None = None
    symbol: str
    side: str
    status: TradeStatus

    input_mode: ChainInputMode
    policy_name: str

    entries_planned: list[EntryPlan] = Field(default_factory=list)
    fills: list[FillRecord] = Field(default_factory=list)

    pending_size: float = 0.0
    open_size: float = 0.0
    avg_entry_price: float | None = None
    max_position_size: float = 0.0

    initial_sl: float | None = None
    current_sl: float | None = None
    tp_levels: list[float] = Field(default_factory=list)
    next_tp_index: int = 0

    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    fees_paid: float = 0.0

    warnings_count: int = 0
    ignored_events_count: int = 0

    close_reason: CloseReason | None = None
    terminal_reason: str | None = None

    created_at: datetime | None = None
    first_fill_at: datetime | None = None
    closed_at: datetime | None = None
