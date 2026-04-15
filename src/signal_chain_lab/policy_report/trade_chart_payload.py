"""Build a self-contained JSON payload for the ECharts trade chart."""
from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult
from src.signal_chain_lab.market.data_models import Candle

_ORDERED_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]

# Maps raw event_type → normalised kind used by the chart JS for colouring
_EVENT_KIND_MAP: dict[str, str] = {
    "OPEN_SIGNAL": "FILL",
    "FILL": "FILL",
    "TP_HIT": "TP",
    "SL_HIT": "SL",
    "MOVE_STOP_TO_BE": "MOVE_SL",
    "MOVE_STOP": "MOVE_SL",
    "CLOSE_PARTIAL": "PARTIAL_CLOSE",
    "PARTIAL_CLOSE": "PARTIAL_CLOSE",
    "CLOSE_FULL": "CLOSE",
    "CLOSE": "CLOSE",
    "CANCEL_PENDING": "CANCEL",
    "CANCEL": "CANCEL",
    "EXPIRED": "CANCEL",
    "TIMEOUT": "CANCEL",
}

_LEVEL_COLORS: dict[str, str] = {
    "ENTRY_LIMIT": "#1d4ed8",
    "ENTRY_MARKET": "#7c3aed",
    "SL": "#b91c1c",
    "TP": "#15803d",
    "AVG_ENTRY": "#0891b2",
}


# NOTE(Fase 2): nuova rappresentazione segmenti temporali livelli.
# Manteniamo anche la struttura legacy in "levels" per compatibilità nella transizione.

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
    """Serialize candles as [ts_ms, open, close, low, high, volume] (ECharts order)."""
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


def _build_levels(
    trade: TradeResult,
    event_log: list[EventLogEntry],
) -> dict[str, list[dict[str, object]]]:
    # Canonical kind list — must match JS LEVEL_SERIES in trade_chart_echarts.py
    entries_planned: list[dict[str, object]] = []
    entries_filled: list[dict[str, object]] = []
    avg_entry: list[dict[str, object]] = []
    sl_initial: list[dict[str, object]] = []
    sl_current: list[dict[str, object]] = []
    tps: list[dict[str, object]] = []
    exit_levels: list[dict[str, object]] = []

    if not event_log:
        return {
            "entries_planned": entries_planned,
            "entries_filled": entries_filled,
            "avg_entry": avg_entry,
            "sl_initial": sl_initial,
            "sl_current": sl_current,
            "tps": tps,
            "exit": exit_levels,
        }

    # Planned entry levels — LIMIT orders only (skip MARKET: no price or entry_type==MARKET)
    first_state = event_log[0].state_after or {}
    planned_list = first_state.get("entries_planned") or []
    for idx, plan in enumerate(planned_list[:5]):
        if not isinstance(plan, dict):
            continue
        entry_type = (plan.get("entry_type") or "").upper()
        if entry_type == "MARKET":
            continue  # MARKET orders: no horizontal level line, only event marker
        price = plan.get("price")
        if isinstance(price, int | float):
            entries_planned.append({"label": f"Entry {idx + 1}", "price": float(price)})

    # Filled entry levels — track LIMIT fills (from FILL events on limit orders)
    for entry in event_log:
        etype = (entry.event_type or "").upper()
        if etype not in {"FILL", "ADD_ENTRY"}:
            continue
        state = entry.state_after or {}
        fill_price = state.get("last_fill_price") or state.get("avg_entry_price")
        if isinstance(fill_price, int | float):
            # Only add if there's a matching planned entry (i.e., it was a limit fill)
            if entries_planned:
                entries_filled.append({
                    "label": f"Fill {len(entries_filled) + 1}",
                    "price": float(fill_price),
                })

    # Avg Entry — only shown when fills_count >= 2
    if trade.avg_entry_price is not None and trade.fills_count >= 2:
        avg_entry.append({"label": "Avg Entry", "price": float(trade.avg_entry_price)})

    # SL: track initial and current (last moved)
    seen_sl: set[float] = set()
    all_sl: list[dict[str, object]] = []
    for entry in event_log:
        state = entry.state_after or {}
        current_sl = state.get("current_sl")
        if not isinstance(current_sl, int | float):
            continue
        sl_price = float(current_sl)
        if sl_price in seen_sl:
            continue
        seen_sl.add(sl_price)
        all_sl.append({"price": sl_price})

    if all_sl:
        sl_initial.append({"label": "Initial SL", "price": all_sl[0]["price"]})
        last_sl_price = all_sl[-1]["price"]
        if len(all_sl) > 1 and last_sl_price != all_sl[0]["price"]:
            sl_current.append({"label": "Current SL", "price": last_sl_price})

    # TPs from last event state
    last_state = event_log[-1].state_after or {}
    tp_levels_raw = last_state.get("tp_levels") or []
    for idx, tp in enumerate(tp_levels_raw):
        if isinstance(tp, int | float):
            tps.append({"label": f"TP{idx + 1}", "price": float(tp)})

    # Exit price
    for key in ("close_price", "market_price", "mark_price", "last_price"):
        val = last_state.get(key)
        if isinstance(val, int | float):
            exit_levels.append({"label": "Final Exit", "price": float(val)})
            break

    return {
        "entries_planned": entries_planned,
        "entries_filled": entries_filled,
        "avg_entry": avg_entry,
        "sl_initial": sl_initial,
        "sl_current": sl_current,
        "tps": tps,
        "exit": exit_levels,
    }


def _infer_trade_window(trade: TradeResult, event_log: list[EventLogEntry]) -> tuple[datetime | None, datetime | None]:
    if not event_log:
        return trade.created_at, trade.closed_at

    start = trade.created_at or event_log[0].timestamp
    end = trade.closed_at or event_log[-1].timestamp
    if start and end and end < start:
        end = start
    return start, end


def _first_fill_timestamp(event_log: list[EventLogEntry]) -> datetime | None:
    for entry in event_log:
        if (entry.event_type or "").upper() in {"ADD_ENTRY", "FILL"}:
            return entry.timestamp
    return None


def _build_level_segments(trade: TradeResult, event_log: list[EventLogEntry]) -> list[dict[str, object]]:
    """Build PRD-B level segments with explicit start/end timestamps."""
    start_ts, end_ts = _infer_trade_window(trade, event_log)
    if start_ts is None or end_ts is None:
        return []

    segments: list[dict[str, object]] = []

    def add_segment(
        kind: str,
        label: str,
        price: float,
        ts_start: datetime,
        ts_end: datetime,
        *,
        style: str,
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
            }
        )

    first_state = event_log[0].state_after if event_log else {}
    first_fill_ts = _first_fill_timestamp(event_log)

    for idx, plan in enumerate((first_state or {}).get("entries_planned") or []):
        if not isinstance(plan, dict):
            continue
        price = plan.get("price")
        if not isinstance(price, (int, float)):
            continue
        entry_type = (plan.get("entry_type") or "LIMIT").upper()
        kind = "ENTRY_MARKET" if entry_type == "MARKET" else "ENTRY_LIMIT"
        end_for_entry = first_fill_ts or end_ts
        add_segment(kind, f"Entry {idx + 1}", float(price), start_ts, end_for_entry, style="dashed")

    if trade.avg_entry_price is not None and trade.fills_count >= 2:
        add_segment(
            "AVG_ENTRY",
            "Avg Entry",
            float(trade.avg_entry_price),
            first_fill_ts or start_ts,
            end_ts,
            style="solid",
        )

    active_sl_price: float | None = None
    active_sl_start: datetime | None = None

    active_tp_segments: dict[float, tuple[datetime, str]] = {}
    next_tp_label_idx = 1

    for entry in event_log:
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
                    add_segment("SL", "Stop Loss", active_sl_price, active_sl_start, ts, style="dashed")
                active_sl_price = sl_price
                active_sl_start = ts

        tp_levels = [float(tp) for tp in (state.get("tp_levels") or []) if isinstance(tp, (int, float))]
        current_prices = set(tp_levels)
        previous_prices = set(active_tp_segments.keys())

        for closed_price in sorted(previous_prices - current_prices):
            tp_start, label = active_tp_segments.pop(closed_price)
            add_segment("TP", label, closed_price, tp_start, ts, style="dashed")

        for price in sorted(current_prices - previous_prices):
            label = f"TP{next_tp_label_idx}"
            next_tp_label_idx += 1
            active_tp_segments[price] = (start_ts, label)

    if active_sl_price is not None and active_sl_start is not None:
        add_segment("SL", "Stop Loss", active_sl_price, active_sl_start, end_ts, style="dashed")

    for price, (tp_start, label) in sorted(active_tp_segments.items()):
        add_segment("TP", label, price, tp_start, end_ts, style="dashed")

    return segments


def _compute_tp_return_pct(
    entry: EventLogEntry,
    trade: TradeResult,
) -> float | None:
    """Return the % return at this TP/CLOSE event relative to avg entry, or None."""
    state = entry.state_after or {}
    avg_entry = state.get("avg_entry_price") or trade.avg_entry_price
    if not isinstance(avg_entry, int | float) or avg_entry == 0:
        return None
    exit_price: float | None = None
    if isinstance(entry.price_reference, int | float):
        exit_price = float(entry.price_reference)
    if exit_price is None:
        for key in ("close_price", "market_price", "mark_price", "last_price"):
            val = state.get(key)
            if isinstance(val, int | float):
                exit_price = float(val)
                break
    if exit_price is None:
        return None
    side = (trade.side or "").upper()
    direction = -1.0 if side in {"SHORT", "SELL"} else 1.0
    return round((exit_price - float(avg_entry)) / float(avg_entry) * 100.0 * direction, 3)


def _build_events(
    event_log: list[EventLogEntry],
    trade: TradeResult,
) -> list[dict[str, object]]:
    # Canonical kind list — must match visibility keys ev_* in trade_chart_echarts.py
    events: list[dict[str, object]] = []
    for entry in event_log:
        ts = _to_epoch_ms(entry.timestamp)
        if ts is None:
            continue

        price: float | None = None
        if isinstance(entry.price_reference, int | float):
            price = float(entry.price_reference)

        if price is None:
            state = entry.state_after or {}
            for key in ("market_price", "mark_price", "last_price", "avg_entry_price", "close_price"):
                val = state.get(key)
                if isinstance(val, int | float):
                    price = float(val)
                    break

        if price is None:
            state = entry.state_after or {}
            plans = state.get("entries_planned") or []
            if isinstance(plans, list) and plans:
                prices = [
                    float(item["price"])
                    for item in plans
                    if isinstance(item, dict) and isinstance(item.get("price"), int | float)
                ]
                if prices:
                    price = sum(prices) / len(prices)

        if price is None:
            continue

        etype = (entry.event_type or "").upper()
        kind = _EVENT_KIND_MAP.get(etype, etype)

        # return_pct for TP / CLOSE events
        return_pct: float | None = None
        if kind in {"TP", "CLOSE", "PARTIAL_CLOSE"}:
            return_pct = _compute_tp_return_pct(entry, trade)

        events.append(
            {
                "ts": ts,
                "price": price,
                "kind": kind,
                "label": entry.event_type or kind,
                "return_pct": return_pct,
                "source": entry.source or "engine",
                "event_type_raw": entry.event_type or "",
            }
        )

    return events


def _build_position_size_series(event_log: list[EventLogEntry]) -> list[list[object]]:
    """Return [ts_ms, open_size] points for the position size step overlay."""
    points: list[list[object]] = []
    for entry in event_log:
        ts = _to_epoch_ms(entry.timestamp)
        if ts is None:
            continue
        state = entry.state_after or {}
        size = state.get("open_size")
        if isinstance(size, (int, float)):
            points.append([ts, float(size)])
    return points


def _build_realized_pnl_series(event_log: list[EventLogEntry]) -> list[list[object]]:
    """Return [ts_ms, realized_pnl] points for the PnL step overlay."""
    points: list[list[object]] = []
    for entry in event_log:
        ts = _to_epoch_ms(entry.timestamp)
        if ts is None:
            continue
        state = entry.state_after or {}
        pnl = state.get("realized_pnl")
        if isinstance(pnl, (int, float)):
            points.append([ts, float(pnl)])
    return points


def _default_timeframe(candles_by_timeframe: dict[str, list[object]]) -> str | None:
    for tf in _ORDERED_TIMEFRAMES:
        if tf in candles_by_timeframe:
            return tf
    keys = list(candles_by_timeframe.keys())
    return keys[0] if keys else None


def build_trade_chart_payload(
    trade: TradeResult,
    event_log: list[EventLogEntry],
    candles_by_timeframe: dict[str, list[Candle]],
) -> dict[str, object]:
    """Return a self-contained dict ready for JSON serialisation and ECharts rendering."""
    candles_serialized: dict[str, list[list[object]]] = {
        tf: _candles_to_array(candles)
        for tf, candles in candles_by_timeframe.items()
        if candles
    }

    return {
        "meta": {
            "signal_id": trade.signal_id,
            "symbol": trade.symbol,
            "side": trade.side,
            "policy_name": trade.policy_name,
            "default_timeframe": _default_timeframe(candles_serialized),
            "fills_count": trade.fills_count,
        },
        "candles_by_timeframe": candles_serialized,
        "levels": _build_levels(trade, event_log),
        "level_segments": _build_level_segments(trade, event_log),
        "events": _build_events(event_log, trade),
        "position_size_series": _build_position_size_series(event_log),
        "realized_pnl_series": _build_realized_pnl_series(event_log),
    }
