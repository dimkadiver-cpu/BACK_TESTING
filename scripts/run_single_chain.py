"""Run the simulator on a single signal chain.

Usage:
    python scripts/run_single_chain.py --signal-id <id> --policy original_chain --db-path db/backtest.sqlite3 --market-dir data/market
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

from src.signal_chain_lab.adapters.chain_adapter import adapt_signal_chain
from src.signal_chain_lab.adapters.chain_builder import SignalChainBuilder
from src.signal_chain_lab.adapters.validators import validate_chain_for_simulation
from src.signal_chain_lab.engine.simulator import simulate_chain
from src.signal_chain_lab.policies.policy_loader import PolicyLoader
from src.signal_chain_lab.reports.chain_plot import write_chain_plot_html, write_chain_plot_png
from src.signal_chain_lab.reports.event_log_report import write_event_log_jsonl
from src.signal_chain_lab.reports.trade_report import (
    build_trade_result,
    write_trade_result_parquet,
    write_trade_results_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run single-chain simulation")
    parser.add_argument("--signal-id", required=True, help="Signal chain id (chain_id)")
    parser.add_argument("--policy", required=True, help="Policy name or YAML path")
    parser.add_argument("--db-path", required=True, help="Path to SQLite backtesting DB")
    parser.add_argument("--market-dir", required=True, help="Path to market data directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    policy = PolicyLoader().load(args.policy)

    chains = SignalChainBuilder.build_all(db_path=args.db_path)
    chain = next((item for item in chains if item.chain_id == args.signal_id), None)
    if chain is None:
        raise SystemExit(f"signal_id not found: {args.signal_id}")

    canonical_chain = adapt_signal_chain(chain)
    validation = validate_chain_for_simulation(canonical_chain)
    if not validation.is_simulable:
        details = ", ".join(f"{gap.field}:{gap.message}" for gap in validation.fatal_gaps)
        raise SystemExit(f"chain is not simulable: {details}")

    _ = Path(args.market_dir)  # reserved for market providers integration
    event_log, state = simulate_chain(canonical_chain, policy=policy, market_provider=None)

    out_dir = Path("artifacts") / _safe_path_component(canonical_chain.signal_id) / _safe_path_component(policy.name)
    event_log_path = write_event_log_jsonl(event_log, out_dir / "event_log.jsonl")
    trade_result = build_trade_result(state, event_log)
    trade_result_path = write_trade_result_parquet(trade_result, out_dir / "trade_result.parquet")
    csv_path = write_trade_results_csv([trade_result], out_dir / "trade_result.csv")
    png_path = write_chain_plot_png(event_log, out_dir / "equity_curve.png")
    html_path = write_chain_plot_html(
        event_log,
        out_dir / "equity_curve.html",
        title=f"{canonical_chain.signal_id} — {policy.name}",
    )

    print(f"policy={policy.name}")
    print(f"event_log={event_log_path}")
    print(f"trade_result={trade_result_path}")
    print(f"trade_result_csv={csv_path}")
    print(f"equity_png={png_path}")
    print(f"equity_html={html_path}")
    return 0


def _safe_path_component(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\\\|?*]+', "_", value).strip()
    sanitized = sanitized.rstrip(". ")
    return sanitized or "unnamed"


if __name__ == "__main__":
    raise SystemExit(main())
