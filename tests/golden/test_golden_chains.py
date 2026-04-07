from __future__ import annotations

import json
from pathlib import Path

from src.signal_chain_lab.engine.simulator import simulate_chain
from src.signal_chain_lab.policies.base import PolicyConfig
from src.signal_chain_lab.reports.trade_report import build_trade_result
from tests.fixtures.benchmark_loader import load_benchmark_chains, load_expectations


def test_golden_benchmark_replay_matches_expected_outputs() -> None:
    policy = PolicyConfig(name="original_chain")
    expectations = load_expectations()
    golden_payload = json.loads(Path("tests/golden/benchmark_golden.json").read_text(encoding="utf-8"))

    for chain in load_benchmark_chains():
        logs, state = simulate_chain(chain, policy)
        result = build_trade_result(state, logs)
        expectation = expectations[chain.signal_id]
        golden = golden_payload[chain.signal_id]

        essential_log = [
            {
                "event_type": entry.event_type,
                "requested_action": entry.requested_action,
                "executed_action": entry.executed_action,
                "processing_status": entry.processing_status.value,
                "reason": entry.reason,
            }
            for entry in logs
        ]

        essential_result = {
            "status": result.status,
            "close_reason": result.close_reason,
            "warnings_count": result.warnings_count,
            "ignored_events_count": result.ignored_events_count,
            "entries_count": result.entries_count,
        }

        assert result.status == expectation.expected_status
        assert result.close_reason == expectation.expected_close_reason
        assert result.warnings_count == expectation.expected_warnings
        assert result.ignored_events_count == expectation.expected_ignored

        assert essential_log == golden["event_log_essential"]
        assert essential_result == golden["trade_result_essential"]
