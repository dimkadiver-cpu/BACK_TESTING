from __future__ import annotations

import pytest

from src.signal_chain_lab.policies.policy_loader import PolicyLoadError, PolicyLoader


def test_load_original_chain_policy() -> None:
    policy = PolicyLoader().load("original_chain")
    assert policy.name == "original_chain"
    assert policy.updates.apply_move_stop is True
    assert policy.execution.latency_ms == 0


def test_load_signal_only_policy() -> None:
    policy = PolicyLoader().load("signal_only")
    assert policy.name == "signal_only"
    assert policy.updates.apply_move_stop is False
    assert policy.updates.apply_close_full is False


def test_load_missing_policy_raises() -> None:
    with pytest.raises(PolicyLoadError):
        PolicyLoader().load("missing_policy")


def test_load_extended_policy_template_supports_nested_contract() -> None:
    policy = PolicyLoader().load("policy_template_full")

    assert policy.entry.entry_split is not None
    assert policy.entry.entry_split.ZONE is not None
    assert policy.entry.entry_split.ZONE.split_mode == "endpoints"

    assert not isinstance(policy.tp.tp_distribution, str)
    assert policy.tp.tp_distribution.mode == "follow_all_signal_tps"
    assert policy.tp.tp_distribution.max_tp_levels == 3
    assert policy.tp.tp_distribution.tp_close_distribution[3] == [30, 30, 40]

    assert policy.pending.cancel_unfilled_if_tp1_reached_before_fill is False
    assert policy.pending.cancel_unfilled_if_reached_before_fill is False
    assert policy.pending.cancel_averaging_pending_after_tp1 is False
    assert policy.pending.cancel_averaging_pending_after is False
