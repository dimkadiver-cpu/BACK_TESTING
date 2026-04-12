"""Trade state machine: transitions driven by market events and signal updates."""
from __future__ import annotations

import logging
import warnings
from copy import deepcopy
from typing import Any

from src.signal_chain_lab.domain.enums import CloseReason, EventProcessingStatus, EventSource, EventType, TradeStatus

_logger = logging.getLogger(__name__)

# ── Canonical entry_plan_type → (entry_type, entry_structure) mappings ────────
_PLAN_TYPE_CANONICAL: dict[str, tuple[str, str]] = {
    "SINGLE_MARKET": ("MARKET", "ONE_SHOT"),
    "SINGLE_LIMIT": ("LIMIT", "ONE_SHOT"),
    "MARKET_WITH_LIMIT_AVERAGING": ("MARKET", "TWO_STEP"),
    "LIMIT_WITH_LIMIT_AVERAGING": ("LIMIT", "TWO_STEP"),
}


def normalize_entry_semantics(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert legacy entry semantics to the canonical (entry_type, entry_structure) form.

    Canonical values after normalization:
      entry_type      → MARKET | LIMIT
      entry_structure → ONE_SHOT | TWO_STEP | RANGE | LADDER

    Legacy values handled:
      entry_structure = SINGLE          → ONE_SHOT
      entry_type      = ZONE            → LIMIT + RANGE
      entry_type      = AVERAGING       → LIMIT + TWO_STEP (2 entries) / LADDER (3+)
      entry_plan_type = SINGLE_MARKET   → MARKET + ONE_SHOT
      entry_plan_type = SINGLE_LIMIT    → LIMIT  + ONE_SHOT
      entry_plan_type = MARKET_WITH_LIMIT_AVERAGING → MARKET + TWO_STEP
      entry_plan_type = LIMIT_WITH_LIMIT_AVERAGING  → LIMIT  + TWO_STEP

    Emits DeprecationWarning for every legacy value encountered.
    Returns a shallow copy of the payload with normalised fields written back.
    """
    result = dict(payload)

    # Capture originals before any conversion
    raw_entry_type = (result.get("entry_type") or "").upper()
    raw_entry_structure = (result.get("entry_structure") or "").upper()
    entry_plan_type = (result.get("entry_plan_type") or "").upper()

    # Count available entry levels for inference
    raw_entries = result.get("entry_plan_entries") or result.get("entries") or []
    entry_prices = result.get("entry_prices") or []
    entry_count = len(raw_entries) if raw_entries else len(entry_prices)

    etype = raw_entry_type or "LIMIT"
    estruture = raw_entry_structure

    # ── Step 1: entry_structure SINGLE → ONE_SHOT ──────────────────────────
    if estruture == "SINGLE":
        warnings.warn(
            "entry_structure='SINGLE' is deprecated. Use 'ONE_SHOT'.",
            DeprecationWarning,
            stacklevel=3,
        )
        estruture = "ONE_SHOT"

    # ── Step 2: entry_type ZONE → LIMIT + RANGE ────────────────────────────
    if etype == "ZONE":
        warnings.warn(
            "entry_type='ZONE' is deprecated. "
            "Use entry_type='LIMIT' with entry_structure='RANGE'.",
            DeprecationWarning,
            stacklevel=3,
        )
        etype = "LIMIT"
        estruture = estruture or "RANGE"

    # ── Step 3: entry_type AVERAGING → LIMIT + TWO_STEP / LADDER ───────────
    elif etype == "AVERAGING":
        warnings.warn(
            "entry_type='AVERAGING' is deprecated. "
            "Use entry_type='LIMIT' with entry_structure='TWO_STEP' or 'LADDER'.",
            DeprecationWarning,
            stacklevel=3,
        )
        etype = "LIMIT"
        if not estruture:
            estruture = "LADDER" if entry_count >= 3 else "TWO_STEP"

    # ── Step 4: entry_plan_type fills missing entry_type / entry_structure ──
    if entry_plan_type in _PLAN_TYPE_CANONICAL:
        pt_type, pt_structure = _PLAN_TYPE_CANONICAL[entry_plan_type]
        warnings.warn(
            f"entry_plan_type='{entry_plan_type}' as a dispatch source is deprecated. "
            f"Set entry_type='{pt_type}' and entry_structure='{pt_structure}' directly.",
            DeprecationWarning,
            stacklevel=3,
        )
        # Only override fields that were absent in the original payload
        if not raw_entry_type:
            etype = pt_type
        if not raw_entry_structure:
            estruture = estruture or pt_structure

    # ── Step 5: inference from entry count (when structure still unknown) ───
    if not estruture and entry_count > 0:
        if entry_count == 1:
            estruture = "ONE_SHOT"
        elif entry_count == 2:
            if raw_entries and isinstance(raw_entries, list):
                roles = {
                    str(e.get("role", "")).upper()
                    for e in raw_entries
                    if isinstance(e, dict)
                }
                if "PRIMARY" in roles and ("AVERAGING" in roles or "SECONDARY" in roles):
                    estruture = "TWO_STEP"
                else:
                    _logger.warning(
                        "normalize_entry_semantics: 2 entries with unclear roles — "
                        "defaulting entry_structure to TWO_STEP"
                    )
                    estruture = "TWO_STEP"
            else:
                _logger.warning(
                    "normalize_entry_semantics: 2 entry_prices without entry_structure — "
                    "defaulting entry_structure to TWO_STEP"
                )
                estruture = "TWO_STEP"
        else:
            estruture = "LADDER"

    # ── Write canonical values back ─────────────────────────────────────────
    result["entry_type"] = etype
    if estruture:
        result["entry_structure"] = estruture

    return result


def normalize_alias_fields(payload: dict) -> dict:
    """Map legacy/alias field names to their canonical counterparts.

    Canonical mappings applied:
      side                    → direction
      new_stop_level          → new_sl_level
      new_stop_price          → new_sl_price
      new_stop_reference_text → new_sl_reference
      partial_close_percent   → close_pct

    Returns a shallow copy of payload with canonical fields written.
    Legacy keys are kept in the copy for backward compatibility with
    consumers that have not yet been updated.
    """
    result = dict(payload)

    if "side" in result and "direction" not in result:
        result["direction"] = result["side"]

    if "new_stop_level" in result and "new_sl_level" not in result:
        result["new_sl_level"] = result["new_stop_level"]

    if "new_stop_price" in result and "new_sl_price" not in result:
        result["new_sl_price"] = result["new_stop_price"]

    if "new_stop_reference_text" in result and "new_sl_reference" not in result:
        result["new_sl_reference"] = result["new_stop_reference_text"]

    if "partial_close_percent" in result and "close_pct" not in result:
        result["close_pct"] = result["partial_close_percent"]

    return result


from src.signal_chain_lab.domain.events import CanonicalEvent
from src.signal_chain_lab.domain.results import EventLogEntry
from src.signal_chain_lab.domain.trade_state import EntryPlan, TradeState
from src.signal_chain_lab.policies.base import PolicyConfig, TpCloseConfig


def _snapshot(state: TradeState) -> dict:
    return state.model_dump(mode="json")


def _warning(state: TradeState) -> None:
    state.warnings_count += 1
    state.ignored_events_count += 1


def _realize_pnl_for_close(state: TradeState, exit_price: float) -> None:
    if state.open_size <= 0 or state.avg_entry_price is None:
        return
    direction = 1.0 if state.side.upper() in {"BUY", "LONG"} else -1.0
    state.realized_pnl += (float(exit_price) - state.avg_entry_price) * state.open_size * direction
    state.unrealized_pnl = 0.0


def _equal_weights(n_tps: int) -> list[float]:
    """Return a uniform weight list of length ``n_tps`` that sums exactly to 1.0.

    The last element absorbs any floating-point remainder so the sum is
    always exactly 1.0 regardless of whether ``n_tps`` divides evenly.
    """
    if n_tps <= 0:
        return []
    if n_tps == 1:
        return [1.0]
    base = 1.0 / n_tps
    weights = [base] * (n_tps - 1)
    weights.append(max(0.0, 1.0 - sum(weights)))
    return weights


def _compute_tp_close_weights(n_tps: int, cd: TpCloseConfig) -> list[float]:
    """Return absolute close-weight list for ``n_tps`` levels from policy config.

    mode "equal":
      Uniform split.  Last level absorbs floating-point remainder.

    mode "table":
      Reads ``cd.table[n_tps]``.  Values are normalised to sum 1.0.
      Falls back to equal split (+ warning) when the row is missing or invalid.
    """
    if n_tps <= 0:
        return []
    if n_tps == 1:
        return [1.0]

    if cd.mode == "table":
        row = cd.table.get(n_tps)
        if row and len(row) == n_tps:
            total = sum(float(v) for v in row)
            if total > 0:
                return [float(v) / total for v in row]
        _logger.warning(
            "tp close_distribution table has no valid row for %d TPs — using equal split", n_tps
        )

    return _equal_weights(n_tps)


def _weights_to_fractions_of_current(absolute_weights: list[float]) -> list[float]:
    """Convert absolute-weight distribution to fraction-of-remaining-open fractions.

    Given ``absolute_weights[i]`` = fraction of TOTAL initial position to close at TP i,
    returns ``fractions[i]`` = fraction of CURRENT open_size to close at TP i.
    The last element is always 1.0 (close all remaining).

    Example – equal with 3 TPs, weights=[1/3, 1/3, 1/3]:
      f0 = (1/3)/1.0  = 0.333
      f1 = (1/3)/0.667 = 0.500
      f2 = 1.0
    """
    n = len(absolute_weights)
    fractions: list[float] = []
    remaining = 1.0
    for i, w in enumerate(absolute_weights):
        if i == n - 1 or remaining <= 1e-10:
            fractions.append(1.0)
        else:
            fractions.append(min(1.0, w / remaining))
        remaining = max(0.0, remaining - w)
    return fractions


def _normalize_order_type(value: Any, *, default: str = "limit") -> str:
    if not isinstance(value, str):
        return default
    lowered = value.lower()
    if lowered in {"market", "limit"}:
        return lowered
    return default


def _normalize_weight_map(raw: dict[str, float] | None, count: int) -> list[float]:
    if count <= 0:
        return []
    if not raw:
        return [1.0 / count] * count

    values: list[float] = []
    for index in range(count):
        key = f"E{index + 1}"
        value = float(raw.get(key, 0.0))
        values.append(max(0.0, value))

    total = sum(values)
    if total <= 0.0:
        return [1.0 / count] * count
    return [value / total for value in values]


def _limit_range_split_mode(policy: PolicyConfig | None) -> str:
    if policy is None or policy.entry.entry_split is None or policy.entry.entry_split.LIMIT is None:
        return "endpoints"
    range_cfg = policy.entry.entry_split.LIMIT.range
    if range_cfg is None:
        return "endpoints"
    return range_cfg.split_mode


def _weights_from_policy(
    *,
    entry_type: str,
    entry_structure: str | None,
    order_types: list[str],
    count: int,
    policy: PolicyConfig | None,
) -> list[float]:
    if count <= 0 or policy is None or policy.entry.entry_split is None:
        return [1.0 / count] * count if count > 0 else []

    entry_split = policy.entry.entry_split
    norm_type = entry_type.upper()
    norm_structure = (entry_structure or "").upper()

    # entry_structure drives the branch; entry_type disambiguates MARKET vs LIMIT
    # for ONE_SHOT and TWO_STEP.  All legacy values must be normalised via
    # normalize_entry_semantics() before reaching this function.

    if norm_structure == "ONE_SHOT":
        if norm_type == "MARKET" and entry_split.MARKET is not None:
            return _normalize_weight_map(entry_split.MARKET.single.weights, count)
        if entry_split.LIMIT is not None:
            return _normalize_weight_map(entry_split.LIMIT.single.weights, count)

    elif norm_structure == "TWO_STEP":
        first_is_market = bool(order_types) and order_types[0] == "market"
        if (first_is_market or norm_type == "MARKET") and entry_split.MARKET is not None:
            return _normalize_weight_map(entry_split.MARKET.averaging.weights, count)
        if entry_split.LIMIT is not None:
            return _normalize_weight_map(entry_split.LIMIT.averaging.weights, count)

    elif norm_structure == "RANGE":
        if entry_split.LIMIT is not None and entry_split.LIMIT.range is not None:
            return _normalize_weight_map(entry_split.LIMIT.range.weights, count)

    elif norm_structure == "LADDER":
        if entry_split.LIMIT is not None:
            return _normalize_weight_map(entry_split.LIMIT.ladder.weights, count)

    return [1.0 / count] * count


def _entry_specs_from_payload(payload: dict[str, Any], policy: PolicyConfig | None) -> list[dict[str, Any]]:
    # Normalise legacy semantics before any dispatch logic runs
    payload = normalize_entry_semantics(payload)

    raw_entries = payload.get("entry_plan_entries") or payload.get("entries")
    entry_type = str(payload.get("entry_type") or "LIMIT").upper()
    entry_structure = payload.get("entry_structure")

    if isinstance(raw_entries, list) and raw_entries:
        specs: list[dict[str, Any]] = []
        for index, item in enumerate(raw_entries):
            if not isinstance(item, dict):
                continue
            price = item.get("price")
            order_type = _normalize_order_type(item.get("order_type"), default="limit")
            role = "primary" if index == 0 else "averaging"
            specs.append({"role": role, "order_type": order_type, "price": price})
        if specs and str(entry_structure or "").upper() == "RANGE":
            split_mode = _limit_range_split_mode(policy)
            if split_mode == "firstpoint":
                # Single order at the first (lowest) price of the range.
                # size_ratio = 1.0 (full position at one level).
                specs = [specs[0]]
            elif split_mode == "lastpoint":
                # Single order at the last (highest) price of the range.
                # size_ratio = 1.0 (full position at one level).
                specs = [specs[-1]]
            elif split_mode == "midpoint" and len(specs) >= 2:
                # Single order at the arithmetic midpoint of the range.
                # size_ratio = 1.0 (full position at the midpoint level).
                low = float(specs[0]["price"])
                high = float(specs[1]["price"])
                specs = [
                    {
                        "role": "primary",
                        "order_type": "limit",
                        "price": (low + high) / 2,
                    }
                ]
            # endpoints: keep all specs as-is; weights from LIMIT.range.weights apply.
        if specs:
            weights = _weights_from_policy(
                entry_type=entry_type,
                entry_structure=str(entry_structure) if entry_structure is not None else None,
                order_types=[str(item["order_type"]) for item in specs],
                count=len(specs),
                policy=policy,
            )
            for spec, weight in zip(specs, weights):
                spec["size_ratio"] = weight
            return specs

    entry_prices = list(payload.get("entry_prices") or [])
    normalized_type = entry_type.upper()

    if entry_prices:
        default_order_type = "market" if normalized_type == "MARKET" else "limit"
        weights = _weights_from_policy(
            entry_type=normalized_type,
            entry_structure=str(entry_structure) if entry_structure is not None else None,
            order_types=[default_order_type] * len(entry_prices),
            count=len(entry_prices),
            policy=policy,
        )
        return [
            {
                "role": "primary" if index == 0 else "averaging",
                "order_type": default_order_type,
                "price": float(price) if price is not None else None,
                "size_ratio": weights[index],
            }
            for index, price in enumerate(entry_prices)
        ]

    return [
        {
            "role": "primary",
            "order_type": _normalize_order_type(payload.get("entry_type"), default="market"),
            "price": None,
            "size_ratio": 1.0,
        }
    ]


def _apply_open_signal(
    state: TradeState,
    event: CanonicalEvent,
    *,
    policy: PolicyConfig | None = None,
) -> tuple[str, EventProcessingStatus, str | None]:
    payload = event.payload
    entry_specs = _entry_specs_from_payload(payload, policy)

    # Limit number of entry levels used by the policy
    if policy is not None and policy.entry.max_entries_to_use is not None:
        limit = int(policy.entry.max_entries_to_use)
        if limit > 0 and len(entry_specs) > limit:
            entry_specs = entry_specs[:limit]
            # Re-normalize size_ratio so remaining entries sum to 1.0
            total_ratio = sum(float(s["size_ratio"]) for s in entry_specs)
            if total_ratio > 0:
                for s in entry_specs:
                    s["size_ratio"] = float(s["size_ratio"]) / total_ratio

    state.entries_planned = [
        EntryPlan(
            role=spec["role"],
            order_type=spec["order_type"],
            price=spec["price"],
            size_ratio=float(spec["size_ratio"]),
            label=f"E{index + 1}",
            sequence=event.sequence,
            activation_ts=event.timestamp,
        )
        for index, spec in enumerate(entry_specs)
    ]
    state.initial_sl = payload.get("sl_price")
    state.current_sl = payload.get("sl_price")

    # Apply TP policy: limit count and compute per-level close fractions
    raw_tp_levels: list[float] = list(payload.get("tp_levels") or [])
    if policy is not None and policy.tp.use_tp_count is not None:
        limit = int(policy.tp.use_tp_count)
        if limit > 0:
            raw_tp_levels = raw_tp_levels[:limit]
    state.tp_levels = raw_tp_levels

    n_tps = len(state.tp_levels)
    if n_tps > 0:
        cd = policy.tp.close_distribution if policy is not None else TpCloseConfig()
        abs_weights = _compute_tp_close_weights(n_tps, cd)
        state.tp_close_fractions = _weights_to_fractions_of_current(abs_weights)
    else:
        state.tp_close_fractions = []

    state.pending_size = sum(plan.size_ratio for plan in state.entries_planned)
    state.status = TradeStatus.PENDING
    state.created_at = event.timestamp
    return "OPEN_SIGNAL", EventProcessingStatus.APPLIED, None


def apply_event(state: TradeState, event: CanonicalEvent, *, policy: PolicyConfig | None = None) -> EventLogEntry:
    before_state = deepcopy(state)
    status = EventProcessingStatus.APPLIED
    executed_action = event.event_type.value
    reason: str | None = None

    if event.event_type == EventType.OPEN_SIGNAL:
        executed_action, status, reason = _apply_open_signal(state, event, policy=policy)
    elif event.event_type == EventType.ADD_ENTRY:
        if state.status in {TradeStatus.CLOSED, TradeStatus.CANCELLED, TradeStatus.EXPIRED, TradeStatus.INVALID}:
            status = EventProcessingStatus.IGNORED
            executed_action = None
            reason = "add_entry_on_terminal_state"
            _warning(state)
        elif (
            policy is not None
            and event.source == EventSource.TRADER
            and (not policy.entry.allow_add_entry_updates or not policy.updates.apply_add_entry)
        ):
            status = EventProcessingStatus.IGNORED
            executed_action = None
            reason = "add_entry_disabled_by_policy"
            _warning(state)
        else:
            state.entries_planned.append(
                EntryPlan(
                    role="averaging",
                    order_type=event.payload.get("order_type", "limit"),
                    price=event.payload.get("price"),
                    size_ratio=float(event.payload.get("size_ratio", 1.0)),
                    sequence=event.sequence,
                    activation_ts=event.timestamp,
                )
            )
            state.pending_size += float(event.payload.get("size_ratio", 1.0))
    elif event.event_type == EventType.MOVE_STOP:
        if state.open_size <= 0:
            status = EventProcessingStatus.IGNORED
            executed_action = None
            reason = "move_stop_without_open_position"
            _warning(state)
        elif (
            policy is not None
            and event.source == EventSource.TRADER
            and not policy.updates.apply_move_stop
        ):
            status = EventProcessingStatus.IGNORED
            executed_action = None
            reason = "move_stop_disabled_by_policy"
            _warning(state)
        else:
            new_sl = event.payload.get("new_sl_price")
            if new_sl is None:
                # None = trader-signalled break-even (parser couldn't resolve price)
                if state.avg_entry_price is not None:
                    state.current_sl = state.avg_entry_price
                else:
                    status = EventProcessingStatus.IGNORED
                    executed_action = None
                    reason = "move_stop_be_without_avg_entry"
                    _warning(state)
            elif isinstance(new_sl, str):
                # Indicative reference: "tp1", "tp2", etc.
                ref = new_sl.strip().lower()
                if ref.startswith("tp"):
                    try:
                        tp_idx = int(ref[2:]) - 1
                        if 0 <= tp_idx < len(state.tp_levels):
                            state.current_sl = state.tp_levels[tp_idx]
                        else:
                            status = EventProcessingStatus.IGNORED
                            executed_action = None
                            reason = f"move_stop_tp_ref_out_of_range:{ref}"
                            _warning(state)
                    except (ValueError, IndexError):
                        status = EventProcessingStatus.IGNORED
                        executed_action = None
                        reason = f"move_stop_unknown_sl_reference:{new_sl}"
                        _warning(state)
                else:
                    status = EventProcessingStatus.IGNORED
                    executed_action = None
                    reason = f"move_stop_unknown_sl_reference:{new_sl}"
                    _warning(state)
            else:
                state.current_sl = float(new_sl)
    elif event.event_type == EventType.MOVE_STOP_TO_BE:
        if state.open_size <= 0 or state.avg_entry_price is None:
            status = EventProcessingStatus.IGNORED
            executed_action = None
            reason = "move_stop_to_be_without_fill"
            _warning(state)
        else:
            state.current_sl = state.avg_entry_price
    elif event.event_type == EventType.CLOSE_PARTIAL:
        if state.open_size <= 0:
            status = EventProcessingStatus.IGNORED
            executed_action = None
            reason = "close_partial_without_open_position"
            _warning(state)
        elif (
            policy is not None
            and event.source == EventSource.TRADER
            and not policy.updates.apply_close_partial
        ):
            status = EventProcessingStatus.IGNORED
            executed_action = None
            reason = "close_partial_disabled_by_policy"
            _warning(state)
        else:
            close_pct = float(event.payload.get("close_pct", 0.5))
            closed_qty = min(state.open_size, state.open_size * close_pct)
            close_price = event.payload.get("close_price")
            if close_price is not None and state.avg_entry_price is not None and closed_qty > 0:
                direction = 1.0 if state.side.upper() in {"BUY", "LONG"} else -1.0
                state.realized_pnl += (float(close_price) - state.avg_entry_price) * closed_qty * direction
            state.open_size -= closed_qty
            state.status = TradeStatus.PARTIALLY_CLOSED if state.open_size > 0 else TradeStatus.CLOSED
            if state.open_size <= 0:
                state.close_reason = CloseReason.MANUAL
                state.closed_at = event.timestamp
    elif event.event_type == EventType.CLOSE_FULL:
        if state.open_size <= 0 and state.pending_size <= 0:
            status = EventProcessingStatus.IGNORED
            executed_action = None
            reason = "close_full_without_position"
            _warning(state)
        elif (
            policy is not None
            and event.source == EventSource.TRADER
            and not policy.updates.apply_close_full
        ):
            status = EventProcessingStatus.IGNORED
            executed_action = None
            reason = "close_full_disabled_by_policy"
            _warning(state)
        else:
            close_price = event.payload.get("close_price")
            if close_price is not None:
                _realize_pnl_for_close(state, float(close_price))
            state.open_size = 0.0
            state.pending_size = 0.0
            state.status = TradeStatus.CLOSED
            close_reason = event.payload.get("reason")
            if close_reason == "chain_timeout":
                state.close_reason = CloseReason.EXPIRED
                state.status = TradeStatus.EXPIRED
            elif close_reason == "tp_hit":
                state.close_reason = CloseReason.TP
            elif close_reason == "sl_hit":
                state.close_reason = CloseReason.SL
            else:
                state.close_reason = CloseReason.MANUAL
            state.closed_at = event.timestamp
    elif event.event_type == EventType.CANCEL_PENDING:
        if state.pending_size <= 0:
            status = EventProcessingStatus.IGNORED
            executed_action = None
            reason = "cancel_pending_without_pending"
            _warning(state)
        elif (
            policy is not None
            and event.source == EventSource.TRADER
            and not policy.updates.apply_cancel_pending
        ):
            status = EventProcessingStatus.IGNORED
            executed_action = None
            reason = "cancel_pending_disabled_by_policy"
            _warning(state)
        else:
            state.pending_size = 0.0
            if state.open_size <= 0:
                if event.payload.get("reason") == "pending_timeout":
                    state.status = TradeStatus.EXPIRED
                    state.close_reason = CloseReason.TIMEOUT
                else:
                    state.status = TradeStatus.CANCELLED
                    state.close_reason = CloseReason.CANCELLED
                state.closed_at = event.timestamp

    return EventLogEntry(
        timestamp=event.timestamp,
        signal_id=event.signal_id,
        event_type=event.event_type.value,
        source=event.source.value,
        requested_action=event.event_type.value,
        executed_action=executed_action,
        processing_status=status,
        reason=reason,
        raw_text=str(event.payload.get("raw_text")) if event.payload.get("raw_text") is not None else None,
        state_before=_snapshot(before_state),
        state_after=_snapshot(state),
    )
