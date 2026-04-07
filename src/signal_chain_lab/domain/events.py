"""Domain events emitted during signal chain simulation."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.signal_chain_lab.domain.enums import ChainInputMode, EventSource, EventType


class CanonicalEvent(BaseModel):
    signal_id: str
    trader_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    timestamp: datetime
    event_type: EventType
    source: EventSource
    payload: dict[str, Any] = Field(default_factory=dict)
    sequence: int

    source_event_type: str | None = None
    source_record_id: str | None = None


class CanonicalChain(BaseModel):
    signal_id: str
    trader_id: str | None = None
    symbol: str
    side: str
    input_mode: ChainInputMode
    has_updates_in_dataset: bool
    created_at: datetime
    events: list[CanonicalEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
