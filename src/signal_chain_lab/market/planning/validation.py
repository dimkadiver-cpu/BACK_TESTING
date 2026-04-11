"""Minimal market-data batch validation (ordering, dedupe, schema, coverage)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationResult:
    cleaned_rows: list[dict[str, Any]] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)


class BatchValidator:
    """Validate and normalize downloaded candle batches."""

    def validate(self, rows: list[dict[str, Any]], requested_range: Interval) -> ValidationResult:
        issues: list[ValidationIssue] = []

        schema_ok_rows: list[dict[str, Any]] = []
        for idx, row in enumerate(rows):
            missing = EXPECTED_SCHEMA - set(row.keys())
            if missing:
                message = f"row[{idx}] missing fields: {sorted(missing)}"
                issues.append(ValidationIssue("error", "SCHEMA_MISSING_FIELDS", message))
                logger.error(message)
                continue
            schema_ok_rows.append({**row})

        normalized = self._normalize_and_sort(schema_ok_rows, issues)
        deduped = self._deduplicate(normalized, issues)
        self._check_coverage(deduped, requested_range, issues)

        return ValidationResult(cleaned_rows=deduped, issues=issues)

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
            except ValueError:
                parse_errors += 1
                message = f"row[{idx}] invalid timestamp: {row['timestamp']}"
                issues.append(ValidationIssue("error", "SCHEMA_INVALID_TIMESTAMP", message))
                logger.error(message)
                continue
            normalized.append({**row, "timestamp": parsed_ts})

        sorted_rows = sorted(normalized, key=lambda item: item["timestamp"])
        if sorted_rows != normalized:
            message = "input rows were not sorted by timestamp"
            issues.append(ValidationIssue("warning", "TIMESTAMP_UNSORTED", message))
            logger.warning(message)
        if parse_errors:
            logger.error("Timestamp parse errors: %s", parse_errors)
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
            issues.append(ValidationIssue("warning", "DUPLICATES_REMOVED", message))
            logger.warning(message)

        return deduped

    def _check_coverage(
        self,
        rows: list[dict[str, Any]],
        requested_range: Interval,
        issues: list[ValidationIssue],
    ) -> None:
        if not rows:
            message = "no rows available after normalization/deduplication"
            issues.append(ValidationIssue("error", "COVERAGE_EMPTY", message))
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
            issues.append(ValidationIssue("error", "COVERAGE_INCOMPLETE", message))
            logger.error(message)


def _as_datetime(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        return raw
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))


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
