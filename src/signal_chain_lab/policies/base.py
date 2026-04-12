"""Base policy protocol and data model for simulation policies."""
from __future__ import annotations

import warnings
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

    @field_validator("ZONE", mode="before")
    @classmethod
    def _warn_zone_deprecated(cls, value: Any) -> Any:
        if value is not None:
            warnings.warn(
                "entry_split.ZONE is deprecated. "
                "Use entry_split.LIMIT.range for RANGE-structured entries.",
                DeprecationWarning,
                stacklevel=2,
            )
        return value

    @field_validator("AVERAGING", mode="before")
    @classmethod
    def _warn_averaging_deprecated(cls, value: Any) -> Any:
        if value is not None:
            warnings.warn(
                "entry_split.AVERAGING is deprecated. "
                "Use entry_split.LIMIT.averaging with entry_structure='TWO_STEP'.",
                DeprecationWarning,
                stacklevel=2,
            )
        return value


class TpCloseConfig(BaseModel):
    """Distribution of position size across TP levels.

    mode:
      "equal" — split uniformly across N TPs.
                The last level absorbs any floating-point remainder,
                so the sum is always exactly 1.0.
      "table" — use explicit percentages from ``table[N]``.
                If the row for N is missing or malformed,
                falls back to equal split with a warning.

    table:
      Keys are integers (number of TPs); values are lists of integers
      (percentages, not required to sum to 100 — they are normalised).
    """

    mode: str = "equal"
    table: dict[int, list[int]] = Field(default_factory=dict)


# Predefined weights used when migrating legacy tp_distribution: tp_50_30_20
_TP_50_30_20_TABLE: dict[int, list[int]] = {
    2: [50, 50],
    3: [50, 30, 20],
    4: [50, 30, 15, 5],
}


class EntryPolicy(BaseModel):
    use_original_entries: bool = True
    entry_allocation: str = "equal"
    max_entries_to_use: int | None = None
    allow_add_entry_updates: bool = True
    entry_split: EntrySplitPolicy | None = None


class TpPolicy(BaseModel):
    use_tp_count: int | None = None
    close_distribution: TpCloseConfig = Field(default_factory=TpCloseConfig)

    model_config = {"extra": "ignore"}

    @field_validator("close_distribution", mode="before")
    @classmethod
    def _coerce_close_distribution(cls, v: Any) -> Any:
        """Allow ``close_distribution: equal`` shorthand (plain string)."""
        if isinstance(v, str):
            return {"mode": v}
        return v

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_tp_distribution(cls, data: Any) -> Any:
        """Map deprecated ``tp_distribution`` field to ``close_distribution``.

        Handled legacy formats:
          tp_distribution: original / equal / follow_all_signal_tps  → equal
          tp_distribution: tp_50_30_20                               → table (predefined)
          tp_distribution: {tp_distribution: ..., tp_close_distribution: {...}}
                                                                     → table (explicit)
        """
        if not isinstance(data, dict):
            return data
        if "close_distribution" in data or "tp_distribution" not in data:
            return data

        old = data.pop("tp_distribution")
        warnings.warn(
            "tp.tp_distribution is deprecated. Use tp.close_distribution.",
            DeprecationWarning,
            stacklevel=2,
        )

        if isinstance(old, str):
            if old == "tp_50_30_20":
                data["close_distribution"] = {"mode": "table", "table": _TP_50_30_20_TABLE}
            else:
                # original / equal / follow_all_signal_tps / unknown → equal
                data["close_distribution"] = {"mode": "equal"}
        elif isinstance(old, dict):
            old_table = old.get("tp_close_distribution", {})
            if old_table:
                data["close_distribution"] = {"mode": "table", "table": old_table}
            else:
                data["close_distribution"] = {"mode": "equal"}

        return data


class SlPolicy(BaseModel):
    use_original_sl: bool = True
    be_trigger: str | None = None

    model_config = {"extra": "ignore"}

    @model_validator(mode="before")
    @classmethod
    def _migrate_break_even_mode(cls, data: Any) -> Any:
        """Remove deprecated ``break_even_mode`` field.

        Previously break_even_mode was required alongside be_trigger, but it
        was redundant: be_trigger != null already encodes the trigger condition.
        Now ignored with a deprecation warning.
        """
        if not isinstance(data, dict):
            return data
        if "break_even_mode" in data:
            data.pop("break_even_mode")
            warnings.warn(
                "sl.break_even_mode is deprecated and ignored. "
                "Use sl.be_trigger to configure break-even behaviour.",
                DeprecationWarning,
                stacklevel=2,
            )
        if "move_sl_with_trader" in data:
            data.pop("move_sl_with_trader")
            warnings.warn(
                "sl.move_sl_with_trader is deprecated and ignored. "
                "Use updates.apply_move_stop instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        return data


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
    cancel_pending_by_engine: bool = True
    cancel_averaging_pending_after: str | None = None
    cancel_unfilled_pending_after: str | None = None

    model_config = {"extra": "ignore"}

    @field_validator("cancel_pending_on_timeout", "cancel_pending_by_engine", mode="before")
    @classmethod
    def _normalize_bool_fields(cls, value: Any) -> Any:
        return _parse_bool_like(value)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_fields(cls, data: Any) -> Any:
        """Migrate deprecated bool pending fields to string references.

        Legacy → new:
          cancel_averaging_pending_after_tp1: true  →  cancel_averaging_pending_after: "tp1"
          cancel_averaging_pending_after: true       →  cancel_averaging_pending_after: "tp1"
          cancel_unfilled_if_tp1_reached_before_fill: true  →  cancel_unfilled_pending_after: "tp1"
          cancel_unfilled_if_reached_before_fill: true      →  cancel_unfilled_pending_after: "tp1"
        """
        if not isinstance(data, dict):
            return data

        migrated: list[str] = []

        # --- cancel_averaging_pending_after ---
        # Priority: new string field > old bool alias > old bool canonical
        if "cancel_averaging_pending_after" not in data or isinstance(
            data.get("cancel_averaging_pending_after"), bool
        ):
            old_bool = data.pop("cancel_averaging_pending_after", None)
            old_tp1 = data.pop("cancel_averaging_pending_after_tp1", None)
            source = old_bool if old_bool is not None else old_tp1
            if source is not None:
                migrated.append("cancel_averaging_pending_after[_tp1]")
                data["cancel_averaging_pending_after"] = "tp1" if source else None
        else:
            data.pop("cancel_averaging_pending_after_tp1", None)

        # --- cancel_unfilled_pending_after ---
        if "cancel_unfilled_pending_after" not in data:
            old_tp1 = data.pop("cancel_unfilled_if_tp1_reached_before_fill", None)
            old_alias = data.pop("cancel_unfilled_if_reached_before_fill", None)
            source = old_tp1 if old_tp1 is not None else old_alias
            if source is not None:
                migrated.append("cancel_unfilled_if_*_reached_before_fill")
                data["cancel_unfilled_pending_after"] = "tp1" if source else None
        else:
            data.pop("cancel_unfilled_if_tp1_reached_before_fill", None)
            data.pop("cancel_unfilled_if_reached_before_fill", None)

        if migrated:
            warnings.warn(
                f"pending: legacy fields {migrated} auto-migrated. "
                "Use cancel_averaging_pending_after and cancel_unfilled_pending_after.",
                DeprecationWarning,
                stacklevel=2,
            )

        return data


class RiskPolicy(BaseModel):
    # "none"   → simulatore gira, metriche R/PnL% assenti nel report
    # "fixed"  → usa sempre risk_pct, ignora risk_percent dal segnale
    # "signal" → usa risk_percent dal segnale se presente, fallback a risk_pct
    mode: str = "none"

    # % del capitale rischiato per trade (usato con mode: fixed o come fallback per mode: signal)
    risk_pct: float | None = None

    # % usato quando il segnale porta solo un hint qualitativo (U_RISK_NOTE senza valore numerico)
    # es. "small risk", "очень аккуратно" → usa questa % invece di risk_pct
    reduced_risk_pct: float | None = None

    model_config = {"extra": "ignore"}

    @model_validator(mode="after")
    def _validate_risk_pct_required(self) -> RiskPolicy:
        if self.mode in {"fixed", "signal"} and self.risk_pct is None:
            raise ValueError(
                f"risk.risk_pct is required when risk.mode='{self.mode}'"
            )
        return self


class ExecutionPolicy(BaseModel):
    latency_ms: int = 0
    slippage_model: str = "none"
    slippage_bps: float = 0.0
    fill_touch_guaranteed: bool = True
    fee_model: str = "none"
    fee_bps: float = 0.0


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
