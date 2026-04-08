"""Market data provider that reads from the Bybit incremental parquet storage layout.

Storage layout expected (written by BybitDownloader / IE.6):
    <market_dir>/bybit/futures_linear/<timeframe>/<SYMBOL>/YYYY-MM.<basis>.parquet

Each monthly file has columns: timestamp, open, high, low, close, volume, symbol, timeframe.

Usage::

    provider = BybitParquetProvider(
        market_dir=Path("data/market"),
        timeframe="1m",
        basis="last",
    )
    candle = provider.get_candle("BTCUSDT", "1m", some_datetime)

Implements MarketDataProvider protocol (src.signal_chain_lab.market.data_models).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.signal_chain_lab.market.data_models import Candle, MarketDataProvider, MarketMetadata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _as_utc_datetime(value: Any) -> datetime:
    """Coerce a pandas Timestamp or ISO string to a UTC-aware datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    # pandas Timestamp or numpy datetime64
    try:
        # pandas Timestamp has .to_pydatetime()
        dt = value.to_pydatetime()
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except AttributeError:
        pass
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _timeframe_to_delta(timeframe: str) -> timedelta | None:
    """Convert '1m', '5m', '1h', '1d' etc. to a timedelta."""
    if not timeframe:
        return None
    unit = timeframe[-1:].lower()
    body = timeframe[:-1]
    if not body.isdigit():
        return None
    amount = int(body)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    return None


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class BybitParquetProvider:
    """Read-only provider over the Bybit incremental parquet storage layout.

    Data is loaded lazily per (symbol, timeframe) pair on first access and then
    kept in memory. This is intentional: backtest runs are expected to access the
    same symbol/timeframe repeatedly, and the dataset fits in RAM.

    Args:
        market_dir:   Root of the market data directory tree
                      (e.g. ``Path("data/market")``).
        exchange:     Exchange folder name (default: ``"bybit"``).
        market_type:  Market type folder (default: ``"futures_linear"``).
        timeframe:    Primary timeframe label, e.g. ``"1m"`` or ``"1h"``.
                      Used as the default when callers don't specify a timeframe.
        basis:        Price basis: ``"last"`` or ``"mark"``.
    """

    def __init__(
        self,
        market_dir: Path | str,
        exchange: str = "bybit",
        market_type: str = "futures_linear",
        timeframe: str = "1m",
        basis: str = "last",
    ) -> None:
        self._root = Path(market_dir)
        self._exchange = exchange
        self._market_type = market_type
        self._timeframe = timeframe
        self._basis = basis
        # cache: (symbol, timeframe) -> sorted list[Candle]
        self._cache: dict[tuple[str, str], list[Candle]] = {}

    # ------------------------------------------------------------------
    # MarketDataProvider interface
    # ------------------------------------------------------------------

    def has_symbol(self, symbol: str) -> bool:
        self._ensure_loaded(symbol, self._timeframe)
        return bool(self._cache.get((symbol, self._timeframe)))

    def get_candle(self, symbol: str, timeframe: str, ts: datetime) -> Candle | None:
        self._ensure_loaded(symbol, timeframe)
        candles = self._cache.get((symbol, timeframe), [])
        # Binary-search would be faster but list is sorted — linear scan is fine for MVP
        for candle in candles:
            if candle.timestamp == ts:
                return candle
        return None

    def get_range(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        self._ensure_loaded(symbol, timeframe)
        return [
            candle
            for candle in self._cache.get((symbol, timeframe), [])
            if start <= candle.timestamp <= end
        ]

    def get_intrabar_range(
        self,
        symbol: str,
        parent_timeframe: str,
        child_timeframe: str,
        ts: datetime,
    ) -> list[Candle]:
        """Return child-timeframe candles that fall within one parent candle at ts."""
        self._ensure_loaded(symbol, child_timeframe)
        parent_delta = _timeframe_to_delta(parent_timeframe)
        if parent_delta is None:
            return [
                candle
                for candle in self._cache.get((symbol, child_timeframe), [])
                if candle.timestamp >= ts
            ]
        upper = ts + parent_delta
        return [
            candle
            for candle in self._cache.get((symbol, child_timeframe), [])
            if ts <= candle.timestamp < upper
        ]

    def get_metadata(self, symbol: str, timeframe: str) -> MarketMetadata | None:
        self._ensure_loaded(symbol, timeframe)
        candles = self._cache.get((symbol, timeframe), [])
        if not candles:
            return None
        return MarketMetadata(
            symbol=symbol,
            timeframe=timeframe,
            provider_name=f"bybit_parquet/{self._basis}",
            timezone="UTC",
            start=candles[0].timestamp,
            end=candles[-1].timestamp,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _symbol_dir(self, symbol: str, timeframe: str) -> Path:
        return self._root / self._exchange / self._market_type / timeframe / symbol

    def _ensure_loaded(self, symbol: str, timeframe: str) -> None:
        key = (symbol, timeframe)
        if key in self._cache:
            return

        sym_dir = self._symbol_dir(symbol, timeframe)
        if not sym_dir.exists():
            logger.debug("No market data directory for %s/%s: %s", symbol, timeframe, sym_dir)
            self._cache[key] = []
            return

        parquet_files = sorted(sym_dir.glob(f"*.{self._basis}.parquet"))
        if not parquet_files:
            logger.warning(
                "No .%s.parquet files for %s/%s in %s", self._basis, symbol, timeframe, sym_dir
            )
            self._cache[key] = []
            return

        try:
            import pandas as pd
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "BybitParquetProvider requires pandas and pyarrow. "
                "Install with: pip install 'signal-chain-lab[analytics]'"
            ) from exc

        frames = []
        for path in parquet_files:
            try:
                frames.append(pd.read_parquet(path))
            except Exception as exc:
                logger.error("Failed to read parquet %s: %s", path, exc)

        if not frames:
            self._cache[key] = []
            return

        combined = pd.concat(frames, ignore_index=True)
        combined = (
            combined
            .drop_duplicates(subset=["timestamp"])
            .sort_values("timestamp")
            .reset_index(drop=True)
        )

        candles: list[Candle] = []
        for row in combined.to_dict(orient="records"):
            try:
                candles.append(
                    Candle(
                        timestamp=_as_utc_datetime(row["timestamp"]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume", 0.0)),
                        symbol=symbol,
                        timeframe=timeframe,
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("Skipping malformed row: %s — %s", row, exc)

        self._cache[key] = candles
        logger.info(
            "Loaded %d candles for %s/%s (basis=%s)", len(candles), symbol, timeframe, self._basis
        )
