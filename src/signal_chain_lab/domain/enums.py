"""Domain enumerations for signal chain simulation."""
from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    OPEN_SIGNAL = "OPEN_SIGNAL"
    ADD_ENTRY = "ADD_ENTRY"
    MOVE_STOP = "MOVE_STOP"
    MOVE_STOP_TO_BE = "MOVE_STOP_TO_BE"
    CLOSE_PARTIAL = "CLOSE_PARTIAL"
    CLOSE_FULL = "CLOSE_FULL"
    CANCEL_PENDING = "CANCEL_PENDING"


class EventSource(str, Enum):
    TRADER = "trader"
    ENGINE = "engine"


class TradeStatus(str, Enum):
    NEW = "NEW"
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"
    INVALID = "INVALID"


class ChainInputMode(str, Enum):
    CHAIN_COMPLETE = "chain_complete"
    SIGNAL_ONLY_NATIVE = "signal_only_native"


class EventProcessingStatus(str, Enum):
    APPLIED = "applied"
    IGNORED = "ignored"
    REJECTED = "rejected"
    GENERATED = "generated"


class CloseReason(str, Enum):
    TP = "tp"
    SL = "sl"
    MANUAL = "manual"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    INVALID = "invalid"
    EXPIRED = "expired"
