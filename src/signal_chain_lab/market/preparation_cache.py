from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_VALIDATION_INDEX_SCHEMA = "market-validation-index.v1"
_FINGERPRINT_SCHEMA = "market-request-fingerprint.v1"


@dataclass(frozen=True, slots=True)
class MarketDataRequest:
    db_path: str
    db_mtime: float
    db_size: int
    trader_filter: str
    date_from: str
    date_to: str
    max_trades: int
    market_data_dir: str
    timeframe: str
    price_basis: str
    source: str



def _normalize_text(value: str | None, *, default: str = "") -> str:
    return (value or default).strip()



def build_market_request(
    *,
    db_path: str,
    market_data_dir: str,
    trader_filter: str,
    date_from: str,
    date_to: str,
    max_trades: int,
    timeframe: str,
    price_basis: str,
    source: str,
) -> MarketDataRequest:
    db_resolved = Path(db_path).expanduser().resolve()
    db_stat = db_resolved.stat()
    market_resolved = Path(market_data_dir).expanduser().resolve()

    return MarketDataRequest(
        db_path=str(db_resolved),
        db_mtime=float(db_stat.st_mtime),
        db_size=int(db_stat.st_size),
        trader_filter=_normalize_text(trader_filter, default="all") or "all",
        date_from=_normalize_text(date_from),
        date_to=_normalize_text(date_to),
        max_trades=max(0, int(max_trades)),
        market_data_dir=str(market_resolved),
        timeframe=_normalize_text(timeframe, default="1m") or "1m",
        price_basis=_normalize_text(price_basis, default="last") or "last",
        source=_normalize_text(source, default="bybit") or "bybit",
    )



def market_request_payload(request: MarketDataRequest) -> dict[str, Any]:
    return {
        "schema": _FINGERPRINT_SCHEMA,
        "db_path": request.db_path,
        "db_mtime": request.db_mtime,
        "db_size": request.db_size,
        "trader_filter": request.trader_filter,
        "date_from": request.date_from,
        "date_to": request.date_to,
        "max_trades": request.max_trades,
        "market_data_dir": request.market_data_dir,
        "timeframe": request.timeframe,
        "price_basis": request.price_basis,
        "source": request.source,
    }



def market_request_fingerprint(request: MarketDataRequest) -> str:
    canonical = json.dumps(market_request_payload(request), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()



def validation_index_path(market_data_dir: str) -> Path:
    return Path(market_data_dir).expanduser().resolve() / "manifests" / "validation_index.json"



def load_validation_index(index_path: Path) -> dict[str, Any]:
    if not index_path.exists():
        return {"schema": _VALIDATION_INDEX_SCHEMA, "records": []}
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list):
        records = []
    return {
        "schema": payload.get("schema") or _VALIDATION_INDEX_SCHEMA,
        "records": records,
    }



def save_validation_index(index_path: Path, payload: dict[str, Any]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")



def find_pass_validation_record(index_payload: dict[str, Any], fingerprint: str) -> dict[str, Any] | None:
    candidates = [
        record
        for record in index_payload.get("records", [])
        if isinstance(record, dict)
        and record.get("fingerprint") == fingerprint
        and str(record.get("status", "")).upper() == "PASS"
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: str(item.get("validated_at", "")), reverse=True)
    return candidates[0]



def upsert_validation_record(
    *,
    index_payload: dict[str, Any],
    request: MarketDataRequest,
    fingerprint: str,
    status: str,
    plan_path: str,
    sync_report_path: str,
    validate_report_path: str,
    summary: dict[str, Any],
) -> dict[str, Any]:
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    record: dict[str, Any] = {
        "fingerprint": fingerprint,
        "status": status.upper(),
        "validated_at": now_iso,
        **market_request_payload(request),
        "plan_path": plan_path,
        "sync_report_path": sync_report_path,
        "validate_report_path": validate_report_path,
        "summary": summary,
    }
    records = [
        row
        for row in index_payload.get("records", [])
        if not (isinstance(row, dict) and row.get("fingerprint") == fingerprint)
    ]
    records.append(record)
    index_payload["records"] = records[-200:]
    return record
