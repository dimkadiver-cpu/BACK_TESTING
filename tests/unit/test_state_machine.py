from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.domain.enums import ChainInputMode, EventProcessingStatus, EventSource, EventType, TradeStatus
from src.signal_chain_lab.domain.events import CanonicalEvent
from src.signal_chain_lab.domain.trade_state import TradeState
from src.signal_chain_lab.engine.state_machine import apply_event


def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def _base_state() -> TradeState:
    return TradeState(
        signal_id="sig-1",
        symbol="BTCUSDT",
        side="BUY",
        status=TradeStatus.NEW,
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        policy_name="original_chain",
    )


def _event(event_type: EventType, payload: dict | None = None, seq: int = 0) -> CanonicalEvent:
    return CanonicalEvent(
        signal_id="sig-1",
        symbol="BTCUSDT",
        side="BUY",
        timestamp=_utc("2026-01-01T00:00:00"),
        event_type=event_type,
        source=EventSource.TRADER,
        payload=payload or {},
        sequence=seq,
    )


def test_open_signal_transitions_to_pending() -> None:
    state = _base_state()
    log = apply_event(state, _event(EventType.OPEN_SIGNAL, {"entry_prices": [100.0], "sl_price": 90.0, "tp_levels": [110.0]}))
    assert state.status == TradeStatus.PENDING
    assert log.processing_status == EventProcessingStatus.APPLIED


def test_move_stop_before_fill_is_ignored() -> None:
    state = _base_state()
    apply_event(state, _event(EventType.OPEN_SIGNAL, {"entry_prices": [100.0], "sl_price": 90.0, "tp_levels": [110.0]}))
    log = apply_event(state, _event(EventType.MOVE_STOP, {"new_sl_price": 95.0}, 1))
    assert log.processing_status == EventProcessingStatus.IGNORED
    assert state.current_sl == 90.0


def test_close_full_without_position_is_ignored() -> None:
    state = _base_state()
    log = apply_event(state, _event(EventType.CLOSE_FULL, seq=1))
    assert log.processing_status == EventProcessingStatus.IGNORED
    assert state.status == TradeStatus.NEW
