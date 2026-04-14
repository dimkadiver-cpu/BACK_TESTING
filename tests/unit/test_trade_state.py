"""Tests for TradeState, EntryPlan, and FillRecord (S1.10)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.signal_chain_lab.domain.enums import ChainInputMode, CloseReason, TradeStatus
from src.signal_chain_lab.domain.trade_state import EntryPlan, FillRecord, TradeState


def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def test_trade_state_minimal_construction() -> None:
    state = TradeState(
        signal_id="chain_001",
        symbol="BTCUSDT",
        side="BUY",
        status=TradeStatus.NEW,
        input_mode=ChainInputMode.SIGNAL_ONLY_NATIVE,
        policy_name="original_chain",
    )
    assert state.signal_id == "chain_001"
    assert state.status == TradeStatus.NEW
    assert state.entries_planned == []
    assert state.fills == []
    assert state.pending_size == 0.0
    assert state.open_size == 0.0
    assert state.avg_entry_price is None
    assert state.close_reason is None


def test_trade_state_default_fields() -> None:
    state = TradeState(
        signal_id="x",
        symbol="ETHUSDT",
        side="SELL",
        status=TradeStatus.PENDING,
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        policy_name="signal_only",
    )
    assert state.realized_pnl == 0.0
    assert state.unrealized_pnl == 0.0
    assert state.fees_paid == 0.0
    assert state.funding_paid == 0.0
    assert state.funding_events_count == 0
    assert state.applied_funding_event_keys == []
    assert state.funding_watermark_ts is None
    assert state.warnings_count == 0
    assert state.ignored_events_count == 0
    assert state.tp_levels == []
    assert state.next_tp_index == 0
    assert state.initial_sl is None
    assert state.current_sl is None
    assert state.trader_id is None
    assert state.closed_at is None
    assert state.first_fill_at is None
    assert state.created_at is None


def test_trade_state_with_entry_plan() -> None:
    plan = EntryPlan(role="primary", order_type="limit", price=90000.0, size_ratio=1.0, label="E1", sequence=0)
    state = TradeState(
        signal_id="x",
        symbol="BTCUSDT",
        side="BUY",
        status=TradeStatus.PENDING,
        input_mode=ChainInputMode.SIGNAL_ONLY_NATIVE,
        policy_name="original_chain",
        entries_planned=[plan],
        initial_sl=85000.0,
        current_sl=85000.0,
        tp_levels=[95000.0, 100000.0],
    )
    assert len(state.entries_planned) == 1
    assert state.entries_planned[0].price == 90000.0
    assert state.initial_sl == 85000.0
    assert len(state.tp_levels) == 2


def test_trade_state_with_fill() -> None:
    fill = FillRecord(
        price=90050.0,
        qty=0.1,
        timestamp=_utc("2025-06-01T10:01:00"),
        fee_paid=0.045,
    )
    state = TradeState(
        signal_id="x",
        symbol="BTCUSDT",
        side="BUY",
        status=TradeStatus.ACTIVE,
        input_mode=ChainInputMode.SIGNAL_ONLY_NATIVE,
        policy_name="original_chain",
        fills=[fill],
        open_size=0.1,
        avg_entry_price=90050.0,
    )
    assert len(state.fills) == 1
    assert state.fills[0].price == 90050.0
    assert state.fills[0].fee_paid == 0.045


def test_entry_plan_roles() -> None:
    primary = EntryPlan(role="primary", order_type="market", price=None, size_ratio=1.0)
    avg = EntryPlan(role="averaging", order_type="limit", price=85000.0, size_ratio=0.5)
    assert primary.role == "primary"
    assert avg.role == "averaging"
    assert avg.price == 85000.0


def test_fill_record_default_fee() -> None:
    fill = FillRecord(
        price=100.0,
        qty=1.0,
        timestamp=_utc("2025-01-01T00:00:00"),
    )
    assert fill.fee_paid == 0.0
    assert fill.source_event_sequence is None


def test_trade_state_close_reason() -> None:
    state = TradeState(
        signal_id="x",
        symbol="BTCUSDT",
        side="BUY",
        status=TradeStatus.CLOSED,
        input_mode=ChainInputMode.SIGNAL_ONLY_NATIVE,
        policy_name="original_chain",
        close_reason=CloseReason.TP,
        closed_at=_utc("2025-06-01T16:00:00"),
    )
    assert state.close_reason == CloseReason.TP
    assert state.status == TradeStatus.CLOSED
