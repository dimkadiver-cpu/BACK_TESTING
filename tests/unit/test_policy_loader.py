from __future__ import annotations

import pytest

from src.signal_chain_lab.policies.policy_loader import PolicyLoadError, PolicyLoader


def test_load_original_chain_policy() -> None:
    policy = PolicyLoader().load("original_chain")
    assert policy.name == "original_chain"
    assert policy.updates.apply_move_stop is True
    assert policy.execution.latency_ms == 0
    assert policy.execution.funding_model == "none"
    assert policy.execution.funding_apply_to_pnl is True


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

    # Canonical blocks — must be present
    assert policy.entry.entry_split.LIMIT is not None
    assert policy.entry.entry_split.LIMIT.range is not None
    assert policy.entry.entry_split.LIMIT.range.split_mode == "endpoints"
    assert policy.entry.entry_split.MARKET is not None

    # Deprecated blocks — must be absent in the canonical template
    assert policy.entry.entry_split.ZONE is None, "ZONE block is deprecated and must not appear in policy_template_full"
    assert policy.entry.entry_split.AVERAGING is None, "AVERAGING block is deprecated and must not appear in policy_template_full"

    # close_distribution uses table mode with the values from policy_template_full
    assert policy.tp.close_distribution.mode == "table"
    assert policy.tp.close_distribution.table[3] == [30, 30, 40]

    # pending: canonical fields
    assert policy.pending.cancel_unfilled_pending_after is None
    assert policy.pending.cancel_averaging_pending_after is None

    # execution: market fill contract
    assert policy.execution.market_fill_mode == "next_open"
    assert policy.execution.market_requested_price_mode == "reference"
    assert policy.execution.market_price_proxy == "hl2"
    assert policy.execution.clamp_requested_to_candle is True
