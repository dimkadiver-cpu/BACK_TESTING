"""Tests for chain validators (S1.11)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.signal_chain_lab.adapters.validators import (
    ChainValidationResult,
    GapSeverity,
    validate_chain_for_simulation,
    validate_chain_identity,
)
from src.signal_chain_lab.domain.enums import ChainInputMode, EventSource, EventType
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent


def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def _make_open_event(
    signal_id: str = "chain_001",
    entries: list[float] | None = None,
    sl: float | None = 85000.0,
    tps: list[float] | None = None,
) -> CanonicalEvent:
    payload: dict = {}
    if entries is not None:
        payload["entry_prices"] = entries
    if sl is not None:
        payload["sl_price"] = sl
    if tps is not None:
        payload["tp_levels"] = tps

    return CanonicalEvent(
        signal_id=signal_id,
        symbol="BTCUSDT",
        side="BUY",
        timestamp=_utc("2025-06-01T10:00:00"),
        event_type=EventType.OPEN_SIGNAL,
        source=EventSource.TRADER,
        payload=payload,
        sequence=0,
    )


def _make_chain(
    signal_id: str = "chain_001",
    symbol: str = "BTCUSDT",
    side: str = "BUY",
    events: list[CanonicalEvent] | None = None,
) -> CanonicalChain:
    if events is None:
        events = [_make_open_event(
            signal_id=signal_id,
            entries=[90000.0],
            sl=85000.0,
            tps=[95000.0, 100000.0],
        )]
    return CanonicalChain(
        signal_id=signal_id,
        symbol=symbol,
        side=side,
        input_mode=ChainInputMode.SIGNAL_ONLY_NATIVE,
        has_updates_in_dataset=False,
        created_at=_utc("2025-06-01T10:00:00"),
        events=events,
    )


# ---------------------------------------------------------------------------
# Identity validation
# ---------------------------------------------------------------------------

def test_valid_chain_identity() -> None:
    chain = _make_chain()
    gaps = validate_chain_identity(chain)
    assert gaps == []


def test_missing_signal_id_is_fatal() -> None:
    chain = _make_chain(signal_id="")
    gaps = validate_chain_identity(chain)
    assert any(g.field == "signal_id" and g.severity == GapSeverity.FATAL for g in gaps)


def test_missing_symbol_is_fatal() -> None:
    chain = _make_chain(symbol="")
    gaps = validate_chain_identity(chain)
    assert any(g.field == "symbol" and g.severity == GapSeverity.FATAL for g in gaps)


def test_missing_side_is_fatal() -> None:
    chain = _make_chain(side="")
    gaps = validate_chain_identity(chain)
    assert any(g.field == "side" and g.severity == GapSeverity.FATAL for g in gaps)


# ---------------------------------------------------------------------------
# Simulation validation — valid chain
# ---------------------------------------------------------------------------

def test_fully_valid_chain_is_simulable() -> None:
    chain = _make_chain()
    result = validate_chain_for_simulation(chain)
    assert result.is_simulable is True
    assert result.is_valid_identity is True
    assert result.fatal_gaps == []


# ---------------------------------------------------------------------------
# Simulation validation — missing entry
# ---------------------------------------------------------------------------

def test_missing_entry_is_fatal() -> None:
    event = _make_open_event(entries=[], sl=85000.0, tps=[95000.0])
    chain = _make_chain(events=[event])
    result = validate_chain_for_simulation(chain)
    assert result.is_simulable is False
    assert any(g.field == "entry" for g in result.fatal_gaps)


# ---------------------------------------------------------------------------
# Simulation validation — missing SL
# ---------------------------------------------------------------------------

def test_missing_sl_is_fatal() -> None:
    event = _make_open_event(entries=[90000.0], sl=None, tps=[95000.0])
    chain = _make_chain(events=[event])
    result = validate_chain_for_simulation(chain)
    assert result.is_simulable is False
    assert any(g.field == "stop_loss" for g in result.fatal_gaps)


# ---------------------------------------------------------------------------
# Simulation validation — missing TP
# ---------------------------------------------------------------------------

def test_missing_tp_is_fatal() -> None:
    event = _make_open_event(entries=[90000.0], sl=85000.0, tps=[])
    chain = _make_chain(events=[event])
    result = validate_chain_for_simulation(chain)
    assert result.is_simulable is False
    assert any(g.field == "take_profit" for g in result.fatal_gaps)


# ---------------------------------------------------------------------------
# Simulation validation — no events
# ---------------------------------------------------------------------------

def test_chain_with_no_events_is_not_simulable() -> None:
    chain = _make_chain(events=[])
    result = validate_chain_for_simulation(chain)
    assert result.is_simulable is False
    assert any(g.field == "events" for g in result.fatal_gaps)


# ---------------------------------------------------------------------------
# Simulation validation — missing entry AND SL
# ---------------------------------------------------------------------------

def test_multiple_fatal_gaps_all_reported() -> None:
    event = _make_open_event(entries=[], sl=None, tps=[95000.0])
    chain = _make_chain(events=[event])
    result = validate_chain_for_simulation(chain)
    assert result.is_simulable is False
    fatal_fields = {g.field for g in result.fatal_gaps}
    assert "entry" in fatal_fields
    assert "stop_loss" in fatal_fields
