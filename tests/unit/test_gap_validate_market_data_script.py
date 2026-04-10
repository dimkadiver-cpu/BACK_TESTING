from __future__ import annotations

import importlib.util
import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path


def _load_gap_validate_module() -> object:
    if "pandas" not in sys.modules:
        fake_pandas = types.SimpleNamespace(read_parquet=lambda _path: [], concat=lambda frames, ignore_index=True: frames)
        sys.modules["pandas"] = fake_pandas
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "gap_validate_market_data.py"
    spec = importlib.util.spec_from_file_location("gap_validate_market_data_script", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sample_plan() -> dict[str, object]:
    return {
        "timeframe": "1m",
        "market_request_fingerprint": "fp-1",
        "symbols": {
            "BTCUSDT": {
                "last": {
                    "gaps": [
                        {
                            "start": datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc).isoformat(),
                            "end": datetime(2026, 4, 1, 0, 2, tzinfo=timezone.utc).isoformat(),
                        }
                    ]
                }
            }
        },
    }


def test_build_gap_jobs_uses_only_ok_sync_results() -> None:
    module = _load_gap_validate_module()
    plan = _sample_plan()
    sync_report = {
        "results": [
            {"symbol": "BTCUSDT", "basis": "last", "status": "ok"},
            {"symbol": "ETHUSDT", "basis": "last", "status": "error"},
        ]
    }

    jobs, issues = module._build_gap_jobs(plan=plan, sync_report=sync_report)

    assert len(jobs) == 1
    assert jobs[0]["symbol"] == "BTCUSDT"
    assert issues == []


def test_main_returns_zero_on_valid_gap(monkeypatch, tmp_path: Path) -> None:
    module = _load_gap_validate_module()
    plan = _sample_plan()
    sync_report = {"results": [{"symbol": "BTCUSDT", "basis": "last", "status": "ok"}]}
    plan_path = tmp_path / "plan.json"
    sync_path = tmp_path / "sync.json"
    output_path = tmp_path / "gap_validate.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    sync_path.write_text(json.dumps(sync_report), encoding="utf-8")

    parquet_dir = tmp_path / "market" / "bybit" / "futures_linear" / "1m" / "BTCUSDT"
    parquet_dir.mkdir(parents=True)
    (parquet_dir / "2026-04.last.parquet").write_text("fake", encoding="utf-8")

    monkeypatch.setattr(
        module,
        "parse_args",
        lambda: module.argparse.Namespace(
            plan_file=str(plan_path),
            sync_file=str(sync_path),
            market_dir=str(tmp_path / "market"),
            output=str(output_path),
        ),
    )
    monkeypatch.setattr(
        module.pd,
        "read_parquet",
        lambda _path: [
            {
                "timestamp": "2026-04-01T00:00:00+00:00",
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "volume": 1.0,
                "symbol": "BTCUSDT",
                "timeframe": "1m",
            },
            {
                "timestamp": "2026-04-01T00:01:00+00:00",
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "volume": 1.0,
                "symbol": "BTCUSDT",
                "timeframe": "1m",
            },
        ],
    )
    monkeypatch.setattr(
        module.pd,
        "concat",
        lambda frames, ignore_index=True: type(
            "_FakeDf",
            (),
            {
                "to_dict": lambda self, orient="records": [row for frame in frames for row in frame],
            },
        )(),
    )

    rc = module.main()
    report = json.loads(output_path.read_text(encoding="utf-8"))

    assert rc == 0
    assert report["status"] == "PASS"
    assert report["checks"] == 1
