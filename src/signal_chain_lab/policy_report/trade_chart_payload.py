"""Build a self-contained JSON payload for the ECharts trade chart."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult
from src.signal_chain_lab.market.data_models import Candle

_ORDERED_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]


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


def _fills_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    fills = state.get("fills") or []
    return [item for item in fills if isinstance(item, dict)]


def _fill_label(fill: dict[str, Any], *, index: int) -> str:
    plan_id = str(fill.get("plan_id") or "")
    if ":E" in plan_id:
        return f"FILL {plan_id.split(':E')[-1]}"
    return f"FILL {index + 1}"


def _event_family(event_type: str, reason: str | None) -> str:
    etype = event_type.upper()
    reason_norm = (reason or "").lower()
    if etype == "FILL":
        return "FILL"
    if etype == "OPEN_SIGNAL":
        return "SIGNAL"
    if etype in {"ADD_ENTRY", "MOVE_STOP", "MOVE_STOP_TO_BE"}:
        return "UPDATE"
    if "TP" in etype or "tp" in reason_norm:
        return "TP"
    if "SL" in etype or "sl" in reason_norm:
        return "SL"
    if etype == "CANCEL_PENDING" or "timeout" in reason_norm or "cancel" in reason_norm or "expired" in reason_norm:
        return "CANCEL"
    if etype == "CLOSE_PARTIAL":
        return "PARTIAL_CLOSE"
    if etype == "CLOSE_FULL":
        return "CLOSE"
    return "EVENT"


def _event_short_label(event_type: str, family: str) -> str:
    etype = event_type.upper()
    if family == "SIGNAL":
        return "SIGNAL"
    if family == "FILL":
        return "FILL"
    if family == "UPDATE":
        if etype == "MOVE_STOP_TO_BE":
            return "MOVE SL BE"
        if etype == "MOVE_STOP":
            return "MOVE SL"
        return etype
    if family in {"TP", "SL", "CLOSE", "PARTIAL_CLOSE", "CANCEL"}:
        return etype
    return etype


def _build_levels(
    trade: TradeResult,
    event_log: list[EventLogEntry],
) -> dict[str, list[dict[str, object]]]:
    levels: dict[str, list[dict[str, object]]] = {
        "entries": [],
        "avg_entry": [],
        "initial_sl": [],
        "last_sl": [],
        "sl_history": [],
        "tps": [],
        "exit": [],
    }

    if not event_log:
        return levels

    first_state = event_log[0].state_after or {}
    entries_planned = first_state.get("entries_planned") or []
    for idx, plan in enumerate(entries_planned[:5]):
        if isinstance(plan, dict):
            price = plan.get("price")
            if isinstance(price, (int, float)):
                levels["entries"].append({"label": f"Entry {idx + 1}", "price": float(price)})

    last_state = event_log[-1].state_after or {}
    final_fills = _fills_from_state(last_state)
    if trade.avg_entry_price is not None and len(final_fills) >= 2:
        levels["avg_entry"].append({"label": "Avg Entry", "price": float(trade.avg_entry_price)})

    seen_sl: list[float] = []
    for entry in event_log:
        current_sl = (entry.state_after or {}).get("current_sl")
        if isinstance(current_sl, (int, float)):
            sl_price = float(current_sl)
            if sl_price not in seen_sl:
                seen_sl.append(sl_price)

    initial_sl = (first_state.get("initial_sl") if isinstance(first_state.get("initial_sl"), (int, float)) else first_state.get("current_sl"))
    if isinstance(initial_sl, (int, float)):
        levels["initial_sl"].append({"label": "Initial SL", "price": float(initial_sl)})

    if seen_sl:
        last_sl = seen_sl[-1]
        levels["last_sl"].append({"label": "Last SL", "price": float(last_sl)})
        if len(seen_sl) > 2:
            for idx, sl_price in enumerate(seen_sl[1:-1], start=1):
                levels["sl_history"].append({"label": f"Moved SL {idx}", "price": sl_price})

    tp_levels = last_state.get("tp_levels") or []
    for idx, tp in enumerate(tp_levels):
        if isinstance(tp, (int, float)):
            levels["tps"].append({"label": f"TP{idx + 1}", "price": float(tp)})

    if trade.final_exit_price is not None:
        levels["exit"].append({"label": "Final Exit", "price": float(trade.final_exit_price)})
    else:
        for key in ("close_price", "market_price", "mark_price", "last_price"):
            val = last_state.get(key)
            if isinstance(val, (int, float)):
                levels["exit"].append({"label": "Final Exit", "price": float(val)})
                break

    return levels


def _event_price(entry: EventLogEntry) -> float | None:
    if isinstance(entry.price_reference, (int, float)):
        return float(entry.price_reference)

    state = entry.state_after or {}
    for key in ("market_price", "mark_price", "last_price", "avg_entry_price", "close_price", "current_sl"):
        val = state.get(key)
        if isinstance(val, (int, float)):
            return float(val)

    plans = state.get("entries_planned") or []
    if isinstance(plans, list) and plans:
        prices = [
            float(item["price"])
            for item in plans
            if isinstance(item, dict) and isinstance(item.get("price"), (int, float))
        ]
        if prices:
            return sum(prices) / len(prices)
    return None


def _build_events(event_log: list[EventLogEntry]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for entry in event_log:
        ts = _to_epoch_ms(entry.timestamp)
        price = _event_price(entry)
        if ts is not None and price is not None:
            family = _event_family(entry.event_type, entry.reason)
            events.append(
                {
                    "ts": ts,
                    "price": price,
                    "family": family,
                    "label": _event_short_label(entry.event_type, family),
                    "event_type": entry.event_type,
                    "source": entry.source,
                    "status": entry.processing_status.value,
                    "reason": entry.reason,
                }
            )

        before_fills = _fills_from_state(entry.state_before or {})
        after_fills = _fills_from_state(entry.state_after or {})
        if len(after_fills) <= len(before_fills):
            continue

        for idx, fill in enumerate(after_fills[len(before_fills):], start=len(before_fills)):
            fill_ts_raw = fill.get("timestamp")
            fill_dt = None
            if isinstance(fill_ts_raw, str):
                try:
                    fill_dt = datetime.fromisoformat(fill_ts_raw.replace("Z", "+00:00"))
                except ValueError:
                    fill_dt = None
            fill_ts = _to_epoch_ms(fill_dt or entry.timestamp)
            fill_price = fill.get("price")
            if fill_ts is None or not isinstance(fill_price, (int, float)):
                continue
            events.append(
                {
                    "ts": fill_ts,
                    "price": float(fill_price),
                    "family": "FILL",
                    "label": _fill_label(fill, index=idx),
                    "event_type": "FILL",
                    "source": "engine",
                    "status": "applied",
                    "reason": "order_filled",
                }
            )

    events.sort(key=lambda item: (int(item["ts"]), str(item["event_type"]), str(item["label"])))
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
