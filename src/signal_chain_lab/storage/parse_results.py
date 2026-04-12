"""Persistence for minimal parse results."""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
import json
import sqlite3

from src.signal_chain_lab.engine.state_machine import normalize_alias_fields, normalize_entry_semantics


@dataclass(slots=True)
class ParseResultRecord:
    raw_message_id: int
    eligibility_status: str
    eligibility_reason: str
    declared_trader_tag: str | None
    resolved_trader_id: str | None
    trader_resolution_method: str
    message_type: str
    parse_status: str
    completeness: str
    is_executable: bool
    symbol: str | None
    direction: str | None
    entry_raw: str | None
    stop_raw: str | None
    target_raw_list: str | None
    leverage_hint: str | None
    risk_hint: str | None
    risky_flag: bool
    linkage_method: str | None
    linkage_status: str | None
    warning_text: str | None
    notes: str | None
    parse_result_normalized_json: str | None
    created_at: str
    updated_at: str


class ParseResultStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def get_raw_text_by_signal_id(self, resolved_trader_id: str, signal_id: int) -> str | None:
        query = """
            SELECT rm.raw_text, pr.parse_result_normalized_json
            FROM parse_results pr
            JOIN raw_messages rm ON rm.raw_message_id = pr.raw_message_id
            WHERE pr.resolved_trader_id = ? AND pr.message_type = 'NEW_SIGNAL'
            ORDER BY rm.raw_message_id ASC
        """
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(query, (resolved_trader_id,)).fetchall()
        for row in rows:
            payload = row[1] or "{}"
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            entities = data.get("entities") if isinstance(data, dict) else None
            if isinstance(entities, dict) and entities.get("signal_id") == signal_id:
                return row[0]
        return None

    def upsert(self, record: ParseResultRecord) -> None:
        normalized_json = _canonicalize_normalized_json(record.parse_result_normalized_json, message_type=record.message_type)
        canonical_direction = _direction_from_payload(normalized_json) or record.direction
        query = """
            INSERT INTO parse_results(
              raw_message_id,
              eligibility_status,
              eligibility_reason,
              declared_trader_tag,
              resolved_trader_id,
              trader_resolution_method,
              message_type,
              parse_status,
              completeness,
              is_executable,
              symbol,
              direction,
              entry_raw,
              stop_raw,
              target_raw_list,
              leverage_hint,
              risk_hint,
              risky_flag,
              linkage_method,
              linkage_status,
              warning_text,
              notes,
              parse_result_normalized_json,
              created_at,
              updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(raw_message_id) DO UPDATE SET
              eligibility_status=excluded.eligibility_status,
              eligibility_reason=excluded.eligibility_reason,
              declared_trader_tag=excluded.declared_trader_tag,
              resolved_trader_id=excluded.resolved_trader_id,
              trader_resolution_method=excluded.trader_resolution_method,
              message_type=excluded.message_type,
              parse_status=excluded.parse_status,
              completeness=excluded.completeness,
              is_executable=excluded.is_executable,
              symbol=excluded.symbol,
              direction=excluded.direction,
              entry_raw=excluded.entry_raw,
              stop_raw=excluded.stop_raw,
              target_raw_list=excluded.target_raw_list,
              leverage_hint=excluded.leverage_hint,
              risk_hint=excluded.risk_hint,
              risky_flag=excluded.risky_flag,
              linkage_method=excluded.linkage_method,
              linkage_status=excluded.linkage_status,
              warning_text=excluded.warning_text,
              notes=excluded.notes,
              parse_result_normalized_json=excluded.parse_result_normalized_json,
              updated_at=excluded.updated_at
        """
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                query,
                (
                    record.raw_message_id,
                    record.eligibility_status,
                    record.eligibility_reason,
                    record.declared_trader_tag,
                    record.resolved_trader_id,
                    record.trader_resolution_method,
                    record.message_type,
                    record.parse_status,
                    record.completeness,
                    1 if record.is_executable else 0,
                    record.symbol,
                    canonical_direction,
                    record.entry_raw,
                    record.stop_raw,
                    record.target_raw_list,
                    record.leverage_hint,
                    record.risk_hint,
                    1 if record.risky_flag else 0,
                    record.linkage_method,
                    record.linkage_status,
                    record.warning_text,
                    record.notes,
                    normalized_json,
                    record.created_at,
                    record.updated_at,
                ),
            )
            conn.commit()


def _canonicalize_normalized_json(raw: str | None, *, message_type: str | None) -> str | None:
    if not raw:
        return raw
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if not isinstance(payload, dict):
        return raw
    canonical = _canonicalize_payload(payload, message_type=message_type)
    return json.dumps(canonical, ensure_ascii=False, default=str)


def _canonicalize_payload(payload: dict, *, message_type: str | None) -> dict:
    result = deepcopy(payload)
    entities = result.get("entities")
    if isinstance(entities, dict):
        entities = normalize_alias_fields(entities)
        if str(message_type or result.get("message_type") or "").upper() == "NEW_SIGNAL":
            entities = normalize_entry_semantics(entities)
            _ensure_entry_plan_entries(entities)
            _ensure_entry_range(entities)
        result["entities"] = entities

    direction = _direction_from_entities(result.get("entities")) or result.get("direction")
    if direction is not None:
        result["direction"] = direction

    symbol = _symbol_from_entities(result.get("entities")) or result.get("symbol")
    if symbol is not None:
        result["symbol"] = symbol

    return result


def _ensure_entry_plan_entries(entities: dict) -> None:
    if entities.get("entry_plan_entries"):
        return
    if entities.get("entries"):
        entities["entry_plan_entries"] = list(entities["entries"])
        return

    entry_range = entities.get("entry_range")
    if isinstance(entry_range, list) and len(entry_range) >= 2:
        prices = [value for value in entry_range[:2] if isinstance(value, (int, float))]
        if len(prices) == 2:
            entities["entry_plan_entries"] = [
                {"role": "RANGE_LOW", "order_type": "LIMIT", "price": float(prices[0])},
                {"role": "RANGE_HIGH", "order_type": "LIMIT", "price": float(prices[1])},
            ]
            return

    low = entities.get("entry_range_low")
    high = entities.get("entry_range_high")
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        entities["entry_plan_entries"] = [
            {"role": "RANGE_LOW", "order_type": "LIMIT", "price": float(low)},
            {"role": "RANGE_HIGH", "order_type": "LIMIT", "price": float(high)},
        ]
        return

    entry = entities.get("entry")
    if isinstance(entry, list):
        entries = []
        for index, value in enumerate(entry):
            if not isinstance(value, (int, float)):
                continue
            role = "PRIMARY" if index == 0 else "AVERAGING"
            entries.append({"role": role, "order_type": "LIMIT", "price": float(value)})
        if entries:
            entities["entry_plan_entries"] = entries
    elif isinstance(entry, (int, float)):
        entities["entry_plan_entries"] = [{"role": "PRIMARY", "order_type": "LIMIT", "price": float(entry)}]


def _ensure_entry_range(entities: dict) -> None:
    if entities.get("entry_range"):
        return
    low = entities.get("entry_range_low")
    high = entities.get("entry_range_high")
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        entities["entry_range"] = [float(low), float(high)]


def _direction_from_payload(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return _direction_from_entities(payload.get("entities")) or payload.get("direction")


def _direction_from_entities(entities: object) -> str | None:
    if not isinstance(entities, dict):
        return None
    direction = entities.get("direction") or entities.get("side")
    return str(direction) if direction is not None else None


def _symbol_from_entities(entities: object) -> str | None:
    if not isinstance(entities, dict):
        return None
    symbol = entities.get("symbol")
    return str(symbol) if symbol is not None else None
