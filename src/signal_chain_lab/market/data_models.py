"""Market data models: OHLCV bars and tick data structures."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel


class Candle(BaseModel):
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: datetime
    symbol: str
    timeframe: str


class MarketMetadata(BaseModel):
    symbol: str
    timeframe: str
    provider_name: str
    timezone: str = "UTC"
    start: datetime | None = None
    end: datetime | None = None


class MarketDataProvider(Protocol):
    def has_symbol(self, symbol: str) -> bool: ...

    def get_candle(self, symbol: str, timeframe: str, ts: datetime) -> Candle | None: ...

    def get_range(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Candle]: ...

    def get_intrabar_range(
        self,
        symbol: str,
        parent_timeframe: str,
        child_timeframe: str,
        ts: datetime,
    ) -> list[Candle]: ...

    def get_metadata(self, symbol: str, timeframe: str) -> MarketMetadata | None: ...
