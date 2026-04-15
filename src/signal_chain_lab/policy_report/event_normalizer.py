"""Canonical event normalizer for policy report system.

Converts EventLogEntry records (domain/results.py) into ReportCanonicalEvent
objects used by chart, event rail, sidebar and audit drawer (PRD-B §14).

This module is the single source of truth for the phase/class/subtype mapping
used throughout the 3-level report system.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult


# ---------------------------------------------------------------------------
# Constants — canonical subtype values (PRD-B §15)
# ---------------------------------------------------------------------------

class Subtype:
    SIGNAL_CREATED = "SIGNAL_CREATED"
    ENTRY_PLANNED = "ENTRY_PLANNED"
    ENTRY_FILLED = "ENTRY_FILLED"
    SCALE_IN_FILLED = "SCALE_IN_FILLED"
    MARKET_ENTRY_FILLED = "MARKET_ENTRY_FILLED"
    SL_SET = "SL_SET"
    SL_MOVED = "SL_MOVED"
    BE_ACTIVATED = "BE_ACTIVATED"
    TP_ARMED = "TP_ARMED"
    TP_HIT = "TP_HIT"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    FINAL_EXIT = "FINAL_EXIT"
    SL_HIT = "SL_HIT"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    TIMEOUT = "TIMEOUT"
    IGNORED = "IGNORED"
    SYSTEM_NOTE = "SYSTEM_NOTE"


class Phase:
    SETUP = "SETUP"
    ENTRY = "ENTRY"
    MANAGEMENT = "MANAGEMENT"
    EXIT = "EXIT"
    POST_MORTEM = "POST_MORTEM"


class EventClass:
    STRUCTURAL = "STRUCTURAL"
    MANAGEMENT = "MANAGEMENT"
    RESULT = "RESULT"
    AUDIT = "AUDIT"


# ---------------------------------------------------------------------------
# Reporting canonical event dataclass (PRD-B §14)
# ---------------------------------------------------------------------------

@dataclass
class ImpactData:
    """Position-level snapshot after the event."""
    position: float | None = None   # open_size after event
    risk: float | None = None       # current_sl after event
    result: float | None = None     # realized_pnl (raw) after event


@dataclass
class ReportCanonicalEvent:
    """Canonical event representation for all report components.

    Used by: price chart, event rail, sidebar lista eventi, audit drawer.
    """
    id: str                         # "{signal_id}_{idx}"
    ts: str                         # ISO datetime string
    phase: str                      # Phase.*
    event_class: str                # EventClass.*  (field: event_class to avoid reserved 'class')
    subtype: str                    # Subtype.*
    title: str                      # human-readable label
    price_anchor: float | None      # price reference for chart alignment
    source: str                     # "TRADER" | "ENGINE" | "SYSTEM"
    impact: ImpactData
    summary: str                    # short one-liner for sidebar collapsed view
    raw_text: str | None            # original Telegram text (only TRADER source)
    details: dict[str, Any] = field(default_factory=dict)  # full state_after + extras


# ---------------------------------------------------------------------------
# Mapping tables
# ---------------------------------------------------------------------------

# (event_type, processing_status, reason_keyword) → (subtype, phase, event_class)
#
# The mapping is evaluated top-down with priority:
#   1. processing_status ignored/rejected → always IGNORED
#   2. event_type exact match with reason refinement for ambiguous cases
#   3. fallback → SYSTEM_NOTE

_CLOSE_FULL_REASON_MAP: list[tuple[str, tuple[str, str, str]]] = [
    # reason keyword (lowercase, substring match) → (subtype, phase, class)
    ("sl_hit",          (Subtype.SL_HIT,     Phase.EXIT, EventClass.RESULT)),
    ("stop_hit",        (Subtype.SL_HIT,     Phase.EXIT, EventClass.RESULT)),
    ("sl_reached",      (Subtype.SL_HIT,     Phase.EXIT, EventClass.RESULT)),
    ("tp_hit",          (Subtype.FINAL_EXIT, Phase.EXIT, EventClass.RESULT)),
    ("tp_reached",      (Subtype.FINAL_EXIT, Phase.EXIT, EventClass.RESULT)),
    ("tp",              (Subtype.FINAL_EXIT, Phase.EXIT, EventClass.RESULT)),
    ("chain_timeout",   (Subtype.TIMEOUT,    Phase.EXIT, EventClass.RESULT)),
    ("timeout",         (Subtype.TIMEOUT,    Phase.EXIT, EventClass.RESULT)),
    ("expired",         (Subtype.EXPIRED,    Phase.EXIT, EventClass.RESULT)),
    ("manual",          (Subtype.FINAL_EXIT, Phase.EXIT, EventClass.RESULT)),
]

_CANCEL_PENDING_REASON_MAP: list[tuple[str, tuple[str, str, str]]] = [
    ("pending_timeout", (Subtype.TIMEOUT,   Phase.EXIT, EventClass.RESULT)),
    ("timeout",         (Subtype.TIMEOUT,   Phase.EXIT, EventClass.RESULT)),
    ("expired",         (Subtype.EXPIRED,   Phase.EXIT, EventClass.RESULT)),
    # tp/sl reached before fill → cancel with result context
    ("tp",              (Subtype.CANCELLED, Phase.EXIT, EventClass.RESULT)),
    ("sl",              (Subtype.CANCELLED, Phase.EXIT, EventClass.RESULT)),
]

# Human-readable titles for each subtype
_SUBTYPE_TITLE: dict[str, str] = {
    Subtype.SIGNAL_CREATED:     "Signal created",
    Subtype.ENTRY_PLANNED:      "Entry planned",
    Subtype.ENTRY_FILLED:       "Entry filled",
    Subtype.SCALE_IN_FILLED:    "Scale-in filled",
    Subtype.MARKET_ENTRY_FILLED:"Market entry filled",
    Subtype.SL_SET:             "Stop loss set",
    Subtype.SL_MOVED:           "Stop loss moved",
    Subtype.BE_ACTIVATED:       "Break-even activated",
    Subtype.TP_ARMED:           "Take profit armed",
    Subtype.TP_HIT:             "Take profit hit",
    Subtype.PARTIAL_EXIT:       "Partial exit",
    Subtype.FINAL_EXIT:         "Final exit",
    Subtype.SL_HIT:             "Stop loss hit",
    Subtype.CANCELLED:          "Cancelled",
    Subtype.EXPIRED:            "Expired",
    Subtype.TIMEOUT:            "Timeout",
    Subtype.IGNORED:            "Ignored",
    Subtype.SYSTEM_NOTE:        "System note",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _derive_subtype_phase_class(
    event_type: str,
    processing_status: str,
    reason: str | None,
) -> tuple[str, str, str]:
    """Return (subtype, phase, event_class) for an event.

    Priority order:
    1. Ignored/rejected events → IGNORED / POST_MORTEM / AUDIT
    2. event_type-specific mapping (with reason refinement for ambiguous types)
    3. Fallback → SYSTEM_NOTE / POST_MORTEM / AUDIT
    """
    status_lc = (processing_status or "").lower()
    reason_lc = (reason or "").lower()
    et = (event_type or "").upper()

    # 1. Ignored / rejected → audit
    if status_lc in ("ignored", "rejected"):
        return Subtype.IGNORED, Phase.POST_MORTEM, EventClass.AUDIT

    # 2. Event-type mapping
    if et == "OPEN_SIGNAL":
        return Subtype.SIGNAL_CREATED, Phase.SETUP, EventClass.STRUCTURAL

    if et == "ADD_ENTRY":
        # ADD_ENTRY can result in a limit fill or a scale-in, both are ENTRY_FILLED
        return Subtype.ENTRY_FILLED, Phase.ENTRY, EventClass.STRUCTURAL

    if et == "MOVE_STOP":
        return Subtype.SL_MOVED, Phase.MANAGEMENT, EventClass.MANAGEMENT

    if et == "MOVE_STOP_TO_BE":
        return Subtype.BE_ACTIVATED, Phase.MANAGEMENT, EventClass.MANAGEMENT

    if et == "CLOSE_PARTIAL":
        # Partial exits: always PARTIAL_EXIT (TP partial or manual partial)
        return Subtype.PARTIAL_EXIT, Phase.EXIT, EventClass.RESULT

    if et == "CLOSE_FULL":
        for keyword, mapping in _CLOSE_FULL_REASON_MAP:
            if keyword in reason_lc:
                return mapping
        # No reason match → treat as final exit
        return Subtype.FINAL_EXIT, Phase.EXIT, EventClass.RESULT

    if et == "CANCEL_PENDING":
        for keyword, mapping in _CANCEL_PENDING_REASON_MAP:
            if keyword in reason_lc:
                return mapping
        return Subtype.CANCELLED, Phase.EXIT, EventClass.RESULT

    # 3. Fallback for unknown event types
    return Subtype.SYSTEM_NOTE, Phase.POST_MORTEM, EventClass.AUDIT


def _build_title(subtype: str, reason: str | None, event_type: str) -> str:
    """Return a human-readable title for the event."""
    base = _SUBTYPE_TITLE.get(subtype, subtype.replace("_", " ").title())
    if reason and subtype in (Subtype.IGNORED, Subtype.SYSTEM_NOTE, Subtype.CANCELLED):
        return f"{base} ({reason})"
    return base


def _build_summary(
    subtype: str,
    title: str,
    price_anchor: float | None,
    reason: str | None,
) -> str:
    """One-liner for sidebar collapsed view."""
    parts = [title]
    if price_anchor is not None:
        parts.append(f"@ {price_anchor:,.4f}".rstrip("0").rstrip("."))
    if reason and subtype not in (
        Subtype.SIGNAL_CREATED, Subtype.ENTRY_FILLED,
        Subtype.PARTIAL_EXIT, Subtype.FINAL_EXIT, Subtype.SL_HIT,
    ):
        parts.append(f"({reason})")
    return " ".join(parts)


def _extract_impact(state_after: dict[str, Any]) -> ImpactData:
    """Extract position-level impact from state_after snapshot."""
    return ImpactData(
        position=state_after.get("open_size"),
        risk=state_after.get("current_sl"),
        result=state_after.get("realized_pnl"),
    )


def _normalize_source(source: str | None) -> str:
    """Normalize source to uppercase canonical value."""
    s = (source or "engine").lower()
    if s == "trader":
        return "TRADER"
    if s == "engine":
        return "ENGINE"
    return s.upper()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_events(
    trade: TradeResult,
    event_log: list[EventLogEntry],
) -> list[ReportCanonicalEvent]:
    """Convert a list of EventLogEntry records to ReportCanonicalEvent objects.

    Args:
        trade: The TradeResult for which we are normalizing events.
               Used to provide signal_id for event IDs.
        event_log: Raw event log from the simulator.

    Returns:
        Ordered list of ReportCanonicalEvent (same order as input).
        Returns empty list if event_log is empty.

    Design notes:
    - Fallback subtype for unknown event_type is SYSTEM_NOTE (never crashes).
    - raw_text is propagated only when source == TRADER (PRD-B §14).
    - impact fields are extracted from state_after of EventLogEntry.
    """
    result: list[ReportCanonicalEvent] = []

    for idx, entry in enumerate(event_log):
        event_id = f"{trade.signal_id}_{idx}"

        subtype, phase, event_class = _derive_subtype_phase_class(
            event_type=entry.event_type,
            processing_status=entry.processing_status.value
            if hasattr(entry.processing_status, "value")
            else str(entry.processing_status),
            reason=entry.reason,
        )

        source = _normalize_source(entry.source)
        price_anchor = entry.price_reference
        title = _build_title(subtype, entry.reason, entry.event_type)
        summary = _build_summary(subtype, title, price_anchor, entry.reason)

        # raw_text only for TRADER-sourced events (PRD-B §14)
        raw_text = entry.raw_text if source == "TRADER" else None

        impact = _extract_impact(entry.state_after)

        # details: full state_after for audit drawer + extra context
        details: dict[str, Any] = dict(entry.state_after)
        if entry.requested_action:
            details["requested_action"] = entry.requested_action
        if entry.executed_action:
            details["executed_action"] = entry.executed_action
        if entry.reason:
            details["reason"] = entry.reason

        ts_str = (
            entry.timestamp.isoformat()
            if hasattr(entry.timestamp, "isoformat")
            else str(entry.timestamp)
        )

        result.append(
            ReportCanonicalEvent(
                id=event_id,
                ts=ts_str,
                phase=phase,
                event_class=event_class,
                subtype=subtype,
                title=title,
                price_anchor=price_anchor,
                source=source,
                impact=impact,
                summary=summary,
                raw_text=raw_text,
                details=details,
            )
        )

    return result
