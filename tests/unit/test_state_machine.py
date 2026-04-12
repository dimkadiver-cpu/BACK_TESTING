from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.domain.enums import ChainInputMode, EventProcessingStatus, EventSource, EventType, TradeStatus
from src.signal_chain_lab.domain.events import CanonicalEvent
from src.signal_chain_lab.domain.trade_state import TradeState
from src.signal_chain_lab.engine.state_machine import apply_event
from src.signal_chain_lab.policies.base import PolicyConfig


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


def test_open_signal_builds_market_plus_limit_averaging_from_payload_entries() -> None:
    state = _base_state()
    policy = PolicyConfig.model_validate(
        {
            "name": "entry_split_policy",
            "entry": {
                "entry_split": {
                    "MARKET": {
                        "single": {"weights": {"E1": 1.0}},
                        "averaging": {"weights": {"E1": 0.7, "E2": 0.3}},
                    }
                }
            },
        }
    )

    payload = {
        "entry_type": "MARKET",
        "entries": [
            {"price": 100.0, "order_type": "MARKET"},
            {"price": 95.0, "order_type": "LIMIT"},
        ],
        "sl_price": 90.0,
        "tp_levels": [110.0],
    }

    apply_event(state, _event(EventType.OPEN_SIGNAL, payload), policy=policy)

    assert len(state.entries_planned) == 2
    assert state.entries_planned[0].order_type == "market"
    assert state.entries_planned[0].size_ratio == 0.7
    assert state.entries_planned[1].order_type == "limit"
    assert state.entries_planned[1].size_ratio == 0.3
    assert state.pending_size == 1.0


def test_open_signal_zone_payload_normalised_to_limit_range_canonical_weights() -> None:
    """Legacy entry_type=ZONE payload is normalised to LIMIT+RANGE; dispatches via LIMIT.range."""
    state = _base_state()
    policy = PolicyConfig.model_validate(
        {
            "name": "range_policy",
            "entry": {
                "entry_split": {
                    "LIMIT": {
                        "single": {"weights": {"E1": 1.0}},
                        "range": {
                            "split_mode": "endpoints",
                            "weights": {"E1": 0.5, "E2": 0.5},
                        },
                        "averaging": {"weights": {"E1": 0.7, "E2": 0.3}},
                        "ladder": {"weights": {"E1": 0.5, "E2": 0.5}},
                    }
                }
            },
        }
    )

    payload = {
        "entry_type": "ZONE",  # legacy — normalised to LIMIT + RANGE by normalize_entry_semantics
        "entry_prices": [100.0, 95.0],
        "sl_price": 90.0,
        "tp_levels": [110.0],
    }

    apply_event(state, _event(EventType.OPEN_SIGNAL, payload), policy=policy)

    assert len(state.entries_planned) == 2
    assert state.entries_planned[0].price == 100.0
    assert state.entries_planned[1].price == 95.0
    assert state.entries_planned[0].size_ratio == 0.5
    assert state.entries_planned[1].size_ratio == 0.5


def test_open_signal_uses_limit_range_weights_for_range_structure() -> None:
    state = _base_state()
    policy = PolicyConfig.model_validate(
        {
            "name": "limit_range_policy",
            "entry": {
                "entry_split": {
                    "LIMIT": {
                        "single": {"weights": {"E1": 1.0}},
                        "range": {
                            "split_mode": "endpoints",
                            "weights": {"E1": 0.4, "E2": 0.6},
                        },
                        "averaging": {"weights": {"E1": 0.7, "E2": 0.3}},
                        "ladder": {"weights": {"E1": 0.5, "E2": 0.5}},
                    }
                }
            },
        }
    )

    payload = {
        "entry_type": "LIMIT",
        "entry_structure": "RANGE",
        "entry_plan_entries": [
            {"role": "RANGE_LOW", "order_type": "LIMIT", "price": 100.0},
            {"role": "RANGE_HIGH", "order_type": "LIMIT", "price": 95.0},
        ],
        "sl_price": 90.0,
        "tp_levels": [110.0],
    }

    apply_event(state, _event(EventType.OPEN_SIGNAL, payload), policy=policy)

    assert len(state.entries_planned) == 2
    assert state.entries_planned[0].size_ratio == 0.4
    assert state.entries_planned[1].size_ratio == 0.6


def test_open_signal_uses_limit_averaging_weights_for_two_step_limit_plan() -> None:
    state = _base_state()
    policy = PolicyConfig.model_validate(
        {
            "name": "limit_avg_policy",
            "entry": {
                "entry_split": {
                    "LIMIT": {
                        "single": {"weights": {"E1": 1.0}},
                        "range": {
                            "split_mode": "endpoints",
                            "weights": {"E1": 0.5, "E2": 0.5},
                        },
                        "averaging": {"weights": {"E1": 0.7, "E2": 0.3}},
                        "ladder": {"weights": {"E1": 0.5, "E2": 0.5}},
                    }
                }
            },
        }
    )

    payload = {
        "entry_type": "LIMIT",
        "entry_plan_type": "LIMIT_WITH_LIMIT_AVERAGING",
        "entry_structure": "TWO_STEP",
        "has_averaging_plan": True,
        "entry_plan_entries": [
            {"role": "PRIMARY", "order_type": "LIMIT", "price": 100.0},
            {"role": "AVERAGING", "order_type": "LIMIT", "price": 95.0},
        ],
        "sl_price": 90.0,
        "tp_levels": [110.0],
    }

    apply_event(state, _event(EventType.OPEN_SIGNAL, payload), policy=policy)

    assert len(state.entries_planned) == 2
    assert state.entries_planned[0].size_ratio == 0.7
    assert state.entries_planned[1].size_ratio == 0.3


def test_open_signal_limit_range_firstpoint_reduces_to_one_entry() -> None:
    state = _base_state()
    policy = PolicyConfig.model_validate(
        {
            "name": "limit_range_firstpoint",
            "entry": {
                "entry_split": {
                    "LIMIT": {
                        "single": {"weights": {"E1": 1.0}},
                        "range": {
                            "split_mode": "firstpoint",
                            "weights": {"E1": 1.0},
                        },
                    }
                }
            },
        }
    )

    payload = {
        "entry_type": "LIMIT",
        "entry_structure": "RANGE",
        "entry_plan_entries": [
            {"role": "RANGE_LOW", "order_type": "LIMIT", "price": 100.0},
            {"role": "RANGE_HIGH", "order_type": "LIMIT", "price": 95.0},
        ],
        "sl_price": 90.0,
        "tp_levels": [110.0],
    }

    apply_event(state, _event(EventType.OPEN_SIGNAL, payload), policy=policy)

    assert len(state.entries_planned) == 1
    assert state.entries_planned[0].price == 100.0
    assert state.entries_planned[0].size_ratio == 1.0


def test_open_signal_limit_range_midpoint_reduces_to_mid_entry() -> None:
    state = _base_state()
    policy = PolicyConfig.model_validate(
        {
            "name": "limit_range_midpoint",
            "entry": {
                "entry_split": {
                    "LIMIT": {
                        "single": {"weights": {"E1": 1.0}},
                        "range": {
                            "split_mode": "midpoint",
                            "weights": {"E1": 1.0},
                        },
                    }
                }
            },
        }
    )

    payload = {
        "entry_type": "LIMIT",
        "entry_structure": "RANGE",
        "entry_plan_entries": [
            {"role": "RANGE_LOW", "order_type": "LIMIT", "price": 100.0},
            {"role": "RANGE_HIGH", "order_type": "LIMIT", "price": 96.0},
        ],
        "sl_price": 90.0,
        "tp_levels": [110.0],
    }

    apply_event(state, _event(EventType.OPEN_SIGNAL, payload), policy=policy)

    assert len(state.entries_planned) == 1
    assert state.entries_planned[0].price == 98.0
    assert state.entries_planned[0].size_ratio == 1.0
