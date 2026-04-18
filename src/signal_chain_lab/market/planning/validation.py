"""Market-data batch validation with schema, OHLC and continuity checks."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from src.signal_chain_lab.market.planning.gap_detection import Interval

logger = logging.getLogger(__name__)

EXPECTED_SCHEMA = {
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "symbol",
    "timeframe",
}

FUNDING_EXPECTED_SCHEMA = {
    "ts_utc",
    "symbol",
    "funding_rate",
}


class IssueSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: IssueSeverity
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationResult:
    cleaned_rows: list[dict[str, Any]] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == IssueSeverity.CRITICAL for issue in self.issues)

    @property
    def critical_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == IssueSeverity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == IssueSeverity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == IssueSeverity.INFO)


class BatchValidator:
    """Validate and normalize downloaded candle batches."""

    def __init__(self, *, tolerated_missing_candles: int = 1) -> None:
        self._tolerated_missing_candles = max(0, int(tolerated_missing_candles))

    def validate(self, rows: list[dict[str, Any]], requested_range: Interval) -> ValidationResult:
        issues: list[ValidationIssue] = []

        schema_ok_rows: list[dict[str, Any]] = []
        for idx, row in enumerate(rows):
            missing = EXPECTED_SCHEMA - set(row.keys())
            if missing:
                message = f"row[{idx}] missing fields: {sorted(missing)}"
                issues.append(ValidationIssue(IssueSeverity.CRITICAL, "SCHEMA_MISSING_FIELDS", message))
                logger.error(message)
                continue
            schema_ok_rows.append({**row})

        normalized = self._normalize_and_sort(schema_ok_rows, issues)
        deduped = self._deduplicate(normalized, issues)
        self._check_ohlc_integrity(deduped, issues)
        self._check_internal_continuity(deduped, issues)
        self._check_coverage(deduped, requested_range, issues)

        return ValidationResult(cleaned_rows=deduped, issues=issues)

    def validate_incremental(
        self,
        rows: list[dict[str, Any]],
        requested_ranges: list[Interval],
        *,
        new_intervals_only: bool = True,
    ) -> list[ValidationResult]:
        intervals = requested_ranges if new_intervals_only else requested_ranges
        return [self.validate(rows=rows, requested_range=interval) for interval in intervals]

    def _normalize_and_sort(
        self,
        rows: list[dict[str, Any]],
        issues: list[ValidationIssue],
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        parse_errors = 0
        for idx, row in enumerate(rows):
            try:
                parsed_ts = _as_datetime(row["timestamp"])
                open_price = _as_float(row["open"])
                high_price = _as_float(row["high"])
                low_price = _as_float(row["low"])
                close_price = _as_float(row["close"])
                volume = _as_float(row["volume"])
            except ValueError as exc:
                parse_errors += 1
                message = f"row[{idx}] normalization error: {exc}"
                issues.append(ValidationIssue(IssueSeverity.CRITICAL, "SCHEMA_INVALID_VALUE", message))
                logger.error(message)
                continue
            normalized.append(
                {
                    **row,
                    "timestamp": parsed_ts,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": volume,
                }
            )

        sorted_rows = sorted(normalized, key=lambda item: item["timestamp"])
        if sorted_rows != normalized:
            message = "input rows were not sorted by timestamp"
            issues.append(ValidationIssue(IssueSeverity.WARNING, "TIMESTAMP_UNSORTED", message))
            logger.warning(message)
        if parse_errors:
            logger.error("Normalization errors: %s", parse_errors)
        return sorted_rows

    def _deduplicate(
        self,
        rows: list[dict[str, Any]],
        issues: list[ValidationIssue],
    ) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[datetime, str, str]] = set()
        duplicates = 0

        for row in rows:
            key = (row["timestamp"], str(row["symbol"]), str(row["timeframe"]))
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            deduped.append(row)

        if duplicates:
            message = f"removed duplicated rows: {duplicates}"
            issues.append(ValidationIssue(IssueSeverity.WARNING, "DUPLICATES_REMOVED", message))
            logger.warning(message)

        return deduped

    def _check_ohlc_integrity(
        self,
        rows: list[dict[str, Any]],
        issues: list[ValidationIssue],
    ) -> None:
        for idx, row in enumerate(rows):
            low = float(row["low"])
            high = float(row["high"])
            open_price = float(row["open"])
            close_price = float(row["close"])
            volume = float(row["volume"])

            if low > high:
                issues.append(
                    ValidationIssue(
                        IssueSeverity.CRITICAL,
                        "OHLC_LOW_GT_HIGH",
                        f"row[{idx}] low > high at {row['timestamp'].isoformat()}",
                    )
                )
            if not (low <= open_price <= high):
                issues.append(
                    ValidationIssue(
                        IssueSeverity.CRITICAL,
                        "OHLC_OPEN_OUT_OF_RANGE",
                        f"row[{idx}] open outside [low, high] at {row['timestamp'].isoformat()}",
                    )
                )
            if not (low <= close_price <= high):
                issues.append(
                    ValidationIssue(
                        IssueSeverity.CRITICAL,
                        "OHLC_CLOSE_OUT_OF_RANGE",
                        f"row[{idx}] close outside [low, high] at {row['timestamp'].isoformat()}",
                    )
                )
            if volume < 0:
                issues.append(
                    ValidationIssue(
                        IssueSeverity.CRITICAL,
                        "VOLUME_NEGATIVE",
                        f"row[{idx}] negative volume at {row['timestamp'].isoformat()}",
                    )
                )

    def _check_internal_continuity(
        self,
        rows: list[dict[str, Any]],
        issues: list[ValidationIssue],
    ) -> None:
        if len(rows) < 2:
            return

        timeframe_delta = _timeframe_to_delta(str(rows[0].get("timeframe", "")))
        if timeframe_delta is None or timeframe_delta <= timedelta(0):
            return

        for previous, current in zip(rows, rows[1:]):
            actual_delta = current["timestamp"] - previous["timestamp"]
            if actual_delta <= timeframe_delta:
                continue

            missing_steps = int(actual_delta / timeframe_delta) - 1
            if missing_steps <= 0:
                continue

            severity = (
                IssueSeverity.WARNING
                if missing_steps > self._tolerated_missing_candles
                else IssueSeverity.INFO
            )
            code = (
                "CONTINUITY_GAP_EXCESSIVE"
                if severity == IssueSeverity.WARNING
                else "CONTINUITY_GAP_TOLERATED"
            )
            message = (
                f"gap between {previous['timestamp'].isoformat()} and {current['timestamp'].isoformat()} "
                f"missing_candles={missing_steps}"
            )
            issues.append(ValidationIssue(severity, code, message))

    def _check_coverage(
        self,
        rows: list[dict[str, Any]],
        requested_range: Interval,
        issues: list[ValidationIssue],
    ) -> None:
        if not rows:
            message = "no rows available after normalization/deduplication"
            issues.append(ValidationIssue(IssueSeverity.CRITICAL, "COVERAGE_EMPTY", message))
            logger.error(message)
            return

        first_ts = rows[0]["timestamp"]
        last_ts = rows[-1]["timestamp"]
        effective_start = first_ts
        effective_end = last_ts
        timeframe_delta = _timeframe_to_delta(str(rows[0].get("timeframe", "")))
        if timeframe_delta is not None:
            effective_start = first_ts - timeframe_delta
            effective_end = last_ts + timeframe_delta

        if effective_start > requested_range.start or effective_end < requested_range.end:
            message = (
                "batch does not fully cover requested range "
                f"[{requested_range.start.isoformat()} - {requested_range.end.isoformat()}] "
                f"(actual [{first_ts.isoformat()} - {last_ts.isoformat()}], "
                f"effective_start={effective_start.isoformat()}, "
                f"effective_end={effective_end.isoformat()})"
            )
            issues.append(ValidationIssue(IssueSeverity.CRITICAL, "COVERAGE_INCOMPLETE", message))
            logger.error(message)


class FundingBatchValidator:
    """Validate locally stored funding-rate parquet batches."""

    def __init__(
        self,
        *,
        gap_warning_hours: float = 12.0,
        gap_critical_hours: float = 24.0,
        plausible_rate_limit: float = 0.05,
    ) -> None:
        self._gap_warning = timedelta(hours=float(gap_warning_hours))
        self._gap_critical = timedelta(hours=float(gap_critical_hours))
        self._plausible_rate_limit = abs(float(plausible_rate_limit))

    def validate(
        self,
        symbol: str,
        parquet_paths: list[Path],
        interval: Interval,
        expected_period_hours: float = 8.0,
        gap_warning_hours: float | None = None,
        gap_critical_hours: float | None = None,
    ) -> ValidationResult:
        issues: list[ValidationIssue] = []
        raw_rows = self._load_rows(parquet_paths, issues)
        normalized = self._normalize_rows(raw_rows, symbol=symbol, issues=issues)
        ordered = self._check_and_sort_monotonic(normalized, issues=issues)
        deduped = self._deduplicate(ordered, issues=issues)
        self._check_rate_ranges(deduped, issues=issues)
        self._check_gap_windows(
            deduped,
            interval=interval,
            issues=issues,
            expected_period=timedelta(hours=float(expected_period_hours)),
            gap_warning=self._resolve_gap_threshold(
                override_hours=gap_warning_hours,
                default=self._gap_warning,
            ),
            gap_critical=self._resolve_gap_threshold(
                override_hours=gap_critical_hours,
                default=self._gap_critical,
            ),
        )
        return ValidationResult(cleaned_rows=deduped, issues=issues)

    def _load_rows(
        self,
        parquet_paths: list[Path],
        issues: list[ValidationIssue],
    ) -> list[dict[str, Any]]:
        try:
            import pandas as pd
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "FundingBatchValidator requires pandas and pyarrow. "
                "Install with: pip install 'signal-chain-lab[analytics]'"
            ) from exc

        rows: list[dict[str, Any]] = []
        for path in sorted(parquet_paths):
            try:
                frame = pd.read_parquet(path)
            except Exception as exc:
                message = f"failed to read funding parquet {path}: {exc}"
                issues.append(ValidationIssue(IssueSeverity.CRITICAL, "PARQUET_READ_ERROR", message))
                logger.error(message)
                continue

            missing = FUNDING_EXPECTED_SCHEMA - set(frame.columns)
            if missing:
                message = f"{path} missing required columns: {sorted(missing)}"
                issues.append(ValidationIssue(IssueSeverity.CRITICAL, "SCHEMA_MISSING_FIELDS", message))
                logger.error(message)
                continue

            rows.extend(frame.to_dict(orient="records"))
        return rows

    def _normalize_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        symbol: str,
        issues: list[ValidationIssue],
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for idx, row in enumerate(rows):
            missing = FUNDING_EXPECTED_SCHEMA - set(row.keys())
            if missing:
                message = f"row[{idx}] missing fields: {sorted(missing)}"
                issues.append(ValidationIssue(IssueSeverity.CRITICAL, "SCHEMA_MISSING_FIELDS", message))
                logger.error(message)
                continue

            try:
                ts_utc = _as_datetime(row["ts_utc"])
                funding_rate = _as_float(row["funding_rate"])
            except ValueError as exc:
                message = f"row[{idx}] normalization error: {exc}"
                issues.append(ValidationIssue(IssueSeverity.CRITICAL, "SCHEMA_INVALID_VALUE", message))
                logger.error(message)
                continue

            if not math.isfinite(funding_rate):
                message = f"row[{idx}] funding_rate is not finite at {ts_utc.isoformat()}"
                issues.append(ValidationIssue(IssueSeverity.CRITICAL, "FUNDING_RATE_NOT_FINITE", message))
                logger.error(message)
                continue

            row_symbol = str(row["symbol"]).upper()
            if row_symbol != symbol.upper():
                logger.warning(
                    "Funding validator found symbol mismatch: requested=%s row_symbol=%s ts=%s",
                    symbol,
                    row_symbol,
                    ts_utc.isoformat(),
                )

            normalized.append(
                {
                    **row,
                    "ts_utc": ts_utc,
                    "symbol": row_symbol,
                    "funding_rate": funding_rate,
                }
            )
        return normalized

    def _check_and_sort_monotonic(
        self,
        rows: list[dict[str, Any]],
        *,
        issues: list[ValidationIssue],
    ) -> list[dict[str, Any]]:
        ordered = list(rows)
        for previous, current in zip(ordered, ordered[1:]):
            if current["ts_utc"] < previous["ts_utc"]:
                message = (
                    "funding timestamps are not monotonic: "
                    f"{previous['ts_utc'].isoformat()} -> {current['ts_utc'].isoformat()}"
                )
                issues.append(ValidationIssue(IssueSeverity.CRITICAL, "TIMESTAMP_NOT_MONOTONIC", message))
                logger.error(message)
                break
        return sorted(ordered, key=lambda item: item["ts_utc"])

    def _deduplicate(
        self,
        rows: list[dict[str, Any]],
        *,
        issues: list[ValidationIssue],
    ) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, datetime]] = set()
        duplicates = 0

        for row in rows:
            key = (str(row["symbol"]), row["ts_utc"])
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            deduped.append(row)

        if duplicates:
            message = f"duplicated funding events removed: {duplicates}"
            issues.append(ValidationIssue(IssueSeverity.WARNING, "DUPLICATE_TIMESTAMP", message))
            logger.warning(message)
        return deduped

    def _check_rate_ranges(
        self,
        rows: list[dict[str, Any]],
        *,
        issues: list[ValidationIssue],
    ) -> None:
        for idx, row in enumerate(rows):
            funding_rate = float(row["funding_rate"])
            if abs(funding_rate) > self._plausible_rate_limit:
                issues.append(
                    ValidationIssue(
                        IssueSeverity.WARNING,
                        "FUNDING_RATE_OUT_OF_RANGE",
                        (
                            f"row[{idx}] funding_rate={funding_rate:.10f} exceeds plausible range "
                            f"at {row['ts_utc'].isoformat()}"
                        ),
                    )
                )

    def _check_gap_windows(
        self,
        rows: list[dict[str, Any]],
        *,
        interval: Interval,
        issues: list[ValidationIssue],
        expected_period: timedelta,
        gap_warning: timedelta,
        gap_critical: timedelta,
    ) -> None:
        if not rows:
            message = "no funding rows available after normalization"
            issues.append(ValidationIssue(IssueSeverity.CRITICAL, "COVERAGE_EMPTY", message))
            logger.error(message)
            return

        checkpoints: list[tuple[datetime, datetime, str]] = []
        checkpoints.append((interval.start, rows[0]["ts_utc"], "range_start"))
        for previous, current in zip(rows, rows[1:]):
            checkpoints.append((previous["ts_utc"], current["ts_utc"], "between_events"))
        checkpoints.append((rows[-1]["ts_utc"], interval.end, "range_end"))

        for left, right, kind in checkpoints:
            delta = right - left
            if delta <= expected_period:
                continue
            if delta > gap_critical:
                severity = IssueSeverity.CRITICAL
                code = "FUNDING_GAP_CRITICAL"
            elif delta > gap_warning:
                severity = IssueSeverity.WARNING
                code = "FUNDING_GAP_WARNING"
            else:
                continue
            issues.append(
                ValidationIssue(
                    severity,
                    code,
                    (
                        f"{kind} gap {delta} exceeds expected funding cadence "
                        f"between {left.isoformat()} and {right.isoformat()}"
                    ),
                )
            )

    def _resolve_gap_threshold(
        self,
        *,
        override_hours: float | None,
        default: timedelta,
    ) -> timedelta:
        if override_hours is None:
            return default
        return timedelta(hours=float(override_hours))


def _as_datetime(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        dt = raw
    else:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _as_float(raw: Any) -> float:
    if isinstance(raw, (int, float)):
        return float(raw)
    value = str(raw).strip()
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"invalid numeric value: {raw}") from exc


def _timeframe_to_delta(timeframe: str) -> timedelta | None:
    if not timeframe:
        return None
    unit = timeframe[-1:].lower()
    value = timeframe[:-1]
    if not value.isdigit():
        return None
    amount = int(value)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    return None
