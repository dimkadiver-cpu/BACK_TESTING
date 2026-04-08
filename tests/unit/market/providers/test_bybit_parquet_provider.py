"""Tests for BybitParquetProvider (IE.8).

Scenarios:
1. test_loads_candles_from_single_month     — reads one monthly partition
2. test_loads_candles_across_multiple_months — concatenates two monthly partitions
3. test_has_symbol_returns_false_if_missing  — missing symbol dir → False
4. test_get_candle_returns_exact_match       — timestamp-exact lookup
5. test_get_range_returns_correct_slice      — bounded range query
6. test_get_intrabar_range_child_timeframe   — loads child timeframe directory
7. test_get_metadata_reflects_loaded_range   — MarketMetadata start/end
8. test_mark_basis_reads_mark_files          — basis="mark" reads .mark.parquet only
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.signal_chain_lab.market.providers.bybit_parquet_provider import BybitParquetProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def _write_parquet(path: Path, candles: list[dict]) -> None:
    """Write a list of candle dicts to a parquet file."""
    import pandas as pd
    pd.DataFrame(candles).to_parquet(path, index=False)


def _make_candle_rows(
    start: datetime,
    count: int,
    symbol: str = "BTCUSDT",
    timeframe: str = "1m",
    basis: str = "last",
) -> list[dict]:
    """Generate synthetic 1m candle rows starting from `start`."""
    rows = []
    for i in range(count):
        ts = start + timedelta(minutes=i)
        price = 50000.0 + i
        rows.append({
            "timestamp": ts,
            "open": price,
            "high": price + 5,
            "low": price - 5,
            "close": price + 1,
            "volume": 1.0 if basis == "last" else 0.0,
            "symbol": symbol,
            "timeframe": timeframe,
        })
    return rows


def _setup_parquet_files(
    market_dir: Path,
    symbol: str,
    timeframe: str,
    basis: str,
    month_candles: dict[str, list[dict]],
    exchange: str = "bybit",
    market_type: str = "futures_linear",
) -> None:
    """Write monthly parquet files into the expected directory structure."""
    sym_dir = market_dir / exchange / market_type / timeframe / symbol
    sym_dir.mkdir(parents=True, exist_ok=True)
    for month_key, rows in month_candles.items():
        path = sym_dir / f"{month_key}.{basis}.parquet"
        _write_parquet(path, rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_loads_candles_from_single_month(tmp_path: Path) -> None:
    pytest.importorskip("pandas", reason="pandas required")

    rows = _make_candle_rows(start=_utc(2026, 4, 1), count=60)
    _setup_parquet_files(tmp_path, "BTCUSDT", "1m", "last", {"2026-04": rows})

    provider = BybitParquetProvider(market_dir=tmp_path, timeframe="1m", basis="last")
    assert provider.has_symbol("BTCUSDT")

    all_candles = provider.get_range("BTCUSDT", "1m", _utc(2026, 4, 1), _utc(2026, 4, 1, 1))
    assert len(all_candles) == 60  # 00:00 through 00:59 (60 rows = count)
    assert all_candles[0].timestamp == _utc(2026, 4, 1, 0, 0)
    assert all_candles[-1].timestamp == _utc(2026, 4, 1, 0, 59)


def test_loads_candles_across_multiple_months(tmp_path: Path) -> None:
    pytest.importorskip("pandas", reason="pandas required")

    rows_march = _make_candle_rows(start=_utc(2026, 3, 31, 23, 0), count=60)
    rows_april = _make_candle_rows(start=_utc(2026, 4, 1, 0, 0), count=60)
    _setup_parquet_files(
        tmp_path, "ETHUSDT", "1m", "last",
        {"2026-03": rows_march, "2026-04": rows_april},
    )

    provider = BybitParquetProvider(market_dir=tmp_path, timeframe="1m", basis="last")
    assert provider.has_symbol("ETHUSDT")

    full = provider.get_range("ETHUSDT", "1m", _utc(2026, 3, 31, 23, 0), _utc(2026, 4, 1, 0, 59))
    # 60 from march + 60 from april = 120
    assert len(full) == 120
    # sorted ascending
    assert full[0].timestamp < full[-1].timestamp


def test_has_symbol_returns_false_if_missing(tmp_path: Path) -> None:
    pytest.importorskip("pandas", reason="pandas required")

    provider = BybitParquetProvider(market_dir=tmp_path, timeframe="1m", basis="last")
    assert not provider.has_symbol("FAKEXYZ")


def test_get_candle_returns_exact_match(tmp_path: Path) -> None:
    pytest.importorskip("pandas", reason="pandas required")

    rows = _make_candle_rows(start=_utc(2026, 5, 1, 10, 0), count=5)
    _setup_parquet_files(tmp_path, "SOLUSDT", "1m", "last", {"2026-05": rows})

    provider = BybitParquetProvider(market_dir=tmp_path, timeframe="1m", basis="last")
    target_ts = _utc(2026, 5, 1, 10, 2)
    candle = provider.get_candle("SOLUSDT", "1m", target_ts)
    assert candle is not None
    assert candle.timestamp == target_ts
    assert candle.symbol == "SOLUSDT"

    # Non-existent timestamp → None
    assert provider.get_candle("SOLUSDT", "1m", _utc(2026, 6, 1)) is None


def test_get_range_returns_correct_slice(tmp_path: Path) -> None:
    pytest.importorskip("pandas", reason="pandas required")

    rows = _make_candle_rows(start=_utc(2026, 4, 1, 0, 0), count=120)
    _setup_parquet_files(tmp_path, "XRPUSDT", "1m", "last", {"2026-04": rows})

    provider = BybitParquetProvider(market_dir=tmp_path, timeframe="1m", basis="last")
    sliced = provider.get_range("XRPUSDT", "1m", _utc(2026, 4, 1, 0, 10), _utc(2026, 4, 1, 0, 20))
    assert len(sliced) == 11  # 10, 11, ..., 20 = 11 points
    assert sliced[0].timestamp == _utc(2026, 4, 1, 0, 10)
    assert sliced[-1].timestamp == _utc(2026, 4, 1, 0, 20)


def test_get_intrabar_range_child_timeframe(tmp_path: Path) -> None:
    pytest.importorskip("pandas", reason="pandas required")

    # Write 1m candles for child timeframe
    rows = _make_candle_rows(start=_utc(2026, 4, 1, 0, 0), count=60, timeframe="1m")
    _setup_parquet_files(tmp_path, "BTCUSDT", "1m", "last", {"2026-04": rows})

    provider = BybitParquetProvider(market_dir=tmp_path, timeframe="1h", basis="last")
    # Parent candle at 00:00, duration 1h → child candles [00:00, 01:00)
    intrabar = provider.get_intrabar_range("BTCUSDT", "1h", "1m", _utc(2026, 4, 1, 0, 0))
    assert len(intrabar) == 60  # 00:00 through 00:59
    assert all(c.timestamp < _utc(2026, 4, 1, 1, 0) for c in intrabar)


def test_get_metadata_reflects_loaded_range(tmp_path: Path) -> None:
    pytest.importorskip("pandas", reason="pandas required")

    rows = _make_candle_rows(start=_utc(2026, 4, 1, 0, 0), count=10)
    _setup_parquet_files(tmp_path, "BNBUSDT", "1m", "last", {"2026-04": rows})

    provider = BybitParquetProvider(market_dir=tmp_path, timeframe="1m", basis="last")
    meta = provider.get_metadata("BNBUSDT", "1m")
    assert meta is not None
    assert meta.symbol == "BNBUSDT"
    assert meta.start == _utc(2026, 4, 1, 0, 0)
    assert meta.end == _utc(2026, 4, 1, 0, 9)
    assert "bybit_parquet" in meta.provider_name
    assert "last" in meta.provider_name


def test_mark_basis_reads_mark_files(tmp_path: Path) -> None:
    pytest.importorskip("pandas", reason="pandas required")

    last_rows = _make_candle_rows(start=_utc(2026, 4, 1), count=5, basis="last")
    mark_rows = _make_candle_rows(start=_utc(2026, 4, 1), count=3, basis="mark")

    _setup_parquet_files(tmp_path, "BTCUSDT", "1m", "last", {"2026-04": last_rows})
    _setup_parquet_files(tmp_path, "BTCUSDT", "1m", "mark", {"2026-04": mark_rows})

    last_provider = BybitParquetProvider(market_dir=tmp_path, timeframe="1m", basis="last")
    mark_provider = BybitParquetProvider(market_dir=tmp_path, timeframe="1m", basis="mark")

    last_candles = last_provider.get_range("BTCUSDT", "1m", _utc(2026, 4, 1), _utc(2026, 4, 1, 0, 10))
    mark_candles = mark_provider.get_range("BTCUSDT", "1m", _utc(2026, 4, 1), _utc(2026, 4, 1, 0, 10))

    assert len(last_candles) == 5
    assert len(mark_candles) == 3
