from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.signal_chain_lab.market.providers.bybit_funding_provider import BybitFundingProvider


def _dt(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _write_month(tmp_path: Path, symbol: str, month_key: str, rows: list[dict[str, object]]) -> Path:
    path = tmp_path / "bybit" / "futures_linear" / "funding" / symbol / f"{month_key}.funding.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def test_get_funding_events_returns_sorted_events_across_months(tmp_path: Path) -> None:
    symbol = "BTCUSDT"
    _write_month(
        tmp_path,
        symbol,
        "2026-03",
        [
            {"ts_utc": _dt(2026, 3, 31, 16), "symbol": symbol, "funding_rate": 0.0003, "source": "bybit", "schema_version": 1},
            {"ts_utc": _dt(2026, 3, 31, 8), "symbol": symbol, "funding_rate": 0.0002, "source": "bybit", "schema_version": 1},
        ],
    )
    _write_month(
        tmp_path,
        symbol,
        "2026-04",
        [
            {"ts_utc": _dt(2026, 4, 1, 0), "symbol": symbol, "funding_rate": 0.0004, "source": "bybit", "schema_version": 1},
        ],
    )

    provider = BybitFundingProvider(tmp_path, symbol)
    events = provider.get_funding_events(symbol, _dt(2026, 3, 31, 0), _dt(2026, 4, 1, 1))

    assert [event.funding_ts_utc for event in events] == [
        _dt(2026, 3, 31, 8),
        _dt(2026, 3, 31, 16),
        _dt(2026, 4, 1, 0),
    ]


def test_get_funding_events_filters_requested_interval(tmp_path: Path) -> None:
    symbol = "BTCUSDT"
    _write_month(
        tmp_path,
        symbol,
        "2026-04",
        [
            {"ts_utc": _dt(2026, 4, 1, 0), "symbol": symbol, "funding_rate": 0.0001, "source": "bybit", "schema_version": 1},
            {"ts_utc": _dt(2026, 4, 1, 8), "symbol": symbol, "funding_rate": 0.0002, "source": "bybit", "schema_version": 1},
            {"ts_utc": _dt(2026, 4, 1, 16), "symbol": symbol, "funding_rate": 0.0003, "source": "bybit", "schema_version": 1},
        ],
    )

    provider = BybitFundingProvider(tmp_path, symbol)
    events = provider.get_funding_events(symbol, _dt(2026, 4, 1, 1), _dt(2026, 4, 1, 12))

    assert [event.funding_ts_utc for event in events] == [_dt(2026, 4, 1, 8)]


def test_get_funding_events_returns_empty_list_for_missing_month(tmp_path: Path) -> None:
    provider = BybitFundingProvider(tmp_path, "BTCUSDT")

    events = provider.get_funding_events("BTCUSDT", _dt(2026, 4, 1), _dt(2026, 4, 2))

    assert events == []


def test_provider_reads_same_month_only_once(tmp_path: Path, monkeypatch) -> None:
    symbol = "BTCUSDT"
    path = _write_month(
        tmp_path,
        symbol,
        "2026-04",
        [
            {"ts_utc": _dt(2026, 4, 1, 0), "symbol": symbol, "funding_rate": 0.0001, "source": "bybit", "schema_version": 1},
            {"ts_utc": _dt(2026, 4, 1, 8), "symbol": symbol, "funding_rate": 0.0002, "source": "bybit", "schema_version": 1},
        ],
    )

    real_read_parquet = pd.read_parquet
    calls: list[Path] = []

    def counting_read_parquet(target, *args, **kwargs):
        calls.append(Path(target))
        return real_read_parquet(target, *args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", counting_read_parquet)

    provider = BybitFundingProvider(tmp_path, symbol)
    provider.get_funding_events(symbol, _dt(2026, 4, 1, 0), _dt(2026, 4, 1, 12))
    provider.get_funding_events(symbol, _dt(2026, 4, 1, 0), _dt(2026, 4, 1, 12))

    assert calls == [path]


def test_get_funding_rate_returns_immediately_previous_event(tmp_path: Path) -> None:
    symbol = "BTCUSDT"
    _write_month(
        tmp_path,
        symbol,
        "2026-03",
        [
            {"ts_utc": _dt(2026, 3, 31, 16), "symbol": symbol, "funding_rate": 0.0007, "source": "bybit", "schema_version": 1},
        ],
    )
    _write_month(
        tmp_path,
        symbol,
        "2026-04",
        [
            {"ts_utc": _dt(2026, 4, 1, 8), "symbol": symbol, "funding_rate": 0.0011, "source": "bybit", "schema_version": 1},
        ],
    )

    provider = BybitFundingProvider(tmp_path, symbol)

    assert provider.get_funding_rate(symbol, _dt(2026, 4, 1, 10)) == 0.0011
    assert provider.get_funding_rate(symbol, _dt(2026, 4, 1, 1)) == 0.0007
    assert provider.get_funding_rate(symbol, _dt(2026, 3, 1, 0)) is None
