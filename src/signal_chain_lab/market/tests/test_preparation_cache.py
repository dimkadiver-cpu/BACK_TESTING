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
        max_trades=20,
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
        max_trades=20,
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
        max_trades=0,
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
        max_trades=0,
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
        max_trades=0,
        timeframe="1m",
        price_basis="last",
        source="bybit",
    )
    changed_max_trades = build_market_request(
        db_path=str(db_path),
        market_data_dir=str(market_dir),
        trader_filter="all",
        date_from="",
        date_to="",
        max_trades=20,
        timeframe="1m",
        price_basis="last",
        source="bybit",
    )

    assert market_request_fingerprint(baseline) != market_request_fingerprint(changed_filter)
    assert market_request_fingerprint(baseline) != market_request_fingerprint(changed_date)
    assert market_request_fingerprint(baseline) != market_request_fingerprint(changed_max_trades)


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
        max_trades=0,
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


def _baseline_request(tmp_path: Path) -> "MarketDataRequest":  # noqa: F821
    from src.signal_chain_lab.market.preparation_cache import build_market_request

    db_path = tmp_path / "db" / "backtest.sqlite3"
    _make_db(db_path)
    return build_market_request(
        db_path=str(db_path),
        market_data_dir=str(tmp_path / "market"),
        trader_filter="all",
        date_from="",
        date_to="",
        max_trades=0,
        timeframe="1m",
        price_basis="last",
        source="bybit",
        download_tfs=["1m"],
        simulation_tf="1m",
        detail_tf="1m",
        validate_mode="light",
        ohlcv_last=True,
        ohlcv_mark=False,
        funding_rate=False,
        buffer_mode="auto",
        pre_buffer_days=0,
        post_buffer_days=0,
        buffer_preset="",
    )


def test_fingerprint_changes_when_download_tfs_changes(tmp_path: Path) -> None:
    baseline = _baseline_request(tmp_path)
    from src.signal_chain_lab.market.preparation_cache import build_market_request, market_request_fingerprint

    db_path = tmp_path / "db" / "backtest.sqlite3"
    changed = build_market_request(
        db_path=str(db_path),
        market_data_dir=str(tmp_path / "market"),
        trader_filter="all",
        date_from="",
        date_to="",
        max_trades=0,
        timeframe="1m",
        price_basis="last",
        source="bybit",
        download_tfs=["1m", "15m", "1h"],
    )
    assert market_request_fingerprint(baseline) != market_request_fingerprint(changed)


def test_fingerprint_changes_when_validate_mode_changes(tmp_path: Path) -> None:
    baseline = _baseline_request(tmp_path)
    from src.signal_chain_lab.market.preparation_cache import build_market_request, market_request_fingerprint

    db_path = tmp_path / "db" / "backtest.sqlite3"
    changed = build_market_request(
        db_path=str(db_path),
        market_data_dir=str(tmp_path / "market"),
        trader_filter="all",
        date_from="",
        date_to="",
        max_trades=0,
        timeframe="1m",
        price_basis="last",
        source="bybit",
        validate_mode="full",
    )
    assert market_request_fingerprint(baseline) != market_request_fingerprint(changed)


def test_fingerprint_changes_when_funding_rate_changes(tmp_path: Path) -> None:
    baseline = _baseline_request(tmp_path)
    from src.signal_chain_lab.market.preparation_cache import build_market_request, market_request_fingerprint

    db_path = tmp_path / "db" / "backtest.sqlite3"
    changed = build_market_request(
        db_path=str(db_path),
        market_data_dir=str(tmp_path / "market"),
        trader_filter="all",
        date_from="",
        date_to="",
        max_trades=0,
        timeframe="1m",
        price_basis="last",
        source="bybit",
        funding_rate=True,
    )
    assert market_request_fingerprint(baseline) != market_request_fingerprint(changed)


def test_old_fingerprint_record_is_treated_as_cache_miss(tmp_path: Path) -> None:
    from src.signal_chain_lab.market.preparation_cache import find_pass_validation_record, load_validation_index, save_validation_index, validation_index_path

    market_dir = tmp_path / "market"
    old_fingerprint = "aabbcc112233"  # simulates a v1 record with a different hash

    index_path = validation_index_path(str(market_dir))
    payload = {"schema": "market-validation-index.v1", "records": [
        {"fingerprint": old_fingerprint, "status": "PASS", "validated_at": "2025-01-01T00:00:00+00:00"},
    ]}
    index_path.parent.mkdir(parents=True, exist_ok=True)
    save_validation_index(index_path, payload)

    loaded = load_validation_index(index_path)
    # Current request has a different fingerprint → cache miss, no KeyError
    found = find_pass_validation_record(loaded, "different-fingerprint-from-v2")
    assert found is None
