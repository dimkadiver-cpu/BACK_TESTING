from __future__ import annotations

from src.signal_chain_lab.engine.simulator import simulate_chain
from src.signal_chain_lab.policies.base import PolicyConfig
from src.signal_chain_lab.reports.trade_report import build_trade_result
from tests.fixtures.benchmark_loader import load_benchmark_chains, load_expectations


def test_regression_metrics_for_benchmark_dataset() -> None:
    policy = PolicyConfig(name="original_chain")
    expectations = load_expectations()

    status_counts: dict[str, int] = {}
    total_warnings = 0
    total_ignored = 0

    for chain in load_benchmark_chains():
        logs, state = simulate_chain(chain, policy)
        result = build_trade_result(state, logs)
        expected = expectations[chain.signal_id]

        assert result.status == expected.expected_status
        assert result.close_reason == expected.expected_close_reason

        total_warnings += result.warnings_count
        total_ignored += result.ignored_events_count
        status_counts[result.status] = status_counts.get(result.status, 0) + 1

    assert len(status_counts) >= 4
    assert status_counts["CANCELLED"] == 3
    assert status_counts["EXPIRED"] == 2
    assert total_warnings == 2
    assert total_ignored == 2
