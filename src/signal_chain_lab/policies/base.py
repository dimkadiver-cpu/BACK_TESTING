"""Base policy protocol and data model for simulation policies."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EntryPolicy(BaseModel):
    use_original_entries: bool = True
    entry_allocation: str = "equal"
    max_entries_to_use: int | None = None
    allow_add_entry_updates: bool = True


class TpPolicy(BaseModel):
    use_original_tp: bool = True
    use_tp_count: int | None = None
    tp_distribution: str = "original"


class SlPolicy(BaseModel):
    use_original_sl: bool = True
    break_even_mode: str = "none"
    be_trigger: str | None = None
    move_sl_with_trader: bool = True


class UpdatesPolicy(BaseModel):
    apply_move_stop: bool = True
    apply_close_partial: bool = True
    apply_close_full: bool = True
    apply_cancel_pending: bool = True
    apply_add_entry: bool = True
    partial_close_fallback_pct: float = 0.5


class PendingPolicy(BaseModel):
    pending_timeout_hours: float = 24.0
    chain_timeout_hours: float = 168.0
    cancel_pending_on_timeout: bool = True
    cancel_unfilled_if_tp1_reached_before_fill: bool = False
    cancel_averaging_pending_after_tp1: bool = False


class RiskPolicy(BaseModel):
    pass


class ExecutionPolicy(BaseModel):
    latency_ms: int = 0
    slippage_model: str = "none"
    fill_touch_guaranteed: bool = True


class PolicyConfig(BaseModel):
    name: str
    entry: EntryPolicy = Field(default_factory=EntryPolicy)
    tp: TpPolicy = Field(default_factory=TpPolicy)
    sl: SlPolicy = Field(default_factory=SlPolicy)
    updates: UpdatesPolicy = Field(default_factory=UpdatesPolicy)
    pending: PendingPolicy = Field(default_factory=PendingPolicy)
    risk: RiskPolicy = Field(default_factory=RiskPolicy)
    execution: ExecutionPolicy = Field(default_factory=ExecutionPolicy)

    model_config = {"extra": "allow"}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyConfig:
        """Build a PolicyConfig from a raw dict (e.g. loaded from YAML)."""
        return cls.model_validate(data)
