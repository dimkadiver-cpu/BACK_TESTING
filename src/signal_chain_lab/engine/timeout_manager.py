"""Timeout manager: handles pending order expiry and entry window logic."""
from __future__ import annotations

from datetime import datetime, timedelta

from src.signal_chain_lab.domain.enums import EventProcessingStatus, EventSource, EventType
from src.signal_chain_lab.domain.events import CanonicalEvent
from src.signal_chain_lab.domain.results import EventLogEntry
from src.signal_chain_lab.domain.trade_state import TradeState
from src.signal_chain_lab.policies.base import PolicyConfig


def _event_from_timeout(
    *,
    signal_id: str,
    timestamp: datetime,
    event_type: EventType,
    sequence: int,
    reason: str,
) -> CanonicalEvent:
    return CanonicalEvent(
        signal_id=signal_id,
        timestamp=timestamp,
        event_type=event_type,
        source=EventSource.ENGINE,
        payload={"reason": reason},
        sequence=sequence,
    )


def check_pending_timeout(
    state: TradeState,
    now: datetime,
    policy: PolicyConfig,
    sequence: int,
) -> CanonicalEvent | None:
    if state.pending_size <= 0 or state.created_at is None:
        return None
    if not policy.pending.cancel_pending_on_timeout:
        return None

    timeout_at = state.created_at + timedelta(hours=policy.pending.pending_timeout_hours)
    if now < timeout_at:
        return None

    return _event_from_timeout(
        signal_id=state.signal_id,
        timestamp=now,
        event_type=EventType.CANCEL_PENDING,
        sequence=sequence,
        reason="pending_timeout",
    )


def check_chain_timeout(
    state: TradeState,
    now: datetime,
    policy: PolicyConfig,
    sequence: int,
) -> CanonicalEvent | None:
    if state.created_at is None:
        return None

    timeout_at = state.created_at + timedelta(hours=policy.pending.chain_timeout_hours)
    if now < timeout_at:
        return None

    return _event_from_timeout(
        signal_id=state.signal_id,
        timestamp=now,
        event_type=EventType.CLOSE_FULL,
        sequence=sequence,
        reason="chain_timeout",
    )


def build_timeout_log_entry(event: CanonicalEvent, state_before: TradeState, state_after: TradeState) -> EventLogEntry:
    return EventLogEntry(
        timestamp=event.timestamp,
        signal_id=event.signal_id,
        event_type=event.event_type.value,
        source=event.source.value,
        requested_action=event.event_type.value,
        executed_action=event.event_type.value,
        processing_status=EventProcessingStatus.GENERATED,
        reason=event.payload.get("reason"),
        state_before=state_before.model_dump(mode="json"),
        state_after=state_after.model_dump(mode="json"),
    )
