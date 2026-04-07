"""CSV market data provider: loads OHLCV data from CSV files."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from src.signal_chain_lab.market.data_models import Candle, MarketMetadata


class CSVProvider:
    """Simple in-memory CSV OHLCV provider.

    Expects one file per symbol/timeframe: <symbol>__<timeframe>.csv
    Required columns: timestamp,open,high,low,close,volume
    """

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self._data: dict[tuple[str, str], list[Candle]] = {}
        self._load_all()

    def _load_all(self) -> None:
        for path in self.root_dir.glob("*.csv"):
            parts = path.stem.split("__")
            if len(parts) != 2:
                continue
            symbol, timeframe = parts
            candles = self._load_file(path, symbol=symbol, timeframe=timeframe)
            self._data[(symbol, timeframe)] = candles

    def _load_file(self, path: Path, *, symbol: str, timeframe: str) -> list[Candle]:
        candles: list[Candle] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                candles.append(
                    Candle(
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume", 0.0)),
                        symbol=symbol,
                        timeframe=timeframe,
                    )
                )
        candles.sort(key=lambda item: item.timestamp)
        return candles

    def has_symbol(self, symbol: str) -> bool:
        return any(key_symbol == symbol for key_symbol, _ in self._data)

    def get_candle(self, symbol: str, timeframe: str, ts: datetime) -> Candle | None:
        for candle in self._data.get((symbol, timeframe), []):
            if candle.timestamp == ts:
                return candle
        return None

    def get_range(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Candle]:
        return [
            candle
            for candle in self._data.get((symbol, timeframe), [])
            if start <= candle.timestamp <= end
        ]

    def get_intrabar_range(
        self,
        symbol: str,
        parent_timeframe: str,
        child_timeframe: str,
        ts: datetime,
    ) -> list[Candle]:
        del parent_timeframe
        return [candle for candle in self._data.get((symbol, child_timeframe), []) if candle.timestamp >= ts]

    def get_metadata(self, symbol: str, timeframe: str) -> MarketMetadata | None:
        candles = self._data.get((symbol, timeframe), [])
        if not candles:
            return None
        return MarketMetadata(
            symbol=symbol,
            timeframe=timeframe,
            provider_name="csv",
            start=candles[0].timestamp,
            end=candles[-1].timestamp,
        )
