from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.signal_chain_lab.core.migrations import apply_migrations
from src.signal_chain_lab.storage.operational_signals_store import (
    OperationalSignalRecord,
    OperationalSignalsStore,
)
from src.signal_chain_lab.storage.signals_store import SignalRecord, SignalsStore


@dataclass(slots=True)
class ParseResultView:
    parse_result_id: int
    raw_message_id: int
    source_chat_id: str
    telegram_message_id: int
    reply_to_message_id: int | None
    raw_text: str
    message_ts: str
    resolved_trader_id: str | None
    message_type: str
    completeness: str
    is_executable: bool
    symbol: str | None
    direction: str | None
    parse_result_normalized_json: str | None


@dataclass(slots=True)
class EngineSignal:
    parse_result: ParseResultView
    trader_id: str
    attempt_key: str | None
    is_blocked: bool
    block_reason: str | None
    risk_mode: str | None = None
    risk_pct_of_capital: float | None = None
    risk_usdt_fixed: float | None = None
    capital_base_usdt: float | None = None
    risk_budget_usdt: float | None = None
    sl_distance_pct: float | None = None
    position_size_usdt: float | None = None
    position_size_pct: float | None = None
    entry_split: dict[str, float] | None = None
    leverage: int | None = None
    risk_hint_used: bool = False
    management_rules: dict[str, Any] | None = None
    applied_rules: list[str] | None = None
    warnings: list[str] | None = None


@dataclass(slots=True)
class ResolvedTarget:
    position_ids: list[int]
    eligibility: str
    reason: str | None


@dataclass(slots=True)
class ReplayStats:
    total: int = 0
    new_signal_inserted: int = 0
    new_signal_blocked: int = 0
    update_linked: int = 0
    update_orphan: int = 0
    skipped_existing: int = 0
    errors: int = 0


class OperationRulesEngine:
    def apply(self, parse_result: ParseResultView, trader_id: str, *, db_path: str, **_: object) -> EngineSignal:
        payload = _normalized_payload(parse_result.parse_result_normalized_json)
        entities = payload.get("entities", {}) if isinstance(payload, dict) else {}

        if parse_result.message_type == "NEW_SIGNAL":
            if parse_result.completeness.upper() != "COMPLETE":
                return EngineSignal(
                    parse_result=parse_result,
                    trader_id=trader_id,
                    attempt_key=_build_attempt_key(parse_result, entities),
                    is_blocked=True,
                    block_reason="new_signal_incomplete",
                    applied_rules=["block_incomplete_new_signal"],
                )
            return EngineSignal(
                parse_result=parse_result,
                trader_id=trader_id,
                attempt_key=_build_attempt_key(parse_result, entities),
                is_blocked=False,
                block_reason=None,
                applied_rules=["accept_new_signal"],
            )

        return EngineSignal(
            parse_result=parse_result,
            trader_id=trader_id,
            attempt_key=None,
            is_blocked=False,
            block_reason=None,
            applied_rules=["accept_update"],
        )


class TargetResolver:
    def resolve(self, parse_result: ParseResultView, trader_id: str, *, db_path: str, **_: object) -> ResolvedTarget:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row

            if parse_result.reply_to_message_id is not None:
                row = conn.execute(
                    """
                    SELECT os.op_signal_id
                    FROM operational_signals os
                    JOIN parse_results pr ON pr.parse_result_id = os.parse_result_id
                    JOIN raw_messages rm ON rm.raw_message_id = pr.raw_message_id
                    WHERE os.message_type = 'NEW_SIGNAL'
                      AND os.trader_id = ?
                      AND rm.source_chat_id = ?
                      AND rm.telegram_message_id = ?
                    ORDER BY os.op_signal_id DESC
                    LIMIT 1
                    """,
                    (trader_id, parse_result.source_chat_id, parse_result.reply_to_message_id),
                ).fetchone()
                if row:
                    return ResolvedTarget(position_ids=[int(row["op_signal_id"])], eligibility="ELIGIBLE", reason=None)

            payload = _normalized_payload(parse_result.parse_result_normalized_json)
            signal_ids = [
                int(item.get("ref"))
                for item in payload.get("target_refs", [])
                if isinstance(item, dict) and item.get("kind") == "signal_id" and str(item.get("ref", "")).isdigit()
            ]
            if signal_ids:
                matches: list[int] = []
                rows = conn.execute(
                    """
                    SELECT os.op_signal_id, pr.parse_result_normalized_json
                    FROM operational_signals os
                    JOIN parse_results pr ON pr.parse_result_id = os.parse_result_id
                    WHERE os.message_type = 'NEW_SIGNAL'
                      AND os.trader_id = ?
                    """,
                    (trader_id,),
                ).fetchall()
                for row in rows:
                    new_payload = _normalized_payload(row["parse_result_normalized_json"])
                    entities = new_payload.get("entities", {})
                    signal_id = entities.get("signal_id") if isinstance(entities, dict) else None
                    if signal_id in signal_ids:
                        matches.append(int(row["op_signal_id"]))
                if matches:
                    return ResolvedTarget(position_ids=matches, eligibility="ELIGIBLE", reason=None)

        return ResolvedTarget(position_ids=[], eligibility="UNRESOLVED", reason="no_matching_open_signal")


def run_replay(
    *,
    db_path: str,
    trader: str | None = None,
    dry_run: bool = False,
) -> ReplayStats:
    if _is_live_db_path(db_path):
        raise RuntimeError(f"Refusing to run on live DB path: {db_path}")

    apply_migrations(db_path=db_path, migrations_dir=str(PROJECT_ROOT / "db" / "migrations"))

    signals_store = SignalsStore(db_path)
    operational_store = OperationalSignalsStore(db_path)
    engine = OperationRulesEngine()
    resolver = TargetResolver()
    stats = ReplayStats()

    rows = _fetch_parse_results(db_path=db_path, trader=trader)
    stats.total = len(rows)

    for row in rows:
        if _operational_exists(db_path, row.parse_result_id):
            stats.skipped_existing += 1
            continue

        trader_id = row.resolved_trader_id or "UNRESOLVED"
        engine_signal = engine.apply(row, trader_id, db_path=db_path)

        if row.message_type == "NEW_SIGNAL":
            if engine_signal.is_blocked:
                stats.new_signal_blocked += 1
            else:
                stats.new_signal_inserted += 1
                if not dry_run and engine_signal.attempt_key is not None:
                    signals_store.insert(_build_signal_record(row, trader_id, engine_signal.attempt_key))

            if not dry_run:
                operational_store.insert(_build_operational_record(engine_signal))
            continue

        target = resolver.resolve(row, trader_id, db_path=db_path)
        if target.position_ids:
            stats.update_linked += 1
        else:
            stats.update_orphan += 1

        if not dry_run:
            operational_store.insert(
                _build_operational_record(
                    engine_signal,
                    resolved_target_ids=json.dumps(target.position_ids) if target.position_ids else None,
                    target_eligibility=target.eligibility,
                    target_reason=target.reason,
                )
            )

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize signals and operational_signals from parse_results")
    parser.add_argument("--db-path", required=True, help="Path to parser/backtest SQLite DB")
    parser.add_argument("--trader", default=None, help="Optional trader filter")
    parser.add_argument("--dry-run", action="store_true", help="Process rows without writing to DB")
    args = parser.parse_args()

    stats = run_replay(db_path=args.db_path, trader=args.trader, dry_run=args.dry_run)
    print(f"db_path: {args.db_path}")
    print(f"trader filter: {args.trader or '(all)'}")
    print(f"total: {stats.total}")
    print(f"new_signal_inserted: {stats.new_signal_inserted}")
    print(f"new_signal_blocked: {stats.new_signal_blocked}")
    print(f"update_linked: {stats.update_linked}")
    print(f"update_orphan: {stats.update_orphan}")
    print(f"skipped_existing: {stats.skipped_existing}")
    print(f"errors: {stats.errors}")
    return 0


def _fetch_parse_results(*, db_path: str, trader: str | None) -> list[ParseResultView]:
    query = """
        SELECT
          pr.parse_result_id,
          pr.raw_message_id,
          rm.source_chat_id,
          rm.telegram_message_id,
          rm.reply_to_message_id,
          COALESCE(rm.raw_text, '') AS raw_text,
          rm.message_ts,
          pr.resolved_trader_id,
          pr.message_type,
          pr.completeness,
          pr.is_executable,
          pr.symbol,
          pr.direction,
          pr.parse_result_normalized_json
        FROM parse_results pr
        JOIN raw_messages rm ON rm.raw_message_id = pr.raw_message_id
        WHERE pr.message_type IN ('NEW_SIGNAL', 'UPDATE')
    """
    params: list[object] = []
    if trader:
        query += " AND pr.resolved_trader_id = ?"
        params.append(trader)
    query += " ORDER BY rm.message_ts ASC, pr.parse_result_id ASC"

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [
        ParseResultView(
            parse_result_id=int(row[0]),
            raw_message_id=int(row[1]),
            source_chat_id=str(row[2]),
            telegram_message_id=int(row[3]),
            reply_to_message_id=int(row[4]) if row[4] is not None else None,
            raw_text=str(row[5]),
            message_ts=str(row[6]),
            resolved_trader_id=str(row[7]) if row[7] else None,
            message_type=str(row[8]),
            completeness=str(row[9] or ""),
            is_executable=bool(row[10]),
            symbol=str(row[11]) if row[11] else None,
            direction=str(row[12]) if row[12] else None,
            parse_result_normalized_json=str(row[13]) if row[13] else None,
        )
        for row in rows
    ]


def _operational_exists(db_path: str, parse_result_id: int) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM operational_signals WHERE parse_result_id = ? LIMIT 1",
            (parse_result_id,),
        ).fetchone()
    return row is not None


def _normalized_payload(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _build_attempt_key(parse_result: ParseResultView, entities: dict[str, Any]) -> str:
    signal_id = entities.get("signal_id")
    suffix = str(signal_id) if signal_id is not None else f"rm{parse_result.raw_message_id}"
    return f"{parse_result.resolved_trader_id or 'unresolved'}:{suffix}"


def _build_signal_record(parse_result: ParseResultView, trader_id: str, attempt_key: str) -> SignalRecord:
    payload = _normalized_payload(parse_result.parse_result_normalized_json)
    entities = payload.get("entities", {}) if isinstance(payload, dict) else {}
    confidence = float(payload.get("confidence", 0.0) or 0.0)

    symbol = _extract_symbol(parse_result, entities)
    side = _normalize_side(_extract_side(parse_result, entities))
    entry_json = json.dumps(_extract_entries(entities))
    sl_value = _extract_stop_loss(entities)
    tp_json = json.dumps(_extract_take_profits(entities))

    return SignalRecord(
        attempt_key=attempt_key,
        env="T",
        channel_id=parse_result.source_chat_id,
        root_telegram_id=str(parse_result.telegram_message_id),
        trader_id=trader_id,
        trader_prefix=trader_id[:2].upper(),
        symbol=symbol,
        side=side,
        entry_json=entry_json,
        sl=sl_value,
        tp_json=tp_json,
        status="PENDING",
        confidence=confidence,
        raw_text=parse_result.raw_text,
        created_at=parse_result.message_ts,
        updated_at=parse_result.message_ts,
    )


def _build_operational_record(
    engine_signal: EngineSignal,
    *,
    resolved_target_ids: str | None = None,
    target_eligibility: str | None = None,
    target_reason: str | None = None,
) -> OperationalSignalRecord:
    return OperationalSignalRecord(
        parse_result_id=engine_signal.parse_result.parse_result_id,
        attempt_key=engine_signal.attempt_key,
        trader_id=engine_signal.trader_id,
        message_type=engine_signal.parse_result.message_type,
        is_blocked=engine_signal.is_blocked,
        block_reason=engine_signal.block_reason,
        risk_mode=engine_signal.risk_mode,
        risk_pct_of_capital=engine_signal.risk_pct_of_capital,
        risk_usdt_fixed=engine_signal.risk_usdt_fixed,
        capital_base_usdt=engine_signal.capital_base_usdt,
        risk_budget_usdt=engine_signal.risk_budget_usdt,
        sl_distance_pct=engine_signal.sl_distance_pct,
        position_size_usdt=engine_signal.position_size_usdt,
        position_size_pct=engine_signal.position_size_pct,
        entry_split_json=json.dumps(engine_signal.entry_split) if engine_signal.entry_split is not None else None,
        leverage=engine_signal.leverage,
        risk_hint_used=engine_signal.risk_hint_used,
        management_rules_json=(
            json.dumps(engine_signal.management_rules) if engine_signal.management_rules is not None else None
        ),
        price_corrections_json=None,
        applied_rules_json=json.dumps(engine_signal.applied_rules or []),
        warnings_json=json.dumps(engine_signal.warnings or []),
        resolved_target_ids=resolved_target_ids,
        target_eligibility=target_eligibility,
        target_reason=target_reason,
        created_at=engine_signal.parse_result.message_ts,
    )


def _extract_symbol(parse_result: ParseResultView, entities: dict[str, Any]) -> str | None:
    for key in ("symbol", "instrument"):
        value = entities.get(key)
        if value:
            return str(value).upper()
    return parse_result.symbol.upper() if parse_result.symbol else None


def _extract_side(parse_result: ParseResultView, entities: dict[str, Any]) -> str | None:
    for key in ("direction", "side"):
        value = entities.get(key)
        if value:
            return str(value).upper()
    return parse_result.direction.upper() if parse_result.direction else None


def _normalize_side(value: str | None) -> str | None:
    if value in {"LONG", "BUY"}:
        return "BUY"
    if value in {"SHORT", "SELL"}:
        return "SELL"
    return value


def _extract_entries(entities: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(entities.get("entry_plan_entries"), list) and entities["entry_plan_entries"]:
        return [
            {
                "price": item.get("price"),
                "type": item.get("order_type", "LIMIT"),
            }
            for item in entities["entry_plan_entries"]
            if isinstance(item, dict)
        ]
    entries = entities.get("entries")
    if isinstance(entries, list) and entries:
        normalized: list[dict[str, Any]] = []
        for item in entries:
            if isinstance(item, dict):
                price = item.get("price")
                if isinstance(price, dict):
                    price = price.get("value")
                normalized.append({"price": price, "type": item.get("order_type", "LIMIT")})
            else:
                normalized.append({"price": item, "type": "LIMIT"})
        return normalized
    entry = entities.get("entry")
    if isinstance(entry, list):
        return [{"price": item, "type": entities.get("entry_order_type", "LIMIT")} for item in entry]
    return []


def _extract_stop_loss(entities: dict[str, Any]) -> float | None:
    stop_loss = entities.get("stop_loss")
    if isinstance(stop_loss, dict):
        price = stop_loss.get("price")
        if isinstance(price, dict):
            value = price.get("value")
            return float(value) if value is not None else None
    if stop_loss is not None:
        return float(stop_loss)
    return None


def _extract_take_profits(entities: dict[str, Any]) -> list[dict[str, Any]]:
    take_profits = entities.get("take_profits")
    if not isinstance(take_profits, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in take_profits:
        if isinstance(item, dict):
            price = item.get("price")
            if isinstance(price, dict):
                price = price.get("value")
            normalized.append({"price": price})
        else:
            normalized.append({"price": item})
    return normalized


def _is_live_db_path(db_path: str) -> bool:
    candidate = Path(db_path).resolve()
    live = (PROJECT_ROOT / "db" / "tele_signal_bot.sqlite3").resolve()
    return candidate == live


if __name__ == "__main__":
    raise SystemExit(main())
