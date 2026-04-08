"""Demand scanner for market-data planning based on signal chains in SQLite DB."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class DemandChain:
    """Minimum demand record derived from DB for a signal chain."""

    chain_id: str
    symbol: str
    timestamp_open: datetime
    timestamp_last_relevant_update: datetime | None
    chain_status: str

    def to_dict(self) -> dict[str, str | None]:
        """Return a deterministic JSON-safe representation."""
        return {
            "chain_id": self.chain_id,
            "symbol": self.symbol,
            "timestamp_open": self.timestamp_open.isoformat(),
            "timestamp_last_relevant_update": (
                self.timestamp_last_relevant_update.isoformat()
                if self.timestamp_last_relevant_update is not None
                else None
            ),
            "chain_status": self.chain_status,
        }


def _parse_ts(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class SignalDemandScanner:
    """Extract demand records for coverage planning from backtesting DB."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def scan(self) -> list[DemandChain]:
        """Return all demand chains sorted deterministically."""
        query = """
            SELECT
                s.attempt_key,
                UPPER(TRIM(s.symbol)) AS symbol,
                s.created_at AS timestamp_open,
                u.last_update_ts,
                s.status
            FROM signals s
            LEFT JOIN (
                SELECT
                    os.attempt_key AS attempt_key,
                    MAX(rm.message_ts) AS last_update_ts
                FROM operational_signals os
                JOIN parse_results pr ON pr.parse_result_id = os.parse_result_id
                JOIN raw_messages rm ON rm.raw_message_id = pr.raw_message_id
                WHERE os.message_type = 'UPDATE'
                  AND os.attempt_key IS NOT NULL
                GROUP BY os.attempt_key
            ) u ON u.attempt_key = s.attempt_key
            WHERE s.symbol IS NOT NULL
              AND TRIM(s.symbol) <> ''
            ORDER BY UPPER(TRIM(s.symbol)) ASC, s.created_at ASC, s.attempt_key ASC
        """

        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(query).fetchall()

        demand: list[DemandChain] = []
        for attempt_key, symbol, raw_open, raw_last_update, status in rows:
            demand.append(
                DemandChain(
                    chain_id=str(attempt_key),
                    symbol=str(symbol),
                    timestamp_open=_parse_ts(str(raw_open)),
                    timestamp_last_relevant_update=(
                        _parse_ts(str(raw_last_update)) if raw_last_update else None
                    ),
                    chain_status=str(status),
                )
            )
        return demand
