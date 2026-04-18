from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import urllib.error

import pandas as pd

from src.signal_chain_lab.market.planning.manifest_store import ManifestStore
from src.signal_chain_lab.market.sync.bybit_funding_downloader import (
    BybitFundingClient,
    BybitFundingDownloader,
    FundingDownloadJob,
    SymbolNotAvailableError,
)


def _dt(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 4, day, hour, tzinfo=timezone.utc)


class _FakeFundingClient:
    def __init__(self, batches: list[list[dict[str, object]]]) -> None:
        self._batches = list(batches)

    def fetch(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        if self._batches:
            return self._batches.pop(0)
        return []


def test_downloader_writes_partition_and_manifest(tmp_path: Path) -> None:
    rows = [
        {
            "symbol": "BTCUSDT",
            "fundingRate": "0.0001",
            "fundingRateTimestamp": str(int(_dt(2, 8).timestamp() * 1000)),
        },
        {
            "symbol": "BTCUSDT",
            "fundingRate": "0.0002",
            "fundingRateTimestamp": str(int(_dt(2, 0).timestamp() * 1000)),
        },
    ]
    downloader = BybitFundingDownloader(
        market_dir=tmp_path,
        manifest_store=ManifestStore(root=tmp_path / "manifests"),
        client=_FakeFundingClient([rows]),
    )

    result = downloader.download(
        [FundingDownloadJob(symbol="BTCUSDT", start_time=_dt(1), end_time=_dt(3))]
    )[0]

    parquet_path = tmp_path / "bybit" / "futures_linear" / "funding" / "BTCUSDT" / "2026-04.funding.parquet"
    frame = pd.read_parquet(parquet_path)

    assert result.status == "ok"
    assert result.events_downloaded == 2
    assert list(frame.columns) == ["ts_utc", "symbol", "funding_rate", "source", "schema_version"]
    assert frame["ts_utc"].is_monotonic_increasing

    coverage = downloader._load_covered("BTCUSDT")
    assert coverage[0].start == _dt(1)
    assert coverage[0].end == _dt(3)


def test_downloader_merges_existing_partition_without_duplicates(tmp_path: Path) -> None:
    downloader = BybitFundingDownloader(
        market_dir=tmp_path,
        manifest_store=ManifestStore(root=tmp_path / "manifests"),
        client=_FakeFundingClient(
            [[
                {
                    "symbol": "BTCUSDT",
                    "fundingRate": "0.0003",
                    "fundingRateTimestamp": str(int(_dt(2, 16).timestamp() * 1000)),
                }
            ]]
        ),
    )

    seed_path = tmp_path / "bybit" / "futures_linear" / "funding" / "BTCUSDT" / "2026-04.funding.parquet"
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ts_utc": _dt(2, 8),
                "symbol": "BTCUSDT",
                "funding_rate": 0.0001,
                "source": "bybit",
                "schema_version": 1,
            },
            {
                "ts_utc": _dt(2, 16),
                "symbol": "BTCUSDT",
                "funding_rate": 0.0003,
                "source": "bybit",
                "schema_version": 1,
            },
        ]
    ).to_parquet(seed_path, index=False)

    downloader.download(
        [FundingDownloadJob(symbol="BTCUSDT", start_time=_dt(2), end_time=_dt(3))]
    )

    frame = pd.read_parquet(seed_path)
    assert len(frame) == 2
    assert frame["ts_utc"].is_monotonic_increasing


def test_downloader_marks_missing_symbol_as_skipped(tmp_path: Path) -> None:
    class MissingSymbolClient:
        def fetch(self, **kwargs):
            raise SymbolNotAvailableError("DOGEINVALID", "symbol not exist")

    downloader = BybitFundingDownloader(
        market_dir=tmp_path,
        manifest_store=ManifestStore(root=tmp_path / "manifests"),
        client=MissingSymbolClient(),
    )

    result = downloader.download(
        [FundingDownloadJob(symbol="DOGEINVALID", start_time=_dt(1), end_time=_dt(2))]
    )[0]

    assert result.status == "skipped"
    assert result.error_message is not None


def test_bybit_funding_client_retries_after_http_429(monkeypatch) -> None:
    calls = {"count": 0}
    slept: list[float] = []

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return (
                b'{"retCode":0,"retMsg":"OK","result":{"list":[{"symbol":"BTCUSDT",'
                b'"fundingRate":"0.0001","fundingRateTimestamp":"1775174400000"}]}}'
            )

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.HTTPError(
                url=str(request.full_url),
                code=429,
                msg="too many requests",
                hdrs=None,
                fp=None,
            )
        return _FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", slept.append)

    client = BybitFundingClient(max_retries=2, retry_base_delay=0.5)
    rows = client.fetch(
        symbol="BTCUSDT",
        start_ms=int(_dt(1).timestamp() * 1000),
        end_ms=int((_dt(1) + timedelta(hours=8)).timestamp() * 1000),
    )

    assert len(rows) == 1
    assert calls["count"] == 2
    assert slept == [0.5]
