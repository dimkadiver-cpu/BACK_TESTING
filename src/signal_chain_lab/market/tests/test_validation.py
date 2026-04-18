from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.signal_chain_lab.market.planning.gap_detection import Interval
from src.signal_chain_lab.market.planning.validation import (
    BatchValidator,
    FundingBatchValidator,
    IssueSeverity,
)


def _dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _row(ts: datetime, *, open_: float = 100.0, high: float = 101.0, low: float = 99.0, close: float = 100.5, volume: float = 1.0) -> dict[str, object]:
    return {
        "timestamp": ts.isoformat(),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "symbol": "BTCUSDT",
        "timeframe": "1m",
    }


def test_validator_flags_invalid_ohlc_as_critical() -> None:
    rows = [_row(_dt(2026, 4, 18, 10, 0), low=102.0, high=101.0)]
    requested = Interval(start=_dt(2026, 4, 18, 9, 59), end=_dt(2026, 4, 18, 10, 1))

    result = BatchValidator().validate(rows=rows, requested_range=requested)

    assert result.has_errors is True
    assert any(issue.code == "OHLC_LOW_GT_HIGH" and issue.severity == IssueSeverity.CRITICAL for issue in result.issues)


def test_validator_flags_negative_volume_as_critical() -> None:
    rows = [_row(_dt(2026, 4, 18, 10, 0), volume=-1.0)]
    requested = Interval(start=_dt(2026, 4, 18, 9, 59), end=_dt(2026, 4, 18, 10, 1))

    result = BatchValidator().validate(rows=rows, requested_range=requested)

    assert result.has_errors is True
    assert any(issue.code == "VOLUME_NEGATIVE" and issue.severity == IssueSeverity.CRITICAL for issue in result.issues)


def test_validator_flags_large_internal_gap_as_warning() -> None:
    rows = [
        _row(_dt(2026, 4, 18, 10, 0)),
        _row(_dt(2026, 4, 18, 10, 3)),
    ]
    requested = Interval(start=_dt(2026, 4, 18, 9, 59), end=_dt(2026, 4, 18, 10, 4))

    result = BatchValidator(tolerated_missing_candles=1).validate(rows=rows, requested_range=requested)

    assert result.has_errors is False
    assert any(issue.code == "CONTINUITY_GAP_EXCESSIVE" and issue.severity == IssueSeverity.WARNING for issue in result.issues)
    assert result.warning_count >= 1


def test_validator_marks_single_missing_candle_as_info_when_tolerated() -> None:
    rows = [
        _row(_dt(2026, 4, 18, 10, 0)),
        _row(_dt(2026, 4, 18, 10, 2)),
    ]
    requested = Interval(start=_dt(2026, 4, 18, 9, 59), end=_dt(2026, 4, 18, 10, 3))

    result = BatchValidator(tolerated_missing_candles=1).validate(rows=rows, requested_range=requested)

    assert result.has_errors is False
    assert any(issue.code == "CONTINUITY_GAP_TOLERATED" and issue.severity == IssueSeverity.INFO for issue in result.issues)
    assert result.info_count >= 1


def test_validate_incremental_returns_one_result_per_interval() -> None:
    rows = [_row(_dt(2026, 4, 18, 10, 0)), _row(_dt(2026, 4, 18, 10, 1))]
    intervals = [
        Interval(start=_dt(2026, 4, 18, 9, 59), end=_dt(2026, 4, 18, 10, 1)),
        Interval(start=_dt(2026, 4, 18, 10, 0), end=_dt(2026, 4, 18, 10, 2)),
    ]

    results = BatchValidator().validate_incremental(rows=rows, requested_ranges=intervals)

    assert len(results) == 2
    assert all(hasattr(result, "issues") for result in results)


try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    pd = None

try:
    import pyarrow  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    pyarrow = None
else:
    pyarrow = True


def _funding_row(ts: datetime, rate: float) -> dict[str, object]:
    return {
        "ts_utc": ts,
        "symbol": "BTCUSDT",
        "funding_rate": rate,
        "source": "bybit",
        "schema_version": 1,
    }


def _write_funding_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


@pytest.mark.skipif(pd is None or pyarrow is None, reason="pandas/pyarrow required")
def test_funding_validator_accepts_regular_8h_cadence(tmp_path: Path) -> None:
    path = tmp_path / "2026-04.funding.parquet"
    _write_funding_parquet(
        path,
        [
            _funding_row(_dt(2026, 4, 1, 0), 0.0001),
            _funding_row(_dt(2026, 4, 1, 8), 0.0002),
            _funding_row(_dt(2026, 4, 1, 16), -0.0001),
        ],
    )

    result = FundingBatchValidator().validate(
        "BTCUSDT",
        [path],
        Interval(start=_dt(2026, 4, 1, 0), end=_dt(2026, 4, 1, 16)),
    )

    assert result.has_errors is False
    assert result.warning_count == 0


@pytest.mark.skipif(pd is None or pyarrow is None, reason="pandas/pyarrow required")
def test_funding_validator_flags_16h_gap_as_warning(tmp_path: Path) -> None:
    path = tmp_path / "2026-04.funding.parquet"
    _write_funding_parquet(
        path,
        [
            _funding_row(_dt(2026, 4, 4, 0), 0.0001),
            _funding_row(_dt(2026, 4, 4, 16), 0.0002),
        ],
    )

    result = FundingBatchValidator().validate(
        "BTCUSDT",
        [path],
        Interval(start=_dt(2026, 4, 4, 0), end=_dt(2026, 4, 4, 16)),
    )

    assert result.has_errors is False
    assert any(issue.code == "FUNDING_GAP_WARNING" for issue in result.issues)


@pytest.mark.skipif(pd is None or pyarrow is None, reason="pandas/pyarrow required")
def test_funding_validator_flags_30h_gap_as_critical(tmp_path: Path) -> None:
    path = tmp_path / "2026-04.funding.parquet"
    _write_funding_parquet(
        path,
        [
            _funding_row(_dt(2026, 4, 5, 0), 0.0001),
            _funding_row(_dt(2026, 4, 6, 6), 0.0002),
        ],
    )

    result = FundingBatchValidator().validate(
        "BTCUSDT",
        [path],
        Interval(start=_dt(2026, 4, 5, 0), end=_dt(2026, 4, 6, 6)),
    )

    assert result.has_errors is True
    assert any(issue.code == "FUNDING_GAP_CRITICAL" for issue in result.issues)


@pytest.mark.skipif(pd is None or pyarrow is None, reason="pandas/pyarrow required")
def test_funding_validator_flags_duplicate_timestamp_as_warning(tmp_path: Path) -> None:
    path = tmp_path / "2026-04.funding.parquet"
    _write_funding_parquet(
        path,
        [
            _funding_row(_dt(2026, 4, 7, 0), 0.0001),
            _funding_row(_dt(2026, 4, 7, 0), 0.0001),
        ],
    )

    result = FundingBatchValidator().validate(
        "BTCUSDT",
        [path],
        Interval(start=_dt(2026, 4, 7, 0), end=_dt(2026, 4, 7, 8)),
    )

    assert any(issue.code == "DUPLICATE_TIMESTAMP" for issue in result.issues)


@pytest.mark.skipif(pd is None or pyarrow is None, reason="pandas/pyarrow required")
def test_funding_validator_flags_nan_rate_as_critical(tmp_path: Path) -> None:
    path = tmp_path / "2026-04.funding.parquet"
    _write_funding_parquet(path, [_funding_row(_dt(2026, 4, 8, 0), float("nan"))])

    result = FundingBatchValidator().validate(
        "BTCUSDT",
        [path],
        Interval(start=_dt(2026, 4, 8, 0), end=_dt(2026, 4, 8, 8)),
    )

    assert result.has_errors is True
    assert any(issue.code == "FUNDING_RATE_NOT_FINITE" for issue in result.issues)


@pytest.mark.skipif(pd is None or pyarrow is None, reason="pandas/pyarrow required")
def test_funding_validator_flags_out_of_range_rate_as_warning(tmp_path: Path) -> None:
    path = tmp_path / "2026-04.funding.parquet"
    _write_funding_parquet(path, [_funding_row(_dt(2026, 4, 9, 0), 0.1)])

    result = FundingBatchValidator().validate(
        "BTCUSDT",
        [path],
        Interval(start=_dt(2026, 4, 9, 0), end=_dt(2026, 4, 9, 8)),
    )

    assert any(issue.code == "FUNDING_RATE_OUT_OF_RANGE" for issue in result.issues)
