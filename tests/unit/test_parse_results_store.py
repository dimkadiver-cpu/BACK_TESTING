from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from src.signal_chain_lab.storage.parse_results import ParseResultRecord, ParseResultStore


def _make_db() -> Path:
    tmp = tempfile.NamedTemporaryFile(prefix="parse_results_", suffix=".sqlite3", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE parse_results (
                raw_message_id INTEGER PRIMARY KEY,
                eligibility_status TEXT,
                eligibility_reason TEXT,
                declared_trader_tag TEXT,
                resolved_trader_id TEXT,
                trader_resolution_method TEXT,
                message_type TEXT,
                parse_status TEXT,
                completeness TEXT,
                is_executable INTEGER,
                symbol TEXT,
                direction TEXT,
                entry_raw TEXT,
                stop_raw TEXT,
                target_raw_list TEXT,
                leverage_hint TEXT,
                risk_hint TEXT,
                risky_flag INTEGER,
                linkage_method TEXT,
                linkage_status TEXT,
                warning_text TEXT,
                notes TEXT,
                parse_result_normalized_json TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.commit()
    return db_path


def test_upsert_canonicalizes_normalized_json_and_direction() -> None:
    db_path = _make_db()
    try:
        store = ParseResultStore(str(db_path))
        store.upsert(
            ParseResultRecord(
                raw_message_id=1,
                eligibility_status="ok",
                eligibility_reason="ok",
                declared_trader_tag=None,
                resolved_trader_id="trader_a",
                trader_resolution_method="content_alias",
                message_type="NEW_SIGNAL",
                parse_status="PARSED",
                completeness="COMPLETE",
                is_executable=True,
                symbol="BTCUSDT",
                direction=None,
                entry_raw=None,
                stop_raw=None,
                target_raw_list=None,
                leverage_hint=None,
                risk_hint=None,
                risky_flag=False,
                linkage_method=None,
                linkage_status=None,
                warning_text=None,
                notes=None,
                parse_result_normalized_json=json.dumps(
                    {
                        "message_type": "NEW_SIGNAL",
                        "entities": {
                            "symbol": "BTCUSDT",
                            "side": "LONG",
                            "entry_type": "ZONE",
                            "entry_range_low": 100.0,
                            "entry_range_high": 101.0,
                            "stop_loss": 99.0,
                            "take_profits": [105.0],
                        },
                    }
                ),
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
            )
        )

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT direction, parse_result_normalized_json FROM parse_results WHERE raw_message_id = 1"
            ).fetchone()
        assert row is not None
        assert row[0] == "LONG"
        payload = json.loads(row[1])
        assert payload["direction"] == "LONG"
        assert payload["entities"]["direction"] == "LONG"
        assert payload["entities"]["entry_type"] == "LIMIT"
        assert payload["entities"]["entry_structure"] == "RANGE"
        assert payload["entities"]["entry_plan_entries"][0]["role"] == "RANGE_LOW"
        assert payload["entities"]["entry_range"] == [100.0, 101.0]
    finally:
        try:
            db_path.unlink(missing_ok=True)
        except PermissionError:
            pass
