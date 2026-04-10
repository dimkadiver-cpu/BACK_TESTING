"""Utility osservabilità/benchmark per il blocco backtest."""
from __future__ import annotations

import json
from pathlib import Path


def load_benchmark_payload(path: Path) -> dict:
    if not path.exists():
        return {"runs": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"runs": []}
    if not isinstance(payload, dict):
        return {"runs": []}
    runs = payload.get("runs")
    if not isinstance(runs, list):
        return {"runs": []}
    return {"runs": runs}


def append_benchmark_entry(path: Path, entry: dict, *, max_entries: int = 200) -> dict:
    payload = load_benchmark_payload(path)
    payload["runs"].append(entry)
    payload["runs"] = payload["runs"][-max_entries:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def compute_benchmark_snapshot(payload: dict) -> dict[str, float]:
    runs = payload.get("runs") or []
    safe_runs = [r for r in runs if r.get("prepare_mode") == "SAFE" and isinstance(r.get("total_seconds"), (int, float))]
    fast_runs = [r for r in runs if r.get("prepare_mode") == "FAST" and isinstance(r.get("total_seconds"), (int, float))]
    single_runs = [r for r in runs if int(r.get("policy_count", 0)) == 1 and isinstance(r.get("total_seconds"), (int, float))]
    multi_runs = [r for r in runs if int(r.get("policy_count", 0)) > 1 and isinstance(r.get("total_seconds"), (int, float))]
    safe_avg = _average([float(r["total_seconds"]) for r in safe_runs])
    fast_avg = _average([float(r["total_seconds"]) for r in fast_runs])
    single_avg = _average([float(r["total_seconds"]) for r in single_runs])
    multi_avg = _average([float(r["total_seconds"]) for r in multi_runs])
    snapshot: dict[str, float] = {}
    if safe_avg is not None:
        snapshot["safe_avg_seconds"] = safe_avg
    if fast_avg is not None:
        snapshot["fast_avg_seconds"] = fast_avg
    if single_avg is not None:
        snapshot["single_policy_avg_seconds"] = single_avg
    if multi_avg is not None:
        snapshot["multi_policy_avg_seconds"] = multi_avg
    return snapshot
