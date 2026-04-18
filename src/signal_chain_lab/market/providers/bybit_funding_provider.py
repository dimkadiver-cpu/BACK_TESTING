"""Funding-rate provider over the Bybit monthly parquet storage layout."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import OrderedDict
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any

from src.signal_chain_lab.market.data_models import FundingEvent

logger = logging.getLogger(__name__)


def _as_utc_datetime(value: Any) -> datetime:
    """Coerce a parquet scalar to a UTC-aware datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    try:
        dt = value.to_pydatetime()
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except AttributeError:
        pass
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _month_key(ts: datetime) -> str:
    return _ensure_utc(ts).strftime("%Y-%m")


def _iter_month_keys(start: datetime, end: datetime) -> list[str]:
    current = _ensure_utc(start).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    limit = _ensure_utc(end).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    keys: list[str] = []
    while current <= limit:
        keys.append(current.strftime("%Y-%m"))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return keys


def _ensure_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


class NullFundingProvider:
    """No-op funding provider used when funding is disabled."""

    def get_funding_rate(self, symbol: str, ts: datetime) -> float | None:
        del symbol, ts
        return None

    def get_funding_events(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[FundingEvent]:
        del symbol, start, end
        return []


class BybitFundingProvider:
    """Implements FundingRateProvider reading local `.funding.parquet` files."""

    def __init__(
        self,
        market_dir: Path | str,
        symbol: str,
        *,
        exchange: str = "bybit",
        market_type: str = "futures_linear",
        cache_size: int = 12,
    ) -> None:
        self._root = Path(market_dir)
        self._symbol = symbol
        self._exchange = exchange
        self._market_type = market_type
        self._cache_size = max(1, cache_size)
        self._month_cache: OrderedDict[str, list[FundingEvent]] = OrderedDict()
        self._available_months: list[str] | None = None

    def get_funding_rate(self, symbol: str, ts: datetime) -> float | None:
        if symbol != self._symbol:
            return None

        target_ts = _ensure_utc(ts)
        month_key = _month_key(target_ts)
        candidate_months = [key for key in self._list_available_months() if key <= month_key]
        for candidate_month in reversed(candidate_months):
            events = self._load_month(candidate_month)
            if not events:
                continue
            timestamps = [event.funding_ts_utc for event in events]
            idx = bisect_right(timestamps, target_ts) - 1
            if idx >= 0:
                return events[idx].funding_rate
        return None

    def get_funding_events(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[FundingEvent]:
        if symbol != self._symbol:
            return []

        start_utc = _ensure_utc(start)
        end_utc = _ensure_utc(end)
        if end_utc < start_utc:
            return []

        events: list[FundingEvent] = []
        for month_key in _iter_month_keys(start_utc, end_utc):
            month_events = self._load_month(month_key)
            if not month_events:
                continue
            timestamps = [event.funding_ts_utc for event in month_events]
            left = bisect_left(timestamps, start_utc)
            right = bisect_right(timestamps, end_utc)
            events.extend(month_events[left:right])

        events.sort(key=lambda item: item.funding_ts_utc)
        return events

    def _symbol_dir(self) -> Path:
        return self._root / self._exchange / self._market_type / "funding" / self._symbol

    def _list_available_months(self) -> list[str]:
        if self._available_months is not None:
            return self._available_months

        symbol_dir = self._symbol_dir()
        if not symbol_dir.exists():
            self._available_months = []
            return self._available_months

        months = []
        for path in symbol_dir.glob("*.funding.parquet"):
            stem = path.name.removesuffix(".funding.parquet")
            if len(stem) == 7 and stem[4] == "-":
                months.append(stem)
        self._available_months = sorted(set(months))
        return self._available_months

    def _load_month(self, month_key: str) -> list[FundingEvent]:
        cached = self._month_cache.get(month_key)
        if cached is not None:
            self._month_cache.move_to_end(month_key)
            return cached

        path = self._symbol_dir() / f"{month_key}.funding.parquet"
        if not path.exists():
            self._remember_month(month_key, [])
            return []

        try:
            import pandas as pd
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "BybitFundingProvider requires pandas and pyarrow. "
                "Install with: pip install 'signal-chain-lab[analytics]'"
            ) from exc

        try:
            frame = pd.read_parquet(path)
        except Exception as exc:
            logger.warning("Failed to read funding parquet %s: %s", path, exc)
            self._remember_month(month_key, [])
            return []

        events: list[FundingEvent] = []
        for row in frame.to_dict(orient="records"):
            try:
                events.append(
                    FundingEvent(
                        symbol=str(row["symbol"]),
                        funding_ts_utc=_as_utc_datetime(row["ts_utc"]),
                        funding_rate=float(row["funding_rate"]),
                        source=str(row.get("source", "bybit")),
                        schema_version=int(row.get("schema_version", 1)),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipping malformed funding row in %s: %s", path, exc)

        events.sort(key=lambda item: item.funding_ts_utc)
        self._remember_month(month_key, events)
        return events

    def _remember_month(self, month_key: str, events: list[FundingEvent]) -> None:
        self._month_cache[month_key] = events
        self._month_cache.move_to_end(month_key)
        while len(self._month_cache) > self._cache_size:
            self._month_cache.popitem(last=False)
