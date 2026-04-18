"""Build the payload used by the single-trade ECharts renderer."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult
from src.signal_chain_lab.market.data_models import Candle
from src.signal_chain_lab.policy_report.event_normalizer import (
    ReportCanonicalEvent,
    Subtype,
    normalize_events,
)

_ORDERED_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]

_LEVEL_COLORS: dict[str, str] = {
    "ENTRY_LIMIT": "#1d4ed8",
    "ENTRY_MARKET": "#7c3aed",
    "SL": "#b91c1c",
    "TP": "#15803d",
    "AVG_ENTRY": "#0891b2",
}

_EVENT_KIND_MAP: dict[str, str] = {
    Subtype.SETUP_CREATED:            "SETUP_CREATED",
    Subtype.ENTRY_ORDER_ADDED:        "ENTRY_ORDER_ADDED",
    Subtype.ENTRY_FILLED_INITIAL:     "ENTRY_FILLED_INITIAL",
    Subtype.ENTRY_FILLED_SCALE_IN:    "ENTRY_FILLED_SCALE_IN",
    Subtype.STOP_MOVED:               "STOP_MOVED",
    Subtype.BREAK_EVEN_ACTIVATED:     "BREAK_EVEN_ACTIVATED",
    Subtype.EXIT_PARTIAL_TP:          "EXIT_PARTIAL_TP",
    Subtype.EXIT_PARTIAL_MANUAL:      "EXIT_PARTIAL_MANUAL",
    Subtype.EXIT_FINAL_TP:            "EXIT_FINAL_TP",
    Subtype.EXIT_FINAL_SL:            "EXIT_FINAL_SL",
    Subtype.EXIT_FINAL_MANUAL:        "EXIT_FINAL_MANUAL",
    Subtype.EXIT_FINAL_TIMEOUT:       "EXIT_FINAL_TIMEOUT",
    Subtype.PENDING_CANCELLED_TRADER: "PENDING_CANCELLED_TRADER",
    Subtype.PENDING_CANCELLED_ENGINE: "PENDING_CANCELLED_ENGINE",
    Subtype.PENDING_TIMEOUT:          "PENDING_TIMEOUT",
    Subtype.SYSTEM_NOTE:              "SYSTEM_NOTE",
    Subtype.IGNORED:                  "IGNORED",
}


def _to_epoch_ms(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _candles_to_array(candles: list[Candle]) -> list[list[object]]:
    return [
        [
            _to_epoch_ms(c.timestamp),
            c.open,
            c.close,
            c.low,
            c.high,
            c.volume,
        ]
        for c in candles
    ]


def _default_timeframe(candles_by_timeframe: dict[str, list[object]]) -> str | None:
    for timeframe in _ORDERED_TIMEFRAMES:
        if timeframe in candles_by_timeframe:
            return timeframe
    keys = list(candles_by_timeframe.keys())
    return keys[0] if keys else None


def _infer_trade_window(
    trade: TradeResult,
    event_log: list[EventLogEntry],
) -> tuple[datetime | None, datetime | None]:
    if not event_log:
        return trade.created_at, trade.closed_at
    start = trade.created_at or event_log[0].timestamp
    end = trade.closed_at or event_log[-1].timestamp
    if start and end and end < start:
        end = start
    return start, end


def _focus_window(
    trade: TradeResult,
    event_log: list[EventLogEntry],
) -> tuple[str | None, str | None]:
    start, end = _infer_trade_window(trade, event_log)
    return _to_iso(start), _to_iso(end)


def _first_fill_timestamp(event_log: list[EventLogEntry]) -> datetime | None:
    for entry in event_log:
        if (entry.event_type or "").upper() in {"FILL", "ADD_ENTRY"}:
            return entry.timestamp
    return None


def _fills_from_event_log(event_log: list[EventLogEntry]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    fills: list[dict[str, Any]] = []
    for entry in event_log:
        for snapshot in (entry.state_before or {}, entry.state_after or {}):
            plans = snapshot.get("entries_planned") or []
            plan_map = {
                str(plan.get("plan_id") or ""): plan
                for plan in plans
                if isinstance(plan, dict)
            }
            for fill in snapshot.get("fills") or []:
                if not isinstance(fill, dict):
                    continue
                key = (
                    str(fill.get("timestamp") or ""),
                    str(fill.get("plan_id") or ""),
                    str(fill.get("price") or ""),
                    str(fill.get("qty") or ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                record = dict(fill)
                record["_plan"] = plan_map.get(str(fill.get("plan_id") or ""))
                fills.append(record)
    fills.sort(key=lambda item: (str(item.get("timestamp") or ""), str(item.get("plan_id") or "")))
    return fills


def _nth_fill_timestamp(event_log: list[EventLogEntry], n: int) -> datetime | None:
    count = 0
    for entry in event_log:
        if (entry.event_type or "").upper() in {"FILL", "ADD_ENTRY"}:
            count += 1
            if count == n:
                return entry.timestamp
    return None


def _event_price(entry: EventLogEntry, trade: TradeResult) -> float | None:
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
    return trade.avg_entry_price


def _build_level_segments(
    trade: TradeResult,
    event_log: list[EventLogEntry],
) -> list[dict[str, object]]:
    start_ts, end_ts = _infer_trade_window(trade, event_log)
    if start_ts is None or end_ts is None or not event_log:
        return []

    side_upper = str(trade.side or "").upper()
    is_short = side_upper in {"SELL", "SHORT", "S"}

    first_state = event_log[0].state_after or {}
    segments: list[dict[str, object]] = []
    fills = _fills_from_event_log(event_log)
    fills_by_plan_id = {
        str(fill.get("plan_id") or ""): fill
        for fill in fills
        if fill.get("plan_id")
    }

    def add_segment(
        *,
        kind: str,
        label: str,
        price: float,
        ts_start: datetime,
        ts_end: datetime,
        style: str = "dashed",
        sequence_index: int = 0,
        source_event_id: str | None = None,
    ) -> None:
        if ts_end < ts_start:
            ts_end = ts_start
        segments.append(
            {
                "kind": kind,
                "label": label,
                "price": float(price),
                "ts_start": _to_iso(ts_start),
                "ts_end": _to_iso(ts_end),
                "color": _LEVEL_COLORS[kind],
                "style": style,
                "sequence_index": sequence_index,
                "source_event_id": source_event_id,
            }
        )

    first_fill_ts = _first_fill_timestamp(event_log)
    planned_entries = first_state.get("entries_planned") or []

    for idx, plan in enumerate(planned_entries):
        if not isinstance(plan, dict):
            continue
        price = plan.get("price")
        if not isinstance(price, (int, float)):
            continue
        entry_type = str(plan.get("order_type") or plan.get("entry_type") or "LIMIT").upper()
        kind = "ENTRY_MARKET" if entry_type == "MARKET" else "ENTRY_LIMIT"
        plan_id = str(plan.get("plan_id") or "")
        fill_record = fills_by_plan_id.get(plan_id)
        fill_ts_raw = fill_record.get("timestamp") if isinstance(fill_record, dict) else None
        fill_ts = datetime.fromisoformat(str(fill_ts_raw).replace("Z", "+00:00")) if fill_ts_raw else None
        if kind == "ENTRY_MARKET":
            # For immediate market entries the event marker is the primary representation.
            continue
        end_for_entry = fill_ts or first_fill_ts or end_ts
        add_segment(
            kind=kind,
            label=f"Entry {idx + 1}",
            price=float(price),
            ts_start=start_ts,
            ts_end=end_for_entry,
            sequence_index=idx,
            source_event_id=f"{trade.signal_id}_{idx}",
        )

    if trade.avg_entry_price is not None and trade.fills_count >= 2:
        avg_start = _nth_fill_timestamp(event_log, 2) or first_fill_ts or start_ts
        add_segment(
            kind="AVG_ENTRY",
            label="Average Entry",
            price=float(trade.avg_entry_price),
            ts_start=avg_start,
            ts_end=end_ts,
            style="solid",
        )

    active_sl_price: float | None = None
    active_sl_start: datetime | None = None
    sl_index = 0
    active_tps: dict[float, tuple[datetime, str]] = {}
    # tp_levels_ordered: engine stores TPs in hit-sequence order — preserve it
    tp_levels_ordered: list[float] = []
    prev_next_tp_idx: int | None = None
    # Tracks TPs already closed (via next_tp_index or state diff) so they are not re-added
    finalized_tps: set[float] = set()

    for idx, entry in enumerate(event_log):
        ts = entry.timestamp
        state = entry.state_after or {}

        current_sl = state.get("current_sl")
        if isinstance(current_sl, (int, float)):
            sl_price = float(current_sl)
            if active_sl_price is None:
                active_sl_price = sl_price
                active_sl_start = start_ts
            elif sl_price != active_sl_price:
                if active_sl_start is not None:
                    label = "Stop Loss initial" if sl_index == 0 else f"New Stop Loss {sl_index}"
                    add_segment(
                        kind="SL",
                        label=label,
                        price=active_sl_price,
                        ts_start=active_sl_start,
                        ts_end=ts,
                        sequence_index=sl_index,
                        source_event_id=f"{trade.signal_id}_{idx}",
                    )
                sl_index += 1
                active_sl_price = sl_price
                active_sl_start = ts

        tp_levels = [float(tp) for tp in (state.get("tp_levels") or []) if isinstance(tp, (int, float))]
        # Capture initial TP ordering as stored by the engine (engine stores in hit-sequence order)
        if not tp_levels_ordered and tp_levels:
            tp_levels_ordered = list(tp_levels)

        current_tp_set = set(tp_levels)
        active_tp_set = set(active_tps.keys())

        # Primary: detect TP hits via next_tp_index — reliable even when tp_levels is not updated
        curr_next_tp = state.get("next_tp_index")
        if (
            isinstance(curr_next_tp, int)
            and isinstance(prev_next_tp_idx, int)
            and curr_next_tp > prev_next_tp_idx
        ):
            for hit_n in range(prev_next_tp_idx, curr_next_tp):
                if hit_n < len(tp_levels_ordered):
                    hit_price = tp_levels_ordered[hit_n]
                    if hit_price in active_tps:
                        tp_start_v, tp_label_v = active_tps.pop(hit_price)
                        finalized_tps.add(hit_price)
                        add_segment(
                            kind="TP",
                            label=tp_label_v,
                            price=hit_price,
                            ts_start=tp_start_v,
                            ts_end=ts,
                            sequence_index=int(tp_label_v.removeprefix("TP")) if tp_label_v.startswith("TP") else 0,
                            source_event_id=f"{trade.signal_id}_{idx}",
                        )

        # Fallback: close TPs removed from tp_levels state (for engines that update the list)
        active_tp_set = set(active_tps.keys())
        for removed_price in sorted(active_tp_set - current_tp_set):
            tp_start_v, tp_label_v = active_tps.pop(removed_price)
            finalized_tps.add(removed_price)
            add_segment(
                kind="TP",
                label=tp_label_v,
                price=removed_price,
                ts_start=tp_start_v,
                ts_end=ts,
                sequence_index=int(tp_label_v.removeprefix("TP")) if tp_label_v.startswith("TP") else 0,
                source_event_id=f"{trade.signal_id}_{idx}",
            )

        # Add newly appearing TPs; skip prices already finalized
        active_tp_set = set(active_tps.keys())
        for price in sorted(current_tp_set - active_tp_set, reverse=is_short):
            if price in finalized_tps:
                continue
            label = f"TP{len(active_tps) + len([s for s in segments if s['kind'] == 'TP']) + 1}"
            active_tps[price] = (start_ts, label)

        if isinstance(curr_next_tp, int):
            prev_next_tp_idx = curr_next_tp

    if active_sl_price is not None and active_sl_start is not None:
        label = "Stop Loss initial" if sl_index == 0 else f"New Stop Loss {sl_index}"
        add_segment(
            kind="SL",
            label=label,
            price=active_sl_price,
            ts_start=active_sl_start,
            ts_end=end_ts,
            sequence_index=sl_index,
        )

    # Remaining active TPs: iterate in engine hit order
    for price in (tp_levels_ordered if tp_levels_ordered else sorted(active_tps.keys(), reverse=is_short)):
        if price not in active_tps:
            continue
        tp_start_v, tp_label_v = active_tps[price]
        add_segment(
            kind="TP",
            label=tp_label_v,
            price=price,
            ts_start=tp_start_v,
            ts_end=end_ts,
            sequence_index=int(tp_label_v.removeprefix("TP")) if tp_label_v.startswith("TP") else 0,
        )

    return segments


def _rail_lane_key(event: ReportCanonicalEvent) -> str:
    return event.subtype


def _build_events(
    canonical_events: list[ReportCanonicalEvent],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for event in canonical_events:
        ts_ms = _to_epoch_ms(datetime.fromisoformat(event.ts))
        if ts_ms is None:
            continue
        if event.visual.lane_key == "sidebar":
            placement = "sidebar"
        else:
            placement = "rail" if event.visual.lane_key == "rail" or event.price_anchor is None else "chart"
        kind = _EVENT_KIND_MAP.get(event.subtype, event.subtype)
        items.append(
            {
                "event_id": event.id,
                "ts": ts_ms,
                "exact_ts": event.ts,
                "price": event.price_anchor,
                "kind": kind,
                "subtype": event.subtype,
                "label": event.title,
                "summary": event.summary,
                "source": event.source,
                "phase": event.phase,
                "placement": placement,
                "chart_anchor_mode": event.visual.chart_anchor_mode,
                "lane_key": _rail_lane_key(event),
                "reason": event.reason,
                "impact": {
                    "position": event.impact.position,
                    "risk": event.impact.risk,
                    "result": event.impact.result,
                },
            }
        )
    return items


def _build_legend_items() -> list[dict[str, str]]:
    return [
        {"key": "entries_planned", "label": "EL levels", "color": _LEVEL_COLORS["ENTRY_LIMIT"], "shape": "line"},
        {"key": "entry_market", "label": "ME levels", "color": _LEVEL_COLORS["ENTRY_MARKET"], "shape": "line"},
        {"key": "avg_entry", "label": "AVG entry", "color": _LEVEL_COLORS["AVG_ENTRY"], "shape": "line"},
        {"key": "sl", "label": "SL", "color": _LEVEL_COLORS["SL"], "shape": "line"},
        {"key": "tps", "label": "TP levels", "color": _LEVEL_COLORS["TP"], "shape": "line"},
        {"key": "ev_ENTRY_FILLED_INITIAL", "label": "Entry filled", "color": "#1d4ed8", "shape": "dot"},
        {"key": "ev_ENTRY_FILLED_SCALE_IN", "label": "Scale-in filled", "color": "#2563eb", "shape": "dot"},
        {"key": "ev_EXIT_PARTIAL_TP", "label": "TP hit", "color": "#15803d", "shape": "dot"},
        {"key": "ev_EXIT_PARTIAL_MANUAL", "label": "Partial close", "color": "#ea580c", "shape": "dot"},
        {"key": "ev_EXIT_FINAL_SL", "label": "SL hit", "color": "#b91c1c", "shape": "dot"},
        {"key": "ev_EXIT_FINAL_TP", "label": "Final exit (TP)", "color": "#15803d", "shape": "dot"},
        {"key": "ev_EXIT_FINAL_MANUAL", "label": "Final exit", "color": "#ea580c", "shape": "dot"},
    ]


def _build_level_summary(event_log: list[EventLogEntry], trade: TradeResult) -> str:
    if not event_log:
        return "-"
    first_state = event_log[0].state_after or {}
    entries = [
        float(plan["price"])
        for plan in (first_state.get("entries_planned") or [])
        if isinstance(plan, dict) and isinstance(plan.get("price"), (int, float))
    ]
    stop = first_state.get("current_sl")
    tps = [float(tp) for tp in (first_state.get("tp_levels") or []) if isinstance(tp, (int, float))]
    chunks: list[str] = []
    if entries:
        chunks.append("entry=" + ", ".join(f"{value:.4f}" for value in entries))
    if isinstance(stop, (int, float)):
        chunks.append(f"sl={float(stop):.4f}")
    if tps:
        chunks.append("tp=" + ", ".join(f"{value:.4f}" for value in tps))
    if trade.avg_entry_price is not None and trade.fills_count >= 2:
        chunks.append(f"avg={float(trade.avg_entry_price):.4f}")
    return " | ".join(chunks) if chunks else "-"


def build_trade_chart_payload(
    trade: TradeResult,
    event_log: list[EventLogEntry],
    candles_by_timeframe: dict[str, list[Candle]],
) -> dict[str, object]:
    candles_serialized: dict[str, list[list[object]]] = {
        timeframe: _candles_to_array(candles)
        for timeframe, candles in candles_by_timeframe.items()
        if candles
    }
    canonical_events = normalize_events(trade, event_log)

    return {
        "meta": {
            "signal_id": trade.signal_id,
            "symbol": trade.symbol,
            "side": trade.side,
            "policy_name": trade.policy_name,
            "default_timeframe": _default_timeframe(candles_serialized),
            "fills_count": trade.fills_count,
            "level_summary": _build_level_summary(event_log, trade),
            "focus_start_ts": _focus_window(trade, event_log)[0],
            "focus_end_ts": _focus_window(trade, event_log)[1],
        },
        "candles_by_timeframe": candles_serialized,
        "level_segments": _build_level_segments(trade, event_log),
        "events": _build_events(canonical_events),
        "legend_items": _build_legend_items(),
    }
