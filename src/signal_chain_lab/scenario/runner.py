"""Run datasets across multiple policies and aggregate scenario metrics."""
from __future__ import annotations

import json
from pathlib import Path

from src.signal_chain_lab.adapters.validators import validate_chain_for_simulation
from src.signal_chain_lab.domain.events import CanonicalChain
from src.signal_chain_lab.domain.results import ScenarioComparison, ScenarioResult, TradeResult
from src.signal_chain_lab.engine.simulator import simulate_chain
from src.signal_chain_lab.market.data_models import MarketDataProvider
from src.signal_chain_lab.policies.base import PolicyConfig
from src.signal_chain_lab.reports.html_report import write_scenario_html_report
from src.signal_chain_lab.reports.trade_report import build_trade_result, write_trade_results_csv


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
    policy_name: str,
    trade_results: list[TradeResult],
    excluded: int,
    price_basis: str = "last",
    exchange_faithful: bool = True,
) -> ScenarioResult:
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

    return ScenarioResult(
        policy_name=policy_name,
        total_pnl=total_pnl,
        return_pct=return_pct,
        max_drawdown=_compute_max_drawdown(realized),
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy=expectancy,
        trades_count=trades_count,
        simulated_chains_count=trades_count,
        excluded_chains_count=excluded,
        avg_warnings_per_trade=avg_warnings,
        price_basis=price_basis,
        exchange_faithful=exchange_faithful,
    )


def run_scenarios(
    chains: list[CanonicalChain],
    policies: list[PolicyConfig],
    market_provider: MarketDataProvider | None = None,
    price_basis: str = "last",
    exchange_faithful: bool = True,
) -> tuple[list[ScenarioResult], dict[str, list[TradeResult]]]:
    scenario_results: list[ScenarioResult] = []
    per_policy_trades: dict[str, list[TradeResult]] = {}

    for policy in policies:
        trade_results: list[TradeResult] = []
        excluded_chains = 0

        for chain in chains:
            validation = validate_chain_for_simulation(chain)
            if not validation.is_simulable:
                excluded_chains += 1
                continue

            event_log, state = simulate_chain(chain, policy=policy, market_provider=market_provider)
            trade_results.append(build_trade_result(state, event_log))

        per_policy_trades[policy.name] = trade_results
        scenario_results.append(
            _aggregate_policy_results(
                policy_name=policy.name,
                trade_results=trade_results,
                excluded=excluded_chains,
                price_basis=price_basis,
                exchange_faithful=exchange_faithful,
            )
        )

    return scenario_results, per_policy_trades


def compare_scenarios(
    scenario_results: list[ScenarioResult],
    baseline_policy: str,
) -> list[ScenarioComparison]:
    baseline = next((item for item in scenario_results if item.policy_name == baseline_policy), None)
    if baseline is None:
        raise ValueError(f"Baseline policy not found in scenario results: {baseline_policy}")

    comparisons: list[ScenarioComparison] = []
    for result in scenario_results:
        if result.policy_name == baseline.policy_name:
            continue
        comparisons.append(
            ScenarioComparison(
                base_policy_name=baseline.policy_name,
                target_policy_name=result.policy_name,
                delta_pnl=result.total_pnl - baseline.total_pnl,
                delta_drawdown=result.max_drawdown - baseline.max_drawdown,
                delta_win_rate=result.win_rate - baseline.win_rate,
                delta_expectancy=result.expectancy - baseline.expectancy,
            )
        )

    return comparisons


def write_scenario_artifacts(
    scenario_results: list[ScenarioResult],
    comparisons: list[ScenarioComparison],
    output_dir: str | Path,
    per_policy_trades: dict[str, list[TradeResult]] | None = None,
) -> tuple[Path, Path, Path | None, Path | None]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    scenario_path = directory / "scenario_results.parquet"
    comparison_path = directory / "scenario_comparison.parquet"

    scenario_path.write_text(
        json.dumps([item.model_dump(mode="json") for item in scenario_results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    comparison_path.write_text(
        json.dumps([item.model_dump(mode="json") for item in comparisons], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    csv_path: Path | None = None
    html_path: Path | None = None

    if per_policy_trades is not None:
        all_trades = [trade for trades in per_policy_trades.values() for trade in trades]
        csv_path = write_trade_results_csv(all_trades, directory / "trade_results.csv")
        html_path = write_scenario_html_report(
            scenario_results=scenario_results,
            comparisons=comparisons,
            per_policy_trades=per_policy_trades,
            output_path=directory / "scenario_report.html",
        )

    return scenario_path, comparison_path, csv_path, html_path
