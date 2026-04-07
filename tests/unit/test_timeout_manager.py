from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.domain.enums import ChainInputMode, TradeStatus
from src.signal_chain_lab.domain.trade_state import TradeState
from src.signal_chain_lab.engine.timeout_manager import check_chain_timeout, check_pending_timeout
from src.signal_chain_lab.policies.base import PolicyConfig


def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def _state() -> TradeState:
    return TradeState(
        signal_id="sig-1",
        symbol="BTCUSDT",
        side="BUY",
        status=TradeStatus.PENDING,
        input_mode=ChainInputMode.SIGNAL_ONLY_NATIVE,
        policy_name="p",
        created_at=_utc("2026-01-01T00:00:00"),
        pending_size=1.0,
    )


def test_pending_timeout_generates_cancel_event() -> None:
    state = _state()
    policy = PolicyConfig(name="p", pending={"pending_timeout_hours": 1.0})
    event = check_pending_timeout(state, _utc("2026-01-01T01:00:01"), policy, sequence=10)
    assert event is not None
    assert event.event_type.value == "CANCEL_PENDING"
    assert event.payload["reason"] == "pending_timeout"


def test_chain_timeout_generates_close_full_event() -> None:
    state = _state()
    policy = PolicyConfig(name="p", pending={"chain_timeout_hours": 2.0})
    event = check_chain_timeout(state, _utc("2026-01-01T02:00:01"), policy, sequence=11)
    assert event is not None
    assert event.event_type.value == "CLOSE_FULL"
    assert event.payload["reason"] == "chain_timeout"
