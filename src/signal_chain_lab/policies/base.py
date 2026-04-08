"""Base policy protocol and data model for simulation policies."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


def _strip_inline_note(value: Any) -> Any:
    """Allow temporary YAML values like ``false // tp1-tp2`` during transition."""
    if not isinstance(value, str):
        return value
    return value.split("//", 1)[0].strip()


def _parse_bool_like(value: Any) -> bool | Any:
    normalized = _strip_inline_note(value)
    if isinstance(normalized, bool):
        return normalized
    if isinstance(normalized, str):
        lowered = normalized.lower()
        if lowered in {"true", "yes", "on"}:
            return True
        if lowered in {"false", "no", "off"}:
            return False
    return value


class WeightedEntries(BaseModel):
    weights: dict[str, float] = Field(default_factory=dict)


class AveragingEntries(BaseModel):
    distribution: str | None = None
    weights: dict[str, float] = Field(default_factory=dict)


class ZoneEntrySplit(BaseModel):
    split_mode: str = "endpoints"
    weights: dict[str, float] = Field(default_factory=dict)


class RangeEntrySplit(BaseModel):
    split_mode: str = "endpoints"
    weights: dict[str, float] = Field(default_factory=dict)


class OrderTypeEntrySplit(BaseModel):
    single: WeightedEntries = Field(default_factory=WeightedEntries)
    averaging: WeightedEntries = Field(default_factory=WeightedEntries)
    range: RangeEntrySplit | None = None
    ladder: WeightedEntries = Field(default_factory=WeightedEntries)


class EntrySplitPolicy(BaseModel):
    ZONE: ZoneEntrySplit | None = None
    LIMIT: OrderTypeEntrySplit | None = None
    MARKET: OrderTypeEntrySplit | None = None
    AVERAGING: AveragingEntries | None = None


class TpDistributionConfig(BaseModel):
    mode: str = Field(default="follow_all_signal_tps", alias="tp_distribution")
    max_tp_levels: int | None = None
    tp_close_distribution: dict[int, list[int]] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class EntryPolicy(BaseModel):
    use_original_entries: bool = True
    entry_allocation: str = "equal"
    max_entries_to_use: int | None = None
    allow_add_entry_updates: bool = True
    entry_split: EntrySplitPolicy | None = None


class TpPolicy(BaseModel):
    use_original_tp: bool = True
    use_tp_count: int | None = None
    tp_distribution: str | TpDistributionConfig = "original"


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
    cancel_unfilled_if_reached_before_fill: bool | None = None
    cancel_averaging_pending_after: bool | None = None

    @field_validator(
        "cancel_pending_on_timeout",
        "cancel_unfilled_if_tp1_reached_before_fill",
        "cancel_averaging_pending_after_tp1",
        "cancel_unfilled_if_reached_before_fill",
        "cancel_averaging_pending_after",
        mode="before",
    )
    @classmethod
    def _normalize_bool_fields(cls, value: Any) -> Any:
        return _parse_bool_like(value)

    @model_validator(mode="after")
    def _sync_alias_fields(self) -> PendingPolicy:
        if self.cancel_unfilled_if_reached_before_fill is not None:
            self.cancel_unfilled_if_tp1_reached_before_fill = self.cancel_unfilled_if_reached_before_fill
        else:
            self.cancel_unfilled_if_reached_before_fill = self.cancel_unfilled_if_tp1_reached_before_fill

        if self.cancel_averaging_pending_after is not None:
            self.cancel_averaging_pending_after_tp1 = self.cancel_averaging_pending_after
        else:
            self.cancel_averaging_pending_after = self.cancel_averaging_pending_after_tp1
        return self


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
