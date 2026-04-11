"""Trade state machine: transitions driven by market events and signal updates."""
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from src.signal_chain_lab.domain.enums import CloseReason, EventProcessingStatus, EventType, TradeStatus

_logger = logging.getLogger(__name__)
from src.signal_chain_lab.domain.events import CanonicalEvent
from src.signal_chain_lab.domain.results import EventLogEntry
from src.signal_chain_lab.domain.trade_state import EntryPlan, TradeState
from src.signal_chain_lab.policies.base import PolicyConfig


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


def _get_tp_absolute_weights(n_tps: int, distribution: str) -> list[float]:
    """Return the fraction of total position to close at each TP level.

    The returned list sums to 1.0 and has length ``n_tps``.
    Supported distributions:
      - "original" / "equal": equal split across all TPs
      - "tp_50_30_20": 50 % / 30 % / 20 % for 3 TPs; predefined tables for 2–4 TPs;
        falls back to equal for any other count with a log warning.
    Unknown distribution names fall back silently to equal.
    """
    if n_tps <= 0:
        return []
    if n_tps == 1:
        return [1.0]

    if distribution == "tp_50_30_20":
        predefined: dict[int, list[float]] = {
            2: [0.5, 0.5],
            3: [0.5, 0.3, 0.2],
            4: [0.5, 0.3, 0.15, 0.05],
        }
        if n_tps in predefined:
            return list(predefined[n_tps])
        _logger.warning(
            "tp_50_30_20 has no predefined table for %d TPs — falling back to equal split", n_tps
        )

    # equal / original / unknown → equal split
    base = 1.0 / n_tps
    weights = [base] * (n_tps - 1)
    weights.append(max(0.0, 1.0 - sum(weights)))
    return weights


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
    entry_plan_type: str | None,
    has_averaging_plan: bool,
    order_types: list[str],
    count: int,
    policy: PolicyConfig | None,
) -> list[float]:
    if count <= 0 or policy is None or policy.entry.entry_split is None:
        return [1.0 / count] * count if count > 0 else []

    entry_split = policy.entry.entry_split
    normalized_entry_type = entry_type.upper()
    normalized_structure = (entry_structure or "").upper()
    normalized_plan_type = (entry_plan_type or "").upper()

    if normalized_entry_type == "ZONE" and entry_split.ZONE is not None:
        return _normalize_weight_map(entry_split.ZONE.weights, count)

    if normalized_entry_type == "MARKET" and entry_split.MARKET is not None:
        if count == 1:
            return _normalize_weight_map(entry_split.MARKET.single.weights, count)
        return _normalize_weight_map(entry_split.MARKET.averaging.weights, count)

    if entry_split.LIMIT is not None:
        if normalized_structure == "RANGE" and entry_split.LIMIT.range is not None:
            return _normalize_weight_map(entry_split.LIMIT.range.weights, count)
        if normalized_structure == "LADDER":
            return _normalize_weight_map(entry_split.LIMIT.ladder.weights, count)
        if has_averaging_plan or "AVERAGING" in normalized_plan_type:
            return _normalize_weight_map(entry_split.LIMIT.averaging.weights, count)

    if normalized_entry_type in {"LIMIT", "AVERAGING"} and entry_split.LIMIT is not None:
        if count == 1:
            return _normalize_weight_map(entry_split.LIMIT.single.weights, count)
        return _normalize_weight_map(entry_split.LIMIT.averaging.weights, count)

    if len(order_types) == 1 and order_types[0] == "market" and entry_split.MARKET is not None:
        return _normalize_weight_map(entry_split.MARKET.single.weights, count)
    if "market" in order_types and entry_split.MARKET is not None:
        return _normalize_weight_map(entry_split.MARKET.averaging.weights, count)
    if entry_split.LIMIT is not None:
        if count == 1:
            return _normalize_weight_map(entry_split.LIMIT.single.weights, count)
        return _normalize_weight_map(entry_split.LIMIT.averaging.weights, count)

    return [1.0 / count] * count


def _entry_specs_from_payload(payload: dict[str, Any], policy: PolicyConfig | None) -> list[dict[str, Any]]:
    raw_entries = payload.get("entry_plan_entries") or payload.get("entries")
    entry_type = str(payload.get("entry_type") or "LIMIT").upper()
    entry_structure = payload.get("entry_structure")
    entry_plan_type = payload.get("entry_plan_type")
    has_averaging_plan = bool(payload.get("has_averaging_plan"))

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
                specs = [specs[0]]
            elif split_mode == "midpoint" and len(specs) >= 2:
                low = float(specs[0]["price"])
                high = float(specs[1]["price"])
                specs = [
                    {
                        "role": "primary",
                        "order_type": "limit",
                        "price": (low + high) / 2,
                    }
                ]
        if specs:
            weights = _weights_from_policy(
                entry_type=entry_type,
                entry_structure=str(entry_structure) if entry_structure is not None else None,
                entry_plan_type=str(entry_plan_type) if entry_plan_type is not None else None,
                has_averaging_plan=has_averaging_plan,
                order_types=[str(item["order_type"]) for item in specs],
                count=len(specs),
                policy=policy,
            )
            for spec, weight in zip(specs, weights):
                spec["size_ratio"] = weight
            return specs

    entry_prices = list(payload.get("entry_prices") or [])
    normalized_type = entry_type.upper()

    if normalized_type == "ZONE" and len(entry_prices) >= 2:
        zone_cfg = policy.entry.entry_split.ZONE if policy and policy.entry.entry_split else None
        split_mode = zone_cfg.split_mode if zone_cfg is not None else "endpoints"
        low = float(entry_prices[0])
        high = float(entry_prices[1])
        if split_mode == "midpoint":
            midpoint = (low + high) / 2
            prices = [midpoint]
        elif split_mode == "three_way":
            midpoint = (low + high) / 2
            prices = [low, midpoint, high]
        else:
            prices = [low, high]
        weights = _weights_from_policy(
            entry_type="ZONE",
            entry_structure="RANGE",
            entry_plan_type="SINGLE",
            has_averaging_plan=False,
            order_types=["limit"] * len(prices),
            count=len(prices),
            policy=policy,
        )
        return [
            {
                "role": "primary" if index == 0 else "averaging",
                "order_type": "limit",
                "price": price,
                "size_ratio": weights[index],
            }
            for index, price in enumerate(prices)
        ]

    if entry_prices:
        default_order_type = "market" if normalized_type == "MARKET" else "limit"
        weights = _weights_from_policy(
            entry_type=normalized_type,
            entry_structure=str(entry_structure) if entry_structure is not None else None,
            entry_plan_type=str(entry_plan_type) if entry_plan_type is not None else None,
            has_averaging_plan=has_averaging_plan,
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
        tp_dist = policy.tp.tp_distribution if policy is not None else "original"
        if isinstance(tp_dist, str):
            dist_name = tp_dist
        else:
            dist_name = getattr(tp_dist, "mode", "original")
        abs_weights = _get_tp_absolute_weights(n_tps, dist_name)
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
        new_sl = event.payload.get("new_sl_price")
        if state.open_size <= 0 or new_sl is None:
            status = EventProcessingStatus.IGNORED
            executed_action = None
            reason = "move_stop_without_open_position"
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
