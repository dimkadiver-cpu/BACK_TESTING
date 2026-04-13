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

    # ── Notional investito ────────────────────────────────────────────────────
    # Σ(fill_price * fill_qty) per tutti i fill di entrata effettivi
    invested_notional: float | None = None
    if state.fills:
        invested_notional = sum(fill.price * fill.qty for fill in state.fills)
        if invested_notional <= 0:
            invested_notional = None

    # ── PnL grezzo (nessuna fee) ──────────────────────────────────────────────
    # realized_pnl = price_delta - close_fees_paid  (valore interno motore)
    # pnl_gross_raw recupera il delta prezzo puro aggiungendo close_fees_paid
    pnl_gross_raw: float | None = None
    pnl_net_raw: float | None = None
    fees_total_raw = state.fees_paid
    funding_total_raw_net = 0.0  # funding non ancora implementato

    if invested_notional is not None:
        close_fees_paid = getattr(state, "close_fees_paid", 0.0)
        pnl_gross_raw = state.realized_pnl + close_fees_paid
        # pnl_net_raw = pnl_gross_raw - tutti i costi + funding netto
        pnl_net_raw = pnl_gross_raw - fees_total_raw + funding_total_raw_net

    # ── Rendimento % lordo e netto ────────────────────────────────────────────
    trade_return_pct_gross: float | None = None
    trade_return_pct_net: float | None = None
    cost_drag_pct: float | None = None

    if invested_notional is not None and invested_notional > 0:
        if pnl_gross_raw is not None:
            trade_return_pct_gross = pnl_gross_raw / invested_notional * 100.0
        if pnl_net_raw is not None:
            trade_return_pct_net = pnl_net_raw / invested_notional * 100.0
        if trade_return_pct_gross is not None and trade_return_pct_net is not None:
            cost_drag_pct = trade_return_pct_gross - trade_return_pct_net

    # ── R-multiple ────────────────────────────────────────────────────────────
    initial_r_pct: float | None = None
    r_multiple: float | None = None

    initial_sl = state.initial_sl
    entry_ref = state.avg_entry_price
    if (
        initial_sl is not None
        and entry_ref is not None
        and entry_ref > 0
        and trade_return_pct_net is not None
    ):
        initial_r_pct = abs(entry_ref - initial_sl) / entry_ref * 100.0
        if initial_r_pct > 0:
            r_multiple = trade_return_pct_net / initial_r_pct

    # ── MAE / MFE normalizzati sul notional investito ─────────────────────────
    mae_pct: float | None = None
    mfe_pct: float | None = None
    capture_ratio_pct: float | None = None

    if invested_notional is not None and invested_notional > 0:
        if mae is not None:
            mae_pct = mae / invested_notional * 100.0
        if mfe is not None:
            mfe_pct = mfe / invested_notional * 100.0

    # capture_ratio: fraction of MFE captured as net PnL
    if mfe is not None and mfe > 0 and pnl_net_raw is not None:
        capture_ratio_pct = pnl_net_raw / mfe * 100.0

    # ── trade_impact_pct (DEPRECATED — solo se initial_capital fornito) ───────
    trade_impact_pct: float | None = None
    if initial_capital and initial_capital > 0:
        trade_impact_pct = state.realized_pnl / initial_capital * 100.0

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
        # raw
        realized_pnl=state.realized_pnl,
        unrealized_pnl=state.unrealized_pnl,
        fees_paid=state.fees_paid,
        # canonical metrics
        invested_notional=invested_notional,
        pnl_gross_raw=pnl_gross_raw,
        pnl_net_raw=pnl_net_raw,
        fees_total_raw=fees_total_raw,
        funding_total_raw_net=funding_total_raw_net,
        trade_return_pct_gross=trade_return_pct_gross,
        trade_return_pct_net=trade_return_pct_net,
        cost_drag_pct=cost_drag_pct,
        initial_r_pct=initial_r_pct,
        r_multiple=r_multiple,
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
        # canonical % metrics (primary)
        "trade_return_pct_net",
        "trade_return_pct_gross",
        "cost_drag_pct",
        "r_multiple",
        "initial_r_pct",
        # cost fields
        "fees_total_raw",
        "funding_total_raw_net",
        # raw PnL (debug)
        "invested_notional",
        "pnl_net_raw",
        "pnl_gross_raw",
        "realized_pnl",
        "unrealized_pnl",
        "fees_paid",
        # excursion
        "mae",
        "mfe",
        "mae_pct",
        "mfe_pct",
        "capture_ratio_pct",
        # equity tracking
        "cum_equity_after_trade_pct",
        # execution
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
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for result in results:
            row = result.model_dump(mode="json")
            writer.writerow(row)
    return path
