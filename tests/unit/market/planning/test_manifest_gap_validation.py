from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.market.planning.gap_detection import Interval, detect_gaps
from src.signal_chain_lab.market.planning.validation import BatchValidator


def test_detect_gaps_with_partial_coverage() -> None:
    required = [
        Interval(
            start=datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 1, 6, 0, tzinfo=timezone.utc),
        )
    ]
    covered = [
        Interval(
            start=datetime(2026, 4, 1, 1, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 1, 2, 0, tzinfo=timezone.utc),
        ),
        Interval(
            start=datetime(2026, 4, 1, 4, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 1, 6, 0, tzinfo=timezone.utc),
        ),
    ]

    gaps = detect_gaps(required=required, covered=covered)

    assert [(gap.start.hour, gap.end.hour) for gap in gaps] == [(0, 1), (2, 4)]


def test_batch_validator_detects_dirty_dataset() -> None:
    validator = BatchValidator()
    requested = Interval(
        start=datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
        end=datetime(2026, 4, 1, 0, 2, tzinfo=timezone.utc),
    )

    rows = [
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
            "timestamp": "2026-04-01T00:02:00+00:00",
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "symbol": "BTCUSDT",
            "timeframe": "1m",
        },
    ]

    result = validator.validate(rows=rows, requested_range=requested)
    codes = {issue.code for issue in result.issues}

    assert "TIMESTAMP_UNSORTED" in codes
    assert "DUPLICATES_REMOVED" in codes
    assert "SCHEMA_MISSING_FIELDS" in codes
    assert "COVERAGE_INCOMPLETE" in codes
    assert result.has_errors is True
