from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.signal_chain_lab.market.planning.coverage_planner import CoveragePlanner, ManualBuffer
from src.signal_chain_lab.market.planning.demand_scanner import SignalDemandScanner
from src.signal_chain_lab.market.planning.gap_detection import detect_gaps
from src.signal_chain_lab.market.planning.manifest_store import CoverageKey, ManifestStore
from src.signal_chain_lab.market.preparation_cache import build_market_request, market_request_fingerprint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a market-data coverage plan from a backtesting DB")
    parser.add_argument("--db-path", required=True, help="Path to SQLite backtesting DB")
    parser.add_argument("--market-dir", required=True, help="Path to market data root")
    parser.add_argument("--timeframe", default="1m", help="Market timeframe (default: 1m)")
    parser.add_argument(
        "--download-tfs",
        default=None,
        help="Comma-separated timeframe list to download (e.g. 1m,15m,1h)",
    )
    parser.add_argument("--simulation-tf", default=None, help="Parent timeframe for main simulation scan")
    parser.add_argument("--detail-tf", default=None, help="Child timeframe for intrabar resolution")
    parser.add_argument("--bases", default="last,mark", help="Comma-separated bases (default: last,mark)")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output JSON path; default under artifacts/market_data/",
    )
    parser.add_argument("--trader-id", default=None, help="Filter signals by trader_id (default: all)")
    parser.add_argument("--date-from", default=None, help="Filter signals from this date YYYY-MM-DD (default: all)")
    parser.add_argument("--date-to", default=None, help="Filter signals up to this date YYYY-MM-DD (default: all)")
    parser.add_argument("--max-trades", type=int, default=0, help="Limit planner to the first N filtered trades (0 = all)")
    parser.add_argument("--source", default="bybit", choices=["bybit", "fixture"], help="Market data source")
    parser.add_argument("--buffer-mode", default="auto", choices=["auto", "manual"], help="Buffer mode (default: auto)")
    parser.add_argument("--pre-buffer-days", type=int, default=0, help="Pre-buffer days (manual mode only)")
    parser.add_argument("--post-buffer-days", type=int, default=0, help="Post-buffer days (manual mode only)")
    parser.add_argument("--buffer-preset", default="custom", help="Buffer preset label (intraday|swing|position|custom)")
    parser.add_argument("--validate-mode", default="light", choices=["full", "light", "off"], help="Validation mode (default: light)")
    return parser.parse_args()


def _normalize_tf(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if lowered == "15":
        return "15m"
    if lowered in {"1d", "d"}:
        return "1d"
    return raw


def _parse_download_tfs(raw: str | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for item in raw.split(","):
        value = _normalize_tf(item)
        if value and value not in out:
            out.append(value)
    return out


def main() -> int:
    args = parse_args()
    market_dir = Path(args.market_dir)
    bases = [item.strip() for item in args.bases.split(",") if item.strip()]

    print("PHASE=planner")
    print("PROGRESS=0")

    demand = SignalDemandScanner(args.db_path).scan(
        trader_id=args.trader_id or None,
        date_from=args.date_from or None,
        date_to=args.date_to or None,
        max_trades=max(0, int(args.max_trades)),
    )
    primary_tf = _normalize_tf(args.timeframe or "1m") or "1m"
    simulation_tf = _normalize_tf(args.simulation_tf or primary_tf) or primary_tf
    detail_tf = _normalize_tf(args.detail_tf or primary_tf) or primary_tf
    download_tfs = _parse_download_tfs(args.download_tfs) or [primary_tf]
    requested_timeframes = list(dict.fromkeys([*download_tfs, simulation_tf, detail_tf]))

    manual_buffer: ManualBuffer | None = None
    if args.buffer_mode == "manual":
        manual_buffer = ManualBuffer(
            pre_days=args.pre_buffer_days,
            post_days=args.post_buffer_days,
            preset=args.buffer_preset,
        )
    coverage_plan = CoveragePlanner().plan(
        demand,
        manual_buffer=manual_buffer,
        timeframes=requested_timeframes,
    )
    manifest = ManifestStore(root=market_dir / "manifests")
    coverage_index = manifest.load_coverage_index()

    payload: dict[str, object] = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "db_path": str(Path(args.db_path).resolve()),
        "market_dir": str(market_dir.resolve()),
        "timeframe": primary_tf,
        "download_tfs": download_tfs,
        "simulation_tf": simulation_tf,
        "detail_tf": detail_tf,
        "requested_timeframes": requested_timeframes,
        "bases": bases,
        "chains_scanned": len(demand),
        "symbols": {},
        "source": args.source,
        "trader_filter": args.trader_id or "all",
        "date_from": args.date_from or "",
        "date_to": args.date_to or "",
        "max_trades": max(0, int(args.max_trades)),
        "buffer_mode": args.buffer_mode,
        "pre_buffer_days": args.pre_buffer_days,
        "post_buffer_days": args.post_buffer_days,
        "buffer_preset": args.buffer_preset,
        "validate_mode": args.validate_mode,
    }
    request = build_market_request(
        db_path=args.db_path,
        market_data_dir=str(market_dir),
        trader_filter=args.trader_id or "all",
        date_from=args.date_from or "",
        date_to=args.date_to or "",
        max_trades=max(0, int(args.max_trades)),
        timeframe=primary_tf,
        price_basis=bases[0] if bases else "last",
        source=args.source,
    )
    payload["market_request_fingerprint"] = market_request_fingerprint(request)

    total_required = 0
    total_gaps = 0
    symbols_payload: dict[str, object] = {}
    for symbol, windows in coverage_plan.windows_by_symbol.items():
        execution_rows = [interval.to_dict() for interval in windows.execution_window]
        chart_rows = [interval.to_dict() for interval in windows.chart_window]
        download_rows = [interval.to_dict() for interval in windows.download_window]
        basis_payload: dict[str, object] = {}
        for basis in bases:
            timeframe_payload: dict[str, object] = {}
            symbol_gap_count = 0
            key = CoverageKey(
                exchange="bybit",
                market_type="futures_linear",
                timeframe=simulation_tf,
                symbol=symbol,
                basis=basis,
            )
            covered = next((record.covered_intervals for record in coverage_index if record.key == key), [])
            gaps = detect_gaps(required=windows.download_window, covered=covered)
            gap_rows = [interval.to_dict() for interval in gaps]
            for timeframe in requested_timeframes:
                timeframe_key = CoverageKey(
                    exchange="bybit",
                    market_type="futures_linear",
                    timeframe=timeframe,
                    symbol=symbol,
                    basis=basis,
                )
                timeframe_covered = next(
                    (record.covered_intervals for record in coverage_index if record.key == timeframe_key),
                    [],
                )
                timeframe_required = windows.download_windows_by_timeframe.get(timeframe, windows.download_window)
                timeframe_gaps = detect_gaps(required=timeframe_required, covered=timeframe_covered)
                timeframe_gap_rows = [interval.to_dict() for interval in timeframe_gaps]
                total_required += len(timeframe_required)
                symbol_gap_count += len(timeframe_gap_rows)
                timeframe_payload[timeframe] = {
                    "download_window": [interval.to_dict() for interval in timeframe_required],
                    "required_intervals": [interval.to_dict() for interval in timeframe_required],
                    "covered_intervals": [interval.to_dict() for interval in timeframe_covered],
                    "gaps": timeframe_gap_rows,
                }
            total_gaps += symbol_gap_count
            basis_payload[basis] = {
                "execution_window": execution_rows,
                "chart_window": chart_rows,
                "download_window": download_rows,
                "required_intervals": download_rows,
                "covered_intervals": [interval.to_dict() for interval in covered],
                "gaps": gap_rows,
                "requested_timeframes": requested_timeframes,
                "timeframes": timeframe_payload,
            }
        symbols_payload[symbol] = basis_payload

    payload["symbols"] = symbols_payload
    payload["summary"] = {
        "symbols": len(symbols_payload),
        "required_intervals": total_required,
        "gaps": total_gaps,
    }

    output = Path(args.output) if args.output else Path("artifacts/market_data/plan_market_data.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("PROGRESS=100")
    print(f"SUMMARY=symbols:{len(symbols_payload)} gaps:{total_gaps}")
    print(f"plan_file={output}")
    print(f"chains_scanned={len(demand)}")
    print(f"symbols={len(symbols_payload)}")
    print(f"required_intervals={total_required}")
    print(f"gaps={total_gaps}")
    print(f"market_request_fingerprint={payload['market_request_fingerprint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
