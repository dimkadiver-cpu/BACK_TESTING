from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path


class _FakeFundingResult:
    def __init__(self, *, status: str = "ok", events_downloaded: int = 3) -> None:
        self.status = status
        self.events_downloaded = events_downloaded
        self.intervals_written = []
        self.error_message = None if status != "error" else "boom"


def _load_sync_module() -> object:
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "sync_funding_rates.py"
    spec = importlib.util.spec_from_file_location("sync_funding_rates_script", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sample_plan() -> dict[str, object]:
    return {
        "symbols": {
            "BTCUSDT": {
                "last": {
                    "required_intervals": [
                        {
                            "start": datetime(2026, 4, 1, tzinfo=timezone.utc).isoformat(),
                            "end": datetime(2026, 4, 2, tzinfo=timezone.utc).isoformat(),
                        }
                    ],
                    "timeframes": {
                        "1m": {
                            "required_intervals": [
                                {
                                    "start": datetime(2026, 4, 1, tzinfo=timezone.utc).isoformat(),
                                    "end": datetime(2026, 4, 2, tzinfo=timezone.utc).isoformat(),
                                }
                            ]
                        }
                    },
                },
                "mark": {
                    "required_intervals": [
                        {
                            "start": datetime(2026, 4, 1, tzinfo=timezone.utc).isoformat(),
                            "end": datetime(2026, 4, 3, tzinfo=timezone.utc).isoformat(),
                        }
                    ]
                },
            },
            "ETHUSDT": {
                "last": {
                    "required_intervals": [
                        {
                            "start": datetime(2026, 4, 5, tzinfo=timezone.utc).isoformat(),
                            "end": datetime(2026, 4, 6, tzinfo=timezone.utc).isoformat(),
                        }
                    ]
                }
            },
        }
    }


def test_build_jobs_merges_intervals_across_bases() -> None:
    module = _load_sync_module()

    jobs = module.build_jobs(_sample_plan())

    assert [(job.symbol, job.start_time.isoformat(), job.end_time.isoformat()) for job in jobs] == [
        (
            "BTCUSDT",
            datetime(2026, 4, 1, tzinfo=timezone.utc).isoformat(),
            datetime(2026, 4, 3, tzinfo=timezone.utc).isoformat(),
        ),
        (
            "ETHUSDT",
            datetime(2026, 4, 5, tzinfo=timezone.utc).isoformat(),
            datetime(2026, 4, 6, tzinfo=timezone.utc).isoformat(),
        ),
    ]


def test_main_returns_nonzero_on_download_error(monkeypatch, tmp_path: Path) -> None:
    module = _load_sync_module()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(_sample_plan()), encoding="utf-8")

    class FakeDownloader:
        def __init__(self, **kwargs):
            pass

        def download(self, jobs):
            return [_FakeFundingResult(status="error")]

    monkeypatch.setattr(module, "BybitFundingDownloader", FakeDownloader)
    monkeypatch.setattr(
        module,
        "parse_args",
        lambda: module.argparse.Namespace(
            market_dir=str(tmp_path / "market"),
            plan_file=str(plan_path),
            symbols="BTCUSDT",
            dry_run=False,
        ),
    )

    rc = module.main()
    assert rc == 1


def test_main_dry_run_skips_downloader(monkeypatch, tmp_path: Path) -> None:
    module = _load_sync_module()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(_sample_plan()), encoding="utf-8")

    class FakeDownloader:
        def __init__(self, **kwargs):
            raise AssertionError("downloader should not be constructed in dry-run")

    monkeypatch.setattr(module, "BybitFundingDownloader", FakeDownloader)
    monkeypatch.setattr(
        module,
        "parse_args",
        lambda: module.argparse.Namespace(
            market_dir=str(tmp_path / "market"),
            plan_file=str(plan_path),
            symbols="BTCUSDT",
            dry_run=True,
        ),
    )

    rc = module.main()
    assert rc == 0
