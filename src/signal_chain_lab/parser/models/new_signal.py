"""Pydantic models for NEW_SIGNAL parser output.

NewSignalEntities is the structured result produced by the parser when it
classifies a message as message_type="NEW_SIGNAL".

Usage:
    from src.signal_chain_lab.parser.models.new_signal import (
        EntryLevel,
        StopLoss,
        TakeProfit,
        NewSignalEntities,
        compute_completeness,
    )
"""

from __future__ import annotations

import re
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.signal_chain_lab.parser.models.canonical import Price


_SYMBOL_SUFFIX_RE = re.compile(r"(?:[._-]?P(?:ERP)?)$", re.IGNORECASE)


def normalize_symbol_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.upper().strip()
    normalized = _SYMBOL_SUFFIX_RE.sub("", normalized)
    return normalized


# ---------------------------------------------------------------------------
# Component models
# ---------------------------------------------------------------------------

class EntryLevel(BaseModel):
    """A single entry price point with order type.

    price is None for MARKET entries that have no fixed target price (e.g. "enter
    at market"). For LIMIT entries price is always set.

    Accepts price as a float or int for convenience — converts to Price automatically.
    """

    model_config = ConfigDict(extra="allow")

    price: Price | None = None
    order_type: Literal["MARKET", "LIMIT"] = "LIMIT"
    note: str | None = None
    """Free-text note from the original message, e.g. "from current price"."""

    @field_validator("price", mode="before")
    @classmethod
    def _coerce_float_price(cls, v: Any) -> Any:
        """Accept a plain float/int and convert to the Price dict form."""
        if isinstance(v, (int, float)):
            return {"raw": str(v), "value": float(v)}
        return v


class StopLoss(BaseModel):
    """A stop-loss level.

    Thin wrapper around Price that allows future extension (trailing stops,
    conditional stops, etc.) without changing the NewSignalEntities interface.
    """

    model_config = ConfigDict(frozen=True)

    price: Price
    trailing: bool = False
    condition: str | None = None
    """Free-text stop condition extracted from the message, if any."""

    @field_validator("price", mode="before")
    @classmethod
    def _coerce_float_price(cls, v: Any) -> Any:
        if isinstance(v, (int, float)):
            return {"raw": str(v), "value": float(v)}
        return v


class TakeProfit(BaseModel):
    """A take-profit level with optional label and partial-close percentage.

    label is the TP identifier as it appeared in the message (e.g. "TP1", "TP2").
    close_pct is the percentage of the position to close at this TP, if specified.
    """

    model_config = ConfigDict(frozen=True)

    price: Price
    label: str | None = None
    close_pct: float | None = None

    @field_validator("price", mode="before")
    @classmethod
    def _coerce_float_price(cls, v: Any) -> Any:
        if isinstance(v, (int, float)):
            return {"raw": str(v), "value": float(v)}
        return v


# ---------------------------------------------------------------------------
# NewSignalEntities
# ---------------------------------------------------------------------------

class NewSignalEntities(BaseModel):
    """All entities extracted from a NEW_SIGNAL message.

    Required fields for completeness=COMPLETE:
        symbol, direction, entry_type, stop_loss, take_profits (≥ 1)
        entry_plan_entries is required when entry_type is LIMIT.

    All fields default to None / empty list so that INCOMPLETE signals can be
    represented and stored for later review.

    Canonical fields (use as primary source for downstream consumers):
        symbol, direction, entry_type, entry_structure, entry_plan_entries,
        stop_loss, take_profits, risk_percent

    Legacy/alias fields (accepted for backward compatibility, do not use as
    primary source in new code):
        entries  → replaced by entry_plan_entries
        risk_pct → replaced by risk_percent
    """

    model_config = ConfigDict(extra="allow")

    # --- Core signal fields -------------------------------------------------

    signal_id: int | None = None
    """Trader-side signal identifier, if present in the message."""

    symbol: str | None = None
    """Normalised trading pair symbol, e.g. "BTCUSDT". Always uppercase."""

    symbol_raw: str | None = None
    """Raw symbol string as it appeared in the message, before normalisation."""

    direction: Literal["LONG", "SHORT"] | None = None
    """Canonical trade direction. Use this; do not use `side`."""

    entry_type: Literal["MARKET", "LIMIT", "AVERAGING", "ZONE"] | None = None
    """
    Canonical values:
      MARKET — market entry; entry_plan_entries may be empty or hold indicative price.
      LIMIT  — limit entry; entry_plan_entries has ≥ 1 price.
    Deprecated (handled by normalize_entry_semantics in state_machine):
      AVERAGING — use LIMIT + entry_structure=TWO_STEP|LADDER
      ZONE      — use LIMIT + entry_structure=RANGE
    """

    entry_structure: Literal["ONE_SHOT", "TWO_STEP", "RANGE", "LADDER"] | None = None
    """Canonical entry plan shape. Primary field for routing entry logic."""

    entry_order_type: str | None = None
    """Raw order-type string extracted from the message (audit/metadata)."""

    entry_plan_type: str | None = None
    """Metadata label describing the entry plan shape (audit only, not dispatch)."""

    has_averaging_plan: bool = False
    """True when the signal includes ≥ 2 distinct limit entry levels."""

    entry_plan_entries: list[EntryLevel] = []
    """Canonical entry levels. Primary source for CREATE_SIGNAL and chain builder."""

    entries: list[EntryLevel] = []
    """Legacy alias for entry_plan_entries. Kept for backward compatibility."""

    entry_range: list[float] = []
    """Two-element [low, high] list for RANGE entries. Canonical complement to entry_plan_entries."""

    stop_loss: StopLoss | None = None
    """Stop-loss level. Required for completeness=COMPLETE."""

    take_profits: list[TakeProfit] = []
    """Take-profit levels. At least one required for completeness=COMPLETE."""

    # --- Risk and leverage --------------------------------------------------

    risk_percent: float | None = None
    """Canonical risk field (% of account). Use this; do not use `risk_pct`."""

    risk_pct: float | None = None
    """Deprecated alias for risk_percent. Populated by legacy parsers only."""

    risk_value_raw: str | None = None
    """Raw risk string as extracted from the message (audit)."""

    risk_value_normalized: float | None = None
    """Normalised risk value, may differ from risk_percent in unit/scale (audit)."""

    leverage: float | None = None
    leverage_hint_raw: str | None = None
    """Raw leverage hint string from the message (audit)."""

    reported_leverage_hint: float | None = None
    """Parsed leverage hint value (audit)."""

    # --- Raw text capture (audit / debugging) -------------------------------

    entry_text_raw: str | None = None
    stop_loss_raw: str | None = None
    targets_text_raw: str | None = None
    take_profits_text_raw: str | None = None
    market_context: str | None = None

    # --- Misc ---------------------------------------------------------------

    conditions: str | None = None
    """Free-text entry conditions not otherwise parsed, e.g. "wait for confirmation"."""

    warnings: list[str] = []
    """Warnings produced during validation. Caller should merge into TraderParseResult.warnings."""

    @field_validator("symbol", mode="before")
    @classmethod
    def _normalise_symbol(cls, v: str | None) -> str | None:
        return normalize_symbol_value(v)

    @field_validator("stop_loss", mode="before")
    @classmethod
    def _coerce_legacy_stop_loss(cls, v: Any) -> Any:
        if isinstance(v, (int, float)):
            return {"price": {"raw": str(v), "value": float(v)}}
        return v

    @field_validator("take_profits", mode="before")
    @classmethod
    def _coerce_legacy_take_profits(cls, v: Any) -> Any:
        if isinstance(v, list):
            coerced: list[Any] = []
            for idx, item in enumerate(v, start=1):
                if isinstance(item, (int, float)):
                    coerced.append(
                        {"price": {"raw": str(item), "value": float(item)}, "label": f"TP{idx}"}
                    )
                else:
                    coerced.append(item)
            return coerced
        return v

    @model_validator(mode="before")
    @classmethod
    def _map_legacy_aliases(cls, values: Any) -> Any:
        """Map deprecated field names to their canonical counterparts."""
        if not isinstance(values, dict):
            return values
        if values.get("entry_structure") == "SINGLE":
            values["entry_structure"] = "ONE_SHOT"
        if "side" in values and "direction" not in values:
            values["direction"] = values["side"]
        # risk_pct → risk_percent
        if "risk_pct" in values and "risk_percent" not in values:
            values["risk_percent"] = values["risk_pct"]
        return values

    @model_validator(mode="after")
    def check_entry_magnitude_consistency(self) -> Self:
        """Se ci sono 2+ entry_plan_entries, il rapporto max/min non deve superare 3x.

        Non blocca il parsing. Aggiunge un warning alla lista warnings del modello.
        Solo entry_plan_entries — non tocca TP e SL.
        """
        active_entries = self.entry_plan_entries or self.entries
        if len(active_entries) < 2:
            return self
        prices = [e.price.value for e in active_entries if e.price is not None]
        if len(prices) < 2:
            return self
        ratio = max(prices) / min(prices)
        if ratio > 3.0:
            self.warnings.append(
                f"entry_magnitude_inconsistent: ratio={ratio:.1f}"
            )
        return self


# ---------------------------------------------------------------------------
# Completeness helper
# ---------------------------------------------------------------------------

def compute_completeness(
    entities: NewSignalEntities,
) -> tuple[Literal["COMPLETE", "INCOMPLETE"], list[str]]:
    """Determine the completeness of a NewSignalEntities instance.

    Returns:
        A 2-tuple of (completeness, missing_fields) where completeness is
        "COMPLETE" or "INCOMPLETE" and missing_fields lists the names of the
        required fields that are absent.
    """
    missing: list[str] = []

    if entities.symbol is None:
        missing.append("symbol")
    if entities.direction is None:
        missing.append("direction")
    if entities.entry_type is None:
        missing.append("entry_type")
    elif entities.entry_type == "LIMIT":
        # Canonical check: entry_plan_entries preferred; fall back to legacy entries
        if not entities.entry_plan_entries and not entities.entries:
            missing.append("entry_plan_entries")
    elif entities.entry_type in {"AVERAGING", "ZONE"}:
        # Legacy types: accept either entries or entry_plan_entries
        if not entities.entry_plan_entries and not entities.entries:
            missing.append("entry_plan_entries")
    if entities.stop_loss is None:
        missing.append("stop_loss")
    if not entities.take_profits:
        missing.append("take_profits")

    completeness: Literal["COMPLETE", "INCOMPLETE"] = (
        "COMPLETE" if not missing else "INCOMPLETE"
    )
    return completeness, missing
