"""Tests for domain enumerations (S1.9)."""
from __future__ import annotations

from src.signal_chain_lab.domain.enums import (
    ChainInputMode,
    CloseReason,
    EventProcessingStatus,
    EventSource,
    EventType,
    TradeStatus,
)


def test_event_type_values() -> None:
    assert EventType.OPEN_SIGNAL == "OPEN_SIGNAL"
    assert EventType.ADD_ENTRY == "ADD_ENTRY"
    assert EventType.MOVE_STOP == "MOVE_STOP"
    assert EventType.MOVE_STOP_TO_BE == "MOVE_STOP_TO_BE"
    assert EventType.CLOSE_PARTIAL == "CLOSE_PARTIAL"
    assert EventType.CLOSE_FULL == "CLOSE_FULL"
    assert EventType.CANCEL_PENDING == "CANCEL_PENDING"


def test_event_type_all_members() -> None:
    members = {e.value for e in EventType}
    assert members == {
        "OPEN_SIGNAL", "ADD_ENTRY", "MOVE_STOP", "MOVE_STOP_TO_BE",
        "CLOSE_PARTIAL", "CLOSE_FULL", "CANCEL_PENDING",
    }


def test_event_source_values() -> None:
    assert EventSource.TRADER == "trader"
    assert EventSource.ENGINE == "engine"


def test_trade_status_values() -> None:
    expected = {"NEW", "PENDING", "ACTIVE", "PARTIALLY_CLOSED", "CANCELLED", "CLOSED", "EXPIRED", "INVALID"}
    assert {s.value for s in TradeStatus} == expected


def test_chain_input_mode_values() -> None:
    assert ChainInputMode.CHAIN_COMPLETE == "chain_complete"
    assert ChainInputMode.SIGNAL_ONLY_NATIVE == "signal_only_native"


def test_event_processing_status_values() -> None:
    expected = {"applied", "ignored", "rejected", "generated"}
    assert {s.value for s in EventProcessingStatus} == expected


def test_close_reason_values() -> None:
    expected = {"tp", "sl", "manual", "timeout", "cancelled", "invalid", "expired"}
    assert {r.value for r in CloseReason} == expected


def test_enums_are_strings() -> None:
    """All enums inherit from str — can be used directly as string values."""
    assert isinstance(EventType.OPEN_SIGNAL, str)
    assert isinstance(TradeStatus.ACTIVE, str)
    assert isinstance(CloseReason.TP, str)
