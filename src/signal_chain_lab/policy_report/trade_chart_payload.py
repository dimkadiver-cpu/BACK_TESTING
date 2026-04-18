"""Build the payload used by the single-trade ECharts renderer."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult
from src.signal_chain_lab.market.data_models import Candle
from src.signal_chain_lab.policy_report.event_normalizer import (
    ReportCanonicalEvent,
    Subtype,
    canonical_event_badge_class,
    canonical_event_legend_items,
    canonical_event_marker_color,
    canonical_event_marker_symbol,
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
    fills = _fills_from_event_log(event_log)
    if fills:
        ts_raw = fills[0].get("timestamp")
        if ts_raw:
            return datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
    for entry in event_log:
        if (entry.event_type or "").upper() == "FILL":
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


def _plan_map(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for idx, plan in enumerate(state.get("entries_planned") or []):
        if not isinstance(plan, dict):
            continue
        mapped[str(plan.get("plan_id") or f"idx:{idx}")] = plan
    return mapped


def _fills_by_key(snapshot: dict[str, Any]) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    mapped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for fill in snapshot.get("fills") or []:
        if not isinstance(fill, dict):
            continue
        key = (
            str(fill.get("timestamp") or ""),
            str(fill.get("plan_id") or ""),
            str(fill.get("price") or ""),
            str(fill.get("qty") or ""),
        )
        mapped[key] = fill
    return mapped


def _nth_fill_timestamp(event_log: list[EventLogEntry], n: int) -> datetime | None:
    fills = _fills_from_event_log(event_log)
    if len(fills) >= n:
        ts_raw = fills[n - 1].get("timestamp")
        if ts_raw:
            return datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
    count = 0
    for entry in event_log:
        if (entry.event_type or "").upper() == "FILL":
            count += 1
            if count == n:
                return entry.timestamp
    return None


def _fill_timestamp(fill: dict[str, Any], fallback_ts: datetime) -> datetime:
    ts_raw = fill.get("timestamp")
    if ts_raw:
        try:
            return datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        except ValueError:
            return fallback_ts
    return fallback_ts


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
    segments: list[dict[str, object]] = []
    pending_entries: dict[str, dict[str, Any]] = {}
    entry_sequence = 0
    active_sl_price: float | None = None
    active_sl_start: datetime | None = None
    sl_index = 0
    active_tps: dict[float, tuple[datetime, str]] = {}
    tp_levels_ordered: list[float] = []
    prev_next_tp_idx: int | None = None
    finalized_tps: set[float] = set()
    avg_entry_start: datetime | None = None
    avg_entry_price: float | None = None
    fill_count = 0
    cumulative_fill_qty = 0.0
    cumulative_fill_notional = 0.0
    seen_fill_keys: set[tuple[str, str, str, str]] = set()

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

    def close_pending(plan_id: str, ts: datetime) -> None:
        pending = pending_entries.pop(plan_id, None)
        if pending is None or pending["kind"] == "ENTRY_MARKET":
            return
        add_segment(
            kind=str(pending["kind"]),
            label=str(pending["label"]),
            price=float(pending["price"]),
            ts_start=pending["ts_start"],
            ts_end=ts,
            sequence_index=int(pending["sequence_index"]),
            source_event_id=str(pending["source_event_id"]),
        )

    def close_avg_entry(ts: datetime) -> None:
        nonlocal avg_entry_start, avg_entry_price
        if avg_entry_start is None or avg_entry_price is None:
            return
        add_segment(
            kind="AVG_ENTRY",
            label="Average Entry",
            price=float(avg_entry_price),
            ts_start=avg_entry_start,
            ts_end=ts,
            style="dashed",
        )
        avg_entry_start = None
        avg_entry_price = None

    def _close_pending_for_fill(*, plan_id: str, fill_price: float | None, ts: datetime) -> None:
        if plan_id:
            if plan_id in pending_entries:
                close_pending(plan_id, ts)
                return
            if fill_price is None:
                return
        if fill_price is not None:
            matching_plan_ids = [
                pending_id
                for pending_id, pending in pending_entries.items()
                if abs(float(pending["price"]) - float(fill_price)) <= 1e-9
            ]
            if len(matching_plan_ids) == 1:
                close_pending(matching_plan_ids[0], ts)
                return
        if not plan_id and len(pending_entries) == 1:
            close_pending(next(iter(pending_entries.keys())), ts)

    def _position_size(snapshot: dict[str, Any]) -> float | None:
        value = snapshot.get("open_size")
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def _pending_size(snapshot: dict[str, Any]) -> float | None:
        value = snapshot.get("pending_size")
        if isinstance(value, (int, float)):
            return float(value)
        plans = [plan for plan in (snapshot.get("entries_planned") or []) if isinstance(plan, dict)]
        ratios = [plan.get("size_ratio") for plan in plans]
        numeric_ratios = [float(ratio) for ratio in ratios if isinstance(ratio, (int, float))]
        if numeric_ratios:
            return float(sum(numeric_ratios))
        if plans:
            return float(len(plans))
        return None

    for idx, entry in enumerate(event_log):
        ts = entry.timestamp
        state_before = entry.state_before or {}
        state_after = entry.state_after or {}
        before_plans = _plan_map(state_before)
        after_plans = _plan_map(state_after)
        before_plan_ids = set(before_plans.keys())
        after_plan_ids = set(after_plans.keys())

        for plan_id in sorted(after_plan_ids - before_plan_ids):
            plan = after_plans[plan_id]
            price = plan.get("price")
            if not isinstance(price, (int, float)):
                continue
            entry_type = str(plan.get("order_type") or plan.get("entry_type") or "LIMIT").upper()
            kind = "ENTRY_MARKET" if entry_type == "MARKET" else "ENTRY_LIMIT"
            pending_entries[plan_id] = {
                "kind": kind,
                "label": f"Entry {entry_sequence + 1}",
                "price": float(price),
                "ts_start": ts,
                "sequence_index": entry_sequence,
                "source_event_id": f"{trade.signal_id}_{idx}",
            }
            entry_sequence += 1

        before_fill_map = _fills_by_key(state_before)
        after_fill_map = _fills_by_key(state_after)
        combined_fill_map = dict(before_fill_map)
        combined_fill_map.update(after_fill_map)
        new_fills = [
            combined_fill_map[key]
            for key in sorted(combined_fill_map.keys())
            if key not in seen_fill_keys
        ]

        for fill in new_fills:
            plan_id = str(fill.get("plan_id") or "")
            price = fill.get("price")
            qty = fill.get("qty")
            fill_price = float(price) if isinstance(price, (int, float)) else None
            fill_ts = _fill_timestamp(fill, ts)
            _close_pending_for_fill(plan_id=plan_id, fill_price=fill_price, ts=fill_ts)
            if not isinstance(price, (int, float)) or not isinstance(qty, (int, float)):
                continue
            fill_count += 1
            cumulative_fill_qty += float(qty)
            cumulative_fill_notional += float(price) * float(qty)
            if fill_count < 2 or cumulative_fill_qty <= 0:
                continue
            current_avg = cumulative_fill_notional / cumulative_fill_qty
            if avg_entry_start is None:
                avg_entry_start = fill_ts
                avg_entry_price = current_avg
            elif avg_entry_price is not None and abs(avg_entry_price - current_avg) > 1e-9:
                close_avg_entry(fill_ts)
                avg_entry_start = fill_ts
                avg_entry_price = current_avg

        before_open_size = _position_size(state_before)
        after_open_size = _position_size(state_after)
        if (
            not new_fills
            and before_open_size is not None
            and after_open_size is not None
            and after_open_size > before_open_size + 1e-12
            and pending_entries
        ):
            _close_pending_for_fill(
                plan_id="",
                fill_price=_event_price(entry, trade),
                ts=ts,
            )

        seen_fill_keys.update(before_fill_map.keys())
        seen_fill_keys.update(after_fill_map.keys())

        for plan_id in sorted(before_plan_ids - after_plan_ids):
            if plan_id in pending_entries:
                close_pending(plan_id, ts)

        event_type = (entry.event_type or "").upper()
        before_pending_size = _pending_size(state_before)
        after_pending_size = _pending_size(state_after)
        if (
            event_type == "CANCEL_PENDING"
            and before_pending_size is not None
            and before_pending_size > 0
            and after_pending_size is not None
            and after_pending_size <= 1e-12
        ):
            for plan_id in list(pending_entries.keys()):
                close_pending(plan_id, ts)

        current_sl = state_after.get("current_sl")
        if isinstance(current_sl, (int, float)):
            sl_price = float(current_sl)
            if active_sl_price is None:
                active_sl_price = sl_price
                active_sl_start = ts
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

        tp_levels = [float(tp) for tp in (state_after.get("tp_levels") or []) if isinstance(tp, (int, float))]
        if not tp_levels_ordered and tp_levels:
            tp_levels_ordered = list(tp_levels)

        current_tp_set = set(tp_levels)
        curr_next_tp = state_after.get("next_tp_index")
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

        for removed_price in sorted(set(active_tps.keys()) - current_tp_set):
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

        for price in sorted(current_tp_set - set(active_tps.keys()), reverse=is_short):
            if price in finalized_tps:
                continue
            if price in tp_levels_ordered:
                label = f"TP{tp_levels_ordered.index(price) + 1}"
            else:
                label = f"TP{len(active_tps) + len([s for s in segments if s['kind'] == 'TP']) + 1}"
            active_tps[price] = (ts, label)

        if isinstance(curr_next_tp, int):
            prev_next_tp_idx = curr_next_tp

        if (entry.event_type or "").upper() == "CLOSE_FULL":
            for plan_id in list(pending_entries.keys()):
                close_pending(plan_id, ts)
            close_avg_entry(ts)
            if active_sl_price is not None and active_sl_start is not None:
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
                active_sl_price = None
                active_sl_start = None
            for price in list(active_tps.keys()):
                tp_start_v, tp_label_v = active_tps.pop(price)
                add_segment(
                    kind="TP",
                    label=tp_label_v,
                    price=price,
                    ts_start=tp_start_v,
                    ts_end=ts,
                    sequence_index=int(tp_label_v.removeprefix("TP")) if tp_label_v.startswith("TP") else 0,
                    source_event_id=f"{trade.signal_id}_{idx}",
                )

    for plan_id in list(pending_entries.keys()):
        close_pending(plan_id, end_ts)

    close_avg_entry(end_ts)

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


def _build_events(
    canonical_events: list[ReportCanonicalEvent],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for event in canonical_events:
        ts_ms = _to_epoch_ms(datetime.fromisoformat(event.ts))
        if ts_ms is None:
            continue
        # Placement driven by chart_marker_kind (PRD §9) and event_list_section (PRD §5).
        # Section B (IGNORED, SYSTEM_NOTE) → excluded from rail, shown only in event list.
        if event.event_list_section == "B":
            placement = "section_b"
        elif event.chart_marker_kind == "REQUIRED" and event.price_anchor is not None:
            placement = "chart"
        elif event.chart_marker_kind == "OPTIONAL_LIGHT" and event.price_anchor is not None:
            placement = "chart_optional"
        else:
            placement = "rail"
        event_code = event.event_code or event.subtype
        items.append(
            {
                "event_id": event.id,
                "ts": ts_ms,
                "exact_ts": event.ts,
                "price": event.price_anchor,
                "kind": event_code,
                "subtype": event.subtype,
                "event_code": event_code,
                "label": event.display_label or event.title,
                "rail_label": event.display_label or event.title,
                "summary": event.summary,
                "source": event.source,
                "phase": event.phase,
                "stage": event.stage,
                "placement": placement,
                "chart_marker_kind": event.chart_marker_kind,
                "geometry_effect": event.geometry_effect,
                "event_list_section": event.event_list_section,
                "position_effect": event.position_effect,
                "state_delta_essential": event.state_delta_essential,
                "chart_anchor_mode": event.visual.chart_anchor_mode,
                "lane_key": event.subtype,
                "badge_class": canonical_event_badge_class(event_code),
                "marker_color": canonical_event_marker_color(event_code),
                "marker_symbol": canonical_event_marker_symbol(event_code),
                "reason": event.reason,
                "impact": {
                    "position": event.impact.position,
                    "risk": event.impact.risk,
                    "result": event.impact.result,
                },
            }
        )
    return items


def _build_legend_items(
    *,
    level_segments: list[dict[str, object]],
    canonical_events: list[ReportCanonicalEvent],
) -> list[dict[str, str]]:
    level_kinds = {str(segment.get("kind") or "") for segment in level_segments}
    visible_event_codes = {str(event.event_code or event.subtype or "") for event in canonical_events}
    items: list[dict[str, str]] = []
    if "ENTRY_LIMIT" in level_kinds:
        items.append(
            {"key": "entries_planned", "label": "EL levels", "color": _LEVEL_COLORS["ENTRY_LIMIT"], "shape": "line"}
        )
    if "AVG_ENTRY" in level_kinds:
        items.append(
            {
                "key": "avg_entry",
                "label": "AVG entry",
                "color": _LEVEL_COLORS["AVG_ENTRY"],
                "shape": "line",
                "line_style": "dashed",
            }
        )
    if "SL" in level_kinds:
        items.append({"key": "sl", "label": "SL", "color": _LEVEL_COLORS["SL"], "shape": "line"})
    if "TP" in level_kinds:
        items.append({"key": "tps", "label": "TP levels", "color": _LEVEL_COLORS["TP"], "shape": "line"})
    items.extend(canonical_event_legend_items(visible_event_codes=visible_event_codes))
    return items


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
    level_segments = _build_level_segments(trade, event_log)

    return {
        "meta": {
            "signal_id": trade.signal_id,
            "symbol": trade.symbol,
            "side": trade.side,
            "policy_name": trade.policy_name,
            "chart_timezone": "UTC",
            "default_timeframe": _default_timeframe(candles_serialized),
            "fills_count": trade.fills_count,
            "level_summary": _build_level_summary(event_log, trade),
            "focus_start_ts": _focus_window(trade, event_log)[0],
            "focus_end_ts": _focus_window(trade, event_log)[1],
        },
        "candles_by_timeframe": candles_serialized,
        "level_segments": level_segments,
        "events": _build_events(canonical_events),
        "legend_items": _build_legend_items(
            level_segments=level_segments,
            canonical_events=canonical_events,
        ),
    }
