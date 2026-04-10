from __future__ import annotations

from pathlib import Path

from src.signal_chain_lab.ui.blocks.backtest_observability import (
    append_benchmark_entry,
    compute_benchmark_snapshot,
    load_benchmark_payload,
)


def test_benchmark_payload_roundtrip(tmp_path: Path) -> None:
    bench_path = tmp_path / "backtest_benchmark.json"
    first = {
        "prepare_mode": "SAFE",
        "policy_count": 1,
        "total_seconds": 12.0,
    }
    second = {
        "prepare_mode": "FAST",
        "policy_count": 3,
        "total_seconds": 8.0,
    }

    append_benchmark_entry(bench_path, first)
    payload = append_benchmark_entry(bench_path, second)

    assert len(payload["runs"]) == 2
    assert payload["runs"][0]["prepare_mode"] == "SAFE"
    assert payload["runs"][1]["prepare_mode"] == "FAST"

    loaded = load_benchmark_payload(bench_path)
    assert loaded == payload


def test_compute_benchmark_snapshot() -> None:
    payload = {
        "runs": [
            {"prepare_mode": "SAFE", "policy_count": 1, "total_seconds": 10.0},
            {"prepare_mode": "SAFE", "policy_count": 2, "total_seconds": 6.0},
            {"prepare_mode": "FAST", "policy_count": 1, "total_seconds": 7.0},
            {"prepare_mode": "FAST", "policy_count": 3, "total_seconds": 5.0},
        ]
    }

    snapshot = compute_benchmark_snapshot(payload)

    assert snapshot["safe_avg_seconds"] == 8.0
    assert snapshot["fast_avg_seconds"] == 6.0
    assert snapshot["single_policy_avg_seconds"] == 8.5
    assert snapshot["multi_policy_avg_seconds"] == 5.5
