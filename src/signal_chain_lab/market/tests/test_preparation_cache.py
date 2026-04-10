from __future__ import annotations

import json
from pathlib import Path

from src.signal_chain_lab.market.preparation_cache import (
    build_market_request,
    find_pass_validation_record,
    load_validation_index,
    market_request_fingerprint,
    save_validation_index,
    upsert_validation_record,
    validation_index_path,
)


def _make_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fixture", encoding="utf-8")


def test_market_request_fingerprint_is_stable_for_same_market_context(tmp_path: Path) -> None:
    db_path = tmp_path / "db" / "backtest.sqlite3"
    market_dir = tmp_path / "market"
    _make_db(db_path)

    request_a = build_market_request(
        db_path=str(db_path),
        market_data_dir=str(market_dir),
        trader_filter="all",
        date_from="2026-01-01",
        date_to="2026-01-31",
        timeframe="1m",
        price_basis="last",
        source="bybit",
    )
    request_b = build_market_request(
        db_path=str(db_path),
        market_data_dir=str(market_dir),
        trader_filter="all",
        date_from="2026-01-01",
        date_to="2026-01-31",
        timeframe="1m",
        price_basis="last",
        source="bybit",
    )

    assert market_request_fingerprint(request_a) == market_request_fingerprint(request_b)


def test_market_request_fingerprint_changes_when_market_context_changes(tmp_path: Path) -> None:
    db_path = tmp_path / "db" / "backtest.sqlite3"
    market_dir = tmp_path / "market"
    _make_db(db_path)

    baseline = build_market_request(
        db_path=str(db_path),
        market_data_dir=str(market_dir),
        trader_filter="all",
        date_from="",
        date_to="",
        timeframe="1m",
        price_basis="last",
        source="bybit",
    )
    changed_filter = build_market_request(
        db_path=str(db_path),
        market_data_dir=str(market_dir),
        trader_filter="trader#a",
        date_from="",
        date_to="",
        timeframe="1m",
        price_basis="last",
        source="bybit",
    )
    changed_date = build_market_request(
        db_path=str(db_path),
        market_data_dir=str(market_dir),
        trader_filter="all",
        date_from="2026-02-01",
        date_to="",
        timeframe="1m",
        price_basis="last",
        source="bybit",
    )

    assert market_request_fingerprint(baseline) != market_request_fingerprint(changed_filter)
    assert market_request_fingerprint(baseline) != market_request_fingerprint(changed_date)


def test_validation_index_roundtrip_and_pass_lookup(tmp_path: Path) -> None:
    db_path = tmp_path / "db" / "backtest.sqlite3"
    market_dir = tmp_path / "market"
    _make_db(db_path)
    request = build_market_request(
        db_path=str(db_path),
        market_data_dir=str(market_dir),
        trader_filter="all",
        date_from="",
        date_to="",
        timeframe="1m",
        price_basis="last",
        source="bybit",
    )
    fingerprint = market_request_fingerprint(request)

    index_path = validation_index_path(str(market_dir))
    payload = load_validation_index(index_path)
    assert payload["records"] == []

    upsert_validation_record(
        index_payload=payload,
        request=request,
        fingerprint=fingerprint,
        status="PASS",
        plan_path="artifacts/market_data/plan_market_data.json",
        sync_report_path="artifacts/market_data/sync_market_data.json",
        validate_report_path="artifacts/market_data/validate_market_data.json",
        summary={"gaps": 0},
    )
    save_validation_index(index_path, payload)

    loaded = load_validation_index(index_path)
    found = find_pass_validation_record(loaded, fingerprint)
    assert found is not None
    assert found["status"] == "PASS"
    assert found["fingerprint"] == fingerprint

    json.loads(index_path.read_text(encoding="utf-8"))
