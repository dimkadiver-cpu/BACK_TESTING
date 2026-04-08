"""Run scenario backtests: same dataset, multiple policies, aggregated comparison."""
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
from src.signal_chain_lab.scenario.runner import compare_scenarios, run_scenarios, write_scenario_artifacts


def _parse_date(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - argparse handles formatting as message
        raise argparse.ArgumentTypeError(f"Invalid date format: {value}. Use YYYY-MM-DD") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run multi-policy scenario simulation")
    parser.add_argument(
        "--policy",
        required=True,
        help="Comma-separated policies, e.g. original_chain,signal_only",
    )
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
    return parser.parse_args()


def _build_market_provider(market_dir: str, timeframe: str, price_basis: str):
    """Instantiate BybitParquetProvider.  Returns None if market-dir is empty or absent."""
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


def main() -> int:
    args = parse_args()

    policy_names = [item.strip() for item in args.policy.split(",") if item.strip()]
    if len(policy_names) < 2:
        raise SystemExit("At least two policies are required for scenario comparison")

    loader = PolicyLoader()
    policies = [loader.load(name) for name in policy_names]

    chains = SignalChainBuilder.build_all(db_path=args.db_path)
    canonical = [adapt_signal_chain(chain) for chain in chains]
    for chain in canonical:
        chain.metadata["timeframe"] = args.timeframe

    if args.date_from is not None:
        canonical = [chain for chain in canonical if chain.created_at >= args.date_from]
    if args.date_to is not None:
        canonical = [chain for chain in canonical if chain.created_at <= args.date_to]

    market_provider = _build_market_provider(
        market_dir=args.market_dir,
        timeframe=args.timeframe,
        price_basis=args.price_basis,
    )

    # exchange_faithful: True when using Bybit as the canonical provider
    # (market-dir must exist and basis must be declared)
    exchange_faithful = market_provider is not None

    scenario_results, per_policy_trades = run_scenarios(
        canonical,
        policies,
        market_provider=market_provider,
        price_basis=args.price_basis,
        exchange_faithful=exchange_faithful,
    )
    comparisons = compare_scenarios(scenario_results, baseline_policy=policies[0].name)

    output_dir = Path("artifacts") / "scenarios"
    scenario_path, comparison_path, csv_path, html_path = write_scenario_artifacts(
        scenario_results=scenario_results,
        comparisons=comparisons,
        output_dir=output_dir,
        per_policy_trades=per_policy_trades,
    )

    print(f"chains_selected={len(canonical)}")
    print(f"policies={','.join(policy_names)}")
    print(f"price_basis={args.price_basis}")
    print(f"exchange_faithful={str(exchange_faithful).lower()}")
    print(f"scenario_results={scenario_path}")
    print(f"scenario_comparison={comparison_path}")
    if csv_path:
        print(f"trade_results_csv={csv_path}")
    if html_path:
        print(f"scenario_html={html_path}")
    print("Summary:")
    for result in scenario_results:
        print(
            f"- {result.policy_name}: pnl={result.total_pnl:.4f}, win_rate={result.win_rate:.2%}, "
            f"expectancy={result.expectancy:.4f}, trades={result.trades_count}, excluded={result.excluded_chains_count}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
