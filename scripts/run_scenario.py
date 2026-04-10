"""Run a single-policy backtest and produce a self-contained report."""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.signal_chain_lab.adapters.chain_adapter import adapt_signal_chain
from src.signal_chain_lab.adapters.chain_builder import SignalChainBuilder
from src.signal_chain_lab.policies.policy_loader import PolicyLoader
from src.signal_chain_lab.policy_report.runner import run_policy_report
from src.signal_chain_lab.scenario.runner import run_scenarios, write_scenario_artifacts


def _parse_date(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - argparse handles formatting as message
        raise argparse.ArgumentTypeError(f"Invalid date format: {value}. Use YYYY-MM-DD") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run single-policy backtest")
    parser.add_argument(
        "--policy",
        default=None,
        help="Single policy name, e.g. original_chain (backward compatible)",
    )
    parser.add_argument(
        "--policies",
        nargs="+",
        default=None,
        help="One or more policy names. Supports both repeated values and comma-separated entries.",
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
    parser.add_argument("--trader-id", default=None, help="Filter chains by trader_id (default: all)")
    parser.add_argument("--max-trades", type=int, default=0, help="Max chains to backtest (0 = no limit)")
    parser.add_argument(
        "--output-dir",
        default="artifacts/scenarios",
        help="Directory for scenario artifacts (default: artifacts/scenarios)",
    )
    return parser.parse_args()


def _normalize_policy_names(args: argparse.Namespace) -> list[str]:
    names: list[str] = []
    if args.policy:
        names.append(args.policy.strip())
    if args.policies:
        for item in args.policies:
            for raw in item.split(","):
                cleaned = raw.strip()
                if cleaned:
                    names.append(cleaned)
    deduped: list[str] = []
    for name in names:
        if name not in deduped:
            deduped.append(name)
    return deduped


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


def _safe_dirname(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\\\|?*]+', "_", value).strip()
    return sanitized or "policy"


def _write_comparison_report(
    *,
    scenario_results,
    output_dir: Path,
    run_metadata: dict[str, object],
) -> tuple[Path, Path, Path]:
    rows = []
    for result in scenario_results:
        policy_name = result.policy_name
        rows.append(
            {
                "policy_name": policy_name,
                "trades_count": result.trades_count,
                "excluded_chains_count": result.excluded_chains_count,
                "win_rate_pct": result.win_rate * 100.0,
                "net_profit_pct": result.total_pnl,
                "profit_factor": result.profit_factor,
                "expectancy_pct": result.expectancy,
                "max_drawdown_pct": result.max_drawdown,
                "avg_warnings_per_trade": result.avg_warnings_per_trade,
                "policy_report": f"{_safe_dirname(policy_name)}/policy_report.html",
            }
        )

    summary_json = output_dir / "comparison_summary.json"
    summary_json.write_text(
        json.dumps({"run_metadata": run_metadata, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary_csv = output_dir / "comparison_summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["policy_name"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    html_rows = []
    for row in rows:
        html_rows.append(
            "<tr>"
            f"<td>{row['policy_name']}</td>"
            f"<td>{row['trades_count']}</td>"
            f"<td>{row['excluded_chains_count']}</td>"
            f"<td>{row['win_rate_pct']:.2f}%</td>"
            f"<td>{row['net_profit_pct']:.2f}%</td>"
            f"<td>{row['profit_factor']:.2f}</td>"
            f"<td>{row['expectancy_pct']:.2f}%</td>"
            f"<td>{row['max_drawdown_pct']:.2f}%</td>"
            f"<td>{row['avg_warnings_per_trade']:.2f}</td>"
            f"<td><a href=\"{row['policy_report']}\">Open Policy Report</a></td>"
            "</tr>"
        )

    comparison_html = output_dir / "comparison_report.html"
    comparison_html.write_text(
        f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Comparison Report</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;background:#f8fafc;color:#0f172a}}.wrap{{max-width:1200px;margin:0 auto;padding:24px}}.card{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin-bottom:16px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left}}th{{font-size:12px;text-transform:uppercase;color:#64748b}}</style>
</head><body><div class="wrap">
<h1>Comparison Report</h1>
<div class="card"><strong>Dataset:</strong> {run_metadata.get("dataset_name", "-")}<br>
<strong>Source DB:</strong> {run_metadata.get("db_path", "-")}<br>
<strong>Date range:</strong> {run_metadata.get("date_from", "-")} → {run_metadata.get("date_to", "-")}<br>
<strong>Trader filter:</strong> {run_metadata.get("trader_filter", "all")}<br>
<strong>Timeframe:</strong> {run_metadata.get("timeframe", "-")}<br>
<strong>Price basis:</strong> {run_metadata.get("price_basis", "-")}<br>
<strong>Policies:</strong> {len(rows)}<br>
<strong>Generated at:</strong> {run_metadata.get("generated_at", "-")}</div>
<div class="card"><table><thead><tr><th>Policy</th><th>Trades</th><th>Excluded chains</th><th>Win rate %</th><th>Net Profit %</th><th>Profit factor</th><th>Expectancy %</th><th>Max drawdown %</th><th>Avg warnings / trade</th><th>Open Policy Report</th></tr></thead><tbody>{''.join(html_rows)}</tbody></table></div>
</div></body></html>""",
        encoding="utf-8",
    )
    return comparison_html, summary_json, summary_csv


def main() -> int:
    args = parse_args()

    policy_names = _normalize_policy_names(args)
    if not policy_names:
        raise SystemExit("At least one policy is required via --policy or --policies")

    loader = PolicyLoader()
    policies = [loader.load(name) for name in policy_names]

    chains = SignalChainBuilder.build_all(db_path=args.db_path)
    canonical = [adapt_signal_chain(chain) for chain in chains]
    for chain in canonical:
        chain.metadata["timeframe"] = args.timeframe

    # Apply dataset filters
    if args.date_from is not None:
        canonical = [chain for chain in canonical if chain.created_at >= args.date_from]
    if args.date_to is not None:
        canonical = [chain for chain in canonical if chain.created_at <= args.date_to]
    if args.trader_id:
        canonical = [chain for chain in canonical if chain.trader_id == args.trader_id]
    if args.max_trades > 0:
        canonical = canonical[: args.max_trades]

    market_provider = _build_market_provider(
        market_dir=args.market_dir,
        timeframe=args.timeframe,
        price_basis=args.price_basis,
    )

    exchange_faithful = market_provider is not None

    scenario_results, per_policy_trades = run_scenarios(
        canonical,
        policies,
        market_provider=market_provider,
        price_basis=args.price_basis,
        exchange_faithful=exchange_faithful,
    )

    output_dir = Path(args.output_dir)
    scenario_path, csv_path, html_path = write_scenario_artifacts(
        scenario_results=scenario_results,
        output_dir=output_dir,
        per_policy_trades=per_policy_trades,
    )

    if len(policies) > 1:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        comparison_root = output_dir / "comparison" / run_id
        comparison_root.mkdir(parents=True, exist_ok=True)
        dataset_metadata = {
            "run_id": run_id,
            "dataset_name": Path(args.db_path).name,
            "db_path": args.db_path,
            "trader_filter": args.trader_id or "all",
            "date_from": args.date_from.date().isoformat() if args.date_from else "-",
            "date_to": args.date_to.date().isoformat() if args.date_to else "-",
            "timeframe": args.timeframe,
            "price_basis": args.price_basis,
            "market_provider": "bybit" if market_provider is not None else "none",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        for policy in policies:
            policy_dir = comparison_root / _safe_dirname(policy.name)
            run_policy_report(
                chains=canonical,
                policy=policy,
                output_dir=policy_dir,
                market_provider=market_provider,
                date_from=args.date_from,
                date_to=args.date_to,
                dataset_metadata=dataset_metadata,
                price_basis=args.price_basis,
                exchange_faithful=exchange_faithful,
            )
        comparison_html, _, _ = _write_comparison_report(
            scenario_results=scenario_results,
            output_dir=comparison_root,
            run_metadata=dataset_metadata,
        )
        html_path = comparison_html

    log_path = Path(args.output_dir) / "LOG.html"

    print(f"chains_selected={len(canonical)}")
    print(f"policies={','.join(policy_names)}")
    print(f"price_basis={args.price_basis}")
    print(f"exchange_faithful={str(exchange_faithful).lower()}")
    print(f"scenario_results={scenario_path}")
    if csv_path:
        print(f"trade_results_csv={csv_path}")
    if html_path:
        print(f"scenario_html={html_path}")
    print(f"artifacts_log={log_path}")
    print("Summary:")
    for result in scenario_results:
        print(
            f"- {result.policy_name}: pnl={result.total_pnl:.4f}, win_rate={result.win_rate:.2%}, "
            f"expectancy={result.expectancy:.4f}, trades={result.trades_count}, excluded={result.excluded_chains_count}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
