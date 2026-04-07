"""Standalone HTML reporting for scenario outputs."""
from __future__ import annotations

import html
from pathlib import Path

from src.signal_chain_lab.domain.results import ScenarioComparison, ScenarioResult, TradeResult


def _equity_series(trades: list[TradeResult]) -> list[float]:
    ordered = sorted(trades, key=lambda item: item.closed_at or item.created_at or "")
    cumulative = 0.0
    series: list[float] = []
    for trade in ordered:
        cumulative += trade.realized_pnl
        series.append(cumulative)
    return series


def _series_to_polyline(series: list[float], width: int = 760, height: int = 260) -> str:
    if not series:
        return ""
    min_y = min(series)
    max_y = max(series)
    span = (max_y - min_y) or 1.0
    coords: list[str] = []
    for idx, value in enumerate(series):
        x = 20 + int((idx / max(len(series) - 1, 1)) * (width - 40))
        y = (height - 20) - int(((value - min_y) / span) * (height - 40))
        coords.append(f"{x},{y}")
    return " ".join(coords)


def write_scenario_html_report(
    scenario_results: list[ScenarioResult],
    comparisons: list[ScenarioComparison],
    per_policy_trades: dict[str, list[TradeResult]],
    output_path: str | Path,
    title: str = "Scenario Report",
) -> Path:
    metrics_rows = "".join(
        (
            "<tr>"
            f"<td>{html.escape(row.policy_name)}</td>"
            f"<td>{row.total_pnl:.4f}</td>"
            f"<td>{row.max_drawdown:.4f}</td>"
            f"<td>{row.win_rate:.2%}</td>"
            f"<td>{row.expectancy:.4f}</td>"
            f"<td>{row.trades_count}</td>"
            "</tr>"
        )
        for row in scenario_results
    )

    delta_rows = "".join(
        (
            "<tr>"
            f"<td>{html.escape(item.base_policy_name)}</td>"
            f"<td>{html.escape(item.target_policy_name)}</td>"
            f"<td>{item.delta_pnl:.4f}</td>"
            f"<td>{item.delta_drawdown:.4f}</td>"
            f"<td>{item.delta_win_rate:.2%}</td>"
            f"<td>{item.delta_expectancy:.4f}</td>"
            "</tr>"
        )
        for item in comparisons
    )

    charts: list[str] = []
    trades_rows: list[str] = []
    for policy_name, trades in per_policy_trades.items():
        series = _equity_series(trades)
        polyline = _series_to_polyline(series)
        charts.append(
            "<section>"
            f"<h3>Equity curve: {html.escape(policy_name)}</h3>"
            "<svg width='760' height='260' xmlns='http://www.w3.org/2000/svg'>"
            "<line x1='20' y1='240' x2='740' y2='240' stroke='#999' />"
            "<line x1='20' y1='20' x2='20' y2='240' stroke='#999' />"
            f"<polyline points='{polyline}' fill='none' stroke='#1f77b4' stroke-width='2' />"
            "</svg>"
            "</section>"
        )
        for trade in trades:
            trades_rows.append(
                "<tr>"
                f"<td>{html.escape(policy_name)}</td>"
                f"<td>{html.escape(trade.signal_id)}</td>"
                f"<td>{html.escape(trade.symbol)}</td>"
                f"<td>{trade.realized_pnl:.4f}</td>"
                f"<td>{html.escape(trade.status)}</td>"
                "</tr>"
            )

    html_doc = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>{html.escape(title)}</title>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <h2>Scenario metrics</h2>
  <table border=\"1\" cellspacing=\"0\" cellpadding=\"6\">
    <thead><tr><th>Policy</th><th>Total PnL</th><th>Max DD</th><th>Win rate</th><th>Expectancy</th><th>Trades</th></tr></thead>
    <tbody>{metrics_rows}</tbody>
  </table>
  <h2>Scenario deltas</h2>
  <table border=\"1\" cellspacing=\"0\" cellpadding=\"6\">
    <thead><tr><th>Base</th><th>Target</th><th>Δ PnL</th><th>Δ DD</th><th>Δ Win rate</th><th>Δ Expectancy</th></tr></thead>
    <tbody>{delta_rows}</tbody>
  </table>
  <h2>Comparison visual</h2>
  {''.join(charts)}
  <h2>Trade results</h2>
  <table border=\"1\" cellspacing=\"0\" cellpadding=\"6\">
    <thead><tr><th>Policy</th><th>Signal ID</th><th>Symbol</th><th>Realized PnL</th><th>Status</th></tr></thead>
    <tbody>{''.join(trades_rows)}</tbody>
  </table>
</body>
</html>
"""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_doc, encoding="utf-8")
    return path
