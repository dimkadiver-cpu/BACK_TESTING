"""Trade report: aggregated per-trade simulation results."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult
from src.signal_chain_lab.domain.trade_state import TradeState

_UPDATE_EVENT_TYPES = frozenset({
    "MOVE_STOP", "MOVE_STOP_TO_BE", "ADD_ENTRY", "MODIFY_ENTRY",
    "UPDATE_TAKE_PROFITS", "REENTER",
})
_CLOSE_EVENT_TYPES = frozenset({
    "CLOSE_FULL", "TP_HIT", "SL_HIT", "CLOSE_PARTIAL",
    "CANCEL_PENDING", "EXPIRED", "TIMEOUT",
})


def _extract_mae_mfe(event_log: list[EventLogEntry]) -> tuple[float | None, float | None]:
    """Approximate MAE/MFE from unrealized_pnl snapshots in the event log."""
    snapshots: list[float] = []
    for entry in event_log:
        for state in (entry.state_before, entry.state_after):
            val = state.get("unrealized_pnl")
            if isinstance(val, (int, float)):
                snapshots.append(float(val))
    if not snapshots:
        return None, None
    return min(snapshots), max(snapshots)


def build_trade_result(
    state: TradeState,
    event_log: list[EventLogEntry],
    *,
    initial_capital: float | None = None,
) -> TradeResult:
    duration_seconds = None
    if state.created_at is not None and state.closed_at is not None:
        duration_seconds = (state.closed_at - state.created_at).total_seconds()

    time_to_fill_seconds = None
    if state.created_at is not None and state.first_fill_at is not None:
        time_to_fill_seconds = (state.first_fill_at - state.created_at).total_seconds()

    fills_count = len(state.fills)
    first_fill_price = state.fills[0].price if state.fills else None

    # final exit price: last price_reference from a close-type event
    final_exit_price: float | None = None
    for entry in reversed(event_log):
        etype = (entry.event_type or "").upper()
        if etype in _CLOSE_EVENT_TYPES and entry.price_reference is not None:
            final_exit_price = float(entry.price_reference)
            break

    updates_applied_count = 0
    partial_closes_count = 0
    for entry in event_log:
        etype = (entry.event_type or "").upper()
        status = (entry.processing_status.value if entry.processing_status else "").upper()
        if status == "APPLIED":
            if etype in _UPDATE_EVENT_TYPES:
                updates_applied_count += 1
            if etype == "CLOSE_PARTIAL":
                partial_closes_count += 1

    mae, mfe = _extract_mae_mfe(event_log)

    trade_impact_pct: float | None = None
    mae_pct: float | None = None
    mfe_pct: float | None = None
    capture_ratio_pct: float | None = None

    if initial_capital and initial_capital > 0:
        trade_impact_pct = state.realized_pnl / initial_capital * 100.0
        if mae is not None:
            mae_pct = mae / initial_capital * 100.0
        if mfe is not None:
            mfe_pct = mfe / initial_capital * 100.0

    # capture_ratio: what fraction of MFE was captured as realized PnL
    if mfe is not None and mfe > 0:
        capture_ratio_pct = state.realized_pnl / mfe * 100.0

    return TradeResult(
        signal_id=state.signal_id,
        trader_id=state.trader_id,
        symbol=state.symbol,
        side=state.side,
        status=state.status.value,
        input_mode=state.input_mode,
        policy_name=state.policy_name,
        close_reason=state.close_reason.value if state.close_reason else None,
        created_at=state.created_at,
        first_fill_at=state.first_fill_at,
        closed_at=state.closed_at,
        duration_seconds=duration_seconds,
        entries_count=len(state.entries_planned),
        avg_entry_price=state.avg_entry_price,
        max_position_size=state.max_position_size,
        final_position_size=state.open_size,
        realized_pnl=state.realized_pnl,
        unrealized_pnl=state.unrealized_pnl,
        fees_paid=state.fees_paid,
        mae=mae,
        mfe=mfe,
        trade_impact_pct=trade_impact_pct,
        mae_pct=mae_pct,
        mfe_pct=mfe_pct,
        capture_ratio_pct=capture_ratio_pct,
        time_to_fill_seconds=time_to_fill_seconds,
        fills_count=fills_count,
        first_fill_price=first_fill_price,
        final_exit_price=final_exit_price,
        updates_applied_count=updates_applied_count,
        partial_closes_count=partial_closes_count,
        warnings_count=state.warnings_count,
        ignored_events_count=state.ignored_events_count,
    )


def write_trade_result_parquet(result: TradeResult, output_path: str | Path) -> Path:
    """Write a parquet-like artifact.

    If parquet libraries are unavailable, fallback to JSON payload in same path.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")
    return path


def write_trade_results_csv(results: list[TradeResult], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "signal_id",
        "trader_id",
        "symbol",
        "side",
        "status",
        "input_mode",
        "policy_name",
        "close_reason",
        "created_at",
        "first_fill_at",
        "closed_at",
        "duration_seconds",
        "entries_count",
        "avg_entry_price",
        "max_position_size",
        "final_position_size",
        "realized_pnl",
        "unrealized_pnl",
        "fees_paid",
        "mae",
        "mfe",
        "trade_impact_pct",
        "cum_equity_after_trade_pct",
        "mae_pct",
        "mfe_pct",
        "capture_ratio_pct",
        "time_to_fill_seconds",
        "bars_in_trade",
        "fills_count",
        "first_fill_price",
        "final_exit_price",
        "updates_applied_count",
        "partial_closes_count",
        "warnings_count",
        "ignored_events_count",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            row = result.model_dump(mode="json")
            writer.writerow(row)
    return path
