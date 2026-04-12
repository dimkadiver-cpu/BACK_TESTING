from __future__ import annotations

from src.signal_chain_lab.policies.policy_loader import PolicyLoader


def test_signal_only_disables_all_updates() -> None:
    policy = PolicyLoader().load("signal_only")

    assert policy.entry.allow_add_entry_updates is False
    # move_sl_with_trader removed — apply_move_stop is the single control point
    assert policy.updates.apply_move_stop is False
    assert policy.updates.apply_close_partial is False
    assert policy.updates.apply_close_full is False
    assert policy.updates.apply_cancel_pending is False
    assert policy.updates.apply_add_entry is False
