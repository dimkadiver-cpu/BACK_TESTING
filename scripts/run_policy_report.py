"""Run a full dataset report for a single policy."""
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
from src.signal_chain_lab.policy_report.runner import run_policy_report


def _parse_date(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - argparse handles formatting as message
        raise argparse.ArgumentTypeError(f"Invalid date format: {value}. Use YYYY-MM-DD") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _build_market_provider(market_dir: str, timeframe: str, price_basis: str):
    from src.signal_chain_lab.market.providers.bybit_parquet_provider import BybitParquetProvider

    root = Path(market_dir)
    if not root.exists():
        print(f"WARNING: market-dir not found ({root}), running without market provider (PnL=0)")
        return None

    return BybitParquetProvider(
        market_dir=root,
        timeframe=timeframe,
        basis=price_basis,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a full dataset report for one policy")
    parser.add_argument("--policy", required=True, help="Policy name or YAML path")
    parser.add_argument("--db-path", required=True, help="Path to SQLite backtesting DB")
    parser.add_argument("--market-dir", required=True, help="Path to market data directory")
    parser.add_argument(
        "--price-basis",
        default="last",
        choices=["last", "mark"],
        help="Price basis for trigger evaluation: 'last' (default) or 'mark'",
    )
    parser.add_argument(
        "--timeframe",
        default="1m",
        help="Market data timeframe to load from provider (default: 1m)",
    )
    parser.add_argument("--date-from", type=_parse_date, default=None, help="Dataset start date (YYYY-MM-DD)")
    parser.add_argument("--date-to", type=_parse_date, default=None, help="Dataset end date (YYYY-MM-DD)")
    parser.add_argument("--trader-id", default=None, help="Filter chains by trader_id (default: all)")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for the policy report (default: artifacts/policy_reports/<policy_name>)",
    )
    parser.add_argument(
        "--write-trade-artifacts",
        action="store_true",
        default=True,
        help="Write per-trade drill-down artifacts under trades/<signal_id>/",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if "," in args.policy:
        raise SystemExit("Exactly one policy is required; do not pass a comma-separated list")

    loader = PolicyLoader()
    policy = loader.load(args.policy)

    chains = SignalChainBuilder.build_all(db_path=args.db_path)
    canonical = [adapt_signal_chain(chain) for chain in chains]
    for chain in canonical:
        chain.metadata["timeframe"] = args.timeframe

    if args.date_from is not None:
        canonical = [chain for chain in canonical if chain.created_at >= args.date_from]
    if args.date_to is not None:
        canonical = [chain for chain in canonical if chain.created_at <= args.date_to]
    if args.trader_id:
        canonical = [chain for chain in canonical if chain.trader_id == args.trader_id]

    market_provider = _build_market_provider(
        market_dir=args.market_dir,
        timeframe=args.timeframe,
        price_basis=args.price_basis,
    )
    exchange_faithful = market_provider is not None

    output_dir = Path(args.output_dir) if args.output_dir else Path("artifacts") / "policy_reports" / policy.name
    artifacts = run_policy_report(
        chains=canonical,
        policy=policy,
        output_dir=output_dir,
        market_provider=market_provider,
        date_from=args.date_from,
        date_to=args.date_to,
        write_trade_artifacts=args.write_trade_artifacts,
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
    )

    print(f"policy={policy.name}")
    print(f"chains_total={len(canonical)}")
    print(f"price_basis={args.price_basis}")
    print(f"exchange_faithful={str(exchange_faithful).lower()}")
    print(f"output_dir={artifacts.output_dir}")
    print(f"policy_summary_json={artifacts.summary_json_path}")
    print(f"policy_summary_csv={artifacts.summary_csv_path}")
    print(f"trade_results_csv={artifacts.trade_results_csv_path}")
    print(f"excluded_chains_csv={artifacts.excluded_chains_csv_path}")
    print(f"policy_report_html={artifacts.html_report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
