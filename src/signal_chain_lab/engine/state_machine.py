"""Trade state machine: transitions driven by market events and signal updates."""
from __future__ import annotations

from copy import deepcopy

from src.signal_chain_lab.domain.enums import CloseReason, EventProcessingStatus, EventType, TradeStatus
from src.signal_chain_lab.domain.events import CanonicalEvent
from src.signal_chain_lab.domain.results import EventLogEntry
from src.signal_chain_lab.domain.trade_state import EntryPlan, TradeState


def _snapshot(state: TradeState) -> dict:
    return state.model_dump(mode="json")


def _warning(state: TradeState) -> None:
    state.warnings_count += 1
    state.ignored_events_count += 1


def _apply_open_signal(state: TradeState, event: CanonicalEvent) -> tuple[str, EventProcessingStatus, str | None]:
    payload = event.payload
    state.entries_planned = [
        EntryPlan(
            role="primary",
            order_type=payload.get("entry_type", "market"),
            price=(payload.get("entry_prices") or [None])[0],
            size_ratio=1.0,
            sequence=event.sequence,
        )
    ]
    state.initial_sl = payload.get("sl_price")
    state.current_sl = payload.get("sl_price")
    state.tp_levels = list(payload.get("tp_levels") or [])
    state.pending_size = 1.0
    state.status = TradeStatus.PENDING
    state.created_at = event.timestamp
    return "OPEN_SIGNAL", EventProcessingStatus.APPLIED, None


def apply_event(state: TradeState, event: CanonicalEvent) -> EventLogEntry:
    before_state = deepcopy(state)
    status = EventProcessingStatus.APPLIED
    executed_action = event.event_type.value
    reason: str | None = None

    if event.event_type == EventType.OPEN_SIGNAL:
        executed_action, status, reason = _apply_open_signal(state, event)
    elif event.event_type == EventType.ADD_ENTRY:
        if state.status in {TradeStatus.CLOSED, TradeStatus.CANCELLED, TradeStatus.EXPIRED, TradeStatus.INVALID}:
            status = EventProcessingStatus.IGNORED
            executed_action = None
            reason = "add_entry_on_terminal_state"
            _warning(state)
        else:
            state.entries_planned.append(
                EntryPlan(
                    role="averaging",
                    order_type=event.payload.get("order_type", "limit"),
                    price=event.payload.get("price"),
                    size_ratio=float(event.payload.get("size_ratio", 1.0)),
                    sequence=event.sequence,
                )
            )
            state.pending_size += float(event.payload.get("size_ratio", 1.0))
    elif event.event_type == EventType.MOVE_STOP:
        new_sl = event.payload.get("new_sl_price")
        if state.open_size <= 0 or new_sl is None:
            status = EventProcessingStatus.IGNORED
            executed_action = None
            reason = "move_stop_without_open_position"
            _warning(state)
        else:
            state.current_sl = float(new_sl)
    elif event.event_type == EventType.MOVE_STOP_TO_BE:
        if state.open_size <= 0 or state.avg_entry_price is None:
            status = EventProcessingStatus.IGNORED
            executed_action = None
            reason = "move_stop_to_be_without_fill"
            _warning(state)
        else:
            state.current_sl = state.avg_entry_price
    elif event.event_type == EventType.CLOSE_PARTIAL:
        if state.open_size <= 0:
            status = EventProcessingStatus.IGNORED
            executed_action = None
            reason = "close_partial_without_open_position"
            _warning(state)
        else:
            close_pct = float(event.payload.get("close_pct", 0.5))
            closed_qty = min(state.open_size, state.open_size * close_pct)
            state.open_size -= closed_qty
            state.status = TradeStatus.PARTIALLY_CLOSED if state.open_size > 0 else TradeStatus.CLOSED
            if state.open_size <= 0:
                state.close_reason = CloseReason.MANUAL
                state.closed_at = event.timestamp
    elif event.event_type == EventType.CLOSE_FULL:
        if state.open_size <= 0 and state.pending_size <= 0:
            status = EventProcessingStatus.IGNORED
            executed_action = None
            reason = "close_full_without_position"
            _warning(state)
        else:
            state.open_size = 0.0
            state.pending_size = 0.0
            state.status = TradeStatus.CLOSED
            close_reason = event.payload.get("reason")
            if close_reason == "chain_timeout":
                state.close_reason = CloseReason.EXPIRED
                state.status = TradeStatus.EXPIRED
            elif close_reason == "tp_hit":
                state.close_reason = CloseReason.TP
            elif close_reason == "sl_hit":
                state.close_reason = CloseReason.SL
            else:
                state.close_reason = CloseReason.MANUAL
            state.closed_at = event.timestamp
    elif event.event_type == EventType.CANCEL_PENDING:
        if state.pending_size <= 0:
            status = EventProcessingStatus.IGNORED
            executed_action = None
            reason = "cancel_pending_without_pending"
            _warning(state)
        else:
            state.pending_size = 0.0
            if state.open_size <= 0:
                if event.payload.get("reason") == "pending_timeout":
                    state.status = TradeStatus.EXPIRED
                    state.close_reason = CloseReason.TIMEOUT
                else:
                    state.status = TradeStatus.CANCELLED
                    state.close_reason = CloseReason.CANCELLED
                state.closed_at = event.timestamp

    return EventLogEntry(
        timestamp=event.timestamp,
        signal_id=event.signal_id,
        event_type=event.event_type.value,
        source=event.source.value,
        requested_action=event.event_type.value,
        executed_action=executed_action,
        processing_status=status,
        reason=reason,
        state_before=_snapshot(before_state),
        state_after=_snapshot(state),
    )
