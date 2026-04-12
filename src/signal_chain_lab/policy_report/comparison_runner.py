"""Run and compare multiple policies on the same dataset, then write a comparison report."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.signal_chain_lab.domain.events import CanonicalChain
from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult
from src.signal_chain_lab.market.data_models import MarketDataProvider
from src.signal_chain_lab.policies.base import PolicyConfig
from src.signal_chain_lab.policy_report.html_writer import (
    flatten_policy_values,
    write_comparison_html_report,
    write_policy_html_report,
    write_single_trade_html_report,
)
from src.signal_chain_lab.policy_report.runner import (
    _assign_cum_equity_pct,
    _aggregate_policy_results,
    _build_summary,
    _copy_chart_assets,
    _load_trade_chart_candles_by_timeframe,
    _run_policy_dataset,
    _safe_dirname,
    _write_excluded_chains_csv,
    _write_single_row_csv,
    filter_chains_by_date,
)
from src.signal_chain_lab.reports.chain_plot import write_chain_plot_html, write_chain_plot_png
from src.signal_chain_lab.reports.event_log_report import write_event_log_jsonl
from src.signal_chain_lab.reports.trade_report import build_trade_result, write_trade_results_csv


_ECHARTS_SOURCE = Path(__file__).parent / "assets" / "echarts.min.js"


@dataclass
class ComparisonArtifacts:
    output_dir: Path
    comparison_html_path: Path
    per_policy_dirs: dict[str, Path]


@dataclass
class ChangedTrade:
    signal_id: str
    symbol: str
    results: dict[str, TradeResult]   # policy_name → TradeResult
    detail_links: dict[str, str]      # policy_name → relative link to detail.html


def _compute_changed_trades(
    results_by_policy: dict[str, list[TradeResult]],
) -> list[ChangedTrade]:
    """Return trades that differ in close_reason or realised_pnl sign across policies."""
    # Index by signal_id per policy
    by_sid: dict[str, dict[str, TradeResult]] = {}
    for policy_name, results in results_by_policy.items():
        for tr in results:
            by_sid.setdefault(tr.signal_id, {})[policy_name] = tr

    policy_names = list(results_by_policy.keys())
    changed: list[ChangedTrade] = []
    for sid, per_policy in by_sid.items():
        if len(per_policy) < 2:
            changed.append(ChangedTrade(
                signal_id=sid,
                symbol=next(iter(per_policy.values())).symbol,
                results=per_policy,
                detail_links={},
            ))
            continue
        trades = list(per_policy.values())
        # Check if any pair differs
        first = trades[0]
        differs = False
        for other in trades[1:]:
            pnl_sign_a = 1 if first.realized_pnl > 0 else (-1 if first.realized_pnl < 0 else 0)
            pnl_sign_b = 1 if other.realized_pnl > 0 else (-1 if other.realized_pnl < 0 else 0)
            if (pnl_sign_a != pnl_sign_b) or (first.close_reason != other.close_reason):
                differs = True
                break
        if differs:
            changed.append(ChangedTrade(
                signal_id=sid,
                symbol=first.symbol,
                results=per_policy,
                detail_links={},
            ))
    return changed


def _delta_metrics(
    results_by_policy: dict[str, list[TradeResult]],
    initial_capital: float | None,
    price_basis: str,
    exchange_faithful: bool,
) -> dict[str, dict[str, object]]:
    """Build per-policy summary metrics for comparison."""
    summaries: dict[str, dict[str, object]] = {}
    for policy_name, results in results_by_policy.items():
        agg = _aggregate_policy_results(
            policy_name=policy_name,
            trade_results=results,
            excluded=0,
            price_basis=price_basis,
            exchange_faithful=exchange_faithful,
            initial_capital=initial_capital,
        )
        summaries[policy_name] = {
            "total_return_pct":      agg.get("total_return_pct"),
            "max_drawdown_pct":      agg.get("max_drawdown_pct"),
            "expectancy_pct":        agg.get("expectancy_pct"),
            "win_rate_pct":          float(agg["win_rate"]) * 100.0,
            "profit_factor":         float(agg["profit_factor"]),
            "avg_trade_impact_pct":  agg.get("avg_trade_impact_pct"),
            "best_trade_pct":        agg.get("best_trade_pct"),
            "worst_trade_pct":       agg.get("worst_trade_pct"),
            "trades_count":          int(agg["trades_count"]),
            "total_pnl":             float(agg["total_pnl"]),
        }
    return summaries


def _write_policy_subtree(
    *,
    policy_name: str,
    output_dir: Path,
    trade_results: list[TradeResult],
    excluded_chains: list[dict[str, str]],
    event_logs_by_signal_id: dict[str, list[EventLogEntry]],
    chains_by_signal_id: dict[str, CanonicalChain],
    market_provider: MarketDataProvider | None,
    summary: dict[str, object],
    dataset_metadata: dict[str, object],
    policy: PolicyConfig,
    initial_capital: float | None,
) -> dict[str, str]:
    """Write per-policy sub-directory and return signal_id → relative detail path."""
    _copy_chart_assets(output_dir)
    trade_detail_links: dict[str, str] = {}
    trades_dir = output_dir / "trades"
    dir_names = [_safe_dirname(t.signal_id) for t in trade_results]
    echarts_rel = "../../../assets/echarts.min.js"

    for index, trade in enumerate(trade_results):
        signal_dir = trades_dir / dir_names[index]
        event_log = event_logs_by_signal_id.get(trade.signal_id, [])
        chart_candles = _load_trade_chart_candles_by_timeframe(
            trade=trade,
            chain=chains_by_signal_id.get(trade.signal_id),
            market_provider=market_provider,
            event_log=event_log,
        )
        prev_link = f"../{dir_names[index - 1]}/detail.html" if index > 0 else None
        next_link = f"../{dir_names[index + 1]}/detail.html" if index < len(trade_results) - 1 else None
        write_event_log_jsonl(event_log, signal_dir / "event_log.jsonl")
        write_trade_results_csv([trade], signal_dir / "trade_result.csv")
        write_chain_plot_png(event_log, signal_dir / "equity_curve.png")
        write_chain_plot_html(event_log, signal_dir / "equity_curve.html",
                              title=f"{trade.signal_id} - {policy_name}")
        write_single_trade_html_report(
            trade=trade,
            event_log=event_log,
            output_path=signal_dir / "detail.html",
            candles_by_timeframe=chart_candles,
            echarts_asset_path=echarts_rel,
            back_link_href=f"../../policy_report.html",
            prev_link=prev_link,
            next_link=next_link,
            trade_index=index + 1,
            trades_total=len(trade_results),
            initial_capital=initial_capital,
        )
        rel = f"trades/{dir_names[index]}/detail.html"
        trade_detail_links[trade.signal_id] = rel

    # Per-policy policy_report.html
    policy_values = flatten_policy_values(policy.model_dump(mode="json", by_alias=True))
    write_policy_html_report(
        summary=summary,
        trade_results=trade_results,
        excluded_chains=excluded_chains,
        dataset_metadata=dataset_metadata,
        policy_values=policy_values,
        output_path=output_dir / "policy_report.html",
        trade_detail_links=trade_detail_links,
        title=f"Policy Report - {policy_name}",
    )
    write_trade_results_csv(trade_results, output_dir / "trade_results.csv")
    _write_excluded_chains_csv(excluded_chains, output_dir / "excluded_chains.csv")
    (output_dir / "policy_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "policy.yaml").write_text(
        yaml.safe_dump(policy.model_dump(mode="json", by_alias=True), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return trade_detail_links


def run_comparison_report(
    *,
    chains: list[CanonicalChain],
    policies: list[PolicyConfig],
    output_dir: str | Path,
    market_provider: MarketDataProvider | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    write_trade_artifacts: bool = True,
    dataset_metadata: dict[str, object] | None = None,
    price_basis: str = "last",
    exchange_faithful: bool = True,
    initial_capital: float | None = None,
) -> ComparisonArtifacts:
    if len(policies) < 2:
        raise ValueError("run_comparison_report requires at least 2 policies")

    selected_chains = filter_chains_by_date(chains, date_from=date_from, date_to=date_to)
    chains_by_signal_id = {chain.signal_id: chain for chain in selected_chains}

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    # Copy shared assets to root
    assets_dest = root / "assets" / "echarts.min.js"
    assets_dest.parent.mkdir(parents=True, exist_ok=True)
    if _ECHARTS_SOURCE.exists() and not assets_dest.exists():
        shutil.copy2(_ECHARTS_SOURCE, assets_dest)

    # Run each policy
    results_by_policy: dict[str, list[TradeResult]] = {}
    excluded_by_policy: dict[str, list[dict[str, str]]] = {}
    event_logs_by_policy: dict[str, dict[str, list[EventLogEntry]]] = {}
    summaries_by_policy: dict[str, dict[str, object]] = {}
    policy_dirs: dict[str, Path] = {}

    meta_base = dict(dataset_metadata or {})

    for policy in policies:
        pname = policy.name
        trade_results, excluded_chains, event_logs = _run_policy_dataset(
            chains=selected_chains,
            policy=policy,
            market_provider=market_provider,
            initial_capital=initial_capital,
        )
        if initial_capital and initial_capital > 0:
            _assign_cum_equity_pct(trade_results, initial_capital)

        results_by_policy[pname] = trade_results
        excluded_by_policy[pname] = excluded_chains
        event_logs_by_policy[pname] = event_logs

        summary = _build_summary(
            policy_name=pname,
            chains_total=len(chains),
            chains_selected=len(selected_chains),
            trade_results=trade_results,
            excluded_chains=excluded_chains,
            price_basis=price_basis,
            exchange_faithful=exchange_faithful,
            initial_capital=initial_capital,
        )
        summaries_by_policy[pname] = summary

        policy_dir = root / pname
        policy_dir.mkdir(parents=True, exist_ok=True)
        policy_dirs[pname] = policy_dir

        dataset_meta_for_policy = {
            "Run Id": f"comparison_{pname}",
            "Dataset Name": meta_base.get("dataset_name") or meta_base.get("db_path") or "dataset",
            "Source Db": meta_base.get("db_path") or "-",
            "Trader Filter": meta_base.get("trader_filter") or "all",
            "Period Start": meta_base.get("date_from") or "-",
            "Period End": meta_base.get("date_to") or "-",
            "Initial Capital": initial_capital if initial_capital is not None else "-",
            "Price Basis": price_basis,
            "Selected Chains": len(selected_chains),
            "Simulable Chains": len(trade_results),
            "Excluded Chains": len(excluded_chains),
            "Generated At": summary["generated_at"],
        }

        if write_trade_artifacts:
            _write_policy_subtree(
                policy_name=pname,
                output_dir=policy_dir,
                trade_results=trade_results,
                excluded_chains=excluded_chains,
                event_logs_by_signal_id=event_logs,
                chains_by_signal_id=chains_by_signal_id,
                market_provider=market_provider,
                summary=summary,
                dataset_metadata=dataset_meta_for_policy,
                policy=policy,
                initial_capital=initial_capital,
            )

    # Compute changed trades
    changed_trades = _compute_changed_trades(results_by_policy)

    # Attach detail links to changed trades
    if write_trade_artifacts:
        for ct in changed_trades:
            for pname, policy_dir in policy_dirs.items():
                tr = ct.results.get(pname)
                if tr is not None:
                    dirname = _safe_dirname(tr.signal_id)
                    ct.detail_links[pname] = f"{pname}/trades/{dirname}/detail.html"

    # Compute per-policy delta metrics
    delta = _delta_metrics(results_by_policy, initial_capital, price_basis, exchange_faithful)

    # Build comparison report
    comparison_html_path = write_comparison_html_report(
        policies=policies,
        summaries_by_policy=summaries_by_policy,
        delta_metrics=delta,
        changed_trades=changed_trades,
        output_path=root / "comparison_report.html",
        dataset_metadata=meta_base,
        initial_capital=initial_capital,
    )

    return ComparisonArtifacts(
        output_dir=root,
        comparison_html_path=comparison_html_path,
        per_policy_dirs=policy_dirs,
    )
