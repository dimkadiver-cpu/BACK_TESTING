"""Tests for normalize_entry_semantics and canonical _weights_from_policy dispatch.

Covers PRD sections 6.1 (mapping rules), 6.2 (inference rules), 7.1 (dispatch target),
13.1 (normalisation unit tests), 13.2 (simulator dispatch), 13.4 (compat tests).
"""
from __future__ import annotations

import warnings
from datetime import datetime, timezone

import pytest

from src.signal_chain_lab.domain.enums import ChainInputMode, EventSource, EventType, TradeStatus
from src.signal_chain_lab.domain.events import CanonicalEvent
from src.signal_chain_lab.domain.trade_state import TradeState
from src.signal_chain_lab.engine.state_machine import apply_event, normalize_entry_semantics
from src.signal_chain_lab.policies.base import PolicyConfig


# ─────────────────────────── helpers ─────────────────────────────────────────

def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def _base_state() -> TradeState:
    return TradeState(
        signal_id="sig-norm",
        symbol="BTCUSDT",
        side="BUY",
        status=TradeStatus.NEW,
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        policy_name="norm_test",
    )


def _event(payload: dict | None = None) -> CanonicalEvent:
    return CanonicalEvent(
        signal_id="sig-norm",
        symbol="BTCUSDT",
        side="BUY",
        timestamp=_utc("2026-01-01T00:00:00"),
        event_type=EventType.OPEN_SIGNAL,
        source=EventSource.TRADER,
        payload=payload or {},
        sequence=0,
    )


def _full_policy(extra_entry_split: dict | None = None) -> PolicyConfig:
    """Policy with all canonical entry_split blocks."""
    base = {
        "LIMIT": {
            "single": {"weights": {"E1": 1.0}},
            "range": {"split_mode": "endpoints", "weights": {"E1": 0.50, "E2": 0.50}},
            "averaging": {"weights": {"E1": 0.70, "E2": 0.30}},
            "ladder": {"weights": {"E1": 0.50, "E2": 0.30, "E3": 0.20}},
        },
        "MARKET": {
            "single": {"weights": {"E1": 1.0}},
            "averaging": {"weights": {"E1": 0.70, "E2": 0.30}},
        },
    }
    if extra_entry_split:
        base.update(extra_entry_split)
    return PolicyConfig.model_validate({"name": "full_test", "entry": {"entry_split": base}})


# ═════════════════════════════════════════════════════════════════════════════
# Section 6.1 — Mapping rules (normalize_entry_semantics)
# ═════════════════════════════════════════════════════════════════════════════

class TestNormalizeMappingRules:
    """PRD §6.1: each legacy input maps to a specific canonical output."""

    def test_single_structure_becomes_one_shot(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_entry_semantics({"entry_structure": "SINGLE"})
        assert result["entry_structure"] == "ONE_SHOT"
        assert any("SINGLE" in str(warning.message) for warning in w)
        assert any(issubclass(warning.category, DeprecationWarning) for warning in w)

    def test_single_market_plan_type(self) -> None:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = normalize_entry_semantics({"entry_plan_type": "SINGLE_MARKET"})
        assert result["entry_type"] == "MARKET"
        assert result["entry_structure"] == "ONE_SHOT"

    def test_single_limit_plan_type(self) -> None:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = normalize_entry_semantics({"entry_plan_type": "SINGLE_LIMIT"})
        assert result["entry_type"] == "LIMIT"
        assert result["entry_structure"] == "ONE_SHOT"

    def test_market_with_limit_averaging_plan_type(self) -> None:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = normalize_entry_semantics({"entry_plan_type": "MARKET_WITH_LIMIT_AVERAGING"})
        assert result["entry_type"] == "MARKET"
        assert result["entry_structure"] == "TWO_STEP"

    def test_limit_with_limit_averaging_plan_type(self) -> None:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = normalize_entry_semantics({"entry_plan_type": "LIMIT_WITH_LIMIT_AVERAGING"})
        assert result["entry_type"] == "LIMIT"
        assert result["entry_structure"] == "TWO_STEP"

    def test_averaging_with_2_entries_becomes_two_step(self) -> None:
        payload = {
            "entry_type": "AVERAGING",
            "entries": [{"price": 100.0, "order_type": "LIMIT"}, {"price": 95.0, "order_type": "LIMIT"}],
        }
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_entry_semantics(payload)
        assert result["entry_type"] == "LIMIT"
        assert result["entry_structure"] == "TWO_STEP"
        assert any(issubclass(warning.category, DeprecationWarning) for warning in w)

    def test_averaging_with_3_entries_becomes_ladder(self) -> None:
        payload = {
            "entry_type": "AVERAGING",
            "entries": [
                {"price": 100.0, "order_type": "LIMIT"},
                {"price": 97.0, "order_type": "LIMIT"},
                {"price": 94.0, "order_type": "LIMIT"},
            ],
        }
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = normalize_entry_semantics(payload)
        assert result["entry_type"] == "LIMIT"
        assert result["entry_structure"] == "LADDER"

    def test_zone_becomes_limit_range(self) -> None:
        payload = {"entry_type": "ZONE", "entry_prices": [100.0, 95.0]}
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_entry_semantics(payload)
        assert result["entry_type"] == "LIMIT"
        assert result["entry_structure"] == "RANGE"
        assert any(issubclass(warning.category, DeprecationWarning) for warning in w)


# ═════════════════════════════════════════════════════════════════════════════
# Section 6.2 — Inference rules
# ═════════════════════════════════════════════════════════════════════════════

class TestNormalizeInferenceRules:
    """PRD §6.2: entry_structure inferred from entry_plan_entries count/roles when absent."""

    def test_single_entry_plan_entry_infers_one_shot(self) -> None:
        payload = {
            "entry_type": "LIMIT",
            "entry_plan_entries": [{"sequence": 1, "role": "PRIMARY", "order_type": "LIMIT", "price": 100.0}],
        }
        result = normalize_entry_semantics(payload)
        assert result["entry_structure"] == "ONE_SHOT"

    def test_two_entries_primary_averaging_infers_two_step(self) -> None:
        payload = {
            "entry_type": "LIMIT",
            "entry_plan_entries": [
                {"sequence": 1, "role": "PRIMARY", "order_type": "LIMIT", "price": 100.0},
                {"sequence": 2, "role": "AVERAGING", "order_type": "LIMIT", "price": 95.0},
            ],
        }
        result = normalize_entry_semantics(payload)
        assert result["entry_structure"] == "TWO_STEP"

    def test_three_plus_entry_plan_entries_infers_ladder(self) -> None:
        payload = {
            "entry_type": "LIMIT",
            "entry_plan_entries": [
                {"sequence": 1, "role": "PRIMARY", "order_type": "LIMIT", "price": 100.0},
                {"sequence": 2, "role": "AVERAGING", "order_type": "LIMIT", "price": 97.0},
                {"sequence": 3, "role": "AVERAGING", "order_type": "LIMIT", "price": 94.0},
            ],
        }
        result = normalize_entry_semantics(payload)
        assert result["entry_structure"] == "LADDER"

    def test_canonical_payload_is_unchanged(self) -> None:
        """Canonical payloads must pass through without modification."""
        payload = {"entry_type": "LIMIT", "entry_structure": "RANGE"}
        result = normalize_entry_semantics(payload)
        assert result["entry_type"] == "LIMIT"
        assert result["entry_structure"] == "RANGE"

    def test_explicit_structure_not_overridden_by_inference(self) -> None:
        """Explicit entry_structure takes precedence over inferred value."""
        payload = {
            "entry_type": "LIMIT",
            "entry_structure": "RANGE",
            "entry_plan_entries": [
                {"sequence": 1, "role": "PRIMARY", "order_type": "LIMIT", "price": 100.0},
            ],
        }
        result = normalize_entry_semantics(payload)
        # 1 entry would normally infer ONE_SHOT, but RANGE is explicit
        assert result["entry_structure"] == "RANGE"

    def test_explicit_entry_type_not_overridden_by_plan_type(self) -> None:
        """Explicit entry_type takes precedence over entry_plan_type mapping."""
        payload = {
            "entry_type": "LIMIT",
            "entry_plan_type": "SINGLE_MARKET",  # would map to MARKET
        }
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = normalize_entry_semantics(payload)
        # entry_type was explicitly set to LIMIT — must not be overridden
        assert result["entry_type"] == "LIMIT"

    def test_returns_shallow_copy_not_mutated_original(self) -> None:
        payload = {"entry_type": "ZONE"}
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = normalize_entry_semantics(payload)
        assert payload["entry_type"] == "ZONE"  # original unchanged
        assert result["entry_type"] == "LIMIT"


# ═════════════════════════════════════════════════════════════════════════════
# Section 7.1 — Dispatch target (full end-to-end via apply_event)
# ═════════════════════════════════════════════════════════════════════════════

class TestDispatchTarget:
    """PRD §7.1: verify correct policy weights are selected for each canonical structure."""

    def test_one_shot_market_uses_market_single(self) -> None:
        state = _base_state()
        policy = _full_policy()
        payload = {
            "entry_type": "MARKET",
            "entry_structure": "ONE_SHOT",
            "entry_plan_entries": [
                {"sequence": 1, "role": "PRIMARY", "order_type": "MARKET", "price": None},
            ],
            "sl_price": 90.0,
            "tp_levels": [110.0],
        }
        apply_event(state, _event(payload), policy=policy)
        assert len(state.entries_planned) == 1
        assert state.entries_planned[0].size_ratio == pytest.approx(1.0)

    def test_one_shot_limit_uses_limit_single(self) -> None:
        state = _base_state()
        policy = _full_policy()
        payload = {
            "entry_type": "LIMIT",
            "entry_structure": "ONE_SHOT",
            "entry_plan_entries": [
                {"sequence": 1, "role": "PRIMARY", "order_type": "LIMIT", "price": 100.0},
            ],
            "sl_price": 90.0,
            "tp_levels": [110.0],
        }
        apply_event(state, _event(payload), policy=policy)
        assert len(state.entries_planned) == 1
        assert state.entries_planned[0].size_ratio == pytest.approx(1.0)

    def test_two_step_market_uses_market_averaging(self) -> None:
        state = _base_state()
        policy = _full_policy()
        payload = {
            "entry_type": "MARKET",
            "entry_structure": "TWO_STEP",
            "entry_plan_entries": [
                {"sequence": 1, "role": "PRIMARY", "order_type": "MARKET", "price": None},
                {"sequence": 2, "role": "AVERAGING", "order_type": "LIMIT", "price": 95.0},
            ],
            "sl_price": 90.0,
            "tp_levels": [110.0],
        }
        apply_event(state, _event(payload), policy=policy)
        assert len(state.entries_planned) == 2
        assert state.entries_planned[0].size_ratio == pytest.approx(0.7)
        assert state.entries_planned[1].size_ratio == pytest.approx(0.3)

    def test_two_step_limit_uses_limit_averaging(self) -> None:
        state = _base_state()
        policy = _full_policy()
        payload = {
            "entry_type": "LIMIT",
            "entry_structure": "TWO_STEP",
            "entry_plan_entries": [
                {"sequence": 1, "role": "PRIMARY", "order_type": "LIMIT", "price": 100.0},
                {"sequence": 2, "role": "AVERAGING", "order_type": "LIMIT", "price": 95.0},
            ],
            "sl_price": 90.0,
            "tp_levels": [110.0],
        }
        apply_event(state, _event(payload), policy=policy)
        assert len(state.entries_planned) == 2
        assert state.entries_planned[0].size_ratio == pytest.approx(0.7)
        assert state.entries_planned[1].size_ratio == pytest.approx(0.3)

    def test_range_uses_limit_range(self) -> None:
        state = _base_state()
        policy = _full_policy()
        payload = {
            "entry_type": "LIMIT",
            "entry_structure": "RANGE",
            "entry_plan_entries": [
                {"sequence": 1, "role": "RANGE_LOW", "order_type": "LIMIT", "price": 100.0},
                {"sequence": 2, "role": "RANGE_HIGH", "order_type": "LIMIT", "price": 95.0},
            ],
            "sl_price": 90.0,
            "tp_levels": [110.0],
        }
        apply_event(state, _event(payload), policy=policy)
        assert len(state.entries_planned) == 2
        assert state.entries_planned[0].size_ratio == pytest.approx(0.5)
        assert state.entries_planned[1].size_ratio == pytest.approx(0.5)

    def test_ladder_uses_limit_ladder(self) -> None:
        state = _base_state()
        policy = _full_policy()
        payload = {
            "entry_type": "LIMIT",
            "entry_structure": "LADDER",
            "entry_plan_entries": [
                {"sequence": 1, "role": "PRIMARY", "order_type": "LIMIT", "price": 100.0},
                {"sequence": 2, "role": "AVERAGING", "order_type": "LIMIT", "price": 97.0},
                {"sequence": 3, "role": "AVERAGING", "order_type": "LIMIT", "price": 94.0},
            ],
            "sl_price": 90.0,
            "tp_levels": [110.0],
        }
        apply_event(state, _event(payload), policy=policy)
        assert len(state.entries_planned) == 3
        total = sum(e.size_ratio for e in state.entries_planned)
        assert total == pytest.approx(1.0)
        # PRD ladder weights: 0.50 / 0.30 / 0.20
        assert state.entries_planned[0].size_ratio == pytest.approx(0.50)
        assert state.entries_planned[1].size_ratio == pytest.approx(0.30)
        assert state.entries_planned[2].size_ratio == pytest.approx(0.20)


# ═════════════════════════════════════════════════════════════════════════════
# Section 13.4 — Backward compatibility (legacy payloads → correct behaviour)
# ═════════════════════════════════════════════════════════════════════════════

class TestBackwardCompatibility:
    """PRD §13.4: legacy payloads still accepted; warnings emitted; behaviour preserved."""

    def test_zone_entry_prices_accepted_with_deprecation_warning(self) -> None:
        state = _base_state()
        # ZONE-only policy (legacy) — fallback path
        policy = PolicyConfig.model_validate({
            "name": "zone_compat",
            "entry": {
                "entry_split": {
                    "ZONE": {"split_mode": "endpoints", "weights": {"E1": 0.5, "E2": 0.5}},
                }
            },
        })
        payload = {
            "entry_type": "ZONE",
            "entry_prices": [100.0, 95.0],
            "sl_price": 90.0,
            "tp_levels": [110.0],
        }
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            apply_event(state, _event(payload), policy=policy)
        assert len(state.entries_planned) == 2
        assert state.entries_planned[0].price == pytest.approx(100.0)
        assert state.entries_planned[1].price == pytest.approx(95.0)
        assert state.entries_planned[0].size_ratio == pytest.approx(0.5)
        assert state.entries_planned[1].size_ratio == pytest.approx(0.5)
        # Must emit DeprecationWarning for ZONE
        deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert deprecations, "Expected at least one DeprecationWarning for entry_type='ZONE'"

    def test_averaging_entry_type_two_entries_uses_limit_averaging(self) -> None:
        state = _base_state()
        policy = _full_policy()
        payload = {
            "entry_type": "AVERAGING",
            "entries": [
                {"price": 100.0, "order_type": "LIMIT"},
                {"price": 95.0, "order_type": "LIMIT"},
            ],
            "sl_price": 90.0,
            "tp_levels": [110.0],
        }
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            apply_event(state, _event(payload), policy=policy)
        assert len(state.entries_planned) == 2
        assert state.entries_planned[0].size_ratio == pytest.approx(0.7)
        assert state.entries_planned[1].size_ratio == pytest.approx(0.3)
        deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert deprecations

    def test_single_structure_normalised_to_one_shot_before_dispatch(self) -> None:
        state = _base_state()
        policy = _full_policy()
        payload = {
            "entry_type": "LIMIT",
            "entry_structure": "SINGLE",  # legacy
            "entry_plan_entries": [
                {"sequence": 1, "role": "PRIMARY", "order_type": "LIMIT", "price": 100.0},
            ],
            "sl_price": 90.0,
            "tp_levels": [110.0],
        }
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            apply_event(state, _event(payload), policy=policy)
        assert len(state.entries_planned) == 1
        assert state.entries_planned[0].size_ratio == pytest.approx(1.0)
        deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert deprecations

    def test_plan_type_limit_with_averaging_dispatches_correctly(self) -> None:
        """entry_plan_type=LIMIT_WITH_LIMIT_AVERAGING with canonical entry_structure still works."""
        state = _base_state()
        policy = _full_policy()
        payload = {
            "entry_type": "LIMIT",
            "entry_plan_type": "LIMIT_WITH_LIMIT_AVERAGING",
            "entry_structure": "TWO_STEP",
            "has_averaging_plan": True,
            "entry_plan_entries": [
                {"sequence": 1, "role": "PRIMARY", "order_type": "LIMIT", "price": 100.0},
                {"sequence": 2, "role": "AVERAGING", "order_type": "LIMIT", "price": 95.0},
            ],
            "sl_price": 90.0,
            "tp_levels": [110.0],
        }
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            apply_event(state, _event(payload), policy=policy)
        assert len(state.entries_planned) == 2
        assert state.entries_planned[0].size_ratio == pytest.approx(0.7)
        assert state.entries_planned[1].size_ratio == pytest.approx(0.3)

    def test_zone_fallback_to_limit_range_when_limit_range_available(self) -> None:
        """If policy has LIMIT.range, ZONE payload prefers it over ZONE block."""
        state = _base_state()
        # Policy has both LIMIT.range and ZONE — LIMIT.range should win
        policy = PolicyConfig.model_validate({
            "name": "range_over_zone",
            "entry": {
                "entry_split": {
                    "LIMIT": {
                        "single": {"weights": {"E1": 1.0}},
                        "range": {"split_mode": "endpoints", "weights": {"E1": 0.6, "E2": 0.4}},
                        "averaging": {"weights": {"E1": 0.7, "E2": 0.3}},
                        "ladder": {"weights": {"E1": 1.0}},
                    },
                    "ZONE": {"split_mode": "endpoints", "weights": {"E1": 0.5, "E2": 0.5}},
                }
            },
        })
        payload = {
            "entry_type": "ZONE",
            "entry_plan_entries": [
                {"sequence": 1, "role": "RANGE_LOW", "order_type": "LIMIT", "price": 100.0},
                {"sequence": 2, "role": "RANGE_HIGH", "order_type": "LIMIT", "price": 95.0},
            ],
            "sl_price": 90.0,
            "tp_levels": [110.0],
        }
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            apply_event(state, _event(payload), policy=policy)
        # LIMIT.range weights (0.6 / 0.4) should be used, not ZONE weights (0.5 / 0.5)
        assert state.entries_planned[0].size_ratio == pytest.approx(0.6)
        assert state.entries_planned[1].size_ratio == pytest.approx(0.4)


# ═════════════════════════════════════════════════════════════════════════════
# Policy model — DeprecationWarning on ZONE / AVERAGING fields
# ═════════════════════════════════════════════════════════════════════════════

class TestPolicyModelDeprecationWarnings:
    """ZONE and AVERAGING blocks in EntrySplitPolicy must emit DeprecationWarning."""

    def test_zone_block_in_policy_emits_deprecation_warning(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            PolicyConfig.model_validate({
                "name": "zone_policy",
                "entry": {"entry_split": {"ZONE": {"split_mode": "endpoints", "weights": {"E1": 0.5}}}},
            })
        assert any(issubclass(x.category, DeprecationWarning) for x in w)

    def test_averaging_block_in_policy_emits_deprecation_warning(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            PolicyConfig.model_validate({
                "name": "avg_policy",
                "entry": {"entry_split": {"AVERAGING": {"distribution": "equal", "weights": {}}}},
            })
        assert any(issubclass(x.category, DeprecationWarning) for x in w)

    def test_canonical_policy_no_deprecation_warning(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            PolicyConfig.model_validate({
                "name": "canonical_policy",
                "entry": {
                    "entry_split": {
                        "LIMIT": {"single": {"weights": {"E1": 1.0}}, "averaging": {"weights": {"E1": 0.7, "E2": 0.3}}, "ladder": {"weights": {"E1": 1.0}}},
                        "MARKET": {"single": {"weights": {"E1": 1.0}}, "averaging": {"weights": {"E1": 0.7, "E2": 0.3}}},
                    }
                },
            })
        deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert not deprecations, f"Unexpected DeprecationWarnings: {deprecations}"
