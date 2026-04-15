"""Tests for event_normalizer — Fase 1 del sistema report 3 livelli.

Verifica:
- Mapping event_type → subtype / phase / event_class
- Propagazione raw_text (solo per source=TRADER)
- Gestione eventi IGNORED (processing_status)
- Trade senza eventi → lista vuota, nessun crash
- Fallback su event_type sconosciuto → SYSTEM_NOTE
- ImpactData estratto correttamente da state_after
- ID evento generato correttamente
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.signal_chain_lab.domain.enums import ChainInputMode, EventProcessingStatus
from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult
from src.signal_chain_lab.policy_report.event_normalizer import (
    EventClass,
    ImpactData,
    Phase,
    ReportCanonicalEvent,
    Subtype,
    normalize_events,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2025, 1, 15, 10, 32, 0, tzinfo=timezone.utc)


def _trade(signal_id: str = "sig_001") -> TradeResult:
    return TradeResult(
        signal_id=signal_id,
        symbol="BTCUSDT",
        side="LONG",
        status="closed",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        policy_name="test_policy",
    )


def _entry(
    event_type: str,
    source: str = "engine",
    processing_status: EventProcessingStatus = EventProcessingStatus.APPLIED,
    price_reference: float | None = None,
    reason: str | None = None,
    raw_text: str | None = None,
    state_after: dict | None = None,
) -> EventLogEntry:
    return EventLogEntry(
        timestamp=_TS,
        signal_id="sig_001",
        event_type=event_type,
        source=source,
        processing_status=processing_status,
        price_reference=price_reference,
        reason=reason,
        raw_text=raw_text,
        state_before={},
        state_after=state_after or {},
    )


# ---------------------------------------------------------------------------
# Tests — output structure
# ---------------------------------------------------------------------------

def test_returns_list_of_canonical_events():
    trade = _trade()
    log = [_entry("OPEN_SIGNAL")]
    result = normalize_events(trade, log)
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], ReportCanonicalEvent)


def test_empty_event_log_returns_empty_list():
    """Trade senza eventi → lista vuota, nessun crash."""
    trade = _trade()
    result = normalize_events(trade, [])
    assert result == []


def test_event_id_format():
    trade = _trade("sig_abc")
    log = [_entry("OPEN_SIGNAL"), _entry("CLOSE_FULL", reason="tp_hit")]
    result = normalize_events(trade, log)
    assert result[0].id == "sig_abc_0"
    assert result[1].id == "sig_abc_1"


def test_timestamp_iso_string():
    trade = _trade()
    log = [_entry("OPEN_SIGNAL")]
    result = normalize_events(trade, log)
    assert "2025-01-15" in result[0].ts


# ---------------------------------------------------------------------------
# Tests — subtype / phase / event_class mapping
# ---------------------------------------------------------------------------

def test_open_signal_maps_to_signal_created():
    """OPEN_SIGNAL → SIGNAL_CREATED / SETUP / STRUCTURAL."""
    trade = _trade()
    log = [_entry("OPEN_SIGNAL")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.SIGNAL_CREATED
    assert ev.phase == Phase.SETUP
    assert ev.event_class == EventClass.STRUCTURAL


def test_entry_filled_mapping():
    """ADD_ENTRY applied → ENTRY_FILLED / ENTRY / STRUCTURAL."""
    trade = _trade()
    log = [_entry("ADD_ENTRY", processing_status=EventProcessingStatus.APPLIED)]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.ENTRY_FILLED
    assert ev.phase == Phase.ENTRY
    assert ev.event_class == EventClass.STRUCTURAL


def test_sl_moved_mapping():
    """MOVE_STOP → SL_MOVED / MANAGEMENT / MANAGEMENT."""
    trade = _trade()
    log = [_entry("MOVE_STOP")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.SL_MOVED
    assert ev.phase == Phase.MANAGEMENT
    assert ev.event_class == EventClass.MANAGEMENT


def test_be_activated_mapping():
    """MOVE_STOP_TO_BE → BE_ACTIVATED / MANAGEMENT / MANAGEMENT."""
    trade = _trade()
    log = [_entry("MOVE_STOP_TO_BE", reason="be_trigger")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.BE_ACTIVATED
    assert ev.phase == Phase.MANAGEMENT
    assert ev.event_class == EventClass.MANAGEMENT


def test_partial_exit_mapping():
    """CLOSE_PARTIAL → PARTIAL_EXIT / EXIT / RESULT."""
    trade = _trade()
    log = [_entry("CLOSE_PARTIAL", reason="tp_hit_partial")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.PARTIAL_EXIT
    assert ev.phase == Phase.EXIT
    assert ev.event_class == EventClass.RESULT


def test_sl_hit_mapping():
    """CLOSE_FULL + reason=sl_hit → SL_HIT / EXIT / RESULT."""
    trade = _trade()
    log = [_entry("CLOSE_FULL", reason="sl_hit")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.SL_HIT
    assert ev.phase == Phase.EXIT
    assert ev.event_class == EventClass.RESULT


def test_final_exit_via_tp_mapping():
    """CLOSE_FULL + reason=tp_hit → FINAL_EXIT / EXIT / RESULT."""
    trade = _trade()
    log = [_entry("CLOSE_FULL", reason="tp_hit")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.FINAL_EXIT
    assert ev.phase == Phase.EXIT
    assert ev.event_class == EventClass.RESULT


def test_final_exit_no_reason():
    """CLOSE_FULL senza reason → FINAL_EXIT (fallback)."""
    trade = _trade()
    log = [_entry("CLOSE_FULL", reason=None)]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.FINAL_EXIT


def test_cancelled_mapping():
    """CANCEL_PENDING → CANCELLED / EXIT / RESULT."""
    trade = _trade()
    log = [_entry("CANCEL_PENDING")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.CANCELLED
    assert ev.phase == Phase.EXIT
    assert ev.event_class == EventClass.RESULT


def test_timeout_via_cancel_pending():
    """CANCEL_PENDING + reason=pending_timeout → TIMEOUT."""
    trade = _trade()
    log = [_entry("CANCEL_PENDING", reason="pending_timeout")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.TIMEOUT
    assert ev.phase == Phase.EXIT


def test_timeout_via_close_full():
    """CLOSE_FULL + reason=chain_timeout → TIMEOUT."""
    trade = _trade()
    log = [_entry("CLOSE_FULL", reason="chain_timeout")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.TIMEOUT


# ---------------------------------------------------------------------------
# Tests — IGNORED / REJECTED events
# ---------------------------------------------------------------------------

def test_ignored_event_maps_to_ignored_subtype():
    """Evento con processing_status=IGNORED → IGNORED / POST_MORTEM / AUDIT."""
    trade = _trade()
    log = [_entry("ADD_ENTRY", processing_status=EventProcessingStatus.IGNORED)]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.IGNORED
    assert ev.phase == Phase.POST_MORTEM
    assert ev.event_class == EventClass.AUDIT


def test_rejected_event_maps_to_ignored():
    """Evento con processing_status=REJECTED → IGNORED / POST_MORTEM / AUDIT."""
    trade = _trade()
    log = [_entry("MOVE_STOP", processing_status=EventProcessingStatus.REJECTED)]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.IGNORED
    assert ev.phase == Phase.POST_MORTEM
    assert ev.event_class == EventClass.AUDIT


def test_any_event_type_ignored_maps_to_ignored():
    """Qualsiasi event_type con IGNORED → sempre IGNORED (non dipende dal tipo)."""
    trade = _trade()
    for et in ("OPEN_SIGNAL", "CLOSE_FULL", "MOVE_STOP_TO_BE", "CANCEL_PENDING"):
        log = [_entry(et, processing_status=EventProcessingStatus.IGNORED)]
        ev = normalize_events(trade, log)[0]
        assert ev.subtype == Subtype.IGNORED, f"Failed for event_type={et}"


# ---------------------------------------------------------------------------
# Tests — raw_text propagation
# ---------------------------------------------------------------------------

def test_raw_text_propagated_for_trader_source():
    """raw_text presente per eventi con source=TRADER."""
    trade = _trade()
    log = [_entry("OPEN_SIGNAL", source="trader", raw_text="BTC LONG 42000")]
    ev = normalize_events(trade, log)[0]
    assert ev.raw_text == "BTC LONG 42000"
    assert ev.source == "TRADER"


def test_raw_text_none_for_engine_source():
    """raw_text deve essere None per eventi ENGINE, anche se presente nel log."""
    trade = _trade()
    log = [_entry("CLOSE_FULL", source="engine", raw_text="some engine text", reason="tp_hit")]
    ev = normalize_events(trade, log)[0]
    assert ev.raw_text is None
    assert ev.source == "ENGINE"


def test_raw_text_none_when_entry_has_no_raw_text():
    """raw_text=None nel log → raw_text=None nel canonico."""
    trade = _trade()
    log = [_entry("OPEN_SIGNAL", source="trader", raw_text=None)]
    ev = normalize_events(trade, log)[0]
    assert ev.raw_text is None


# ---------------------------------------------------------------------------
# Tests — SYSTEM_NOTE fallback
# ---------------------------------------------------------------------------

def test_unknown_event_type_fallback_to_system_note():
    """event_type sconosciuto → SYSTEM_NOTE / POST_MORTEM / AUDIT."""
    trade = _trade()
    log = [_entry("COMPLETELY_UNKNOWN_TYPE")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.SYSTEM_NOTE
    assert ev.phase == Phase.POST_MORTEM
    assert ev.event_class == EventClass.AUDIT


# ---------------------------------------------------------------------------
# Tests — ImpactData extraction from state_after
# ---------------------------------------------------------------------------

def test_impact_extracted_from_state_after():
    """ImpactData.position/risk/result letti da state_after."""
    trade = _trade()
    state_after = {
        "open_size": 0.5,
        "current_sl": 41500.0,
        "realized_pnl": 125.0,
    }
    log = [_entry("ADD_ENTRY", state_after=state_after)]
    ev = normalize_events(trade, log)[0]
    assert ev.impact.position == 0.5
    assert ev.impact.risk == 41500.0
    assert ev.impact.result == 125.0


def test_impact_none_when_state_after_empty():
    """Tutti i campi ImpactData sono None se state_after è vuoto."""
    trade = _trade()
    log = [_entry("OPEN_SIGNAL", state_after={})]
    ev = normalize_events(trade, log)[0]
    assert ev.impact.position is None
    assert ev.impact.risk is None
    assert ev.impact.result is None


def test_impact_partial_state_after():
    """Solo i campi presenti in state_after sono popolati."""
    trade = _trade()
    state_after = {"current_sl": 40000.0}
    log = [_entry("MOVE_STOP", state_after=state_after)]
    ev = normalize_events(trade, log)[0]
    assert ev.impact.position is None
    assert ev.impact.risk == 40000.0
    assert ev.impact.result is None


# ---------------------------------------------------------------------------
# Tests — price_anchor
# ---------------------------------------------------------------------------

def test_price_anchor_from_price_reference():
    """price_anchor = entry.price_reference."""
    trade = _trade()
    log = [_entry("CLOSE_FULL", price_reference=42150.5, reason="tp_hit")]
    ev = normalize_events(trade, log)[0]
    assert ev.price_anchor == 42150.5


def test_price_anchor_none_when_not_set():
    """price_anchor=None quando price_reference non è fornito."""
    trade = _trade()
    log = [_entry("OPEN_SIGNAL")]
    ev = normalize_events(trade, log)[0]
    assert ev.price_anchor is None


# ---------------------------------------------------------------------------
# Tests — multiple events in sequence
# ---------------------------------------------------------------------------

def test_multiple_events_ordered_and_indexed():
    """Lista di eventi: IDs sequenziali, ordine preservato."""
    trade = _trade("sig_xyz")
    log = [
        _entry("OPEN_SIGNAL", source="trader"),
        _entry("ADD_ENTRY", processing_status=EventProcessingStatus.APPLIED),
        _entry("CLOSE_FULL", reason="sl_hit"),
    ]
    result = normalize_events(trade, log)
    assert len(result) == 3
    assert result[0].id == "sig_xyz_0"
    assert result[1].id == "sig_xyz_1"
    assert result[2].id == "sig_xyz_2"
    assert result[0].subtype == Subtype.SIGNAL_CREATED
    assert result[1].subtype == Subtype.ENTRY_FILLED
    assert result[2].subtype == Subtype.SL_HIT


def test_details_contain_state_after_and_extras():
    """details contiene state_after + requested_action + executed_action + reason."""
    trade = _trade()
    state_after = {"open_size": 1.0, "current_sl": 100.0}
    log = [
        EventLogEntry(
            timestamp=_TS,
            signal_id="sig_001",
            event_type="OPEN_SIGNAL",
            source="trader",
            processing_status=EventProcessingStatus.APPLIED,
            requested_action="open_trade",
            executed_action="position_opened",
            reason="initial_setup",
            state_before={},
            state_after=state_after,
        )
    ]
    ev = normalize_events(trade, log)[0]
    assert ev.details["open_size"] == 1.0
    assert ev.details["current_sl"] == 100.0
    assert ev.details["requested_action"] == "open_trade"
    assert ev.details["executed_action"] == "position_opened"
    assert ev.details["reason"] == "initial_setup"
