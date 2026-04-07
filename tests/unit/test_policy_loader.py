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
