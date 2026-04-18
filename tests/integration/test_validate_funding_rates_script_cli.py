from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas", reason="pandas required for funding parquet integration test")
pytest.importorskip("pyarrow", reason="pyarrow required for funding parquet integration test")


def _dt(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _funding_row(ts: datetime, rate: float) -> dict[str, object]:
    return {
        "ts_utc": ts,
        "symbol": "BTCUSDT",
        "funding_rate": rate,
        "source": "bybit",
        "schema_version": 1,
    }


def _write_plan(plan_path: Path) -> None:
    payload = {
        "market_request_fingerprint": "fp-funding-validate-cli",
        "symbols": {
            "BTCUSDT": {
                "last": {
                    "required_intervals": [
                        {
                            "start": _dt(2026, 4, 1, 0).isoformat(),
                            "end": _dt(2026, 4, 1, 16).isoformat(),
                        }
                    ]
                }
            }
        },
    }
    plan_path.write_text(json.dumps(payload), encoding="utf-8")


def _write_funding_parquet(market_dir: Path) -> None:
    target = market_dir / "bybit" / "futures_linear" / "funding" / "BTCUSDT"
    target.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            _funding_row(_dt(2026, 4, 1, 0), 0.0001),
            _funding_row(_dt(2026, 4, 1, 16), 0.0002),
        ]
    ).to_parquet(target / "2026-04.funding.parquet", index=False)


def test_validate_funding_rates_cli_strict_fails_on_warning(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    plan_path = tmp_path / "plan.json"
    market_dir = tmp_path / "market"
    output_loose = tmp_path / "validate_funding_loose.json"
    output_strict = tmp_path / "validate_funding_strict.json"

    _write_plan(plan_path)
    _write_funding_parquet(market_dir)

    loose = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "validate_funding_rates.py"),
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
            str(repo_root / "scripts" / "validate_funding_rates.py"),
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
    assert "PHASE=validate_funding" in loose.stdout
    assert "SUMMARY=pass:" in loose.stdout
    assert loose_report["status"] == "PASS"
    assert strict_report["status"] == "FAIL"
    assert strict_report["strict"] is True
    assert strict_report["warning_count"] >= 1
    assert any(
        issue["code"] == "FUNDING_GAP_WARNING" and issue["severity"] == "warning"
        for result in strict_report["results"]
        for issue in result["issues"]
    )
