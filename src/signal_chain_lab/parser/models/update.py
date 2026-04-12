"""Pydantic model for UPDATE parser output.

UpdateEntities is the structured result produced by the parser when it classifies
a message as message_type="UPDATE". All fields are optional because any single
update message activates only a subset of intents.

Intent-to-field mapping:
    U_MOVE_STOP           → new_sl_level, new_sl_price, new_sl_reference
    U_MOVE_STOP_TO_BE     → (new_sl_level is None ≡ move to breakeven)
    U_CLOSE_FULL          → close_price (optional)
    U_CLOSE_PARTIAL       → close_pct, partial_close_price
    U_CANCEL_PENDING      → cancel_scope
    U_REENTER             → reenter_entries, reenter_entry_type
    U_ADD_ENTRY           → new_entry_price, new_entry_type
    U_MODIFY_ENTRY        → old_entry_price, modified_entry_price
    U_UPDATE_TAKE_PROFITS → old_take_profits, new_take_profits
    U_TP_HIT (context)    → tp_hit_number, reported_profit_r, reported_profit_pct
    U_SL_HIT (context)    → reported_profit_r, reported_profit_pct

Legacy aliases (accepted in input, mapped to canonical names by model_validator):
    new_stop_level       → new_sl_level
    new_stop_price       → new_sl_price
    new_stop_reference_text → new_sl_reference
    partial_close_percent → close_pct

Usage:
    from src.signal_chain_lab.parser.models.update import UpdateEntities
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, field_validator, model_validator

from src.signal_chain_lab.parser.models.canonical import Price
from src.signal_chain_lab.parser.models.new_signal import EntryLevel


class UpdateEntities(BaseModel):
    """All entities that can appear in an UPDATE message.

    All fields default to None / empty list. A profile sets only the fields
    relevant to the intents it detected; consumers inspect the intent list to
    know which fields are meaningful.

    Canonical fields (primary source for downstream consumers):
        new_sl_level, new_sl_price, new_sl_reference
        close_pct, partial_close_price
        cancel_scope, manual_close, stop_price, signal_id

    Legacy input aliases (auto-mapped by model_validator, do not use as output):
        new_stop_level, new_stop_price, new_stop_reference_text
        partial_close_percent
    """

    model_config = {"extra": "allow"}

    @field_validator(
        "new_sl_level",
        "new_sl_price",
        "close_price",
        "partial_close_price",
        "stop_price",
        "new_entry_price",
        "old_entry_price",
        "modified_entry_price",
        mode="before",
    )
    @classmethod
    def _coerce_float_price(cls, v: Any) -> Any:
        if isinstance(v, (int, float)):
            return {"raw": str(v), "value": float(v)}
        return v

    @model_validator(mode="before")
    @classmethod
    def _map_legacy_aliases(cls, values: Any) -> Any:
        """Map deprecated field names to canonical counterparts."""
        if not isinstance(values, dict):
            return values
        # new_stop_* → new_sl_*
        if "new_stop_level" in values and "new_sl_level" not in values:
            values["new_sl_level"] = values["new_stop_level"]
        if "new_stop_price" in values and "new_sl_price" not in values:
            values["new_sl_price"] = values["new_stop_price"]
        if "new_stop_reference_text" in values and "new_sl_reference" not in values:
            values["new_sl_reference"] = values["new_stop_reference_text"]
        # partial_close_percent → close_pct
        if "partial_close_percent" in values and "close_pct" not in values:
            values["close_pct"] = values["partial_close_percent"]
        legacy_level = values.get("new_sl_level")
        if isinstance(legacy_level, str):
            normalized_level = legacy_level.strip().upper()
            if normalized_level in {"ENTRY", "BE", "BREAKEVEN"}:
                values["new_sl_level"] = None
                values.setdefault("new_sl_reference", "ENTRY")
            elif normalized_level.startswith("TP") and normalized_level[2:].isdigit():
                values["new_sl_level"] = None
                values.setdefault("new_sl_reference", normalized_level)
        return values

    # --- Identifiers --------------------------------------------------------

    signal_id: int | None = None
    """Trader-side signal identifier, used for targeting."""

    # --- U_MOVE_STOP / U_MOVE_STOP_TO_BE ------------------------------------

    new_sl_level: Price | None = None
    """New stop-loss price. None when the intent is move-to-breakeven."""

    new_sl_price: Price | None = None
    """Concrete price for the new stop (may equal new_sl_level)."""

    new_sl_reference: str | None = None
    """Human-readable reference for the stop move (e.g. "BREAKEVEN", "TP1")."""

    # --- U_CLOSE_FULL -------------------------------------------------------

    close_price: Price | None = None
    """Price at which the position was closed, if reported."""

    # --- U_CLOSE_PARTIAL ----------------------------------------------------

    close_pct: float | None = None
    """Percentage of position to close (0–100)."""

    partial_close_price: Price | None = None
    """Price at which the partial close was executed, if reported."""

    # --- U_CANCEL_PENDING ---------------------------------------------------

    cancel_scope: str | None = None
    """Scope of pending order cancellation (e.g. "ALL_PENDING_ENTRIES")."""

    # --- Manual close / stop price ------------------------------------------

    manual_close: bool = False
    """True when the update explicitly instructs a manual position close."""

    stop_price: Price | None = None
    """Stop price as reported in an update message (audit / reporting)."""

    # --- U_REENTER ----------------------------------------------------------

    reenter_entries: list[EntryLevel] = []
    """New entry levels for re-entering the trade."""

    reenter_entry_type: Literal["MARKET", "LIMIT", "AVERAGING", "ZONE"] | None = None

    # --- U_ADD_ENTRY --------------------------------------------------------

    new_entry_price: Price | None = None
    """Price of the additional entry to add."""

    new_entry_type: Literal["MARKET", "LIMIT"] | None = None

    # --- U_MODIFY_ENTRY -----------------------------------------------------

    old_entry_price: Price | None = None
    """Existing entry price to be modified or removed."""

    modified_entry_price: Price | None = None
    """Replacement price for the modified entry. None = remove the entry."""

    # --- U_UPDATE_TAKE_PROFITS ----------------------------------------------

    old_take_profits: list[Price] | None = None
    """Previous take-profit levels being replaced. None = not reported."""

    new_take_profits: list[Price] = []
    """Replacement take-profit levels."""

    # --- Context / reporting fields (U_TP_HIT, U_SL_HIT) -------------------

    tp_hit_number: int | None = None
    """Index of the take-profit that was hit (1-based), if reported."""

    reported_profit_r: float | None = None
    """Reported profit or loss in R-multiples (positive = profit)."""

    reported_profit_pct: float | None = None
    """Reported profit or loss as a percentage (positive = profit)."""
