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
    # ── New canonical fields (PRD §6.2, §9, §15.2) ───────────────────────────
    event_code: str = ""            # = subtype; explicit canonical alias (PRD)
    stage: str = ""                 # ENTRY | MANAGEMENT | EXIT (= phase)
    position_effect: str = "NO_EFFECT"
    display_group: str = ""
    display_label: str = ""
    event_list_section: str = "A"   # "A" (operational) | "B" (audit/ignored)
    chart_marker_kind: str = "NONE" # REQUIRED | OPTIONAL_LIGHT | NONE
    geometry_effect: str = "NONE"
    state_delta_full: list[dict[str, Any]] = field(default_factory=list)
    state_delta_essential: list[dict[str, Any]] = field(default_factory=list)
    raw_event_ref: str | None = None


_CANONICAL_EVENT_BADGE_CLASS: dict[str, str] = {
    Subtype.SETUP_CREATED:            "ti-kind-NEW_SIGNAL",
    Subtype.ENTRY_ORDER_ADDED:        "ti-kind-NEW_SIGNAL",
    Subtype.ENTRY_FILLED_INITIAL:     "ti-kind-FILL",
    Subtype.ENTRY_FILLED_SCALE_IN:    "ti-kind-FILL",
    Subtype.STOP_MOVED:               "ti-kind-MOVE_SL",
    Subtype.BREAK_EVEN_ACTIVATED:     "ti-kind-MOVE_SL",
    Subtype.EXIT_PARTIAL_TP:          "ti-kind-TP",
    Subtype.EXIT_PARTIAL_MANUAL:      "ti-kind-PARTIAL_CLOSE",
    Subtype.EXIT_FINAL_TP:            "ti-kind-EXIT",
    Subtype.EXIT_FINAL_SL:            "ti-kind-SL",
    Subtype.EXIT_FINAL_MANUAL:        "ti-kind-EXIT",
    Subtype.EXIT_FINAL_TIMEOUT:       "ti-kind-CANCEL",
    Subtype.PENDING_CANCELLED_TRADER: "ti-kind-CANCEL",
    Subtype.PENDING_CANCELLED_ENGINE: "ti-kind-CANCEL",
    Subtype.PENDING_TIMEOUT:          "ti-kind-CANCEL",
    Subtype.IGNORED:                  "ti-kind-UPDATE",
    Subtype.SYSTEM_NOTE:              "ti-kind-UPDATE",
}

_CANONICAL_EVENT_MARKER_COLOR: dict[str, str] = {
    Subtype.SETUP_CREATED:            "#0369a1",
    Subtype.ENTRY_ORDER_ADDED:        "#1d4ed8",
    Subtype.ENTRY_FILLED_INITIAL:     "#1d4ed8",
    Subtype.ENTRY_FILLED_SCALE_IN:    "#2563eb",
    Subtype.STOP_MOVED:               "#c2410c",
    Subtype.BREAK_EVEN_ACTIVATED:     "#f59e0b",
    Subtype.EXIT_PARTIAL_TP:          "#15803d",
    Subtype.EXIT_PARTIAL_MANUAL:      "#ea580c",
    Subtype.EXIT_FINAL_TP:            "#15803d",
    Subtype.EXIT_FINAL_SL:            "#b91c1c",
    Subtype.EXIT_FINAL_MANUAL:        "#ea580c",
    Subtype.EXIT_FINAL_TIMEOUT:       "#64748b",
    Subtype.PENDING_CANCELLED_TRADER: "#eab308",
    Subtype.PENDING_CANCELLED_ENGINE: "#eab308",
    Subtype.PENDING_TIMEOUT:          "#94a3b8",
    Subtype.IGNORED:                  "#94a3b8",
    Subtype.SYSTEM_NOTE:              "#475569",
}

_CANONICAL_EVENT_MARKER_SYMBOL: dict[str, str] = {
    Subtype.SETUP_CREATED:            "circle",
    Subtype.ENTRY_ORDER_ADDED:        "rect",
    Subtype.ENTRY_FILLED_INITIAL:     "circle",
    Subtype.ENTRY_FILLED_SCALE_IN:    "circle",
    Subtype.STOP_MOVED:               "rect",
    Subtype.BREAK_EVEN_ACTIVATED:     "pin",
    Subtype.EXIT_PARTIAL_TP:          "diamond",
    Subtype.EXIT_PARTIAL_MANUAL:      "pin",
    Subtype.EXIT_FINAL_TP:            "diamond",
    Subtype.EXIT_FINAL_SL:            "triangle",
    Subtype.EXIT_FINAL_MANUAL:        "roundRect",
    Subtype.EXIT_FINAL_TIMEOUT:       "triangle",
    Subtype.PENDING_CANCELLED_TRADER: "triangle",
    Subtype.PENDING_CANCELLED_ENGINE: "triangle",
    Subtype.PENDING_TIMEOUT:          "triangle",
    Subtype.IGNORED:                  "emptyCircle",
    Subtype.SYSTEM_NOTE:              "circle",
}

_CANONICAL_EVENT_LEGEND_LABEL: dict[str, str] = {
    Subtype.ENTRY_FILLED_INITIAL: "Entry filled",
    Subtype.ENTRY_FILLED_SCALE_IN: "Scale-in filled",
    Subtype.EXIT_PARTIAL_TP: "TP hit",
    Subtype.EXIT_PARTIAL_MANUAL: "Partial close",
    Subtype.EXIT_FINAL_SL: "SL hit",
    Subtype.EXIT_FINAL_TP: "Final exit (TP)",
    Subtype.EXIT_FINAL_MANUAL: "Final exit",
}


def canonical_event_badge_class(event_code: str) -> str:
    return _CANONICAL_EVENT_BADGE_CLASS.get(event_code, "ti-kind-UPDATE")


def canonical_event_marker_color(event_code: str) -> str:
    return _CANONICAL_EVENT_MARKER_COLOR.get(event_code, "#475569")


def canonical_event_marker_symbol(event_code: str) -> str:
    return _CANONICAL_EVENT_MARKER_SYMBOL.get(event_code, "circle")


def canonical_event_legend_items(
    visible_event_codes: set[str] | None = None,
) -> list[dict[str, str]]:
    ordered_event_codes = [
        Subtype.ENTRY_FILLED_INITIAL,
        Subtype.ENTRY_FILLED_SCALE_IN,
        Subtype.EXIT_PARTIAL_TP,
        Subtype.EXIT_PARTIAL_MANUAL,
        Subtype.EXIT_FINAL_SL,
        Subtype.EXIT_FINAL_TP,
        Subtype.EXIT_FINAL_MANUAL,
    ]
    return [
        {
            "key": f"ev_{event_code}",
            "label": _CANONICAL_EVENT_LEGEND_LABEL[event_code],
            "color": canonical_event_marker_color(event_code),
            "shape": "marker",
            "symbol": canonical_event_marker_symbol(event_code),
        }
        for event_code in ordered_event_codes
        if visible_event_codes is None or event_code in visible_event_codes
    ]


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
    Subtype.SETUP_CREATED:          "SETUP",
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

# ── New canonical lookup tables (PRD §6.2, §9, §15.2) ──────────────────────

# PRD §9 — chart marker visibility
_CHART_MARKER_KIND: dict[str, str] = {
    Subtype.SETUP_CREATED:            "NONE",
    Subtype.ENTRY_ORDER_ADDED:        "NONE",
    Subtype.ENTRY_FILLED_INITIAL:     "REQUIRED",
    Subtype.ENTRY_FILLED_SCALE_IN:    "REQUIRED",
    Subtype.STOP_MOVED:               "NONE",
    Subtype.BREAK_EVEN_ACTIVATED:     "NONE",
    Subtype.EXIT_PARTIAL_TP:          "REQUIRED",
    Subtype.EXIT_PARTIAL_MANUAL:      "REQUIRED",
    Subtype.EXIT_FINAL_TP:            "REQUIRED",
    Subtype.EXIT_FINAL_SL:            "REQUIRED",
    Subtype.EXIT_FINAL_MANUAL:        "REQUIRED",
    Subtype.EXIT_FINAL_TIMEOUT:       "REQUIRED",
    Subtype.PENDING_CANCELLED_TRADER: "OPTIONAL_LIGHT",
    Subtype.PENDING_CANCELLED_ENGINE: "OPTIONAL_LIGHT",
    Subtype.PENDING_TIMEOUT:          "OPTIONAL_LIGHT",
    Subtype.IGNORED:                  "NONE",
    Subtype.SYSTEM_NOTE:              "NONE",
}

# PRD §15.2 — geometry effect on level segments
_GEOMETRY_EFFECT: dict[str, str] = {
    Subtype.SETUP_CREATED:            "CREATE_INITIAL_LEVELS",
    Subtype.ENTRY_ORDER_ADDED:        "ADD_PENDING_LEVEL",
    Subtype.ENTRY_FILLED_INITIAL:     "ACTIVATE_FILLED_ENTRY",
    Subtype.ENTRY_FILLED_SCALE_IN:    "UPDATE_AVERAGE_ENTRY_AND_POSITION_LEVELS",
    Subtype.STOP_MOVED:               "UPDATE_STOP_LINE",
    Subtype.BREAK_EVEN_ACTIVATED:     "CONVERT_STOP_TO_BE",
    Subtype.EXIT_PARTIAL_TP:          "REDUCE_POSITION_LEVELS",
    Subtype.EXIT_PARTIAL_MANUAL:      "REDUCE_POSITION_LEVELS",
    Subtype.EXIT_FINAL_TP:            "CLOSE_POSITION_LEVELS",
    Subtype.EXIT_FINAL_SL:            "CLOSE_POSITION_LEVELS",
    Subtype.EXIT_FINAL_MANUAL:        "CLOSE_POSITION_LEVELS",
    Subtype.EXIT_FINAL_TIMEOUT:       "CLOSE_POSITION_LEVELS",
    Subtype.PENDING_CANCELLED_TRADER: "REMOVE_PENDING_LEVEL",
    Subtype.PENDING_CANCELLED_ENGINE: "REMOVE_PENDING_LEVEL",
    Subtype.PENDING_TIMEOUT:          "REMOVE_PENDING_LEVEL",
    Subtype.IGNORED:                  "ANNOTATION_ONLY",
    Subtype.SYSTEM_NOTE:              "ANNOTATION_ONLY",
}

# PRD §5 — event list section (default "A"; only IGNORED/SYSTEM_NOTE → "B")
_EVENT_LIST_SECTION: dict[str, str] = {
    Subtype.IGNORED:     "B",
    Subtype.SYSTEM_NOTE: "B",
}

# PRD §6.2 — position effect of each event
_POSITION_EFFECT: dict[str, str] = {
    Subtype.SETUP_CREATED:            "PLAN_CREATED",
    Subtype.ENTRY_ORDER_ADDED:        "PLAN_UPDATED",
    Subtype.ENTRY_FILLED_INITIAL:     "POSITION_OPENED",
    Subtype.ENTRY_FILLED_SCALE_IN:    "POSITION_INCREASED",
    Subtype.STOP_MOVED:               "PLAN_UPDATED",
    Subtype.BREAK_EVEN_ACTIVATED:     "PLAN_UPDATED",
    Subtype.EXIT_PARTIAL_TP:          "POSITION_REDUCED",
    Subtype.EXIT_PARTIAL_MANUAL:      "POSITION_REDUCED",
    Subtype.EXIT_FINAL_TP:            "POSITION_CLOSED",
    Subtype.EXIT_FINAL_SL:            "POSITION_CLOSED",
    Subtype.EXIT_FINAL_MANUAL:        "POSITION_CLOSED",
    Subtype.EXIT_FINAL_TIMEOUT:       "POSITION_CLOSED",
    Subtype.PENDING_CANCELLED_TRADER: "PENDING_CANCELLED",
    Subtype.PENDING_CANCELLED_ENGINE: "PENDING_CANCELLED",
    Subtype.PENDING_TIMEOUT:          "PENDING_CANCELLED",
    Subtype.IGNORED:                  "NO_EFFECT",
    Subtype.SYSTEM_NOTE:              "NO_EFFECT",
}

_DISPLAY_GROUP: dict[str, str] = {
    Subtype.SETUP_CREATED:            "SETUP",
    Subtype.ENTRY_ORDER_ADDED:        "ENTRY_PLAN",
    Subtype.ENTRY_FILLED_INITIAL:     "ENTRY_FILL",
    Subtype.ENTRY_FILLED_SCALE_IN:    "ENTRY_FILL",
    Subtype.STOP_MOVED:               "STOP_MANAGEMENT",
    Subtype.BREAK_EVEN_ACTIVATED:     "STOP_MANAGEMENT",
    Subtype.EXIT_PARTIAL_TP:          "EXIT_PARTIAL",
    Subtype.EXIT_PARTIAL_MANUAL:      "EXIT_PARTIAL",
    Subtype.EXIT_FINAL_TP:            "EXIT_FINAL",
    Subtype.EXIT_FINAL_SL:            "EXIT_FINAL",
    Subtype.EXIT_FINAL_MANUAL:        "EXIT_FINAL",
    Subtype.EXIT_FINAL_TIMEOUT:       "EXIT_FINAL",
    Subtype.PENDING_CANCELLED_TRADER: "PENDING_CANCEL",
    Subtype.PENDING_CANCELLED_ENGINE: "PENDING_CANCEL",
    Subtype.PENDING_TIMEOUT:          "PENDING_CANCEL",
    Subtype.IGNORED:                  "AUDIT",
    Subtype.SYSTEM_NOTE:              "AUDIT",
}

_STATE_DELTA_SPECS: list[tuple[str, str | None, int]] = [
    ("status", "state", 1),
    ("open_size", "qty", 1),
    ("pending_size", "qty", 2),
    ("avg_entry_price", "price", 2),
    ("current_sl", "price", 1),
    ("next_tp_index", "index", 2),
    ("realized_pnl", "pnl", 1),
    ("unrealized_pnl", "pnl", 3),
    ("close_fees_paid", "fee", 2),
    ("fills_count", "count", 2),
    ("max_position_size", "qty", 3),
    ("closed_at", "timestamp", 2),
    ("entries_planned_count", "count", 3),
    ("tp_levels_count", "count", 3),
]


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


def _compute_stage(subtype: str, phase: str, entry: EventLogEntry) -> str:
    """PRD §12: for CANCEL/TIMEOUT events, stage depends on open_size in state_before.

    - open_size == 0 (no fills yet) → stage = ENTRY
    - open_size > 0  (partial position) → stage = MANAGEMENT
    - open_size unknown → default ENTRY (conservative: no fills assumed)
    """
    if subtype in {
        Subtype.PENDING_CANCELLED_TRADER,
        Subtype.PENDING_CANCELLED_ENGINE,
        Subtype.PENDING_TIMEOUT,
    }:
        state_before = entry.state_before or {}
        open_size = state_before.get("open_size")
        if isinstance(open_size, (int, float)):
            return Phase.ENTRY if open_size == 0 else Phase.MANAGEMENT
        return Phase.ENTRY
    return phase


def _normalize_delta_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 8)
    if isinstance(value, list):
        return [_normalize_delta_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize_delta_value(val) for key, val in sorted(value.items())}
    return value


def _state_metric(state: dict[str, Any], field_path: str) -> Any:
    if field_path == "entries_planned_count":
        return len([plan for plan in state.get("entries_planned") or [] if isinstance(plan, dict)])
    if field_path == "tp_levels_count":
        return len([tp for tp in state.get("tp_levels") or [] if isinstance(tp, (int, float))])
    if field_path == "fills_count":
        explicit = state.get("fills_count")
        if isinstance(explicit, int):
            return explicit
        return len([fill for fill in state.get("fills") or [] if isinstance(fill, dict)])
    return state.get(field_path)


def _build_state_delta_full(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    delta_full: list[dict[str, Any]] = []
    for field_path, unit, display_priority in _STATE_DELTA_SPECS:
        before_value = _normalize_delta_value(_state_metric(before, field_path))
        after_value = _normalize_delta_value(_state_metric(after, field_path))
        if before_value == after_value:
            continue
        delta_full.append(
            {
                "field_path": field_path,
                "before": before_value,
                "after": after_value,
                "unit": unit,
                "is_mutative": True,
                "display_priority": display_priority,
            }
        )

    for field_path, unit, display_priority in [
        ("tp_levels", "levels", 3),
        ("entries_planned", "plans", 4),
    ]:
        before_value = _normalize_delta_value(before.get(field_path))
        after_value = _normalize_delta_value(after.get(field_path))
        if before_value == after_value:
            continue
        delta_full.append(
            {
                "field_path": field_path,
                "before": before_value,
                "after": after_value,
                "unit": unit,
                "is_mutative": True,
                "display_priority": display_priority,
            }
        )
    return delta_full


def _derive_state_delta_essential(delta_full: list[dict[str, Any]]) -> list[dict[str, Any]]:
    essential = [
        item
        for item in delta_full
        if item.get("is_mutative") and int(item.get("display_priority", 99)) <= 2
    ]
    essential.sort(key=lambda item: (int(item.get("display_priority", 99)), str(item.get("field_path", ""))))
    return essential[:6]


def _build_position_effect(event_code: str, state_before: dict[str, Any], state_after: dict[str, Any]) -> str:
    if event_code == Subtype.ENTRY_FILLED_INITIAL:
        before_open = state_before.get("open_size")
        after_open = state_after.get("open_size")
        if isinstance(before_open, (int, float)) and isinstance(after_open, (int, float)) and before_open > 0:
            return "POSITION_INCREASED"
    return _POSITION_EFFECT.get(event_code, "NO_EFFECT")


def _build_geometry_effect(event_code: str) -> str:
    return _GEOMETRY_EFFECT.get(event_code, "NONE")


def _build_chart_marker_kind(event_code: str) -> str:
    return _CHART_MARKER_KIND.get(event_code, "NONE")


def _build_event_list_section(event_code: str) -> str:
    return _EVENT_LIST_SECTION.get(event_code, "A")


def _build_display_group(event_code: str) -> str:
    return _DISPLAY_GROUP.get(event_code, "GENERAL")


def _build_display_label(event_code: str) -> str:
    return _build_title(event_code)


def _derive_fill_subtype(entry: EventLogEntry) -> str:
    before_open = (entry.state_before or {}).get("open_size")
    if isinstance(before_open, (int, float)) and before_open > 0:
        return Subtype.ENTRY_FILLED_SCALE_IN
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
    if event_type == "ADD_ENTRY":
        return Subtype.ENTRY_ORDER_ADDED, Phase.ENTRY, EventClass.STRUCTURAL
    if event_type == "FILL":
        subtype = _derive_fill_subtype(entry)
        phase = Phase.ENTRY if subtype == Subtype.ENTRY_FILLED_INITIAL else Phase.MANAGEMENT
        return subtype, phase, EventClass.STRUCTURAL
    if event_type == "MOVE_STOP":
        return Subtype.STOP_MOVED, Phase.MANAGEMENT, EventClass.MANAGEMENT
    if event_type == "MOVE_STOP_TO_BE":
        return Subtype.BREAK_EVEN_ACTIVATED, Phase.MANAGEMENT, EventClass.MANAGEMENT
    if event_type == "CLOSE_PARTIAL":
        if "tp_hit" in reason_lc or "tp_reached" in reason_lc or "tp" in reason_lc:
            return Subtype.EXIT_PARTIAL_TP, Phase.MANAGEMENT, EventClass.RESULT
        return Subtype.EXIT_PARTIAL_MANUAL, Phase.MANAGEMENT, EventClass.RESULT
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
    if event_type == "ADD_ENTRY":
        for snapshot in (entry.state_after or {}, entry.state_before or {}):
            plans = snapshot.get("entries_planned") or []
            for plan in reversed(plans):
                if isinstance(plan, dict) and isinstance(plan.get("price"), (int, float)):
                    return float(plan["price"])
        return None
    if event_type == "CANCEL_PENDING":
        before_plans = {
            str(plan.get("plan_id") or f"idx:{idx}"): plan
            for idx, plan in enumerate((entry.state_before or {}).get("entries_planned") or [])
            if isinstance(plan, dict)
        }
        after_plan_ids = {
            str(plan.get("plan_id") or f"idx:{idx}")
            for idx, plan in enumerate((entry.state_after or {}).get("entries_planned") or [])
            if isinstance(plan, dict)
        }
        removed_ids = [plan_id for plan_id in before_plans if plan_id not in after_plan_ids]
        for plan_id in removed_ids:
            plan = before_plans.get(plan_id) or {}
            price = plan.get("price")
            if isinstance(price, (int, float)):
                return float(price)
        before_pending_size = (entry.state_before or {}).get("pending_size")
        after_pending_size = (entry.state_after or {}).get("pending_size")
        if (
            isinstance(before_pending_size, (int, float))
            and before_pending_size > 0
            and isinstance(after_pending_size, (int, float))
            and after_pending_size <= 0
        ):
            for plan in reversed(list(before_plans.values())):
                price = plan.get("price")
                if isinstance(price, (int, float)):
                    return float(price)
    if event_type == "FILL":
        fill_price = _latest_fill_price(entry)
        if fill_price is not None:
            return fill_price
    if event_type == "CLOSE_PARTIAL" and "tp" in (entry.reason or "").lower():
        tp_price = _tp_hit_price(entry)
        if tp_price is not None:
            return tp_price
    if event_type == "CLOSE_FULL" and "tp" in (entry.reason or "").lower():
        tp_price = _tp_hit_price(entry)
        if tp_price is not None:
            return tp_price
    if event_type == "CLOSE_FULL" and any(
        keyword in (entry.reason or "").lower() for keyword in ("sl_hit", "stop_hit", "sl_reached")
    ):
        for snapshot in (entry.state_before or {}, entry.state_after or {}):
            current_sl = snapshot.get("current_sl")
            if isinstance(current_sl, (int, float)):
                return float(current_sl)
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
    state_delta_full: list[dict[str, Any]] = []
    return ReportCanonicalEvent(
        id=f"{trade.signal_id}_fill_{index}",
        ts=str(ts),
        phase=Phase.ENTRY if subtype == Subtype.ENTRY_FILLED_INITIAL else Phase.MANAGEMENT,
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
        event_code=subtype,
        stage=Phase.ENTRY if subtype == Subtype.ENTRY_FILLED_INITIAL else Phase.MANAGEMENT,
        position_effect=_build_position_effect(subtype, {}, details),
        display_group=_build_display_group(subtype),
        display_label=_build_display_label(subtype),
        event_list_section=_build_event_list_section(subtype),
        chart_marker_kind=_build_chart_marker_kind(subtype),
        geometry_effect=_build_geometry_effect(subtype),
        state_delta_full=state_delta_full,
        state_delta_essential=_derive_state_delta_essential(state_delta_full),
        raw_event_ref=f"synthetic_fill:{trade.signal_id}:{index}",
    )


# Priority order for deterministic sorting when multiple events share the same timestamp.
_SUBTYPE_SORT_PRIORITY: dict[str, int] = {
    Subtype.SETUP_CREATED:            0,
    Subtype.ENTRY_ORDER_ADDED:        1,
    Subtype.ENTRY_FILLED_INITIAL:     2,
    Subtype.ENTRY_FILLED_SCALE_IN:    3,
    Subtype.STOP_MOVED:               4,
    Subtype.EXIT_PARTIAL_TP:          5,
    Subtype.BREAK_EVEN_ACTIVATED:     6,
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
        state_before = dict(entry.state_before or {})
        state_after = dict(entry.state_after or {})
        state_delta_full = _build_state_delta_full(state_before, state_after)
        state_delta_essential = _derive_state_delta_essential(state_delta_full)
        details = dict(state_after)
        details["state_before"] = state_before
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
                impact=_extract_impact(state_after),
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
                event_code=subtype,
                stage=_compute_stage(subtype, phase, entry),
                position_effect=_build_position_effect(subtype, state_before, state_after),
                display_group=_build_display_group(subtype),
                display_label=_build_display_label(subtype),
                event_list_section=_build_event_list_section(subtype),
                chart_marker_kind=_build_chart_marker_kind(subtype),
                geometry_effect=_build_geometry_effect(subtype),
                state_delta_full=state_delta_full,
                state_delta_essential=state_delta_essential,
                raw_event_ref=f"{trade.signal_id}:{idx}:{entry.event_type}",
            )
        )

    has_raw_fill_events = any((entry.event_type or "").upper() == "FILL" for entry in event_log)
    synthetic_fills = []
    if not has_raw_fill_events:
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
