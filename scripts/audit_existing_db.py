"""Audit the existing source database before running the adapter and simulator.

Prints a structured summary of:
- raw_messages: counts by processing_status and trader
- parse_results: counts by message_type and trader
- operational_signals: counts by message_type, blocked status
- chain readiness: NEW_SIGNAL rows with entry+SL+TP present
- messages in review queue

Usage:
    python scripts/audit_existing_db.py [--db PATH]
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

from dotenv import load_dotenv

load_dotenv()


def _section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def audit(db_path: str) -> None:
    print(f"DB: {db_path}")

    with sqlite3.connect(db_path) as c:
        c.row_factory = sqlite3.Row

        # --- raw_messages ---
        _section("raw_messages — by processing_status")
        for r in c.execute(
            "SELECT processing_status, COUNT(*) AS n FROM raw_messages GROUP BY processing_status ORDER BY n DESC"
        ):
            print(f"  {r['processing_status']:20s}  {r['n']}")

        _section("raw_messages — by source_trader_id")
        for r in c.execute(
            "SELECT source_trader_id, COUNT(*) AS n FROM raw_messages GROUP BY source_trader_id ORDER BY n DESC"
        ):
            print(f"  {str(r['source_trader_id']):20s}  {r['n']}")

        # --- parse_results ---
        _section("parse_results — by message_type")
        for r in c.execute(
            "SELECT message_type, COUNT(*) AS n FROM parse_results GROUP BY message_type ORDER BY n DESC"
        ):
            print(f"  {str(r['message_type']):20s}  {r['n']}")

        # --- operational_signals ---
        try:
            _section("operational_signals — by message_type / is_blocked")
            for r in c.execute(
                "SELECT message_type, is_blocked, COUNT(*) AS n FROM operational_signals "
                "GROUP BY message_type, is_blocked ORDER BY message_type, is_blocked"
            ):
                blocked = "BLOCKED" if r["is_blocked"] else "ok"
                print(f"  {str(r['message_type']):20s}  {blocked:10s}  {r['n']}")

            _section("operational_signals — NEW_SIGNAL chain readiness")
            total = c.execute(
                "SELECT COUNT(*) FROM operational_signals WHERE message_type='NEW_SIGNAL'"
            ).fetchone()[0]
            # Check signals table for symbol+side
            try:
                with_symbol = c.execute(
                    "SELECT COUNT(*) FROM operational_signals os "
                    "JOIN signals s ON s.attempt_key = os.attempt_key "
                    "WHERE os.message_type='NEW_SIGNAL' AND s.symbol IS NOT NULL AND s.side IS NOT NULL"
                ).fetchone()[0]
            except sqlite3.OperationalError:
                with_symbol = "N/A (signals table missing)"
            print(f"  Total NEW_SIGNAL:          {total}")
            print(f"  With symbol+side resolved: {with_symbol}")
        except sqlite3.OperationalError as e:
            print(f"  (operational_signals not available: {e})")

        # --- review queue ---
        _section("review_queue — messages pending review")
        try:
            rows = c.execute(
                """
                SELECT rm.raw_message_id, rm.telegram_message_id, rm.source_trader_id,
                       rm.reply_to_message_id, rq.reason, rm.raw_text
                FROM raw_messages rm
                JOIN review_queue rq ON rq.raw_message_id = rm.raw_message_id
                WHERE rm.processing_status = 'review'
                ORDER BY rm.raw_message_id
                LIMIT 20
                """
            ).fetchall()
            if not rows:
                print("  (none)")
            for r in rows:
                print(
                    f"\n  [id={r['raw_message_id']} tg_msg={r['telegram_message_id']} "
                    f"trader={r['source_trader_id']} reply_to={r['reply_to_message_id']} "
                    f"reason={r['reason']}]"
                )
                text = (r["raw_text"] or "")[:200]
                print(f"  {text}")
        except sqlite3.OperationalError as e:
            print(f"  (review_queue not available: {e})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit existing source database")
    parser.add_argument(
        "--db",
        default=os.getenv("DATABASE_URL", "data/source.sqlite3").replace("sqlite:///", ""),
        help="Path to the SQLite database file",
    )
    args = parser.parse_args()
    audit(args.db)


if __name__ == "__main__":
    main()
