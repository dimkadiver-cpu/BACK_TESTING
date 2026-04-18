"""Tests for event_normalizer — Step 1 tassonomia PRD event_code.

Verifica:
- Mapping event_type → subtype (event_code PRD) / phase / event_class
- Propagazione raw_text (solo per source=TRADER)
- Gestione eventi IGNORED (processing_status)
- Trade senza eventi → lista vuota, nessun crash
- Fallback su event_type sconosciuto → SYSTEM_NOTE
- ImpactData estratto correttamente da state_after
- ID evento generato correttamente
- Distinzione PENDING_CANCELLED_TRADER vs PENDING_CANCELLED_ENGINE
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
    state_before: dict | None = None,
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
        state_before=state_before or {},
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
# Tests — subtype / phase / event_class mapping (PRD event_code names)
# ---------------------------------------------------------------------------

def test_open_signal_maps_to_setup_created():
    """OPEN_SIGNAL → SETUP_CREATED / ENTRY / STRUCTURAL."""
    trade = _trade()
    log = [_entry("OPEN_SIGNAL")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.SETUP_CREATED
    assert ev.phase == Phase.ENTRY
    assert ev.event_class == EventClass.STRUCTURAL


def test_entry_filled_mapping():
    """ADD_ENTRY applied → ENTRY_FILLED_INITIAL / ENTRY / STRUCTURAL."""
    trade = _trade()
    log = [_entry("ADD_ENTRY", processing_status=EventProcessingStatus.APPLIED)]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.ENTRY_FILLED_INITIAL
    assert ev.phase == Phase.ENTRY
    assert ev.event_class == EventClass.STRUCTURAL


def test_scale_in_fill_mapping():
    """ADD_ENTRY with fills_count >= 2 → ENTRY_FILLED_SCALE_IN."""
    trade = _trade()
    log = [_entry("ADD_ENTRY", state_after={"fills_count": 2})]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.ENTRY_FILLED_SCALE_IN
    assert ev.phase == Phase.ENTRY


def test_sl_moved_mapping():
    """MOVE_STOP → STOP_MOVED / MANAGEMENT / MANAGEMENT."""
    trade = _trade()
    log = [_entry("MOVE_STOP")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.STOP_MOVED
    assert ev.phase == Phase.MANAGEMENT
    assert ev.event_class == EventClass.MANAGEMENT


def test_be_activated_mapping():
    """MOVE_STOP_TO_BE → BREAK_EVEN_ACTIVATED / MANAGEMENT / MANAGEMENT."""
    trade = _trade()
    log = [_entry("MOVE_STOP_TO_BE", reason="be_trigger")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.BREAK_EVEN_ACTIVATED
    assert ev.phase == Phase.MANAGEMENT
    assert ev.event_class == EventClass.MANAGEMENT


def test_partial_exit_tp_mapping():
    """CLOSE_PARTIAL with tp reason → EXIT_PARTIAL_TP / EXIT / RESULT."""
    trade = _trade()
    log = [_entry("CLOSE_PARTIAL", reason="tp_hit")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.EXIT_PARTIAL_TP
    assert ev.phase == Phase.EXIT
    assert ev.event_class == EventClass.RESULT


def test_partial_exit_manual_mapping():
    """CLOSE_PARTIAL without tp reason → EXIT_PARTIAL_MANUAL / EXIT / RESULT."""
    trade = _trade()
    log = [_entry("CLOSE_PARTIAL", reason="manual_partial")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.EXIT_PARTIAL_MANUAL
    assert ev.phase == Phase.EXIT
    assert ev.event_class == EventClass.RESULT


def test_sl_hit_mapping():
    """CLOSE_FULL + reason=sl_hit → EXIT_FINAL_SL / EXIT / RESULT."""
    trade = _trade()
    log = [_entry("CLOSE_FULL", reason="sl_hit")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.EXIT_FINAL_SL
    assert ev.phase == Phase.EXIT
    assert ev.event_class == EventClass.RESULT


def test_final_exit_via_tp_mapping():
    """CLOSE_FULL + reason=tp_hit → EXIT_FINAL_TP / EXIT / RESULT."""
    trade = _trade()
    log = [_entry("CLOSE_FULL", reason="tp_hit")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.EXIT_FINAL_TP
    assert ev.phase == Phase.EXIT
    assert ev.event_class == EventClass.RESULT


def test_final_exit_manual_no_reason():
    """CLOSE_FULL senza reason → EXIT_FINAL_MANUAL (fallback)."""
    trade = _trade()
    log = [_entry("CLOSE_FULL", reason=None)]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.EXIT_FINAL_MANUAL


def test_final_exit_manual_explicit():
    """CLOSE_FULL + reason=manual → EXIT_FINAL_MANUAL."""
    trade = _trade()
    log = [_entry("CLOSE_FULL", reason="manual")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.EXIT_FINAL_MANUAL


def test_exit_final_timeout_from_close_full():
    """CLOSE_FULL + reason=chain_timeout → EXIT_FINAL_TIMEOUT."""
    trade = _trade()
    log = [_entry("CLOSE_FULL", reason="chain_timeout")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.EXIT_FINAL_TIMEOUT


def test_cancel_pending_engine_source():
    """CANCEL_PENDING (engine source, no timeout reason) → PENDING_CANCELLED_ENGINE / EXIT / RESULT."""
    trade = _trade()
    log = [_entry("CANCEL_PENDING", source="engine")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.PENDING_CANCELLED_ENGINE
    assert ev.phase == Phase.EXIT
    assert ev.event_class == EventClass.RESULT


def test_cancel_pending_trader_source():
    """CANCEL_PENDING (trader source) → PENDING_CANCELLED_TRADER / EXIT / RESULT."""
    trade = _trade()
    log = [_entry("CANCEL_PENDING", source="trader")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.PENDING_CANCELLED_TRADER
    assert ev.phase == Phase.EXIT
    assert ev.event_class == EventClass.RESULT


def test_pending_timeout_via_cancel_pending():
    """CANCEL_PENDING + reason=pending_timeout → PENDING_TIMEOUT."""
    trade = _trade()
    log = [_entry("CANCEL_PENDING", reason="pending_timeout")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.PENDING_TIMEOUT
    assert ev.phase == Phase.EXIT


def test_pending_timeout_via_timeout_reason():
    """CANCEL_PENDING + reason=timeout → PENDING_TIMEOUT (timeout overrides source)."""
    trade = _trade()
    log = [_entry("CANCEL_PENDING", source="engine", reason="timeout")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.PENDING_TIMEOUT


# ---------------------------------------------------------------------------
# Tests — IGNORED / REJECTED events
# ---------------------------------------------------------------------------

def test_ignored_event_maps_to_ignored_subtype():
    """Evento con processing_status=IGNORED → IGNORED / MANAGEMENT / AUDIT."""
    trade = _trade()
    log = [_entry("ADD_ENTRY", processing_status=EventProcessingStatus.IGNORED)]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.IGNORED
    assert ev.phase == Phase.MANAGEMENT
    assert ev.event_class == EventClass.AUDIT


def test_rejected_event_maps_to_ignored():
    """Evento con processing_status=REJECTED → IGNORED / MANAGEMENT / AUDIT."""
    trade = _trade()
    log = [_entry("MOVE_STOP", processing_status=EventProcessingStatus.REJECTED)]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.IGNORED
    assert ev.phase == Phase.MANAGEMENT
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
    """event_type sconosciuto → SYSTEM_NOTE / MANAGEMENT / AUDIT."""
    trade = _trade()
    log = [_entry("COMPLETELY_UNKNOWN_TYPE")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.SYSTEM_NOTE
    assert ev.phase == Phase.MANAGEMENT
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


def test_fill_event_uses_fill_price_as_anchor() -> None:
    trade = _trade()
    log = [
        _entry(
            "FILL",
            state_after={
                "fills": [
                    {"timestamp": "2025-01-15T10:32:05+00:00", "price": 42001.25, "qty": 1.0},
                ]
            },
        )
    ]
    ev = normalize_events(trade, log)[0]
    assert ev.price_anchor == 42001.25


def test_tp_hit_anchor_uses_removed_tp_when_next_tp_index_missing() -> None:
    trade = _trade()
    log = [
        _entry(
            "CLOSE_PARTIAL",
            reason="tp_hit",
            state_before={"tp_levels": [42100.0, 42200.0]},
            state_after={"tp_levels": [42200.0]},
        )
    ]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.EXIT_PARTIAL_TP
    assert ev.price_anchor == 42100.0


def test_tp_hit_anchor_uses_previous_tp_when_engine_snapshot_is_already_advanced() -> None:
    trade = _trade()
    log = [
        _entry(
            "CLOSE_PARTIAL",
            reason="tp_hit_partial",
            state_before={"next_tp_index": 1, "tp_levels": [42100.0, 42200.0]},
            state_after={"next_tp_index": 1, "tp_levels": [42100.0, 42200.0]},
        )
    ]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.EXIT_PARTIAL_TP
    assert ev.price_anchor == 42100.0


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
    assert result[0].subtype == Subtype.SETUP_CREATED
    assert result[1].subtype == Subtype.ENTRY_FILLED_INITIAL
    assert result[2].subtype == Subtype.EXIT_FINAL_SL


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
