"""Parquet market data provider: loads OHLCV data from parquet files."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from src.signal_chain_lab.market.data_models import Candle, MarketMetadata


class ParquetProvider:
    """Simple in-memory parquet OHLCV provider.

    Expects one file per symbol/timeframe: <symbol>__<timeframe>.parquet
    Required columns: timestamp, open, high, low, close, volume
    """

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self._data: dict[tuple[str, str], list[Candle]] = {}
        self._load_all()

    def _load_all(self) -> None:
        for path in self.root_dir.glob("*.parquet"):
            parts = path.stem.split("__")
            if len(parts) != 2:
                continue
            symbol, timeframe = parts
            self._data[(symbol, timeframe)] = self._load_file(path, symbol=symbol, timeframe=timeframe)

    def _load_file(self, path: Path, *, symbol: str, timeframe: str) -> list[Candle]:
        try:
            import pandas as pd
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional extras
            raise RuntimeError("ParquetProvider requires pandas and pyarrow dependencies") from exc

        dataframe = pd.read_parquet(path)
        candles = [
            Candle(
                timestamp=self._as_datetime(record["timestamp"]),
                open=float(record["open"]),
                high=float(record["high"]),
                low=float(record["low"]),
                close=float(record["close"]),
                volume=float(record.get("volume", 0.0)),
                symbol=symbol,
                timeframe=timeframe,
            )
            for record in dataframe.to_dict(orient="records")
        ]
        candles.sort(key=lambda item: item.timestamp)
        return candles

    @staticmethod
    def _as_datetime(value: object) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

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
        parent_delta = self._timeframe_to_delta(parent_timeframe)
        if parent_delta is None:
            return [candle for candle in self._data.get((symbol, child_timeframe), []) if candle.timestamp >= ts]

        upper_bound = ts + parent_delta
        return [
            candle
            for candle in self._data.get((symbol, child_timeframe), [])
            if ts <= candle.timestamp < upper_bound
        ]

    def get_metadata(self, symbol: str, timeframe: str) -> MarketMetadata | None:
        candles = self._data.get((symbol, timeframe), [])
        if not candles:
            return None
        return MarketMetadata(
            symbol=symbol,
            timeframe=timeframe,
            provider_name="parquet",
            start=candles[0].timestamp,
            end=candles[-1].timestamp,
        )

    @staticmethod
    def _timeframe_to_delta(timeframe: str) -> timedelta | None:
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
