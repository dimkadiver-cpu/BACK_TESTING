"""Build a self-contained JSON payload for the ECharts trade chart."""
from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult
from src.signal_chain_lab.market.data_models import Candle

_ORDERED_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]

_EVENT_KIND_MAP: dict[str, str] = {
    "OPEN_SIGNAL": "FILL",
    "FILL": "FILL",
    "TP_HIT": "TP_HIT",
    "SL_HIT": "SL_HIT",
    "MOVE_STOP_TO_BE": "MOVE_SL_BE",
    "MOVE_STOP": "MOVE_SL_BE",
    "PARTIAL_CLOSE": "PARTIAL_CLOSE",
    "CLOSE": "CLOSE",
    "CANCEL": "CANCEL",
}


def _to_epoch_ms(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


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
    entries: list[dict[str, object]] = []
    sl: list[dict[str, object]] = []
    tps: list[dict[str, object]] = []
    exit_levels: list[dict[str, object]] = []

    if not event_log:
        return {"entries": entries, "sl": sl, "tps": tps, "exit": exit_levels}

    first_state = event_log[0].state_after or {}
    entries_planned = first_state.get("entries_planned") or []
    for idx, plan in enumerate(entries_planned[:5]):
        if isinstance(plan, dict):
            price = plan.get("price")
            if isinstance(price, int | float):
                entries.append({"label": f"Entry {idx + 1}", "price": float(price)})

    if trade.avg_entry_price is not None:
        entries.append({"label": "Avg Entry", "price": float(trade.avg_entry_price)})

    # SL from each state to capture BE moves
    seen_sl: set[float] = set()
    be_added = False
    for entry in event_log:
        etype = (entry.event_type or "").upper()
        state = entry.state_after or {}
        current_sl = state.get("current_sl")
        if not isinstance(current_sl, int | float):
            continue
        sl_price = float(current_sl)
        if sl_price in seen_sl:
            continue
        seen_sl.add(sl_price)
        if not sl:
            sl.append({"label": "Initial SL", "price": sl_price})
        elif "MOVE_STOP" in etype or "BE" in etype:
            if not be_added:
                sl.append({"label": "Break Even", "price": sl_price})
                be_added = True

    # TPs from last state
    last_state = event_log[-1].state_after or {}
    tp_levels = last_state.get("tp_levels") or []
    for idx, tp in enumerate(tp_levels):
        if isinstance(tp, int | float):
            tps.append({"label": f"TP{idx + 1}", "price": float(tp)})

    # Exit price from final state keys
    for key in ("close_price", "market_price", "mark_price", "last_price"):
        val = last_state.get(key)
        if isinstance(val, int | float):
            exit_levels.append({"label": "Final Exit", "price": float(val)})
            break

    return {"entries": entries, "sl": sl, "tps": tps, "exit": exit_levels}


def _build_events(event_log: list[EventLogEntry]) -> list[dict[str, object]]:
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
        events.append(
            {
                "ts": ts,
                "price": price,
                "kind": kind,
                "label": entry.event_type or kind,
            }
        )

    return events


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
        },
        "candles_by_timeframe": candles_serialized,
        "levels": _build_levels(trade, event_log),
        "events": _build_events(event_log),
    }
