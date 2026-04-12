"""Run a multi-policy comparison report on the same dataset."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.signal_chain_lab.adapters.chain_adapter import adapt_signal_chain
from src.signal_chain_lab.adapters.chain_builder import SignalChainBuilder
from src.signal_chain_lab.policies.policy_loader import PolicyLoader
from src.signal_chain_lab.policy_report.comparison_runner import run_comparison_report


def _parse_date(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date format: {value}. Use YYYY-MM-DD") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _build_market_provider(market_dir: str, timeframe: str, price_basis: str):
    from src.signal_chain_lab.market.providers.bybit_parquet_provider import BybitParquetProvider
    root = Path(market_dir)
    if not root.exists():
        print(f"WARNING: market-dir not found ({root}), running without market provider")
        return None
    return BybitParquetProvider(market_dir=root, timeframe=timeframe, basis=price_basis)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a multi-policy comparison report on the same dataset"
    )
    parser.add_argument(
        "--policies", required=True,
        help="Comma-separated policy names or YAML paths (min 2), e.g. policy_a,policy_b",
    )
    parser.add_argument("--db-path",    required=True, help="Path to SQLite backtesting DB")
    parser.add_argument("--market-dir", required=True, help="Path to market data directory")
    parser.add_argument(
        "--price-basis", default="last", choices=["last", "mark"],
        help="Price basis for trigger evaluation (default: last)",
    )
    parser.add_argument(
        "--timeframe", default="1m",
        help="Market data timeframe (default: 1m)",
    )
    parser.add_argument("--date-from", type=_parse_date, default=None)
    parser.add_argument("--date-to",   type=_parse_date, default=None)
    parser.add_argument("--trader-id", default=None, help="Filter by trader_id")
    parser.add_argument("--max-trades", type=int, default=0, help="Max chains (0 = no limit)")
    parser.add_argument(
        "--output-dir", default=None,
        help="Output directory (default: artifacts/comparison_reports/<name>)",
    )
    parser.add_argument(
        "--initial-capital", type=float, default=None,
        help="Hypothetical capital for %% metric calculation (e.g. 10000)",
    )
    parser.add_argument(
        "--write-trade-artifacts", action="store_true", default=True,
        help="Write per-trade detail files (default: True)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    policy_names = [p.strip() for p in args.policies.split(",") if p.strip()]
    if len(policy_names) < 2:
        raise SystemExit("--policies requires at least 2 comma-separated policy names")

    loader = PolicyLoader()
    policies = [loader.load(name) for name in policy_names]

    chains = SignalChainBuilder.build_all(
        db_path=args.db_path,
        trader_id=args.trader_id,
        date_from=args.date_from.date().isoformat() if args.date_from else None,
        date_to=args.date_to.date().isoformat() if args.date_to else None,
    )
    canonical = [adapt_signal_chain(chain) for chain in chains]
    for chain in canonical:
        chain.metadata["timeframe"] = args.timeframe

    if args.date_from:
        canonical = [c for c in canonical if c.created_at.date() >= args.date_from.date()]
    if args.date_to:
        canonical = [c for c in canonical if c.created_at.date() <= args.date_to.date()]
    if args.trader_id:
        canonical = [c for c in canonical if c.trader_id == args.trader_id]
    if args.max_trades > 0:
        canonical = canonical[: args.max_trades]

    market_provider = _build_market_provider(
        market_dir=args.market_dir,
        timeframe=args.timeframe,
        price_basis=args.price_basis,
    )
    exchange_faithful = market_provider is not None

    run_name = "_vs_".join(policy_names)
    output_dir = Path(args.output_dir) if args.output_dir else (
        Path("artifacts") / "comparison_reports" / run_name
    )

    artifacts = run_comparison_report(
        chains=canonical,
        policies=policies,
        output_dir=output_dir,
        market_provider=market_provider,
        date_from=args.date_from,
        date_to=args.date_to,
        write_trade_artifacts=getattr(args, "write_trade_artifacts", True),
        dataset_metadata={
            "db_path": args.db_path,
            "market_dir": args.market_dir,
            "date_from": args.date_from.isoformat() if args.date_from else None,
            "date_to": args.date_to.isoformat() if args.date_to else None,
            "trader_filter": args.trader_id or "all",
            "timeframe": args.timeframe,
            "price_basis": args.price_basis,
        },
        price_basis=args.price_basis,
        exchange_faithful=exchange_faithful,
        initial_capital=getattr(args, "initial_capital", None),
    )

    print(f"policies={'|'.join(policy_names)}")
    print(f"chains_total={len(canonical)}")
    print(f"output_dir={artifacts.output_dir}")
    print(f"comparison_report={artifacts.comparison_html_path}")
    for pname, pdir in artifacts.per_policy_dirs.items():
        print(f"  policy_dir_{pname}={pdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
