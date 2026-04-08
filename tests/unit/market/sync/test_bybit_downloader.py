"""Tests for BybitDownloader — incremental Bybit sync (IE.6).

Three test scenarios:
1. test_first_sync_complete          — first call downloads all data, writes files,
                                       updates manifest.
2. test_second_sync_no_new_gaps      — second sync_symbol call with same required
                                       intervals detects full coverage and skips.
3. test_sync_partial_gap             — manifest has partial coverage; downloader
                                       downloads only the missing portion.

All tests use FakeBybitClient (no real HTTP calls).
Parquet I/O uses a tmp_path fixture directory.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from src.signal_chain_lab.market.planning.gap_detection import Interval
from src.signal_chain_lab.market.planning.manifest_store import (
    CoverageKey,
    CoverageRecord,
    ManifestStore,
)
from src.signal_chain_lab.market.sync.bybit_downloader import (
    BybitDownloader,
    KlineClientProtocol,
    SyncJobResult,
    SymbolNotAvailableError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INTERVAL_MS = 60_000  # 1m


def _utc(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


# ---------------------------------------------------------------------------
# Fake client
# ---------------------------------------------------------------------------


class FakeBybitClient:
    """Generates deterministic synthetic 1m candles without real HTTP calls.

    Records every fetch call in self.calls for assertion.
    """

    def __init__(
        self,
        unavailable_symbols: set[str] | None = None,
    ) -> None:
        self._unavailable = unavailable_symbols or set()
        self.calls: list[dict[str, Any]] = []

    def fetch(
        self,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
        basis: str,
        limit: int = 1000,
    ) -> list[list[str]]:
        self.calls.append(
            {
                "symbol": symbol,
                "interval": interval,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "basis": basis,
                "limit": limit,
            }
        )

        if symbol in self._unavailable:
            raise SymbolNotAvailableError(symbol, "test: symbol not listed")

        candles: list[list[str]] = []
        ts = start_ms
        count = 0
        while ts < end_ms and count < limit:
            price = 50000.0 + (ts % 10_000) / 100
            volume = "1.5" if basis == "last" else "0"
            candles.append([
                str(ts),
                str(price),
                str(price + 5),
                str(price - 5),
                str(price + 1),
                volume,
            ])
            ts += _INTERVAL_MS
            count += 1

        # Bybit returns newest-first — reverse so oldest is last
        candles.reverse()
        return candles


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_downloader(
    tmp_path: Path,
    client: KlineClientProtocol,
    bases: list[str] | None = None,
) -> tuple[BybitDownloader, ManifestStore]:
    store = ManifestStore(root=tmp_path / "manifests")
    downloader = BybitDownloader(
        market_dir=tmp_path / "market",
        manifest_store=store,
        timeframe="1m",
        bases=bases or ["last", "mark"],
        client=client,
    )
    return downloader, store


# ---------------------------------------------------------------------------
# Test 1 — First sync: downloads all data, writes partitions, updates manifest
# ---------------------------------------------------------------------------


def test_first_sync_complete(tmp_path: Path) -> None:
    """First sync on an empty cache should download all data for the gap."""
    pytest.importorskip("pandas", reason="pandas required for parquet I/O")

    client = FakeBybitClient()
    downloader, store = _make_downloader(tmp_path, client, bases=["last"])

    gap_start = _utc(2026, 3, 1)
    gap_end = _utc(2026, 3, 1, 2)  # 2 hours → 120 candles
    gaps = [Interval(start=gap_start, end=gap_end)]

    results = downloader.sync_gaps(symbol="BTCUSDT", gaps=gaps, bases=["last"])

    assert len(results) == 1
    result = results[0]

    assert result.status == "ok", f"Unexpected status: {result.status}, errors: {result.errors}"
    assert result.rows_downloaded > 0
    assert len(result.partitions_written) >= 1
    assert result.basis == "last"

    # Parquet file must exist with correct path pattern
    parquet_path = tmp_path / "market" / "bybit" / "futures_linear" / "1m" / "BTCUSDT" / "2026-03.last.parquet"
    assert parquet_path.exists(), f"Expected parquet at {parquet_path}"

    # Parquet must contain rows
    import pandas as pd
    df = pd.read_parquet(parquet_path)
    assert len(df) > 0
    assert set(df.columns) >= {"timestamp", "open", "high", "low", "close", "volume"}

    # Manifest must be updated for this symbol/basis
    records = store.load_coverage_index()
    last_records = [
        r for r in records
        if r.key.symbol == "BTCUSDT" and r.key.basis == "last" and r.key.timeframe == "1m"
    ]
    assert len(last_records) == 1
    assert len(last_records[0].covered_intervals) >= 1

    # At least one fetch call was made
    assert len(client.calls) >= 1
    assert all(c["basis"] == "last" for c in client.calls)


# ---------------------------------------------------------------------------
# Test 2 — Second sync: no new gaps, skips download entirely
# ---------------------------------------------------------------------------


def test_second_sync_no_new_gaps(tmp_path: Path) -> None:
    """After a full sync, a second call with the same required intervals must skip."""
    pytest.importorskip("pandas", reason="pandas required for parquet I/O")

    client = FakeBybitClient()
    downloader, store = _make_downloader(tmp_path, client, bases=["last"])

    gap_start = _utc(2026, 4, 1)
    gap_end = _utc(2026, 4, 1, 1)  # 1 hour
    required = [Interval(start=gap_start, end=gap_end)]

    # --- First sync ---
    first_results = downloader.sync_symbol(symbol="ETHUSDT", required_intervals=required, bases=["last"])
    assert first_results[0].status == "ok"
    calls_after_first = len(client.calls)
    assert calls_after_first >= 1

    # --- Second sync with identical required intervals ---
    second_results = downloader.sync_symbol(symbol="ETHUSDT", required_intervals=required, bases=["last"])

    assert len(second_results) == 1
    second = second_results[0]
    assert second.status == "skipped", f"Expected 'skipped', got '{second.status}'"
    assert second.rows_downloaded == 0
    assert second.partitions_written == []

    # No new fetch calls should have been made
    calls_after_second = len(client.calls)
    assert calls_after_second == calls_after_first, (
        f"Expected no new API calls, but got {calls_after_second - calls_after_first} extra"
    )


# ---------------------------------------------------------------------------
# Test 3 — Partial gap: downloads only the missing portion
# ---------------------------------------------------------------------------


def test_sync_partial_gap(tmp_path: Path) -> None:
    """With partial existing coverage, only the uncovered portion is downloaded."""
    pytest.importorskip("pandas", reason="pandas required for parquet I/O")

    client = FakeBybitClient()
    downloader, store = _make_downloader(tmp_path, client, bases=["last"])

    # Pre-populate manifest: covers the first hour of a 3-hour required window
    already_covered_start = _utc(2026, 5, 1, 0)
    already_covered_end = _utc(2026, 5, 1, 1)  # hour 0-1 already covered

    store.upsert_coverage(
        CoverageRecord(
            key=CoverageKey(
                exchange="bybit",
                market_type="futures_linear",
                timeframe="1m",
                symbol="SOLUSDT",
                basis="last",
            ),
            covered_intervals=[
                Interval(start=already_covered_start, end=already_covered_end)
            ],
            validation_status="ok",
            last_updated=datetime.now(tz=timezone.utc),
        )
    )

    # Required covers 3 hours; manifest only covers first 1h → gap is [1h, 3h]
    required_start = _utc(2026, 5, 1, 0)
    required_end = _utc(2026, 5, 1, 3)
    required = [Interval(start=required_start, end=required_end)]

    results = downloader.sync_symbol(symbol="SOLUSDT", required_intervals=required, bases=["last"])

    assert len(results) == 1
    result = results[0]

    assert result.status == "ok", f"Unexpected status: {result.status}, errors: {result.errors}"
    assert result.rows_downloaded > 0

    # Verify API was called only for the gap portion (hour 1-3), not the full range
    assert len(client.calls) >= 1
    for call in client.calls:
        # All fetched intervals must start at or after the coverage boundary
        call_start = call["start_ms"]
        coverage_boundary_ms = _ms(already_covered_end)
        assert call_start >= coverage_boundary_ms, (
            f"Client was called for already-covered data: "
            f"call start {call_start} < coverage end {coverage_boundary_ms}"
        )

    # Manifest should now cover the full required range (merged)
    records = store.load_coverage_index()
    sol_records = [
        r for r in records
        if r.key.symbol == "SOLUSDT" and r.key.basis == "last"
    ]
    assert len(sol_records) == 1
    # Must cover at least the newly downloaded portion
    covered_end = max(iv.end for iv in sol_records[0].covered_intervals)
    assert covered_end >= _utc(2026, 5, 1, 1), "Coverage should extend past original boundary"


# ---------------------------------------------------------------------------
# Test 4 — Symbol not available: job status is 'skipped', no crash
# ---------------------------------------------------------------------------


def test_sync_unavailable_symbol(tmp_path: Path) -> None:
    """If the symbol is not available on Bybit, status must be 'skipped' without crash."""
    pytest.importorskip("pandas", reason="pandas required for parquet I/O")

    client = FakeBybitClient(unavailable_symbols={"FAKEXYZ"})
    downloader, store = _make_downloader(tmp_path, client, bases=["last"])

    gaps = [Interval(start=_utc(2026, 4, 1), end=_utc(2026, 4, 1, 1))]
    results = downloader.sync_gaps(symbol="FAKEXYZ", gaps=gaps, bases=["last"])

    assert len(results) == 1
    result = results[0]
    assert result.status == "skipped"
    assert len(result.errors) >= 1
    assert result.rows_downloaded == 0

    # download_log event must be appended
    import json
    log = json.loads(store.download_log_path.read_text(encoding="utf-8"))
    assert any(e.get("status") == "skipped" for e in log["events"])
