from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from src.signal_chain_lab.market.planning.coverage_planner import CoveragePlanner, PlannerConfig
from src.signal_chain_lab.market.planning.demand_scanner import DemandChain, SignalDemandScanner


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE signals (
            attempt_key TEXT PRIMARY KEY,
            symbol TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE parse_results (
            parse_result_id INTEGER PRIMARY KEY,
            raw_message_id INTEGER NOT NULL
        );

        CREATE TABLE raw_messages (
            raw_message_id INTEGER PRIMARY KEY,
            message_ts TEXT NOT NULL
        );

        CREATE TABLE operational_signals (
            op_signal_id INTEGER PRIMARY KEY,
            parse_result_id INTEGER NOT NULL,
            attempt_key TEXT,
            message_type TEXT NOT NULL
        );
        """
    )
    conn.commit()


def test_scanner_extracts_complete_chain(tmp_path) -> None:
    db_path = tmp_path / "scanner.sqlite3"
    with sqlite3.connect(db_path) as conn:
        _create_schema(conn)

        conn.execute(
            "INSERT INTO signals(attempt_key, symbol, status, created_at) VALUES (?, ?, ?, ?)",
            ("chain_1", "btcusdt", "CLOSED", "2026-04-01T10:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO raw_messages(raw_message_id, message_ts) VALUES (?, ?)",
            (100, "2026-04-01T18:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO parse_results(parse_result_id, raw_message_id) VALUES (?, ?)",
            (200, 100),
        )
        conn.execute(
            """
            INSERT INTO operational_signals(op_signal_id, parse_result_id, attempt_key, message_type)
            VALUES (?, ?, ?, ?)
            """,
            (300, 200, "chain_1", "UPDATE"),
        )
        conn.commit()

    records = SignalDemandScanner(str(db_path)).scan()

    assert len(records) == 1
    assert records[0].chain_id == "chain_1"
    assert records[0].symbol == "BTCUSDT"
    assert records[0].chain_status == "CLOSED"
    assert records[0].timestamp_open == datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
    assert records[0].timestamp_last_relevant_update == datetime(
        2026,
        4,
        1,
        18,
        0,
        tzinfo=timezone.utc,
    )


def test_planner_handles_incomplete_chain_with_unknown_class() -> None:
    chain = DemandChain(
        chain_id="chain_incomplete",
        symbol="ETHUSDT",
        timestamp_open=datetime(2026, 4, 2, 9, 0, tzinfo=timezone.utc),
        timestamp_last_relevant_update=None,
        chain_status="EXPIRED",
    )

    planner = CoveragePlanner(config=PlannerConfig())
    duration_class = planner.classify_duration(chain)
    plan = planner.plan([chain]).to_dict()

    assert duration_class == "unknown"
    assert plan["ETHUSDT"][0]["start"] == "2026-03-31T09:00:00+00:00"
    assert plan["ETHUSDT"][0]["end"] == "2026-04-30T09:00:00+00:00"


def test_planner_merges_adjacent_intervals_for_same_symbol() -> None:
    planner = CoveragePlanner(
        config=PlannerConfig(merge_threshold=timedelta(minutes=30))
    )

    chain_a = DemandChain(
        chain_id="a",
        symbol="BTCUSDT",
        timestamp_open=datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
        timestamp_last_relevant_update=datetime(2026, 4, 1, 1, 0, tzinfo=timezone.utc),
        chain_status="CLOSED",
    )
    chain_b = DemandChain(
        chain_id="b",
        symbol="BTCUSDT",
        timestamp_open=datetime(2026, 4, 1, 1, 10, tzinfo=timezone.utc),
        timestamp_last_relevant_update=datetime(2026, 4, 1, 2, 0, tzinfo=timezone.utc),
        chain_status="CLOSED",
    )

    plan = planner.plan([chain_a, chain_b]).to_dict()

    assert len(plan["BTCUSDT"]) == 1
    assert plan["BTCUSDT"][0]["start"] == "2026-03-31T00:00:00+00:00"
    assert plan["BTCUSDT"][0]["end"] == "2026-04-04T02:00:00+00:00"
