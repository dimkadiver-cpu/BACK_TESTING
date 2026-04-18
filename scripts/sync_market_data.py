from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.signal_chain_lab.market.planning.gap_detection import Interval
from src.signal_chain_lab.market.planning.manifest_store import CoverageKey, CoverageRecord, ManifestStore
from src.signal_chain_lab.market.sync.bybit_downloader import BybitDownloader, _atomic_write_parquet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync missing market-data gaps to local parquet storage")
    parser.add_argument("--plan-file", required=True, help="Plan JSON produced by plan_market_data.py")
    parser.add_argument("--db-path", default=None, help="Path to SQLite backtesting DB (required only for fixture source)")
    parser.add_argument("--market-dir", required=True, help="Path to market data root")
    parser.add_argument(
        "--source",
        default="bybit",
        choices=["bybit", "fixture"],
        help="Data source backend. Default: bybit (real download).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional sync report JSON path; default under artifacts/market_data/",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = json.loads(Path(args.plan_file).read_text(encoding="utf-8"))
    market_dir = Path(args.market_dir)
    manifest = ManifestStore(root=market_dir / "manifests")
    timeframe = str(plan["timeframe"])

    print("PHASE=sync")
    print("PROGRESS=0")

    if args.source == "fixture":
        if not args.db_path:
            raise SystemExit("--db-path is required when --source=fixture")
        results = _sync_fixture(
            plan=plan,
            db_path=args.db_path,
            market_dir=market_dir,
            manifest=manifest,
            timeframe=timeframe,
            source=args.source,
        )
    else:
        results = _sync_bybit(
            plan=plan,
            market_dir=market_dir,
            manifest=manifest,
            source=args.source,
        )

    output = Path(args.output) if args.output else Path("artifacts/market_data/sync_market_data.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "source": args.source,
                "plan_file": str(Path(args.plan_file).resolve()),
                "market_request_fingerprint": plan.get("market_request_fingerprint", ""),
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    ok_count = sum(1 for item in results if item["status"] == "ok")
    skipped_count = sum(1 for item in results if item["status"] == "skipped")
    failed_count = sum(1 for item in results if item["status"] in {"error", "partial"})

    print("PROGRESS=100")
    print(f"SUMMARY=ok:{ok_count} skipped:{skipped_count} error:{failed_count}")
    print(f"sync_report={output}")
    print(f"source={args.source}")
    print(f"jobs={len(results)}")
    print(f"ok={ok_count}")
    print(f"skipped={skipped_count}")
    print(f"failed={failed_count}")
    print(f"market_request_fingerprint={plan.get('market_request_fingerprint', '')}")

    return 1 if failed_count else 0


def _sync_bybit(
    *,
    plan: dict[str, object],
    market_dir: Path,
    manifest: ManifestStore,
    source: str,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    symbols_payload = plan.get("symbols", {})
    for symbol, basis_payload in symbols_payload.items():
        if not isinstance(basis_payload, dict):
            continue

        for basis, entry in basis_payload.items():
            timeframe_entries = entry.get("timeframes") if isinstance(entry, dict) else None
            if isinstance(timeframe_entries, dict) and timeframe_entries:
                for requested_timeframe, timeframe_entry in timeframe_entries.items():
                    gaps = [Interval.from_dict(item) for item in timeframe_entry.get("gaps", [])]
                    if not gaps:
                        results.append(
                            {
                                "symbol": symbol,
                                "basis": basis,
                                "timeframe": requested_timeframe,
                                "status": "skipped",
                                "rows_written": 0,
                                "source": source,
                            }
                        )
                        continue

                    downloader = BybitDownloader(
                        market_dir=market_dir,
                        manifest_store=manifest,
                        timeframe=str(requested_timeframe),
                        bases=["last", "mark"],
                    )
                    sync_result = downloader.sync_gaps(symbol=symbol, gaps=gaps, bases=[basis])[0]
                    if sync_result.status in {"error", "partial"}:
                        print(
                            f"ERROR sync_bybit symbol={symbol} basis={basis} timeframe={requested_timeframe} "
                            f"status={sync_result.status} errors={sync_result.errors}"
                        )

                    results.append(
                        {
                            "symbol": symbol,
                            "basis": basis,
                            "timeframe": requested_timeframe,
                            "status": sync_result.status,
                            "rows_written": sync_result.rows_downloaded,
                            "partitions_written": sync_result.partitions_written,
                            "errors": sync_result.errors,
                            "source": source,
                        }
                    )
                continue

            gaps = [Interval.from_dict(item) for item in entry.get("gaps", [])]
            if not gaps:
                results.append({"symbol": symbol, "basis": basis, "timeframe": plan["timeframe"], "status": "skipped", "rows_written": 0})
                continue

            downloader = BybitDownloader(
                market_dir=market_dir,
                manifest_store=manifest,
                timeframe=str(plan["timeframe"]),
                bases=["last", "mark"],
            )
            sync_result = downloader.sync_gaps(symbol=symbol, gaps=gaps, bases=[basis])[0]
            if sync_result.status in {"error", "partial"}:
                print(
                    f"ERROR sync_bybit symbol={symbol} basis={basis} "
                    f"status={sync_result.status} errors={sync_result.errors}"
                )

            results.append(
                {
                    "symbol": symbol,
                    "basis": basis,
                    "timeframe": plan["timeframe"],
                    "status": sync_result.status,
                    "rows_written": sync_result.rows_downloaded,
                    "partitions_written": sync_result.partitions_written,
                    "errors": sync_result.errors,
                    "source": source,
                }
            )
    return results


def _sync_fixture(
    *,
    plan: dict[str, object],
    db_path: str,
    market_dir: Path,
    manifest: ManifestStore,
    timeframe: str,
    source: str,
) -> list[dict[str, object]]:
    signal_map = _load_signal_specs(db_path)
    results: list[dict[str, object]] = []

    for symbol, basis_payload in plan["symbols"].items():
        signal_spec = signal_map.get(symbol)
        if signal_spec is None:
            for basis in basis_payload.keys():
                results.append(
                    {
                        "symbol": symbol,
                        "basis": basis,
                        "status": "missing_reference_price",
                        "rows_written": 0,
                        "source": source,
                    }
                )
            continue
        for basis, entry in basis_payload.items():
            gaps = [Interval.from_dict(item) for item in entry.get("gaps", [])]
            if not gaps:
                results.append({"symbol": symbol, "basis": basis, "status": "skipped", "rows_written": 0, "source": source})
                continue

            rows_written = 0
            partitions_written: list[str] = []
            for gap in gaps:
                rows = _build_fixture_rows(
                    symbol=symbol,
                    basis=basis,
                    timeframe=timeframe,
                    gap=gap,
                    reference_price=float(signal_spec["reference_price"]),
                    trigger_timestamps={datetime.fromisoformat(item) for item in signal_spec["open_timestamps"]},
                )
                rows_written += len(rows)
                partitions_written.extend(_write_rows(market_dir, symbol, basis, timeframe, rows))
                manifest.upsert_coverage(
                    CoverageRecord(
                        key=CoverageKey(
                            exchange="bybit",
                            market_type="futures_linear",
                            timeframe=timeframe,
                            symbol=symbol,
                            basis=basis,
                        ),
                        covered_intervals=[gap],
                        validation_status="ok",
                        last_updated=datetime.now(tz=timezone.utc),
                    )
                )
                manifest.append_download_event(
                    {
                        "event_id": str(uuid.uuid4()),
                        "exchange": "bybit",
                        "market_type": "futures_linear",
                        "timeframe": timeframe,
                        "symbol": symbol,
                        "basis": basis,
                        "gap_start": gap.start.isoformat(),
                        "gap_end": gap.end.isoformat(),
                        "rows": len(rows),
                        "partitions": partitions_written,
                        "status": "ok",
                        "source": source,
                    }
                )

            results.append(
                {
                    "symbol": symbol,
                    "basis": basis,
                    "status": "ok",
                    "rows_written": rows_written,
                    "partitions_written": partitions_written,
                    "source": source,
                }
            )
    return results


def _load_signal_specs(db_path: str) -> dict[str, dict[str, object]]:
    query = """
        SELECT
            UPPER(pr.symbol) AS symbol,
            rm.message_ts,
            pr.parse_result_normalized_json
        FROM parse_results pr
        JOIN raw_messages rm ON rm.raw_message_id = pr.raw_message_id
        WHERE pr.symbol IS NOT NULL
          AND pr.parse_result_normalized_json IS NOT NULL
    """
    specs: dict[str, dict[str, object]] = {}
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query).fetchall()
    for symbol, message_ts, normalized_json in rows:
        payload = json.loads(normalized_json)
        reference_price = _extract_reference_price(payload)
        if reference_price is not None:
            key = str(symbol)
            spec = specs.setdefault(key, {"reference_price": reference_price, "open_timestamps": []})
            spec["open_timestamps"].append(str(message_ts))
    return specs


def _extract_reference_price(payload: dict[str, object]) -> float | None:
    entities = payload.get("entities", {})
    if not isinstance(entities, dict):
        return None
    entry_plan_entries = entities.get("entry_plan_entries")
    if isinstance(entry_plan_entries, list):
        for item in entry_plan_entries:
            price = _coerce_price(item.get("price")) if isinstance(item, dict) else _coerce_price(item)
            if price is not None:
                return price

    entries = entities.get("entries")
    if isinstance(entries, list):
        for item in entries:
            if isinstance(item, dict):
                price = _coerce_price(item.get("price"))
            else:
                price = _coerce_price(item)
            if price is not None:
                return price

    entry = entities.get("entry")
    if isinstance(entry, list):
        for item in entry:
            price = _coerce_price(item)
            if price is not None:
                return price
    direct_entry = _coerce_price(entry)
    if direct_entry is not None:
        return direct_entry
    return _derive_market_reference_price(payload)


def _derive_market_reference_price(payload: dict[str, object]) -> float | None:
    entities = payload.get("entities", {})
    if not isinstance(entities, dict):
        return None
    side = str(entities.get("side") or "").upper()
    stop_loss = _coerce_price(entities.get("stop_loss"))

    take_profits = entities.get("take_profits")
    first_tp: float | None = None
    if isinstance(take_profits, list):
        for item in take_profits:
            first_tp = _coerce_price(item)
            if first_tp is not None:
                break

    if stop_loss is not None and first_tp is not None:
        return (stop_loss + first_tp) / 2.0
    if side == "LONG" and stop_loss is not None:
        return stop_loss * 1.02
    if side == "SHORT" and stop_loss is not None:
        return stop_loss * 0.98
    if first_tp is not None and side == "LONG":
        return first_tp * 0.98
    if first_tp is not None and side == "SHORT":
        return first_tp * 1.02
    return None


def _coerce_price(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    if isinstance(value, dict):
        nested = value.get("value")
        if isinstance(nested, (int, float)):
            return float(nested)
        raw = value.get("raw")
        if isinstance(raw, str):
            try:
                return float(raw)
            except ValueError:
                return None
    return None


def _build_fixture_rows(
    *,
    symbol: str,
    basis: str,
    timeframe: str,
    gap: Interval,
    reference_price: float,
    trigger_timestamps: set[datetime],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    ts = gap.start
    while ts <= gap.end:
        if ts in trigger_timestamps:
            low = reference_price * 0.90
            high = reference_price * 1.12
            open_price = reference_price
            close_price = reference_price * (1.08 if symbol != "ETHUSDT" else 0.94)
        else:
            open_price = reference_price
            high = reference_price * 1.01
            low = reference_price * 0.99
            close_price = reference_price
        rows.append(
            {
                "timestamp": ts,
                "open": round(open_price, 8),
                "high": round(high, 8),
                "low": round(low, 8),
                "close": round(close_price, 8),
                "volume": 1.0 if basis == "last" else 0.0,
                "symbol": symbol,
                "timeframe": timeframe,
            }
        )
        ts += timedelta(minutes=1)
    return rows


def _write_rows(
    market_dir: Path,
    symbol: str,
    basis: str,
    timeframe: str,
    rows: list[dict[str, object]],
) -> list[str]:
    by_month: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        month_key = row["timestamp"].strftime("%Y-%m")
        by_month.setdefault(month_key, []).append(row)

    written: list[str] = []
    for month_key, month_rows in sorted(by_month.items()):
        path = market_dir / "bybit" / "futures_linear" / timeframe / symbol / f"{month_key}.{basis}.parquet"
        _atomic_write_parquet(path=path, new_rows=month_rows)
        written.append(str(path))
    return written


if __name__ == "__main__":
    raise SystemExit(main())
