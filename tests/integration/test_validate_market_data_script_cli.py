from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas", reason="pandas required for parquet integration test")
pytest.importorskip("pyarrow", reason="pyarrow required for parquet integration test")


def _dt(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _row(ts: datetime) -> dict[str, object]:
    return {
        "timestamp": ts.isoformat(),
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1.0,
        "symbol": "BTCUSDT",
        "timeframe": "1m",
    }


def _write_plan(plan_path: Path) -> None:
    payload = {
        "timeframe": "1m",
        "market_request_fingerprint": "fp-strict-cli",
        "symbols": {
            "BTCUSDT": {
                "last": {
                    "required_intervals": [
                        {
                            "start": _dt(2026, 4, 18, 9, 59).isoformat(),
                            "end": _dt(2026, 4, 18, 10, 4).isoformat(),
                        }
                    ],
                    "execution_window": [],
                    "chart_window": [],
                    "download_window": [],
                    "gaps": [],
                }
            }
        },
    }
    plan_path.write_text(json.dumps(payload), encoding="utf-8")


def _write_market_parquet(market_dir: Path) -> None:
    target = market_dir / "bybit" / "futures_linear" / "1m" / "BTCUSDT"
    target.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [
            _row(_dt(2026, 4, 18, 10, 0)),
            _row(_dt(2026, 4, 18, 10, 3)),
        ]
    )
    df.to_parquet(target / "2026-04.last.parquet", index=False)


def test_validate_market_data_cli_strict_fails_on_warning(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    plan_path = tmp_path / "plan.json"
    market_dir = tmp_path / "market"
    output_loose = tmp_path / "validate_loose.json"
    output_strict = tmp_path / "validate_strict.json"

    _write_plan(plan_path)
    _write_market_parquet(market_dir)

    loose = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "validate_market_data.py"),
            "--plan-file",
            str(plan_path),
            "--market-dir",
            str(market_dir),
            "--output",
            str(output_loose),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    strict = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "validate_market_data.py"),
            "--plan-file",
            str(plan_path),
            "--market-dir",
            str(market_dir),
            "--output",
            str(output_strict),
            "--strict",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    loose_report = json.loads(output_loose.read_text(encoding="utf-8"))
    strict_report = json.loads(output_strict.read_text(encoding="utf-8"))

    assert loose.returncode == 0, loose.stderr or loose.stdout
    assert strict.returncode == 1, strict.stderr or strict.stdout
    assert "warnings:" in loose.stdout
    assert "warnings:" in strict.stdout
    assert loose_report["status"] == "PASS"
    assert strict_report["status"] == "FAIL"
    assert strict_report["strict"] is True
    assert strict_report["warning_count"] >= 1
    assert any(
        issue["code"] == "CONTINUITY_GAP_EXCESSIVE" and issue["severity"] == "warning"
        for result in strict_report["results"]
        for issue in result["issues"]
    )
