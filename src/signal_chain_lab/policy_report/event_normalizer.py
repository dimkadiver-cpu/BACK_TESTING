"""Canonical event normalizer for the single-trade policy report.

The normalizer is the shared source of truth for:
- chart markers
- event rail
- unified sidebar events list
- audit drawer

It keeps one canonical representation per event so the UI can stay aligned.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult


class Subtype:
    # ── Setup / plan ───────────────────────────────────────────────────────
    SETUP_CREATED = "SETUP_CREATED"
    ENTRY_ORDER_ADDED = "ENTRY_ORDER_ADDED"
    # ── Entry fills ────────────────────────────────────────────────────────
    ENTRY_FILLED_INITIAL = "ENTRY_FILLED_INITIAL"
    ENTRY_FILLED_SCALE_IN = "ENTRY_FILLED_SCALE_IN"
    # ── Management ─────────────────────────────────────────────────────────
    STOP_MOVED = "STOP_MOVED"
    BREAK_EVEN_ACTIVATED = "BREAK_EVEN_ACTIVATED"
    # ── Partial exits ──────────────────────────────────────────────────────
    EXIT_PARTIAL_TP = "EXIT_PARTIAL_TP"
    EXIT_PARTIAL_MANUAL = "EXIT_PARTIAL_MANUAL"
    # ── Final exits ────────────────────────────────────────────────────────
    EXIT_FINAL_TP = "EXIT_FINAL_TP"
    EXIT_FINAL_SL = "EXIT_FINAL_SL"
    EXIT_FINAL_MANUAL = "EXIT_FINAL_MANUAL"
    EXIT_FINAL_TIMEOUT = "EXIT_FINAL_TIMEOUT"
    # ── Pending cancellations ──────────────────────────────────────────────
    PENDING_CANCELLED_TRADER = "PENDING_CANCELLED_TRADER"
    PENDING_CANCELLED_ENGINE = "PENDING_CANCELLED_ENGINE"
    PENDING_TIMEOUT = "PENDING_TIMEOUT"
    # ── Audit / informational ──────────────────────────────────────────────
    IGNORED = "IGNORED"
    SYSTEM_NOTE = "SYSTEM_NOTE"


class Phase:
    ENTRY = "ENTRY"
    MANAGEMENT = "MANAGEMENT"
    EXIT = "EXIT"


class EventClass:
    STRUCTURAL = "STRUCTURAL"
    MANAGEMENT = "MANAGEMENT"
    RESULT = "RESULT"
    AUDIT = "AUDIT"


@dataclass
class ImpactData:
    position: float | None = None
    risk: float | None = None
    result: float | None = None


@dataclass
class EventVisual:
    color_key: str | None = None
    lane_key: str | None = None
    chart_anchor_mode: str = "exact"


@dataclass
class EventRelations:
    parent_event_id: str | None = None
    derived_from_policy: bool = False
    sequence_group: str | None = None


@dataclass
class ReportCanonicalEvent:
    id: str
    ts: str
    phase: str
    event_class: str
    subtype: str
    title: str
    price_anchor: float | None
    source: str
    impact: ImpactData
    summary: str
    raw_text: str | None
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    visual: EventVisual = field(default_factory=EventVisual)
    relations: EventRelations = field(default_factory=EventRelations)


# Maps keywords in `reason` (lowercase) → (subtype, phase, event_class) for CLOSE_FULL events.
# Evaluated in order; first match wins.
_CLOSE_FULL_REASON_MAP: list[tuple[str, tuple[str, str, str]]] = [
    ("sl_hit",       (Subtype.EXIT_FINAL_SL,      Phase.EXIT, EventClass.RESULT)),
    ("stop_hit",     (Subtype.EXIT_FINAL_SL,      Phase.EXIT, EventClass.RESULT)),
    ("sl_reached",   (Subtype.EXIT_FINAL_SL,      Phase.EXIT, EventClass.RESULT)),
    ("chain_timeout",(Subtype.EXIT_FINAL_TIMEOUT, Phase.EXIT, EventClass.RESULT)),
    ("timeout",      (Subtype.EXIT_FINAL_TIMEOUT, Phase.EXIT, EventClass.RESULT)),
    ("expired",      (Subtype.EXIT_FINAL_TIMEOUT, Phase.EXIT, EventClass.RESULT)),
    ("tp_hit",       (Subtype.EXIT_FINAL_TP,      Phase.EXIT, EventClass.RESULT)),
    ("tp_reached",   (Subtype.EXIT_FINAL_TP,      Phase.EXIT, EventClass.RESULT)),
    ("tp",           (Subtype.EXIT_FINAL_TP,      Phase.EXIT, EventClass.RESULT)),
    ("manual",       (Subtype.EXIT_FINAL_MANUAL,  Phase.EXIT, EventClass.RESULT)),
]

_SUBTYPE_TITLE: dict[str, str] = {
    Subtype.SETUP_CREATED:          "SETUP OPENED",
    Subtype.ENTRY_ORDER_ADDED:      "ENTRY PLANNED",
    Subtype.ENTRY_FILLED_INITIAL:   "ENTRY FILLED",
    Subtype.ENTRY_FILLED_SCALE_IN:  "ADD ENTRY FILLED",
    Subtype.STOP_MOVED:             "MOVE STOP",
    Subtype.BREAK_EVEN_ACTIVATED:   "BREAK-EVEN ACTIVATED",
    Subtype.EXIT_PARTIAL_TP:        "TAKE PROFIT HIT",
    Subtype.EXIT_PARTIAL_MANUAL:    "PARTIAL CLOSE",
    Subtype.EXIT_FINAL_TP:          "FULL CLOSE (TP)",
    Subtype.EXIT_FINAL_SL:          "STOP LOSS HIT",
    Subtype.EXIT_FINAL_MANUAL:      "FULL CLOSE",
    Subtype.EXIT_FINAL_TIMEOUT:     "TIMEOUT",
    Subtype.PENDING_CANCELLED_TRADER: "CANCELLED (TRADER)",
    Subtype.PENDING_CANCELLED_ENGINE: "CANCELLED",
    Subtype.PENDING_TIMEOUT:        "PENDING TIMEOUT",
    Subtype.IGNORED:                "IGNORED EVENT",
    Subtype.SYSTEM_NOTE:            "SYSTEM NOTE",
}

_VISUAL_COLOR_KEY: dict[str, str] = {
    Subtype.SETUP_CREATED:          "setup",
    Subtype.ENTRY_ORDER_ADDED:      "entry",
    Subtype.ENTRY_FILLED_INITIAL:   "entry",
    Subtype.ENTRY_FILLED_SCALE_IN:  "entry",
    Subtype.STOP_MOVED:             "management",
    Subtype.BREAK_EVEN_ACTIVATED:   "management",
    Subtype.EXIT_PARTIAL_TP:        "tp",
    Subtype.EXIT_PARTIAL_MANUAL:    "exit",
    Subtype.EXIT_FINAL_TP:          "tp",
    Subtype.EXIT_FINAL_SL:          "sl",
    Subtype.EXIT_FINAL_MANUAL:      "exit",
    Subtype.EXIT_FINAL_TIMEOUT:     "technical",
    Subtype.PENDING_CANCELLED_TRADER: "technical",
    Subtype.PENDING_CANCELLED_ENGINE: "technical",
    Subtype.PENDING_TIMEOUT:        "technical",
    Subtype.IGNORED:                "audit",
    Subtype.SYSTEM_NOTE:            "audit",
}


def _normalize_source(source: str | None) -> str:
    value = (source or "engine").strip().upper()
    if value == "TRADER":
        return "TRADER"
    if value == "ENGINE":
        return "ENGINE"
    if value == "SYSTEM":
        return "SYSTEM"
    return value or "ENGINE"


def _detect_market_fill(entry: EventLogEntry) -> bool:
    text_bits = " ".join(
        part
        for part in [
            entry.event_type or "",
            entry.requested_action or "",
            entry.executed_action or "",
            entry.reason or "",
        ]
        if part
    ).lower()
    if "market" in text_bits:
        return True
    plans = (entry.state_after or {}).get("entries_planned") or []
    for plan in plans:
        if isinstance(plan, dict) and str(plan.get("entry_type") or "").upper() == "MARKET":
            return True
    return False


def _entry_order_type_from_state(state: dict[str, Any], plan_id: str | None = None) -> str | None:
    plans = state.get("entries_planned") or []
    for plan in plans:
        if not isinstance(plan, dict):
            continue
        if plan_id is not None and str(plan.get("plan_id") or "") != plan_id:
            continue
        order_type = plan.get("order_type") or plan.get("entry_type")
        if order_type:
            return str(order_type).upper()
    return None


def _collect_snapshot_fills(entry: EventLogEntry) -> list[dict[str, Any]]:
    fills: list[dict[str, Any]] = []
    for snapshot in (entry.state_before or {}, entry.state_after or {}):
        for fill in snapshot.get("fills") or []:
            if isinstance(fill, dict):
                fills.append(fill)
    return fills


def _latest_fill_price(entry: EventLogEntry) -> float | None:
    latest_ts: str = ""
    latest_price: float | None = None
    for fill in _collect_snapshot_fills(entry):
        price = fill.get("price")
        if not isinstance(price, (int, float)):
            continue
        fill_ts = str(fill.get("timestamp") or "")
        if latest_price is None or fill_ts >= latest_ts:
            latest_ts = fill_ts
            latest_price = float(price)
    return latest_price


def _tp_hit_price(entry: EventLogEntry) -> float | None:
    before_state = entry.state_before or {}
    after_state = entry.state_after or {}

    before_idx = before_state.get("next_tp_index")
    before_tps = before_state.get("tp_levels") or []
    after_idx = after_state.get("next_tp_index")
    after_tps = after_state.get("tp_levels") or []

    # Engine-generated TP closes may already have advanced next_tp_index in
    # state_before by the time the EventLogEntry is created. Handle both
    # "pre-hit" and "already-advanced" snapshots explicitly.
    if isinstance(before_idx, int) and isinstance(after_idx, int):
        if after_idx > before_idx:
            hit_idx = before_idx
        else:
            hit_idx = before_idx - 1
        if 0 <= hit_idx < len(before_tps):
            tp_val = before_tps[hit_idx]
            if isinstance(tp_val, (int, float)):
                return float(tp_val)
    elif isinstance(before_idx, int):
        preferred = before_idx - 1 if before_idx > 0 else before_idx
        if 0 <= preferred < len(before_tps):
            tp_val = before_tps[preferred]
            if isinstance(tp_val, (int, float)):
                return float(tp_val)
    elif isinstance(after_idx, int) and after_idx > 0:
        hit_idx = after_idx - 1
        if 0 <= hit_idx < len(before_tps):
            tp_val = before_tps[hit_idx]
            if isinstance(tp_val, (int, float)):
                return float(tp_val)

    before_tp_prices = {
        float(tp) for tp in before_tps if isinstance(tp, (int, float))
    }
    after_tp_prices = {
        float(tp) for tp in after_tps if isinstance(tp, (int, float))
    }
    removed = sorted(before_tp_prices - after_tp_prices)
    if removed:
        return removed[0]
    return None


def _derive_fill_subtype(entry: EventLogEntry) -> str:
    fills_count = (entry.state_after or {}).get("fills_count")
    if isinstance(fills_count, int) and fills_count >= 2:
        return Subtype.ENTRY_FILLED_SCALE_IN
    return Subtype.ENTRY_FILLED_INITIAL


def _derive_subtype_phase_class(entry: EventLogEntry) -> tuple[str, str, str]:
    processing_status = (
        entry.processing_status.value
        if hasattr(entry.processing_status, "value")
        else str(entry.processing_status)
    )
    status_lc = (processing_status or "").lower()
    reason_lc = (entry.reason or "").lower()
    event_type = (entry.event_type or "").upper()

    if status_lc in {"ignored", "rejected"}:
        return Subtype.IGNORED, Phase.MANAGEMENT, EventClass.AUDIT

    if event_type == "OPEN_SIGNAL":
        return Subtype.SETUP_CREATED, Phase.ENTRY, EventClass.STRUCTURAL
    if event_type in {"FILL", "ADD_ENTRY"}:
        return _derive_fill_subtype(entry), Phase.ENTRY, EventClass.STRUCTURAL
    if event_type == "MOVE_STOP":
        return Subtype.STOP_MOVED, Phase.MANAGEMENT, EventClass.MANAGEMENT
    if event_type == "MOVE_STOP_TO_BE":
        return Subtype.BREAK_EVEN_ACTIVATED, Phase.MANAGEMENT, EventClass.MANAGEMENT
    if event_type == "CLOSE_PARTIAL":
        if "tp_hit" in reason_lc or "tp_reached" in reason_lc or "tp" in reason_lc:
            return Subtype.EXIT_PARTIAL_TP, Phase.EXIT, EventClass.RESULT
        return Subtype.EXIT_PARTIAL_MANUAL, Phase.EXIT, EventClass.RESULT
    if event_type == "CLOSE_FULL":
        for keyword, mapping in _CLOSE_FULL_REASON_MAP:
            if keyword in reason_lc:
                return mapping
        return Subtype.EXIT_FINAL_MANUAL, Phase.EXIT, EventClass.RESULT
    if event_type == "CANCEL_PENDING":
        source_normalized = _normalize_source(entry.source)
        if "timeout" in reason_lc or "expired" in reason_lc:
            return Subtype.PENDING_TIMEOUT, Phase.EXIT, EventClass.RESULT
        if source_normalized == "TRADER":
            return Subtype.PENDING_CANCELLED_TRADER, Phase.EXIT, EventClass.RESULT
        return Subtype.PENDING_CANCELLED_ENGINE, Phase.EXIT, EventClass.RESULT
    return Subtype.SYSTEM_NOTE, Phase.MANAGEMENT, EventClass.AUDIT


def _build_title(subtype: str) -> str:
    return _SUBTYPE_TITLE.get(subtype, subtype.replace("_", " ").title())


def _price_anchor(entry: EventLogEntry) -> float | None:
    event_type = (entry.event_type or "").upper()
    if event_type == "OPEN_SIGNAL":
        state = entry.state_after or {}
        plans = state.get("entries_planned") or []
        for plan in plans:
            if isinstance(plan, dict) and isinstance(plan.get("price"), (int, float)):
                return float(plan["price"])
        return None
    if event_type in {"FILL", "ADD_ENTRY"}:
        fill_price = _latest_fill_price(entry)
        if fill_price is not None:
            return fill_price
    if event_type == "CLOSE_PARTIAL" and "tp" in (entry.reason or "").lower():
        tp_price = _tp_hit_price(entry)
        if tp_price is not None:
            return tp_price
    if isinstance(entry.price_reference, (int, float)):
        return float(entry.price_reference)

    state = entry.state_after or {}
    for key in (
        "last_fill_price",
        "close_price",
        "avg_entry_price",
        "market_price",
        "mark_price",
        "last_price",
        "current_sl",
    ):
        value = state.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _build_summary(
    subtype: str,
    price_anchor: float | None,
    reason: str | None,
    *,
    custom_title: str | None = None,
) -> str:
    parts = [custom_title if custom_title is not None else _build_title(subtype)]
    if price_anchor is not None:
        parts.append(f"@ {price_anchor:,.4f}".rstrip("0").rstrip("."))
    if reason and subtype not in {
        Subtype.SETUP_CREATED,
        Subtype.ENTRY_FILLED_INITIAL,
        Subtype.ENTRY_FILLED_SCALE_IN,
    }:
        parts.append(f"({reason})")
    return " ".join(parts)


def _extract_impact(state_after: dict[str, Any]) -> ImpactData:
    return ImpactData(
        position=state_after.get("open_size") if isinstance(state_after.get("open_size"), (int, float)) else None,
        risk=state_after.get("current_sl") if isinstance(state_after.get("current_sl"), (int, float)) else None,
        result=state_after.get("realized_pnl") if isinstance(state_after.get("realized_pnl"), (int, float)) else None,
    )


def _build_visual(subtype: str, price_anchor: float | None) -> EventVisual:
    price_event_subtypes = {
        Subtype.ENTRY_FILLED_INITIAL,
        Subtype.ENTRY_FILLED_SCALE_IN,
        Subtype.EXIT_PARTIAL_TP,
        Subtype.EXIT_PARTIAL_MANUAL,
        Subtype.EXIT_FINAL_TP,
        Subtype.EXIT_FINAL_SL,
        Subtype.EXIT_FINAL_MANUAL,
        Subtype.EXIT_FINAL_TIMEOUT,
    }
    rail_subtypes = {
        Subtype.STOP_MOVED,
        Subtype.BREAK_EVEN_ACTIVATED,
        Subtype.PENDING_CANCELLED_TRADER,
        Subtype.PENDING_CANCELLED_ENGINE,
        Subtype.PENDING_TIMEOUT,
        Subtype.SYSTEM_NOTE,
        Subtype.IGNORED,
    }
    chart_anchor_mode = "candle_snapped" if subtype in price_event_subtypes else "exact"
    if subtype == Subtype.SETUP_CREATED:
        lane_key = "sidebar"
    else:
        lane_key = "rail" if subtype in rail_subtypes or price_anchor is None else "chart"
    return EventVisual(
        color_key=_VISUAL_COLOR_KEY.get(subtype),
        lane_key=lane_key,
        chart_anchor_mode=chart_anchor_mode,
    )


def _collect_fill_records(event_log: list[EventLogEntry]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    fills: list[dict[str, Any]] = []
    for entry in event_log:
        for snapshot_name in ("state_before", "state_after"):
            snapshot = getattr(entry, snapshot_name, {}) or {}
            for fill in snapshot.get("fills") or []:
                if not isinstance(fill, dict):
                    continue
                ts = str(fill.get("timestamp") or "")
                plan_id = str(fill.get("plan_id") or "")
                price = str(fill.get("price") or "")
                qty = str(fill.get("qty") or "")
                key = (ts, plan_id, price, qty)
                if key in seen:
                    continue
                seen.add(key)
                record = dict(fill)
                record["_order_type"] = _entry_order_type_from_state(snapshot, plan_id=plan_id)
                fills.append(record)
    fills.sort(key=lambda item: (str(item.get("timestamp") or ""), str(item.get("plan_id") or "")))
    return fills


def _synthetic_fill_event(
    *,
    trade: TradeResult,
    fill: dict[str, Any],
    index: int,
) -> ReportCanonicalEvent | None:
    ts = fill.get("timestamp")
    price = fill.get("price")
    qty = fill.get("qty")
    if not ts or not isinstance(price, (int, float)):
        return None
    subtype = Subtype.ENTRY_FILLED_SCALE_IN if index >= 1 else Subtype.ENTRY_FILLED_INITIAL
    details = {
        "fill_price": price,
        "fill_qty": qty,
        "plan_id": fill.get("plan_id"),
        "order_type": str(fill.get("_order_type") or "").upper() or None,
    }
    summary = _build_summary(subtype, float(price), None)
    return ReportCanonicalEvent(
        id=f"{trade.signal_id}_fill_{index}",
        ts=str(ts),
        phase=Phase.ENTRY,
        event_class=EventClass.STRUCTURAL,
        subtype=subtype,
        title=_build_title(subtype),
        price_anchor=float(price),
        source="ENGINE",
        impact=ImpactData(position=qty if isinstance(qty, (int, float)) else None, risk=None, result=None),
        summary=summary,
        raw_text=None,
        reason=None,
        details=details,
        visual=_build_visual(subtype, float(price)),
        relations=EventRelations(parent_event_id=None, derived_from_policy=False, sequence_group=str(ts)),
    )


# Priority order for deterministic sorting when multiple events share the same timestamp.
_SUBTYPE_SORT_PRIORITY: dict[str, int] = {
    Subtype.SETUP_CREATED:            0,
    Subtype.ENTRY_ORDER_ADDED:        1,
    Subtype.ENTRY_FILLED_INITIAL:     2,
    Subtype.ENTRY_FILLED_SCALE_IN:    3,
    Subtype.STOP_MOVED:               4,
    Subtype.BREAK_EVEN_ACTIVATED:     5,
    Subtype.EXIT_PARTIAL_TP:          6,
    Subtype.EXIT_PARTIAL_MANUAL:      7,
    Subtype.EXIT_FINAL_TP:            8,
    Subtype.EXIT_FINAL_SL:            9,
    Subtype.EXIT_FINAL_MANUAL:        10,
    Subtype.EXIT_FINAL_TIMEOUT:       11,
    Subtype.PENDING_CANCELLED_TRADER: 12,
    Subtype.PENDING_CANCELLED_ENGINE: 12,
    Subtype.PENDING_TIMEOUT:          12,
    Subtype.IGNORED:                  13,
    Subtype.SYSTEM_NOTE:              13,
}


def normalize_events(
    trade: TradeResult,
    event_log: list[EventLogEntry],
) -> list[ReportCanonicalEvent]:
    """Convert raw event log entries into canonical report events."""
    normalized: list[ReportCanonicalEvent] = []
    tp_hit_counter = 0

    for idx, entry in enumerate(event_log):
        subtype, phase, event_class = _derive_subtype_phase_class(entry)
        source = _normalize_source(entry.source)
        price_anchor = _price_anchor(entry)
        details = dict(entry.state_after)
        details["state_before"] = dict(entry.state_before)
        if subtype == Subtype.SETUP_CREATED:
            details.setdefault("symbol", trade.symbol)
            details.setdefault("side", trade.side)
        if entry.requested_action:
            details["requested_action"] = entry.requested_action
        if entry.executed_action:
            details["executed_action"] = entry.executed_action
        if entry.reason:
            details["reason"] = entry.reason
        details["raw_event_type"] = entry.event_type

        custom_title: str | None = None
        if subtype == Subtype.EXIT_PARTIAL_TP:
            tp_hit_counter += 1
            custom_title = f"TP HIT {tp_hit_counter}"
            tp_price = _tp_hit_price(entry)
            if tp_price is not None:
                price_anchor = tp_price

        event_id = f"{trade.signal_id}_{idx}"
        normalized.append(
            ReportCanonicalEvent(
                id=event_id,
                ts=entry.timestamp.isoformat(),
                phase=phase,
                event_class=event_class,
                subtype=subtype,
                title=custom_title if custom_title is not None else _build_title(subtype),
                price_anchor=price_anchor,
                source=source,
                impact=_extract_impact(entry.state_after or {}),
                summary=_build_summary(subtype, price_anchor, entry.reason, custom_title=custom_title),
                raw_text=entry.raw_text if source == "TRADER" else None,
                reason=entry.reason,
                details=details,
                visual=_build_visual(subtype, price_anchor),
                relations=EventRelations(
                    parent_event_id=None,
                    derived_from_policy=source in {"ENGINE", "SYSTEM"} and subtype in {
                        Subtype.STOP_MOVED,
                        Subtype.BREAK_EVEN_ACTIVATED,
                    },
                    sequence_group=entry.timestamp.isoformat(),
                ),
            )
        )

    synthetic_fills = [
        event
        for idx, fill in enumerate(_collect_fill_records(event_log))
        for event in [_synthetic_fill_event(trade=trade, fill=fill, index=idx)]
        if event is not None
    ]

    all_events = normalized + synthetic_fills
    all_events.sort(
        key=lambda event: (
            event.ts,
            _SUBTYPE_SORT_PRIORITY.get(event.subtype, 99),
            event.id,
        )
    )
    return all_events
