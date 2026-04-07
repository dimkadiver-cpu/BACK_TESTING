"""Trade report: aggregated per-trade simulation results."""
from __future__ import annotations

import json
from pathlib import Path

from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult
from src.signal_chain_lab.domain.trade_state import TradeState


def build_trade_result(state: TradeState, event_log: list[EventLogEntry]) -> TradeResult:
    duration_seconds = None
    if state.created_at is not None and state.closed_at is not None:
        duration_seconds = (state.closed_at - state.created_at).total_seconds()

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
