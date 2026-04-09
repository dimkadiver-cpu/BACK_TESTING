"""Run datasets across multiple policies and aggregate scenario metrics."""
from __future__ import annotations

import html as _html
import json
import re
from datetime import datetime, timezone
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


def _make_run_dir(base_dir: Path, policy_name: str) -> Path:
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^\w-]", "_", policy_name)[:40]
    run_dir = base_dir / f"{ts}_{safe}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _rebuild_log_html(base_dir: Path) -> Path:
    entries: list[tuple[str, dict, list[dict], bool]] = []
    for sub in sorted(base_dir.iterdir(), reverse=True):
        if not sub.is_dir():
            continue
        meta_file = sub / "run_meta.json"
        results_file = sub / "scenario_results.json"
        if not (meta_file.exists() and results_file.exists()):
            continue
        meta: dict = json.loads(meta_file.read_text(encoding="utf-8"))
        results: list[dict] = json.loads(results_file.read_text(encoding="utf-8"))
        has_html = (sub / "backtest_report.html").exists()
        entries.append((sub.name, meta, results, has_html))

    rows_html = ""
    for run_id, meta, results, has_html in entries:
        for r in results:
            link = (
                f'<a href="./{_html.escape(run_id)}/backtest_report.html" target="_blank">open report</a>'
                if has_html
                else "—"
            )
            rows_html += (
                "<tr>"
                f"<td>{_html.escape(meta.get('run_at', ''))}</td>"
                f"<td>{_html.escape(r.get('policy_name', ''))}</td>"
                f"<td>{r.get('trades_count', 0)}</td>"
                f"<td>{r.get('win_rate', 0.0):.1%}</td>"
                f"<td>{r.get('return_pct', 0.0):.2%}</td>"
                f"<td>{r.get('max_drawdown', 0.0):.2%}</td>"
                f"<td>{r.get('profit_factor', 0.0):.2f}</td>"
                f"<td>{r.get('expectancy', 0.0):.4f}</td>"
                f"<td>{link}</td>"
                "</tr>\n"
            )

    log_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Backtest Artifacts Log</title>
  <style>
    body {{ font-family: sans-serif; margin: 2em; background: #fff; color: #222; }}
    h1 {{ margin-bottom: 0.3em; }}
    p.subtitle {{ color: #666; margin-top: 0; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1em; }}
    th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; white-space: nowrap; }}
    th {{ background: #f0f0f0; font-weight: 600; }}
    tr:nth-child(even) {{ background: #fafafa; }}
    a {{ color: #1a6fc4; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <h1>Backtest Artifacts — LOG</h1>
  <p class="subtitle">Auto-generated index. Newest runs first. Metrics in % where applicable.</p>
  <table>
    <thead>
      <tr>
        <th>Run at (UTC)</th>
        <th>Policy</th>
        <th>Trades</th>
        <th>Win rate</th>
        <th>Return / trade</th>
        <th>Max DD</th>
        <th>Profit factor</th>
        <th>Expectancy</th>
        <th>Report</th>
      </tr>
    </thead>
    <tbody>
{rows_html}    </tbody>
  </table>
</body>
</html>
"""

    log_path = base_dir / "LOG.html"
    log_path.write_text(log_html, encoding="utf-8")
    return log_path


def write_scenario_artifacts(
    scenario_results: list[ScenarioResult],
    output_dir: str | Path,
    per_policy_trades: dict[str, list[TradeResult]] | None = None,
) -> tuple[Path, Path | None, Path | None]:
    base_dir = Path(output_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    policy_name = scenario_results[0].policy_name if scenario_results else "run"
    run_dir = _make_run_dir(base_dir, policy_name)

    run_meta = {
        "run_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "policy_name": policy_name,
    }
    (run_dir / "run_meta.json").write_text(
        json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    scenario_path = run_dir / "scenario_results.json"
    scenario_path.write_text(
        json.dumps([item.model_dump(mode="json") for item in scenario_results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    csv_path: Path | None = None
    html_path: Path | None = None

    if per_policy_trades is not None:
        all_trades = [trade for trades in per_policy_trades.values() for trade in trades]
        csv_path = write_trade_results_csv(all_trades, run_dir / "trade_results.csv")
        html_path = write_scenario_html_report(
            scenario_results=scenario_results,
            per_policy_trades=per_policy_trades,
            output_path=run_dir / "backtest_report.html",
            title=f"Backtest Report: {policy_name}",
        )

    _rebuild_log_html(base_dir)

    return scenario_path, csv_path, html_path
