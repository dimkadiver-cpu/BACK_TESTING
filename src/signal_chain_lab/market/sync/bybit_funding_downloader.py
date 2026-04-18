"""Incremental Bybit funding-rate downloader.

Storage layout
--------------
<market_dir>/bybit/futures_linear/funding/<SYMBOL>/YYYY-MM.funding.parquet

Each parquet file contains one calendar month of funding events.

Manifest
--------
ManifestStore coverage is updated with timeframe="funding" after every
successful partition write. Coverage intervals represent downloaded request
windows, not the discrete event timestamps, so the sync can remain incremental.

Error handling
--------------
- Rate-limit (HTTP 429 / retCode 10006): exponential back-off, up to max_retries.
- Symbol not available on exchange: logged as warning; job status -> "skipped".
- Other API / network errors after retries: logged; job status -> "error".
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from src.signal_chain_lab.market.planning.gap_detection import Interval, detect_gaps
from src.signal_chain_lab.market.planning.manifest_store import (
    CoverageKey,
    CoverageRecord,
    ManifestStore,
)

logger = logging.getLogger(__name__)

BYBIT_BASE_URL = "https://api.bybit.com"
BYBIT_FUNDING_ENDPOINT = "/v5/market/funding/history"
BYBIT_MAX_EVENTS_PER_REQUEST = 200


class BybitAPIError(Exception):
    """Non-zero retCode from Bybit API."""

    def __init__(self, ret_code: int, message: str) -> None:
        super().__init__(f"Bybit API error {ret_code}: {message}")
        self.ret_code = ret_code


class SymbolNotAvailableError(Exception):
    """Symbol is not listed or not active on Bybit for the requested market."""

    def __init__(self, symbol: str, detail: str = "") -> None:
        super().__init__(f"Symbol not available on Bybit: {symbol} - {detail}")
        self.symbol = symbol


class BybitRateLimitError(Exception):
    """Rate limit exhausted after all retries."""


@runtime_checkable
class FundingClientProtocol(Protocol):
    def fetch(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        limit: int = BYBIT_MAX_EVENTS_PER_REQUEST,
    ) -> list[dict[str, Any]]:
        """Return raw funding rows from Bybit, newest-first."""
        ...


class BybitFundingClient:
    """HTTP client for Bybit V5 funding-history endpoint with retry / back-off."""

    def __init__(
        self,
        *,
        base_url: str = BYBIT_BASE_URL,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        request_timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._timeout = request_timeout

    def fetch(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        limit: int = BYBIT_MAX_EVENTS_PER_REQUEST,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {
            "category": "linear",
            "symbol": symbol,
            "startTime": str(start_ms),
            "endTime": str(end_ms),
            "limit": str(limit),
        }
        url = f"{self._base_url}{BYBIT_FUNDING_ENDPOINT}?{urllib.parse.urlencode(params)}"

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))

                ret_code = int(raw.get("retCode", -1))
                ret_msg = str(raw.get("retMsg", ""))

                if ret_code == 10001 or ("symbol" in ret_msg.lower() and "not exist" in ret_msg.lower()):
                    raise SymbolNotAvailableError(symbol, ret_msg)
                if ret_code == 10006:
                    raise BybitRateLimitError(f"Rate limit: {ret_msg}")
                if ret_code != 0:
                    raise BybitAPIError(ret_code, ret_msg)

                result = raw.get("result", {})
                items = result.get("list", [])
                return list(items) if isinstance(items, list) else []

            except (SymbolNotAvailableError, BybitAPIError):
                raise
            except BybitRateLimitError as exc:
                last_exc = exc
                delay = self._retry_base_delay * (2**attempt)
                logger.warning(
                    "Funding rate-limit on attempt %d/%d, retrying in %.1fs: %s",
                    attempt + 1,
                    self._max_retries + 1,
                    delay,
                    exc,
                )
            except urllib.error.HTTPError as exc:
                last_exc = exc
                if exc.code == 429:
                    delay = self._retry_base_delay * (2**attempt)
                    logger.warning(
                        "Funding HTTP 429 on attempt %d/%d, retrying in %.1fs",
                        attempt + 1,
                        self._max_retries + 1,
                        delay,
                    )
                elif exc.code >= 500:
                    delay = self._retry_base_delay * (2**attempt)
                    logger.warning(
                        "Funding HTTP %d on attempt %d/%d, retrying in %.1fs",
                        exc.code,
                        attempt + 1,
                        self._max_retries + 1,
                        delay,
                    )
                else:
                    raise
            except urllib.error.URLError as exc:
                last_exc = exc
                delay = self._retry_base_delay * (2**attempt)
                logger.warning(
                    "Funding URLError on attempt %d/%d, retrying in %.1fs: %s",
                    attempt + 1,
                    self._max_retries + 1,
                    delay,
                    exc,
                )

            if attempt < self._max_retries:
                time.sleep(delay)  # type: ignore[possibly-undefined]

        raise BybitRateLimitError(f"All {self._max_retries + 1} attempts exhausted") from last_exc


@dataclass(frozen=True, slots=True)
class FundingDownloadJob:
    symbol: str
    start_time: datetime
    end_time: datetime


@dataclass(slots=True)
class FundingDownloadResult:
    symbol: str
    status: Literal["ok", "skipped", "error"]
    events_downloaded: int
    intervals_written: list[Interval]
    error_message: str | None = None


class BybitFundingDownloader:
    """Incremental downloader for Bybit futures linear funding history."""

    def __init__(
        self,
        market_dir: Path | str,
        *,
        manifest_store: ManifestStore | None = None,
        base_url: str = BYBIT_BASE_URL,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        client: FundingClientProtocol | None = None,
    ) -> None:
        self._market_dir = Path(market_dir)
        self._store = manifest_store or ManifestStore(root=self._market_dir / "manifests")
        self._exchange = "bybit"
        self._market_type = "futures_linear"
        self._timeframe = "funding"
        self._client = client or BybitFundingClient(
            base_url=base_url,
            max_retries=max_retries,
            retry_base_delay=backoff_base,
        )

    def download(self, jobs: list[FundingDownloadJob]) -> list[FundingDownloadResult]:
        results: list[FundingDownloadResult] = []
        for job in jobs:
            results.append(self._download_job(job))
        return results

    def _download_job(self, job: FundingDownloadJob) -> FundingDownloadResult:
        requested = Interval(
            start=_ensure_utc(job.start_time),
            end=_ensure_utc(job.end_time),
        )
        covered = self._load_covered(job.symbol)
        gaps = detect_gaps(required=[requested], covered=covered)
        if not gaps:
            return FundingDownloadResult(
                symbol=job.symbol,
                status="skipped",
                events_downloaded=0,
                intervals_written=[],
            )

        total_events = 0
        intervals_written: list[Interval] = []

        for gap in gaps:
            try:
                rows = self._fetch_all_for_gap(symbol=job.symbol, gap=gap)
            except SymbolNotAvailableError as exc:
                message = str(exc)
                logger.warning(message)
                self._store.append_download_event(
                    {
                        "event_id": str(uuid.uuid4()),
                        "exchange": self._exchange,
                        "market_type": self._market_type,
                        "timeframe": self._timeframe,
                        "symbol": job.symbol,
                        "gap_start": gap.start.isoformat(),
                        "gap_end": gap.end.isoformat(),
                        "status": "skipped",
                        "error": message,
                    }
                )
                return FundingDownloadResult(
                    symbol=job.symbol,
                    status="skipped",
                    events_downloaded=0,
                    intervals_written=[],
                    error_message=message,
                )
            except Exception as exc:
                message = (
                    f"Funding download error for {job.symbol} "
                    f"{gap.start.isoformat()}/{gap.end.isoformat()}: {exc}"
                )
                logger.error(message)
                self._store.append_download_event(
                    {
                        "event_id": str(uuid.uuid4()),
                        "exchange": self._exchange,
                        "market_type": self._market_type,
                        "timeframe": self._timeframe,
                        "symbol": job.symbol,
                        "gap_start": gap.start.isoformat(),
                        "gap_end": gap.end.isoformat(),
                        "status": "error",
                        "error": message,
                    }
                )
                return FundingDownloadResult(
                    symbol=job.symbol,
                    status="error",
                    events_downloaded=total_events,
                    intervals_written=intervals_written,
                    error_message=message,
                )

            if not rows:
                logger.warning(
                    "No funding rows returned for %s in %s - %s",
                    job.symbol,
                    gap.start.isoformat(),
                    gap.end.isoformat(),
                )
                continue

            written_intervals = self._write_month_partitions(
                symbol=job.symbol,
                rows=rows,
                requested_gap=gap,
            )
            total_events += len(rows)
            intervals_written.extend(written_intervals)
            self._store.append_download_event(
                {
                    "event_id": str(uuid.uuid4()),
                    "exchange": self._exchange,
                    "market_type": self._market_type,
                    "timeframe": self._timeframe,
                    "symbol": job.symbol,
                    "gap_start": gap.start.isoformat(),
                    "gap_end": gap.end.isoformat(),
                    "events": len(rows),
                    "status": "ok",
                }
            )

        status: Literal["ok", "skipped", "error"] = "ok" if intervals_written else "skipped"
        return FundingDownloadResult(
            symbol=job.symbol,
            status=status,
            events_downloaded=total_events,
            intervals_written=intervals_written,
        )

    def _fetch_all_for_gap(self, *, symbol: str, gap: Interval) -> list[dict[str, Any]]:
        start_ms = _dt_to_ms(gap.start)
        end_ms = _dt_to_ms(gap.end)
        cursor_end_ms = end_ms
        all_rows: list[dict[str, Any]] = []
        seen_timestamps: set[int] = set()

        while cursor_end_ms >= start_ms:
            batch = self._client.fetch(
                symbol=symbol,
                start_ms=start_ms,
                end_ms=cursor_end_ms,
                limit=BYBIT_MAX_EVENTS_PER_REQUEST,
            )
            if not batch:
                break

            oldest_ts_ms: int | None = None
            for item in batch:
                parsed = _parse_funding_row(item, symbol=symbol)
                if parsed is None:
                    continue
                ts_ms = _dt_to_ms(parsed["ts_utc"])
                if ts_ms < start_ms or ts_ms > end_ms:
                    continue
                if ts_ms in seen_timestamps:
                    continue
                seen_timestamps.add(ts_ms)
                all_rows.append(parsed)
                if oldest_ts_ms is None or ts_ms < oldest_ts_ms:
                    oldest_ts_ms = ts_ms

            if oldest_ts_ms is None:
                break
            if oldest_ts_ms <= start_ms:
                break
            if len(batch) < BYBIT_MAX_EVENTS_PER_REQUEST:
                break
            cursor_end_ms = oldest_ts_ms - 1

        all_rows.sort(key=lambda row: row["ts_utc"])
        return all_rows

    def _write_month_partitions(
        self,
        *,
        symbol: str,
        rows: list[dict[str, Any]],
        requested_gap: Interval,
    ) -> list[Interval]:
        by_month: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            month_key = row["ts_utc"].strftime("%Y-%m")
            by_month.setdefault(month_key, []).append(row)

        written_intervals: list[Interval] = []
        for month_key in sorted(by_month):
            month_rows = by_month[month_key]
            path = self._parquet_path(symbol=symbol, month_key=month_key)
            _atomic_write_funding_parquet(path=path, new_rows=month_rows)

            partition_interval = _month_overlap_interval(month_key=month_key, requested=requested_gap)
            self._store.upsert_coverage(
                CoverageRecord(
                    key=CoverageKey(
                        exchange=self._exchange,
                        market_type=self._market_type,
                        timeframe=self._timeframe,
                        symbol=symbol,
                    ),
                    covered_intervals=[partition_interval],
                    validation_status="ok",
                    last_updated=datetime.now(tz=timezone.utc),
                )
            )
            written_intervals.append(partition_interval)
        return written_intervals

    def _parquet_path(self, *, symbol: str, month_key: str) -> Path:
        return (
            self._market_dir
            / self._exchange
            / self._market_type
            / self._timeframe
            / symbol
            / f"{month_key}.funding.parquet"
        )

    def _load_covered(self, symbol: str) -> list[Interval]:
        key = CoverageKey(
            exchange=self._exchange,
            market_type=self._market_type,
            timeframe=self._timeframe,
            symbol=symbol,
        )
        for record in self._store.load_coverage_index():
            if record.key == key:
                return list(record.covered_intervals)
        return []


def _dt_to_ms(dt: datetime) -> int:
    return int(_ensure_utc(dt).timestamp() * 1000)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_funding_row(item: dict[str, Any], *, symbol: str) -> dict[str, Any] | None:
    try:
        raw_symbol = str(item.get("symbol") or symbol)
        ts_ms = int(item["fundingRateTimestamp"])
        ts_utc = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        return {
            "ts_utc": ts_utc,
            "symbol": raw_symbol,
            "funding_rate": float(item["fundingRate"]),
            "source": "bybit",
            "schema_version": 1,
        }
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Could not parse funding item %s: %s", item, exc)
        return None


def _month_overlap_interval(*, month_key: str, requested: Interval) -> Interval:
    month_start = datetime.fromisoformat(f"{month_key}-01T00:00:00+00:00")
    if month_start.month == 12:
        month_end = datetime(month_start.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        month_end = datetime(month_start.year, month_start.month + 1, 1, tzinfo=timezone.utc)
    return Interval(start=max(requested.start, month_start), end=min(requested.end, month_end))


def _atomic_write_funding_parquet(path: Path, new_rows: list[dict[str, Any]]) -> int:
    try:
        import pandas as pd
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "BybitFundingDownloader requires pandas and pyarrow. "
            "Install with: pip install 'signal-chain-lab[analytics]'"
        ) from exc

    new_df = pd.DataFrame(new_rows)

    if path.exists():
        existing_df = pd.read_parquet(path)
        combined = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        combined = new_df.copy()
        path.parent.mkdir(parents=True, exist_ok=True)

    if not pd.api.types.is_datetime64_any_dtype(combined["ts_utc"]):
        combined["ts_utc"] = pd.to_datetime(combined["ts_utc"], utc=True)
    elif combined["ts_utc"].dt.tz is None:
        combined["ts_utc"] = combined["ts_utc"].dt.tz_localize("UTC")
    else:
        combined["ts_utc"] = combined["ts_utc"].dt.tz_convert("UTC")

    combined["symbol"] = combined["symbol"].astype(str)
    combined["funding_rate"] = combined["funding_rate"].astype(float)
    combined["source"] = combined["source"].astype(str)
    combined["schema_version"] = combined["schema_version"].astype(int)

    combined = (
        combined.drop_duplicates(subset=["ts_utc", "symbol"])
        .sort_values("ts_utc")
        .reset_index(drop=True)
    )

    tmp_path = path.with_suffix(".parquet.tmp")
    combined.to_parquet(tmp_path, index=False)
    os.replace(str(tmp_path), str(path))
    return len(combined)
