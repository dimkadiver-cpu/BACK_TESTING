"""Domain models for the chain adapter layer: ChainedMessage and SignalChain."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.signal_chain_lab.parser.models.new_signal import NewSignalEntities
from src.signal_chain_lab.parser.models.update import UpdateEntities


class ChainedMessage(BaseModel):
    """A single message (NEW_SIGNAL or UPDATE) in a signal chain."""

    raw_message_id: int
    parse_result_id: int
    telegram_message_id: int
    message_ts: datetime
    message_type: Literal["NEW_SIGNAL", "UPDATE"]
    intents: list[str] = Field(default_factory=list)
    entities: NewSignalEntities | UpdateEntities | None = None

    op_signal_id: int | None = None
    attempt_key: str | None = None
    is_blocked: bool = False
    block_reason: str | None = None
    risk_budget_usdt: float | None = None
    position_size_usdt: float | None = None
    entry_split: dict[str, float] | None = None
    management_rules: dict | None = None


class SignalChain(BaseModel):
    """A reconstructed signal chain: one NEW_SIGNAL with all linked UPDATEs."""

    chain_id: str
    trader_id: str | None = None
    symbol: str
    side: str
    new_signal: ChainedMessage
    updates: list[ChainedMessage] = Field(default_factory=list)
    entry_prices: list[float] = Field(default_factory=list)
    sl_price: float = 0.0
    tp_prices: list[float] = Field(default_factory=list)
    open_ts: datetime
    close_ts: datetime | None = None
