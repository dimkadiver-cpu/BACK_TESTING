from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.signal_chain_lab.market.planning.coverage_planner import CoveragePlanner
from src.signal_chain_lab.market.planning.demand_scanner import SignalDemandScanner
from src.signal_chain_lab.market.planning.gap_detection import detect_gaps
from src.signal_chain_lab.market.planning.manifest_store import CoverageKey, ManifestStore
from src.signal_chain_lab.market.preparation_cache import build_market_request, market_request_fingerprint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a market-data coverage plan from a backtesting DB")
    parser.add_argument("--db-path", required=True, help="Path to SQLite backtesting DB")
    parser.add_argument("--market-dir", required=True, help="Path to market data root")
    parser.add_argument("--timeframe", default="1m", help="Market timeframe (default: 1m)")
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    market_dir = Path(args.market_dir)
    bases = [item.strip() for item in args.bases.split(",") if item.strip()]

    demand = SignalDemandScanner(args.db_path).scan(
        trader_id=args.trader_id or None,
        date_from=args.date_from or None,
        date_to=args.date_to or None,
        max_trades=max(0, int(args.max_trades)),
    )
    coverage_plan = CoveragePlanner().plan(demand)
    manifest = ManifestStore(root=market_dir / "manifests")
    coverage_index = manifest.load_coverage_index()

    payload: dict[str, object] = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "db_path": str(Path(args.db_path).resolve()),
        "market_dir": str(market_dir.resolve()),
        "timeframe": args.timeframe,
        "bases": bases,
        "chains_scanned": len(demand),
        "symbols": {},
        "source": args.source,
        "trader_filter": args.trader_id or "all",
        "date_from": args.date_from or "",
        "date_to": args.date_to or "",
        "max_trades": max(0, int(args.max_trades)),
    }
    request = build_market_request(
        db_path=args.db_path,
        market_data_dir=str(market_dir),
        trader_filter=args.trader_id or "all",
        date_from=args.date_from or "",
        date_to=args.date_to or "",
        max_trades=max(0, int(args.max_trades)),
        timeframe=args.timeframe,
        price_basis=bases[0] if bases else "last",
        source=args.source,
    )
    payload["market_request_fingerprint"] = market_request_fingerprint(request)

    total_required = 0
    total_gaps = 0
    symbols_payload: dict[str, object] = {}
    for symbol, intervals in coverage_plan.intervals_by_symbol.items():
        required_rows = [interval.to_dict() for interval in intervals]
        total_required += len(required_rows)
        basis_payload: dict[str, object] = {}
        for basis in bases:
            key = CoverageKey(
                exchange="bybit",
                market_type="futures_linear",
                timeframe=args.timeframe,
                symbol=symbol,
                basis=basis,
            )
            covered = next((record.covered_intervals for record in coverage_index if record.key == key), [])
            gaps = detect_gaps(required=intervals, covered=covered)
            gap_rows = [interval.to_dict() for interval in gaps]
            total_gaps += len(gap_rows)
            basis_payload[basis] = {
                "required_intervals": required_rows,
                "covered_intervals": [interval.to_dict() for interval in covered],
                "gaps": gap_rows,
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

    print(f"plan_file={output}")
    print(f"chains_scanned={len(demand)}")
    print(f"symbols={len(symbols_payload)}")
    print(f"required_intervals={total_required}")
    print(f"gaps={total_gaps}")
    print(f"market_request_fingerprint={payload['market_request_fingerprint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
