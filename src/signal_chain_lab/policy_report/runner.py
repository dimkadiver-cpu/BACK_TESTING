"""Run and write a full dataset report for a single policy."""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.signal_chain_lab.adapters.validators import validate_chain_for_simulation
from src.signal_chain_lab.domain.events import CanonicalChain
from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult
from src.signal_chain_lab.engine.simulator import simulate_chain
from src.signal_chain_lab.market.data_models import MarketDataProvider
from src.signal_chain_lab.policies.base import PolicyConfig
from src.signal_chain_lab.policy_report.html_writer import write_policy_html_report
from src.signal_chain_lab.reports.chain_plot import write_chain_plot_html, write_chain_plot_png
from src.signal_chain_lab.reports.event_log_report import write_event_log_jsonl
from src.signal_chain_lab.reports.trade_report import build_trade_result, write_trade_results_csv


@dataclass
class PolicyReportArtifacts:
    output_dir: Path
    summary_json_path: Path
    summary_csv_path: Path
    trade_results_csv_path: Path
    excluded_chains_csv_path: Path
    html_report_path: Path


def _safe_dirname(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\\\|?*]+', "_", value).strip()
    return sanitized or "unknown_signal"


def filter_chains_by_date(
    chains: list[CanonicalChain],
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[CanonicalChain]:
    selected = chains
    if date_from is not None:
        selected = [chain for chain in selected if chain.created_at >= date_from]
    if date_to is not None:
        selected = [chain for chain in selected if chain.created_at <= date_to]
    return selected


def _compute_max_drawdown(pnl_series: list[float]) -> float:
    if not pnl_series:
        return 0.0

    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for pnl in pnl_series:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        drawdown = peak - cumulative
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    return max_drawdown


def _aggregate_policy_results(
    *,
    policy_name: str,
    trade_results: list[TradeResult],
    excluded: int,
    price_basis: str,
    exchange_faithful: bool,
) -> dict[str, object]:
    trades_count = len(trade_results)
    realized = [item.realized_pnl for item in trade_results]
    wins = [pnl for pnl in realized if pnl > 0.0]
    losses = [pnl for pnl in realized if pnl < 0.0]

    total_pnl = sum(realized)
    gross_profit = sum(wins)
    gross_loss_abs = abs(sum(losses))
    win_rate = (len(wins) / trades_count) if trades_count else 0.0
    expectancy = (total_pnl / trades_count) if trades_count else 0.0
    return_pct = (total_pnl / trades_count) if trades_count else 0.0
    profit_factor = (gross_profit / gross_loss_abs) if gross_loss_abs > 0.0 else 0.0
    avg_warnings = (
        sum(item.warnings_count for item in trade_results) / trades_count if trades_count else 0.0
    )

    return {
        "policy_name": policy_name,
        "total_pnl": total_pnl,
        "return_pct": return_pct,
        "max_drawdown": _compute_max_drawdown(realized),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "trades_count": trades_count,
        "simulated_chains_count": trades_count,
        "excluded_chains_count": excluded,
        "avg_warnings_per_trade": avg_warnings,
        "price_basis": price_basis,
        "exchange_faithful": exchange_faithful,
    }


def _build_exclusion_record(chain: CanonicalChain, reason_code: str, reason_message: str) -> dict[str, str]:
    return {
        "signal_id": chain.signal_id,
        "reason_code": reason_code,
        "reason_message": reason_message,
    }


def _validation_exclusion_record(chain: CanonicalChain) -> dict[str, str] | None:
    validation = validate_chain_for_simulation(chain)
    if validation.is_simulable:
        return None

    fatal_gaps = validation.fatal_gaps
    if fatal_gaps:
        primary_gap = fatal_gaps[0]
        reason_message = "; ".join(f"{gap.field}: {gap.message}" for gap in fatal_gaps)
        return _build_exclusion_record(chain, primary_gap.field, reason_message)

    return _build_exclusion_record(
        chain,
        "validation_failed",
        "chain failed validation for simulation",
    )


def _run_policy_dataset(
    *,
    chains: list[CanonicalChain],
    policy: PolicyConfig,
    market_provider: MarketDataProvider | None,
) -> tuple[list[TradeResult], list[dict[str, str]], dict[str, list[EventLogEntry]]]:
    trade_results: list[TradeResult] = []
    excluded_chains: list[dict[str, str]] = []
    event_logs_by_signal_id: dict[str, list[EventLogEntry]] = {}

    for chain in chains:
        exclusion = _validation_exclusion_record(chain)
        if exclusion is not None:
            excluded_chains.append(exclusion)
            continue

        event_log, state = simulate_chain(chain, policy=policy, market_provider=market_provider)
        event_logs_by_signal_id[chain.signal_id] = event_log
        trade_results.append(build_trade_result(state, event_log))

    return trade_results, excluded_chains, event_logs_by_signal_id


def _build_summary(
    *,
    policy_name: str,
    chains_total: int,
    chains_selected: int,
    trade_results: list[TradeResult],
    excluded_chains: list[dict[str, str]],
    price_basis: str,
    exchange_faithful: bool,
) -> dict[str, object]:
    aggregated = _aggregate_policy_results(
        policy_name=policy_name,
        trade_results=trade_results,
        excluded=len(excluded_chains),
        price_basis=price_basis,
        exchange_faithful=exchange_faithful,
    )
    excluded_reasons = Counter(item["reason_code"] for item in excluded_chains)
    total_ignored_events = sum(item.ignored_events_count for item in trade_results)

    return {
        "policy_name": str(aggregated["policy_name"]),
        "chains_total": chains_total,
        "chains_selected": chains_selected,
        "chains_simulated": int(aggregated["simulated_chains_count"]),
        "chains_excluded": int(aggregated["excluded_chains_count"]),
        "excluded_reasons_summary": dict(sorted(excluded_reasons.items())),
        "trades_count": int(aggregated["trades_count"]),
        "total_pnl": float(aggregated["total_pnl"]),
        "return_pct": float(aggregated["return_pct"]),
        "max_drawdown": float(aggregated["max_drawdown"]),
        "win_rate": float(aggregated["win_rate"]),
        "profit_factor": float(aggregated["profit_factor"]),
        "expectancy": float(aggregated["expectancy"]),
        "avg_warnings_per_trade": float(aggregated["avg_warnings_per_trade"]),
        "total_ignored_events": total_ignored_events,
        "price_basis": price_basis,
        "exchange_faithful": exchange_faithful,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _write_single_row_csv(row: dict[str, object], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)
    return path


def _write_excluded_chains_csv(excluded_chains: list[dict[str, str]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["signal_id", "reason_code", "reason_message"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in excluded_chains:
            writer.writerow(row)
    return path


def _write_trade_artifacts(
    *,
    output_dir: Path,
    trade_results: list[TradeResult],
    event_logs_by_signal_id: dict[str, list[EventLogEntry]],
) -> dict[str, str]:
    trade_detail_links: dict[str, str] = {}
    trades_dir = output_dir / "trades"
    for trade in trade_results:
        signal_dir = trades_dir / _safe_dirname(trade.signal_id)
        event_log = event_logs_by_signal_id.get(trade.signal_id, [])
        write_event_log_jsonl(event_log, signal_dir / "event_log.jsonl")
        write_trade_results_csv([trade], signal_dir / "trade_result.csv")
        write_chain_plot_png(event_log, signal_dir / "equity_curve.png")
        write_chain_plot_html(
            event_log,
            signal_dir / "equity_curve.html",
            title=f"{trade.signal_id} - {trade.policy_name}",
        )
        trade_detail_links[trade.signal_id] = f"trades/{signal_dir.name}/equity_curve.html"
    return trade_detail_links


def run_policy_report(
    *,
    chains: list[CanonicalChain],
    policy: PolicyConfig,
    output_dir: str | Path,
    market_provider: MarketDataProvider | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    write_trade_artifacts: bool = False,
    dataset_metadata: dict[str, object] | None = None,
    price_basis: str = "last",
    exchange_faithful: bool = True,
) -> PolicyReportArtifacts:
    selected_chains = filter_chains_by_date(chains, date_from=date_from, date_to=date_to)
    trade_results, excluded_chains, event_logs_by_signal_id = _run_policy_dataset(
        chains=selected_chains,
        policy=policy,
        market_provider=market_provider,
    )

    summary = _build_summary(
        policy_name=policy.name,
        chains_total=len(chains),
        chains_selected=len(selected_chains),
        trade_results=trade_results,
        excluded_chains=excluded_chains,
        price_basis=price_basis,
        exchange_faithful=exchange_faithful,
    )

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    summary_json_path = directory / "policy_summary.json"
    summary_json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_csv_path = _write_single_row_csv(summary, directory / "policy_summary.csv")
    trade_results_csv_path = write_trade_results_csv(trade_results, directory / "trade_results.csv")
    excluded_chains_csv_path = _write_excluded_chains_csv(excluded_chains, directory / "excluded_chains.csv")

    metadata = dict(dataset_metadata or {})
    metadata.setdefault("policy_name", policy.name)
    metadata.setdefault("chains_total", len(chains))
    metadata.setdefault("chains_selected", len(selected_chains))

    trade_detail_links = None
    if write_trade_artifacts:
        trade_detail_links = _write_trade_artifacts(
            output_dir=directory,
            trade_results=trade_results,
            event_logs_by_signal_id=event_logs_by_signal_id,
        )

    html_report_path = write_policy_html_report(
        summary=summary,
        trade_results=trade_results,
        excluded_chains=excluded_chains,
        dataset_metadata=metadata,
        output_path=directory / "policy_report.html",
        trade_detail_links=trade_detail_links,
        title=f"Policy Report - {policy.name}",
    )

    return PolicyReportArtifacts(
        output_dir=directory,
        summary_json_path=summary_json_path,
        summary_csv_path=summary_csv_path,
        trade_results_csv_path=trade_results_csv_path,
        excluded_chains_csv_path=excluded_chains_csv_path,
        html_report_path=html_report_path,
    )
