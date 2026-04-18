from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

from src.signal_chain_lab.market.planning.gap_detection import Interval


class _FakeSyncResult:
    def __init__(self, *, status: str = "ok") -> None:
        self.status = status
        self.rows_downloaded = 5
        self.partitions_written = ["/tmp/2026-04.last.parquet"]
        self.errors = [] if status == "ok" else ["boom"]


def _load_sync_module() -> object:
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "sync_market_data.py"
    spec = importlib.util.spec_from_file_location("sync_market_data_script", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sample_plan() -> dict[str, object]:
    return {
        "timeframe": "1m",
        "symbols": {
            "BTCUSDT": {
                "last": {
                    "gaps": [
                        {
                            "start": datetime(2026, 4, 1, tzinfo=timezone.utc).isoformat(),
                            "end": datetime(2026, 4, 1, 1, tzinfo=timezone.utc).isoformat(),
                        }
                    ]
                }
            }
        },
    }


def test_sync_bybit_uses_downloader(monkeypatch, tmp_path: Path) -> None:
    module = _load_sync_module()

    called: list[tuple[str, str, int]] = []

    class FakeDownloader:
        def __init__(self, **kwargs):
            pass

        def sync_gaps(self, symbol: str, gaps: list[Interval], bases: list[str]):
            called.append((symbol, bases[0], len(gaps)))
            return [_FakeSyncResult(status="ok")]

    monkeypatch.setattr(module, "BybitDownloader", FakeDownloader)

    report = module._sync_bybit(
        plan=_sample_plan(),
        market_dir=tmp_path,
        manifest=module.ManifestStore(root=tmp_path / "manifests"),
        source="bybit",
    )

    assert called == [("BTCUSDT", "last", 1)]
    assert report[0]["status"] == "ok"
    assert report[0]["source"] == "bybit"
    assert report[0]["timeframe"] == "1m"


def test_sync_bybit_uses_requested_timeframes_when_present(monkeypatch, tmp_path: Path) -> None:
    module = _load_sync_module()

    called: list[tuple[str, str, str, int]] = []
    plan = {
        "timeframe": "15m",
        "symbols": {
            "BTCUSDT": {
                "last": {
                    "timeframes": {
                        "15m": {
                            "gaps": [
                                {
                                    "start": datetime(2026, 4, 1, tzinfo=timezone.utc).isoformat(),
                                    "end": datetime(2026, 4, 1, 1, tzinfo=timezone.utc).isoformat(),
                                }
                            ]
                        },
                        "1m": {
                            "gaps": [
                                {
                                    "start": datetime(2026, 4, 1, tzinfo=timezone.utc).isoformat(),
                                    "end": datetime(2026, 4, 1, 0, 15, tzinfo=timezone.utc).isoformat(),
                                }
                            ]
                        },
                    }
                }
            }
        },
    }

    class FakeDownloader:
        def __init__(self, **kwargs):
            self.timeframe = kwargs["timeframe"]

        def sync_gaps(self, symbol: str, gaps: list[Interval], bases: list[str]):
            called.append((symbol, bases[0], self.timeframe, len(gaps)))
            return [_FakeSyncResult(status="ok")]

    monkeypatch.setattr(module, "BybitDownloader", FakeDownloader)

    report = module._sync_bybit(
        plan=plan,
        market_dir=tmp_path,
        manifest=module.ManifestStore(root=tmp_path / "manifests"),
        source="bybit",
    )

    assert called == [
        ("BTCUSDT", "last", "15m", 1),
        ("BTCUSDT", "last", "1m", 1),
    ]
    assert [item["timeframe"] for item in report] == ["15m", "1m"]


def test_main_returns_nonzero_on_sync_error(monkeypatch, tmp_path: Path) -> None:
    module = _load_sync_module()

    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(_sample_plan()), encoding="utf-8")

    class FakeDownloader:
        def __init__(self, **kwargs):
            pass

        def sync_gaps(self, symbol: str, gaps: list[Interval], bases: list[str]):
            return [_FakeSyncResult(status="error")]

    monkeypatch.setattr(module, "BybitDownloader", FakeDownloader)
    monkeypatch.setattr(
        module,
        "parse_args",
        lambda: module.argparse.Namespace(
            plan_file=str(plan_path),
            db_path=None,
            market_dir=str(tmp_path / "market"),
            source="bybit",
            output=str(tmp_path / "sync_report.json"),
        ),
    )

    rc = module.main()
    assert rc == 1
