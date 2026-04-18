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
    """FILL applied → ENTRY_FILLED_INITIAL / ENTRY / STRUCTURAL."""
    trade = _trade()
    log = [_entry("FILL", processing_status=EventProcessingStatus.APPLIED)]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.ENTRY_FILLED_INITIAL
    assert ev.phase == Phase.ENTRY
    assert ev.event_class == EventClass.STRUCTURAL


def test_scale_in_fill_mapping():
    """FILL with fills_count >= 2 → ENTRY_FILLED_SCALE_IN."""
    trade = _trade()
    log = [_entry("FILL", state_before={"open_size": 1.0}, state_after={"fills_count": 2, "open_size": 2.0})]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.ENTRY_FILLED_SCALE_IN
    assert ev.phase == Phase.MANAGEMENT


def test_entry_order_added_mapping():
    """ADD_ENTRY applied without fill → ENTRY_ORDER_ADDED / ENTRY / STRUCTURAL."""
    trade = _trade()
    log = [_entry("ADD_ENTRY", processing_status=EventProcessingStatus.APPLIED)]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.ENTRY_ORDER_ADDED
    assert ev.phase == Phase.ENTRY
    assert ev.event_class == EventClass.STRUCTURAL


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
    """CLOSE_PARTIAL with tp reason → EXIT_PARTIAL_TP / MANAGEMENT / RESULT."""
    trade = _trade()
    log = [_entry("CLOSE_PARTIAL", reason="tp_hit")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.EXIT_PARTIAL_TP
    assert ev.phase == Phase.MANAGEMENT
    assert ev.event_class == EventClass.RESULT


def test_partial_exit_manual_mapping():
    """CLOSE_PARTIAL without tp reason → EXIT_PARTIAL_MANUAL / MANAGEMENT / RESULT."""
    trade = _trade()
    log = [_entry("CLOSE_PARTIAL", reason="manual_partial")]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.EXIT_PARTIAL_MANUAL
    assert ev.phase == Phase.MANAGEMENT
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
    log = [_entry("FILL", state_after=state_after)]
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


def test_close_full_tp_anchor_uses_removed_tp_when_price_reference_missing() -> None:
    trade = _trade()
    log = [
        _entry(
            "CLOSE_FULL",
            reason="tp_hit",
            state_before={"tp_levels": [42100.0, 42200.0], "open_size": 1.0},
            state_after={"tp_levels": [42200.0], "open_size": 0.0},
        )
    ]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.EXIT_FINAL_TP
    assert ev.price_anchor == 42100.0


def test_sl_hit_anchor_uses_state_before_current_sl_when_price_reference_missing() -> None:
    trade = _trade()
    log = [
        _entry(
            "CLOSE_FULL",
            reason="sl_hit",
            state_before={"open_size": 1.0, "current_sl": 41850.0},
            state_after={"open_size": 0.0, "realized_pnl": -150.0},
        )
    ]
    ev = normalize_events(trade, log)[0]
    assert ev.subtype == Subtype.EXIT_FINAL_SL
    assert ev.price_anchor == 41850.0


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
    assert result[1].subtype == Subtype.ENTRY_ORDER_ADDED
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


# ---------------------------------------------------------------------------
# Tests — chart_marker_kind (PRD §9)
# ---------------------------------------------------------------------------

def test_chart_marker_kind_required_for_entry_filled_initial():
    """ENTRY_FILLED_INITIAL → chart_marker_kind = REQUIRED (PRD §9)."""
    ev = normalize_events(_trade(), [_entry("FILL")])[0]
    assert ev.chart_marker_kind == "REQUIRED"


def test_chart_marker_kind_required_for_entry_filled_scale_in():
    """ENTRY_FILLED_SCALE_IN → chart_marker_kind = REQUIRED."""
    ev = normalize_events(_trade(), [_entry("FILL", state_before={"open_size": 1.0}, state_after={"fills_count": 2})])[0]
    assert ev.chart_marker_kind == "REQUIRED"


def test_chart_marker_kind_required_for_exit_partial_tp():
    ev = normalize_events(_trade(), [_entry("CLOSE_PARTIAL", reason="tp_hit")])[0]
    assert ev.chart_marker_kind == "REQUIRED"


def test_chart_marker_kind_required_for_exit_final_sl():
    ev = normalize_events(_trade(), [_entry("CLOSE_FULL", reason="sl_hit")])[0]
    assert ev.chart_marker_kind == "REQUIRED"


def test_chart_marker_kind_optional_light_for_exit_final_timeout():
    """EXIT_FINAL_TIMEOUT → chart_marker_kind = REQUIRED (PRD §9)."""
    ev = normalize_events(_trade(), [_entry("CLOSE_FULL", reason="chain_timeout")])[0]
    assert ev.chart_marker_kind == "REQUIRED"


def test_chart_marker_kind_none_for_setup_created():
    """SETUP_CREATED → chart_marker_kind = NONE (PRD §9)."""
    ev = normalize_events(_trade(), [_entry("OPEN_SIGNAL")])[0]
    assert ev.chart_marker_kind == "NONE"


def test_chart_marker_kind_none_for_stop_moved():
    """STOP_MOVED → chart_marker_kind = NONE — geometry only, no chart marker."""
    ev = normalize_events(_trade(), [_entry("MOVE_STOP")])[0]
    assert ev.chart_marker_kind == "NONE"


def test_chart_marker_kind_none_for_break_even_activated():
    ev = normalize_events(_trade(), [_entry("MOVE_STOP_TO_BE")])[0]
    assert ev.chart_marker_kind == "NONE"


def test_chart_marker_kind_none_for_pending_cancelled_trader():
    ev = normalize_events(_trade(), [_entry("CANCEL_PENDING", source="trader")])[0]
    assert ev.chart_marker_kind == "OPTIONAL_LIGHT"


def test_chart_marker_kind_optional_light_for_pending_timeout():
    ev = normalize_events(_trade(), [_entry("CANCEL_PENDING", reason="timeout")])[0]
    assert ev.chart_marker_kind == "OPTIONAL_LIGHT"


def test_event_list_section_a_for_pending_cancelled():
    ev = normalize_events(_trade(), [_entry("CANCEL_PENDING", source="trader")])[0]
    assert ev.event_list_section == "A"


def test_chart_marker_kind_none_for_ignored():
    ev = normalize_events(
        _trade(),
        [_entry("ADD_ENTRY", processing_status=EventProcessingStatus.IGNORED)],
    )[0]
    assert ev.chart_marker_kind == "NONE"


# ---------------------------------------------------------------------------
# Tests — event_list_section (PRD §5)
# ---------------------------------------------------------------------------

def test_event_list_section_a_for_setup_created():
    ev = normalize_events(_trade(), [_entry("OPEN_SIGNAL")])[0]
    assert ev.event_list_section == "A"


def test_event_list_section_a_for_entry_filled():
    ev = normalize_events(_trade(), [_entry("FILL")])[0]
    assert ev.event_list_section == "A"


def test_event_list_section_a_for_exit_events():
    for event_type, reason in [
        ("CLOSE_FULL", "sl_hit"),
        ("CLOSE_FULL", "tp_hit"),
        ("CLOSE_PARTIAL", "tp_hit"),
        ("CLOSE_FULL", "chain_timeout"),
    ]:
        ev = normalize_events(_trade(), [_entry(event_type, reason=reason)])[0]
        assert ev.event_list_section == "A", f"Expected A for {event_type}+{reason}"


def test_event_list_section_b_for_ignored():
    """IGNORED → event_list_section = B (Section B — audit/informational, PRD §5)."""
    ev = normalize_events(
        _trade(),
        [_entry("ADD_ENTRY", processing_status=EventProcessingStatus.IGNORED)],
    )[0]
    assert ev.event_list_section == "B"


def test_event_list_section_b_for_system_note():
    """SYSTEM_NOTE (unknown event_type) → event_list_section = B."""
    ev = normalize_events(_trade(), [_entry("COMPLETELY_UNKNOWN")])[0]
    assert ev.event_list_section == "B"


# ---------------------------------------------------------------------------
# Tests — position_effect (PRD §6.2)
# ---------------------------------------------------------------------------

def test_position_effect_plan_created_for_setup():
    ev = normalize_events(_trade(), [_entry("OPEN_SIGNAL")])[0]
    assert ev.position_effect == "PLAN_CREATED"


def test_position_effect_position_opened_for_initial_fill():
    ev = normalize_events(_trade(), [_entry("FILL")])[0]
    assert ev.position_effect == "POSITION_OPENED"


def test_position_effect_position_increased_for_scale_in():
    ev = normalize_events(_trade(), [_entry("FILL", state_before={"open_size": 1.0}, state_after={"fills_count": 2})])[0]
    assert ev.position_effect == "POSITION_INCREASED"


def test_position_effect_stop_adjusted_for_stop_moved():
    ev = normalize_events(_trade(), [_entry("MOVE_STOP")])[0]
    assert ev.position_effect == "PLAN_UPDATED"


def test_position_effect_position_closed_for_sl_hit():
    ev = normalize_events(_trade(), [_entry("CLOSE_FULL", reason="sl_hit")])[0]
    assert ev.position_effect == "POSITION_CLOSED"


def test_position_effect_plan_cancelled_for_cancel_pending():
    ev = normalize_events(_trade(), [_entry("CANCEL_PENDING", source="trader")])[0]
    assert ev.position_effect == "PENDING_CANCELLED"


def test_position_effect_no_effect_for_ignored():
    ev = normalize_events(
        _trade(),
        [_entry("ADD_ENTRY", processing_status=EventProcessingStatus.IGNORED)],
    )[0]
    assert ev.position_effect == "NO_EFFECT"


# ---------------------------------------------------------------------------
# Tests — geometry_effect (PRD §15.2)
# ---------------------------------------------------------------------------

def test_geometry_effect_create_initial_levels_for_setup():
    ev = normalize_events(_trade(), [_entry("OPEN_SIGNAL")])[0]
    assert ev.geometry_effect == "CREATE_INITIAL_LEVELS"


def test_geometry_effect_activate_filled_entry_for_fill():
    ev = normalize_events(_trade(), [_entry("FILL")])[0]
    assert ev.geometry_effect == "ACTIVATE_FILLED_ENTRY"


def test_geometry_effect_scale_in_updates_average_entry():
    ev = normalize_events(_trade(), [_entry("FILL", state_before={"open_size": 1.0}, state_after={"fills_count": 2})])[0]
    assert ev.geometry_effect == "UPDATE_AVERAGE_ENTRY_AND_POSITION_LEVELS"


def test_geometry_effect_move_sl_level_for_stop_moved():
    ev = normalize_events(_trade(), [_entry("MOVE_STOP")])[0]
    assert ev.geometry_effect == "UPDATE_STOP_LINE"


def test_geometry_effect_break_even_converts_stop():
    ev = normalize_events(_trade(), [_entry("MOVE_STOP_TO_BE")])[0]
    assert ev.geometry_effect == "CONVERT_STOP_TO_BE"


def test_geometry_effect_close_all_for_sl_hit():
    ev = normalize_events(_trade(), [_entry("CLOSE_FULL", reason="sl_hit")])[0]
    assert ev.geometry_effect == "CLOSE_POSITION_LEVELS"


def test_geometry_effect_cancel_pending_level_for_cancel():
    ev = normalize_events(_trade(), [_entry("CANCEL_PENDING")])[0]
    assert ev.geometry_effect == "REMOVE_PENDING_LEVEL"


def test_cancel_pending_anchor_falls_back_to_entry_level_when_snapshot_keeps_plan() -> None:
    ev = normalize_events(
        _trade(),
        [
            _entry(
                "CANCEL_PENDING",
                state_before={
                    "pending_size": 1.0,
                    "entries_planned": [{"plan_id": "e1", "price": 41950.0, "order_type": "LIMIT"}],
                },
                state_after={
                    "pending_size": 0.0,
                    "entries_planned": [{"plan_id": "e1", "price": 41950.0, "order_type": "LIMIT"}],
                },
            )
        ],
    )[0]
    assert ev.price_anchor == 41950.0


def test_geometry_effect_none_for_ignored():
    ev = normalize_events(
        _trade(),
        [_entry("ADD_ENTRY", processing_status=EventProcessingStatus.IGNORED)],
    )[0]
    assert ev.geometry_effect == "ANNOTATION_ONLY"


# ---------------------------------------------------------------------------
# Tests — Step 2 canonical enrichment / state delta (PRD §6, §11)
# ---------------------------------------------------------------------------

def test_display_label_falls_back_from_event_code():
    ev = normalize_events(_trade(), [_entry("MOVE_STOP")])[0]
    assert ev.display_label == "MOVE STOP"


def test_display_group_assigned_for_exit_final():
    ev = normalize_events(_trade(), [_entry("CLOSE_FULL", reason="sl_hit")])[0]
    assert ev.display_group == "EXIT_FINAL"


def test_raw_event_ref_contains_source_index_and_type():
    ev = normalize_events(_trade("sig_step2"), [_entry("OPEN_SIGNAL")])[0]
    assert ev.raw_event_ref == "sig_step2:0:OPEN_SIGNAL"


def test_state_delta_full_contains_mutations_for_core_fields():
    ev = normalize_events(
        _trade(),
        [
            _entry(
                "MOVE_STOP",
                state_before={"open_size": 1.0, "current_sl": 42000.0, "status": "ACTIVE"},
                state_after={"open_size": 1.0, "current_sl": 42150.0, "status": "ACTIVE"},
            )
        ],
    )[0]
    fields = {item["field_path"] for item in ev.state_delta_full}
    assert "current_sl" in fields
    assert "open_size" not in fields


def test_state_delta_essential_derived_from_state_delta_full():
    ev = normalize_events(
        _trade(),
        [
            _entry(
                "CLOSE_PARTIAL",
                reason="tp_hit",
                state_before={"open_size": 1.0, "realized_pnl": 0.0, "current_sl": 42000.0},
                state_after={"open_size": 0.5, "realized_pnl": 115.0, "current_sl": 42100.0},
            )
        ],
    )[0]
    assert ev.state_delta_full
    essential_fields = {item["field_path"] for item in ev.state_delta_essential}
    assert "open_size" in essential_fields
    assert "realized_pnl" in essential_fields


# ---------------------------------------------------------------------------
# Tests — stage per CANCEL/TIMEOUT (PRD §12)
# ---------------------------------------------------------------------------

def test_stage_cancel_open_size_zero_is_entry():
    """CANCEL_PENDING con open_size=0 in state_before → stage = ENTRY (PRD §12)."""
    log = [_entry("CANCEL_PENDING", source="trader", state_before={"open_size": 0})]
    ev = normalize_events(_trade(), log)[0]
    assert ev.stage == Phase.ENTRY


def test_stage_cancel_open_size_positive_is_management():
    """CANCEL_PENDING con open_size>0 in state_before → stage = MANAGEMENT (PRD §12)."""
    log = [_entry("CANCEL_PENDING", source="engine", state_before={"open_size": 0.5})]
    ev = normalize_events(_trade(), log)[0]
    assert ev.stage == Phase.MANAGEMENT


def test_stage_pending_timeout_open_size_zero_is_entry():
    """PENDING_TIMEOUT con open_size=0 → stage = ENTRY."""
    log = [_entry("CANCEL_PENDING", reason="timeout", state_before={"open_size": 0})]
    ev = normalize_events(_trade(), log)[0]
    assert ev.subtype == Subtype.PENDING_TIMEOUT
    assert ev.stage == Phase.ENTRY


def test_stage_pending_timeout_open_size_positive_is_management():
    """PENDING_TIMEOUT con open_size>0 → stage = MANAGEMENT."""
    log = [_entry("CANCEL_PENDING", reason="timeout", state_before={"open_size": 1.0})]
    ev = normalize_events(_trade(), log)[0]
    assert ev.stage == Phase.MANAGEMENT


def test_stage_cancel_no_state_before_defaults_to_entry():
    """CANCEL_PENDING senza open_size in state_before → default stage = ENTRY."""
    log = [_entry("CANCEL_PENDING", source="engine", state_before={})]
    ev = normalize_events(_trade(), log)[0]
    assert ev.stage == Phase.ENTRY


def test_stage_non_cancel_events_equals_phase():
    """Per eventi non-CANCEL, stage == phase (nessuna override PRD §12)."""
    cases = [
        ("OPEN_SIGNAL", Phase.ENTRY),
        ("ADD_ENTRY", Phase.ENTRY),
        ("FILL", Phase.ENTRY),
        ("MOVE_STOP", Phase.MANAGEMENT),
        ("CLOSE_FULL", Phase.EXIT),
    ]
    for event_type, expected_stage in cases:
        kwargs = {"reason": "sl_hit"} if event_type == "CLOSE_FULL" else {}
        ev = normalize_events(_trade(), [_entry(event_type, **kwargs)])[0]
        assert ev.stage == expected_stage, f"Failed for {event_type}"


def test_raw_fill_events_are_not_duplicated_by_synthetic_fill_generation():
    trade = _trade("sig_dedup")
    log = [
        _entry(
            "FILL",
            state_before={"open_size": 0.0},
            state_after={
                "fills": [{"timestamp": _TS.isoformat(), "price": 42000.0, "qty": 1.0, "plan_id": "e1"}],
                "fills_count": 1,
                "open_size": 1.0,
            },
        )
    ]
    result = normalize_events(trade, log)
    fills = [ev for ev in result if ev.event_code == Subtype.ENTRY_FILLED_INITIAL]
    assert len(fills) == 1


# ---------------------------------------------------------------------------
# Tests — ordinamento deterministico (PRD §13.2)
# ---------------------------------------------------------------------------

def test_deterministic_order_setup_before_fill_same_timestamp():
    """SETUP_CREATED precede ENTRY_FILLED_INITIAL a parità di timestamp (PRD §13.2)."""
    trade = _trade()
    # FILL first in log, OPEN_SIGNAL second — same timestamp
    log = [
        _entry("FILL"),        # ENTRY_FILLED_INITIAL, priority 2
        _entry("OPEN_SIGNAL"), # SETUP_CREATED, priority 0
    ]
    result = normalize_events(trade, log)
    operational = [
        ev for ev in result
        if ev.subtype in {Subtype.SETUP_CREATED, Subtype.ENTRY_FILLED_INITIAL}
    ]
    assert len(operational) >= 2
    assert operational[0].subtype == Subtype.SETUP_CREATED
    assert operational[1].subtype == Subtype.ENTRY_FILLED_INITIAL


def test_deterministic_order_tp_before_be_same_timestamp():
    """EXIT_PARTIAL_TP precede BREAK_EVEN_ACTIVATED a parità di timestamp (PRD §13.2)."""
    trade = _trade()
    log = [
        _entry("MOVE_STOP_TO_BE"),              # BREAK_EVEN_ACTIVATED, priority 5
        _entry("CLOSE_PARTIAL", reason="tp_hit"), # EXIT_PARTIAL_TP, priority 6
    ]
    result = normalize_events(trade, log)
    operational = [
        ev for ev in result
        if ev.subtype in {Subtype.EXIT_PARTIAL_TP, Subtype.BREAK_EVEN_ACTIVATED}
    ]
    assert len(operational) == 2
    assert operational[0].subtype == Subtype.EXIT_PARTIAL_TP
    assert operational[1].subtype == Subtype.BREAK_EVEN_ACTIVATED
