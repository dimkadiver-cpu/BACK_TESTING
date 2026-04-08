"""Incremental Bybit futures_linear OHLCV downloader (last + mark basis).

Storage layout
--------------
<market_dir>/bybit/futures_linear/<timeframe>/<SYMBOL>/YYYY-MM.<basis>.parquet

Each .parquet file contains one calendar-month of candles.

Atomic writes
-------------
New data is first written to a .tmp sibling file; the existing partition (if any)
is loaded, merged, deduplicated and sorted; then os.replace() atomically promotes
the .tmp to the final path.

Manifest
--------
ManifestStore is updated after every successful partition write.
Each download event is appended to download_log.json with a unique event_id.

Error handling
--------------
- Rate-limit (HTTP 429 / retCode 10006): exponential back-off, up to max_retries.
- Symbol not available on exchange: logged as warning; job status → "skipped".
- Other API / network errors after retries: logged; job status → "error".
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
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from src.signal_chain_lab.market.planning.gap_detection import Interval, detect_gaps
from src.signal_chain_lab.market.planning.manifest_store import (
    CoverageKey,
    CoverageRecord,
    ManifestStore,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BYBIT_BASE_URL = "https://api.bybit.com"

_BYBIT_ENDPOINT: dict[str, str] = {
    "last": "/v5/market/kline",
    "mark": "/v5/market/mark-price-kline",
}

# Bybit interval parameter name → timeframe label used in this project
_INTERVAL_MAP: dict[str, str] = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "2h": "120",
    "4h": "240",
    "6h": "360",
    "12h": "720",
    "1d": "D",
    "1w": "W",
    "1M": "M",
}

# Milliseconds per candle for numeric timeframes (used for chunk pagination)
_INTERVAL_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}

BYBIT_MAX_CANDLES_PER_REQUEST = 1000

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BybitAPIError(Exception):
    """Non-zero retCode from Bybit API."""

    def __init__(self, ret_code: int, message: str) -> None:
        super().__init__(f"Bybit API error {ret_code}: {message}")
        self.ret_code = ret_code


class SymbolNotAvailableError(Exception):
    """Symbol is not listed or not active on Bybit for the requested market."""

    def __init__(self, symbol: str, detail: str = "") -> None:
        super().__init__(f"Symbol not available on Bybit: {symbol} — {detail}")
        self.symbol = symbol


class BybitRateLimitError(Exception):
    """Rate limit exhausted after all retries."""


# ---------------------------------------------------------------------------
# Client protocol (injectable for tests)
# ---------------------------------------------------------------------------


@runtime_checkable
class KlineClientProtocol(Protocol):
    """Minimal interface for a Bybit kline HTTP client."""

    def fetch(
        self,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
        basis: str,
        limit: int,
    ) -> list[list[str]]:
        """Return raw kline rows as lists of strings, newest-first (Bybit convention)."""
        ...


# ---------------------------------------------------------------------------
# Real HTTP client
# ---------------------------------------------------------------------------


class BybitKlineClient:
    """HTTP client for Bybit V5 kline endpoints with retry / back-off.

    Implements KlineClientProtocol.
    """

    def __init__(
        self,
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
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
        basis: str,
        limit: int = BYBIT_MAX_CANDLES_PER_REQUEST,
    ) -> list[list[str]]:
        if basis not in _BYBIT_ENDPOINT:
            raise ValueError(f"Unsupported basis '{basis}'; choose from {list(_BYBIT_ENDPOINT)}")

        endpoint = _BYBIT_ENDPOINT[basis]
        params: dict[str, str] = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "start": str(start_ms),
            "end": str(end_ms),
            "limit": str(limit),
        }
        url = f"{self._base_url}{endpoint}?{urllib.parse.urlencode(params)}"

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))

                ret_code: int = raw.get("retCode", -1)
                ret_msg: str = raw.get("retMsg", "")

                if ret_code == 10001 or "symbol" in ret_msg.lower() and "not exist" in ret_msg.lower():
                    raise SymbolNotAvailableError(symbol, ret_msg)
                if ret_code == 10006:  # rate limit
                    raise BybitRateLimitError(f"Rate limit: {ret_msg}")
                if ret_code != 0:
                    raise BybitAPIError(ret_code, ret_msg)

                return raw.get("result", {}).get("list", [])  # type: ignore[no-any-return]

            except (SymbolNotAvailableError, BybitAPIError):
                raise  # propagate non-retryable errors immediately

            except BybitRateLimitError as exc:
                last_exc = exc
                delay = self._retry_base_delay * (2**attempt)
                logger.warning(
                    "Rate limit on attempt %d/%d, retrying in %.1fs: %s",
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
                        "HTTP 429 on attempt %d/%d, retrying in %.1fs",
                        attempt + 1,
                        self._max_retries + 1,
                        delay,
                    )
                elif exc.code >= 500:
                    delay = self._retry_base_delay * (2**attempt)
                    logger.warning(
                        "HTTP %d on attempt %d/%d, retrying in %.1fs",
                        exc.code,
                        attempt + 1,
                        self._max_retries + 1,
                        delay,
                    )
                else:
                    raise  # 4xx (non-429) — don't retry

            except urllib.error.URLError as exc:
                last_exc = exc
                delay = self._retry_base_delay * (2**attempt)
                logger.warning(
                    "URLError on attempt %d/%d, retrying in %.1fs: %s",
                    attempt + 1,
                    self._max_retries + 1,
                    delay,
                    exc,
                )

            if attempt < self._max_retries:
                time.sleep(delay)  # type: ignore[possibly-undefined]

        raise BybitRateLimitError(f"All {self._max_retries + 1} attempts exhausted") from last_exc


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class SyncJobResult:
    symbol: str
    basis: str
    timeframe: str
    exchange: str = "bybit"
    market_type: str = "futures_linear"
    gaps_requested: list[Interval] = field(default_factory=list)
    intervals_downloaded: list[Interval] = field(default_factory=list)
    partitions_written: list[str] = field(default_factory=list)
    rows_downloaded: int = 0
    errors: list[str] = field(default_factory=list)
    status: str = "ok"  # "ok" | "partial" | "skipped" | "error"


# ---------------------------------------------------------------------------
# Main downloader
# ---------------------------------------------------------------------------


class BybitDownloader:
    """Incremental downloader for Bybit futures_linear OHLCV data.

    Usage example::

        store = ManifestStore(root=Path("data/market/manifests"))
        downloader = BybitDownloader(
            market_dir=Path("data/market"),
            manifest_store=store,
            timeframe="1m",
        )
        results = downloader.sync_symbol(
            symbol="BTCUSDT",
            required_intervals=planner_gaps,
        )
    """

    def __init__(
        self,
        market_dir: Path | str,
        manifest_store: ManifestStore,
        exchange: str = "bybit",
        market_type: str = "futures_linear",
        timeframe: str = "1m",
        bases: list[str] | None = None,
        client: KlineClientProtocol | None = None,
    ) -> None:
        self._market_dir = Path(market_dir)
        self._store = manifest_store
        self._exchange = exchange
        self._market_type = market_type
        self._timeframe = timeframe
        self._bases: list[str] = bases if bases is not None else ["last", "mark"]
        self._client: KlineClientProtocol = client or BybitKlineClient()

        if timeframe not in _INTERVAL_MAP:
            raise ValueError(
                f"Unsupported timeframe '{timeframe}'; supported: {list(_INTERVAL_MAP)}"
            )
        if timeframe not in _INTERVAL_MS:
            raise ValueError(
                f"Timeframe '{timeframe}' has no ms mapping; "
                "daily/weekly/monthly timeframes are not supported for incremental sync"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sync_gaps(
        self,
        symbol: str,
        gaps: list[Interval],
        bases: list[str] | None = None,
    ) -> list[SyncJobResult]:
        """Download pre-computed gap intervals for each basis.

        Args:
            symbol: e.g. "BTCUSDT"
            gaps: pre-computed gap intervals (from detect_gaps / planner)
            bases: override instance default bases; None → use instance default

        Returns:
            One SyncJobResult per basis.
        """
        actual_bases = bases if bases is not None else self._bases
        results: list[SyncJobResult] = []
        for basis in actual_bases:
            result = self._sync_gaps_for_basis(symbol=symbol, gaps=gaps, basis=basis)
            results.append(result)
        return results

    def sync_symbol(
        self,
        symbol: str,
        required_intervals: list[Interval],
        bases: list[str] | None = None,
    ) -> list[SyncJobResult]:
        """Detect gaps from manifest then sync only what is missing.

        Args:
            symbol: e.g. "BTCUSDT"
            required_intervals: full coverage required (from planner)
            bases: override instance default bases; None → use instance default

        Returns:
            One SyncJobResult per basis.
        """
        actual_bases = bases if bases is not None else self._bases
        results: list[SyncJobResult] = []
        for basis in actual_bases:
            covered = self._load_covered(symbol=symbol, basis=basis)
            gaps = detect_gaps(required=required_intervals, covered=covered)
            if not gaps:
                logger.info(
                    "Coverage complete for %s/%s/%s, no download needed",
                    symbol,
                    basis,
                    self._timeframe,
                )
                results.append(
                    SyncJobResult(
                        symbol=symbol,
                        basis=basis,
                        timeframe=self._timeframe,
                        exchange=self._exchange,
                        market_type=self._market_type,
                        gaps_requested=[],
                        status="skipped",
                    )
                )
                continue
            result = self._sync_gaps_for_basis(symbol=symbol, gaps=gaps, basis=basis)
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Internal orchestration
    # ------------------------------------------------------------------

    def _sync_gaps_for_basis(
        self,
        symbol: str,
        gaps: list[Interval],
        basis: str,
    ) -> SyncJobResult:
        result = SyncJobResult(
            symbol=symbol,
            basis=basis,
            timeframe=self._timeframe,
            exchange=self._exchange,
            market_type=self._market_type,
            gaps_requested=list(gaps),
        )

        for gap in gaps:
            try:
                rows = self._fetch_all_for_gap(symbol=symbol, gap=gap, basis=basis)
            except SymbolNotAvailableError as exc:
                msg = f"Symbol not available: {exc}"
                logger.warning("%s — skipping basis=%s", msg, basis)
                result.errors.append(msg)
                result.status = "skipped"
                self._store.append_download_event(
                    {
                        "event_id": str(uuid.uuid4()),
                        "exchange": self._exchange,
                        "market_type": self._market_type,
                        "timeframe": self._timeframe,
                        "symbol": symbol,
                        "basis": basis,
                        "gap_start": gap.start.isoformat(),
                        "gap_end": gap.end.isoformat(),
                        "status": "skipped",
                        "error": msg,
                    }
                )
                return result
            except Exception as exc:
                msg = f"Download error for gap {gap.start.isoformat()}/{gap.end.isoformat()}: {exc}"
                logger.error(msg)
                result.errors.append(msg)
                result.status = "error"
                self._store.append_download_event(
                    {
                        "event_id": str(uuid.uuid4()),
                        "exchange": self._exchange,
                        "market_type": self._market_type,
                        "timeframe": self._timeframe,
                        "symbol": symbol,
                        "basis": basis,
                        "gap_start": gap.start.isoformat(),
                        "gap_end": gap.end.isoformat(),
                        "status": "error",
                        "error": msg,
                    }
                )
                continue

            if not rows:
                logger.warning(
                    "No rows returned for %s/%s gap %s–%s",
                    symbol,
                    basis,
                    gap.start.isoformat(),
                    gap.end.isoformat(),
                )
                continue

            result.rows_downloaded += len(rows)
            result.intervals_downloaded.append(gap)

            # Write month partitions and update manifest
            written_partitions = self._write_month_partitions(
                symbol=symbol, rows=rows, basis=basis
            )
            result.partitions_written.extend(written_partitions)

            self._store.append_download_event(
                {
                    "event_id": str(uuid.uuid4()),
                    "exchange": self._exchange,
                    "market_type": self._market_type,
                    "timeframe": self._timeframe,
                    "symbol": symbol,
                    "basis": basis,
                    "gap_start": gap.start.isoformat(),
                    "gap_end": gap.end.isoformat(),
                    "rows": len(rows),
                    "partitions": written_partitions,
                    "status": "ok",
                }
            )

        if result.status == "ok" and result.errors:
            result.status = "partial"

        return result

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    def _fetch_all_for_gap(
        self,
        symbol: str,
        gap: Interval,
        basis: str,
    ) -> list[dict[str, Any]]:
        """Fetch all candles for the gap interval using chunk-based pagination."""
        interval_str = _INTERVAL_MAP[self._timeframe]
        interval_ms = _INTERVAL_MS[self._timeframe]

        start_ms = _dt_to_ms(gap.start)
        end_ms = _dt_to_ms(gap.end)

        chunk_ms = BYBIT_MAX_CANDLES_PER_REQUEST * interval_ms
        all_rows: list[dict[str, Any]] = []

        cursor_ms = start_ms
        while cursor_ms < end_ms:
            batch_end_ms = min(cursor_ms + chunk_ms, end_ms)

            raw_list = self._client.fetch(
                symbol=symbol,
                interval=interval_str,
                start_ms=cursor_ms,
                end_ms=batch_end_ms,
                basis=basis,
                limit=BYBIT_MAX_CANDLES_PER_REQUEST,
            )

            if raw_list:
                for item in raw_list:
                    parsed = _parse_kline_row(item, symbol=symbol, timeframe=self._timeframe)
                    if parsed is not None:
                        all_rows.append(parsed)

            # Advance cursor regardless of whether we got data (avoids infinite loop)
            cursor_ms = batch_end_ms + interval_ms

        return all_rows

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def _write_month_partitions(
        self,
        symbol: str,
        rows: list[dict[str, Any]],
        basis: str,
    ) -> list[str]:
        """Group rows by YYYY-MM, write each partition atomically, update manifest."""
        by_month: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            ts: datetime = row["timestamp"]
            month_key = ts.strftime("%Y-%m")
            by_month.setdefault(month_key, []).append(row)

        written: list[str] = []
        for month_key in sorted(by_month):
            month_rows = by_month[month_key]
            path = self._parquet_path(symbol=symbol, month_key=month_key, basis=basis)
            try:
                n_written = _atomic_write_parquet(path=path, new_rows=month_rows)
            except Exception as exc:
                logger.error(
                    "Failed to write partition %s: %s", path, exc
                )
                continue

            written.append(str(path))

            # Compute actual interval covered by this partition's rows.
            # cov_end extends one interval past the last candle's open timestamp
            # because a candle at T covers data through T + interval_duration.
            timestamps: list[datetime] = sorted(r["timestamp"] for r in month_rows)
            cov_start = timestamps[0]
            interval_td = timedelta(milliseconds=_INTERVAL_MS[self._timeframe])
            cov_end = timestamps[-1] + interval_td

            self._store.upsert_coverage(
                CoverageRecord(
                    key=CoverageKey(
                        exchange=self._exchange,
                        market_type=self._market_type,
                        timeframe=self._timeframe,
                        symbol=symbol,
                        basis=basis,
                    ),
                    covered_intervals=[Interval(start=cov_start, end=cov_end)],
                    validation_status="ok",
                    last_updated=datetime.now(tz=timezone.utc),
                )
            )
            logger.info(
                "Wrote %d rows → %s (%s rows total in file)", len(month_rows), path, n_written
            )

        return written

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parquet_path(self, symbol: str, month_key: str, basis: str) -> Path:
        return (
            self._market_dir
            / self._exchange
            / self._market_type
            / self._timeframe
            / symbol
            / f"{month_key}.{basis}.parquet"
        )

    def _load_covered(self, symbol: str, basis: str) -> list[Interval]:
        """Load covered intervals for (symbol, basis) from manifest."""
        key = CoverageKey(
            exchange=self._exchange,
            market_type=self._market_type,
            timeframe=self._timeframe,
            symbol=symbol,
            basis=basis,
        )
        for record in self._store.load_coverage_index():
            if record.key == key:
                return list(record.covered_intervals)
        return []


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _dt_to_ms(dt: datetime) -> int:
    """Convert a timezone-aware datetime to milliseconds since epoch."""
    return int(dt.timestamp() * 1000)


def _parse_kline_row(
    item: list[str],
    symbol: str,
    timeframe: str,
) -> dict[str, Any] | None:
    """Parse a single Bybit kline list item into a candle dict."""
    if not item:
        return None
    try:
        ts_ms = int(item[0])
        ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        return {
            "timestamp": ts,
            "open": float(item[1]),
            "high": float(item[2]),
            "low": float(item[3]),
            "close": float(item[4]),
            # mark-price kline has no volume (5 fields); last has volume at index 5
            "volume": float(item[5]) if len(item) > 5 else 0.0,
            "symbol": symbol,
            "timeframe": timeframe,
        }
    except (IndexError, ValueError) as exc:
        logger.warning("Could not parse kline item %s: %s", item, exc)
        return None


def _atomic_write_parquet(path: Path, new_rows: list[dict[str, Any]]) -> int:
    """Merge new_rows with existing parquet partition, dedup/sort, write atomically.

    Uses os.replace() for cross-platform atomic promotion of .tmp → final.

    Returns total number of rows in the resulting file.
    """
    try:
        import pandas as pd
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "BybitDownloader requires pandas and pyarrow. "
            "Install with: pip install 'signal-chain-lab[analytics]'"
        ) from exc

    new_df = pd.DataFrame(new_rows)

    if path.exists():
        existing_df = pd.read_parquet(path)
        combined = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        combined = new_df.copy()
        path.parent.mkdir(parents=True, exist_ok=True)

    # Normalise timestamp column to tz-aware UTC
    if not pd.api.types.is_datetime64_any_dtype(combined["timestamp"]):
        combined["timestamp"] = pd.to_datetime(combined["timestamp"], utc=True)
    elif combined["timestamp"].dt.tz is None:
        combined["timestamp"] = combined["timestamp"].dt.tz_localize("UTC")
    else:
        combined["timestamp"] = combined["timestamp"].dt.tz_convert("UTC")

    # Deduplicate and sort
    combined = (
        combined
        .drop_duplicates(subset=["timestamp", "symbol", "timeframe"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    tmp_path = path.with_suffix(".parquet.tmp")
    combined.to_parquet(tmp_path, index=False)
    os.replace(str(tmp_path), str(path))

    return len(combined)
