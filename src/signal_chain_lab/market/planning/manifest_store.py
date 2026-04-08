"""Local manifest persistence for incremental market data coverage.

JSON format (coverage_index.json)
---------------------------------
{
  "version": 1,
  "updated_at": "2026-04-08T12:00:00+00:00",
  "entries": [
    {
      "exchange": "bybit",
      "market_type": "futures_linear",
      "timeframe": "1m",
      "symbol": "BTCUSDT",
      "covered_intervals": [
        {"start": "2026-04-01T00:00:00+00:00", "end": "2026-04-01T12:00:00+00:00"}
      ],
      "validation_status": "ok",
      "last_updated": "2026-04-08T12:00:00+00:00"
    }
  ]
}

download_log.json and validation_log.json are append-only JSON documents with
"events" list. Persist operations are idempotent where possible:
- coverage intervals are normalized and merged before write
- duplicated events (same event_id) are ignored
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from src.signal_chain_lab.market.planning.gap_detection import Interval, merge_intervals

logger = logging.getLogger(__name__)

ValidationStatus = Literal["unknown", "ok", "warning", "error"]


@dataclass(frozen=True, slots=True)
class CoverageKey:
    exchange: str
    market_type: str
    timeframe: str
    symbol: str


@dataclass(frozen=True, slots=True)
class CoverageRecord:
    key: CoverageKey
    covered_intervals: list[Interval]
    validation_status: ValidationStatus
    last_updated: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.key.exchange,
            "market_type": self.key.market_type,
            "timeframe": self.key.timeframe,
            "symbol": self.key.symbol,
            "covered_intervals": [interval.to_dict() for interval in self.covered_intervals],
            "validation_status": self.validation_status,
            "last_updated": self.last_updated.isoformat(),
        }


class ManifestStore:
    """Persist and read market-data manifests under data/market/manifests/."""

    def __init__(self, root: Path | str = Path("data/market/manifests")) -> None:
        self._root = Path(root)
        self._coverage_path = self._root / "coverage_index.json"
        self._download_log_path = self._root / "download_log.json"
        self._validation_log_path = self._root / "validation_log.json"
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def coverage_path(self) -> Path:
        return self._coverage_path

    @property
    def download_log_path(self) -> Path:
        return self._download_log_path

    @property
    def validation_log_path(self) -> Path:
        return self._validation_log_path

    def load_coverage_index(self) -> list[CoverageRecord]:
        payload = self._read_json(self._coverage_path, fallback={"entries": []})
        records: list[CoverageRecord] = []
        for entry in payload.get("entries", []):
            records.append(
                CoverageRecord(
                    key=CoverageKey(
                        exchange=str(entry["exchange"]),
                        market_type=str(entry["market_type"]),
                        timeframe=str(entry["timeframe"]),
                        symbol=str(entry["symbol"]),
                    ),
                    covered_intervals=[Interval.from_dict(i) for i in entry.get("covered_intervals", [])],
                    validation_status=entry.get("validation_status", "unknown"),
                    last_updated=_parse_dt(entry.get("last_updated")),
                )
            )
        return records

    def upsert_coverage(self, record: CoverageRecord) -> None:
        records = self.load_coverage_index()
        normalized = CoverageRecord(
            key=record.key,
            covered_intervals=merge_intervals(record.covered_intervals),
            validation_status=record.validation_status,
            last_updated=record.last_updated,
        )

        updated = False
        for index, existing in enumerate(records):
            if existing.key == normalized.key:
                merged_intervals = merge_intervals(existing.covered_intervals + normalized.covered_intervals)
                records[index] = CoverageRecord(
                    key=existing.key,
                    covered_intervals=merged_intervals,
                    validation_status=normalized.validation_status,
                    last_updated=normalized.last_updated,
                )
                updated = True
                break

        if not updated:
            records.append(normalized)

        records = sorted(
            records,
            key=lambda item: (
                item.key.exchange,
                item.key.market_type,
                item.key.timeframe,
                item.key.symbol,
            ),
        )

        self._write_json(
            self._coverage_path,
            {
                "version": 1,
                "updated_at": _utc_now().isoformat(),
                "entries": [r.to_dict() for r in records],
            },
        )

    def append_download_event(self, event: dict[str, Any]) -> bool:
        return self._append_event(self._download_log_path, event)

    def append_validation_event(self, event: dict[str, Any]) -> bool:
        return self._append_event(self._validation_log_path, event)

    def _append_event(self, path: Path, event: dict[str, Any]) -> bool:
        if "event_id" not in event:
            logger.warning("Manifest event skipped: missing event_id (path=%s)", path)
            return False

        payload = self._read_json(path, fallback={"events": []})
        event_id = str(event["event_id"])
        if any(str(existing.get("event_id")) == event_id for existing in payload.get("events", [])):
            logger.warning("Duplicate manifest event ignored: event_id=%s path=%s", event_id, path)
            return False

        serializable = {**event}
        if "timestamp" not in serializable:
            serializable["timestamp"] = _utc_now().isoformat()

        payload.setdefault("events", []).append(serializable)
        self._write_json(path, payload)
        return True

    def _read_json(self, path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return fallback
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.error("Manifest JSON invalid, fallback used: %s", path)
            return fallback

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def _parse_dt(raw: str | None) -> datetime:
    if not raw:
        return _utc_now()
    dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)
