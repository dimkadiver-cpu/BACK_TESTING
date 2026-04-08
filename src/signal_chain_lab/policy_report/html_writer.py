"""HTML writer for single-policy dataset reports."""
from __future__ import annotations

import html
from collections import Counter
from pathlib import Path

from src.signal_chain_lab.domain.results import TradeResult


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
    for index, value in enumerate(series):
        x = 20 + int((index / max(len(series) - 1, 1)) * (width - 40))
        y = (height - 20) - int(((value - min_y) / span) * (height - 40))
        coords.append(f"{x},{y}")
    return " ".join(coords)


def _dataset_metadata_rows(dataset_metadata: dict[str, object]) -> str:
    rows: list[str] = []
    for key, value in dataset_metadata.items():
        rows.append(
            "<tr>"
            f"<th align='left'>{html.escape(str(key))}</th>"
            f"<td>{html.escape(str(value))}</td>"
            "</tr>"
        )
    return "".join(rows)


def write_policy_html_report(
    *,
    summary: dict[str, object],
    trade_results: list[TradeResult],
    excluded_chains: list[dict[str, str]],
    dataset_metadata: dict[str, object],
    output_path: str | Path,
    trade_detail_links: dict[str, str] | None = None,
    title: str = "Policy Report",
) -> Path:
    summary_rows = "".join(
        (
            "<tr>"
            f"<th align='left'>{html.escape(str(key))}</th>"
            f"<td>{html.escape(str(value))}</td>"
            "</tr>"
        )
        for key, value in summary.items()
    )

    excluded_summary_rows = "".join(
        (
            "<tr>"
            f"<td>{html.escape(reason_code)}</td>"
            f"<td>{count}</td>"
            "</tr>"
        )
        for reason_code, count in sorted(Counter(item["reason_code"] for item in excluded_chains).items())
    )

    excluded_rows = "".join(
        (
            "<tr>"
            f"<td>{html.escape(item['signal_id'])}</td>"
            f"<td>{html.escape(item['reason_code'])}</td>"
            f"<td>{html.escape(item['reason_message'])}</td>"
            "</tr>"
        )
        for item in excluded_chains
    )

    trade_rows: list[str] = []
    for trade in trade_results:
        detail_link = ""
        if trade_detail_links and trade.signal_id in trade_detail_links:
            detail_link = f"<a href='{html.escape(trade_detail_links[trade.signal_id])}'>detail</a>"
        trade_rows.append(
            "<tr>"
            f"<td>{html.escape(trade.signal_id)}</td>"
            f"<td>{html.escape(trade.symbol)}</td>"
            f"<td>{html.escape(trade.side)}</td>"
            f"<td>{html.escape(trade.status)}</td>"
            f"<td>{trade.realized_pnl:.4f}</td>"
            f"<td>{trade.warnings_count}</td>"
            f"<td>{trade.ignored_events_count}</td>"
            f"<td>{detail_link}</td>"
            "</tr>"
        )

    polyline = _series_to_polyline(_equity_series(trade_results))
    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; color: #1f2937; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; vertical-align: top; }}
    .cards {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0 24px; }}
    .card {{ border: 1px solid #d1d5db; border-radius: 8px; padding: 12px 16px; min-width: 160px; }}
    .card-title {{ font-size: 12px; color: #6b7280; text-transform: uppercase; }}
    .card-value {{ font-size: 24px; font-weight: 600; }}
    svg {{ border: 1px solid #d1d5db; background: #fff; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <h2>Dataset metadata</h2>
  <table>
    <tbody>{_dataset_metadata_rows(dataset_metadata)}</tbody>
  </table>
  <div class="cards">
    <div class="card"><div class="card-title">Trades</div><div class="card-value">{summary["trades_count"]}</div></div>
    <div class="card"><div class="card-title">Total PnL</div><div class="card-value">{summary["total_pnl"]}</div></div>
    <div class="card"><div class="card-title">Win rate</div><div class="card-value">{summary["win_rate"]}</div></div>
    <div class="card"><div class="card-title">Excluded chains</div><div class="card-value">{summary["chains_excluded"]}</div></div>
  </div>
  <h2>Summary metrics</h2>
  <table>
    <tbody>{summary_rows}</tbody>
  </table>
  <h2>Equity curve</h2>
  <svg width="760" height="260" xmlns="http://www.w3.org/2000/svg">
    <line x1="20" y1="240" x2="740" y2="240" stroke="#999" />
    <line x1="20" y1="20" x2="20" y2="240" stroke="#999" />
    <polyline points="{polyline}" fill="none" stroke="#1f77b4" stroke-width="2" />
  </svg>
  <h2>Excluded chains summary</h2>
  <table>
    <thead><tr><th>Reason code</th><th>Count</th></tr></thead>
    <tbody>{excluded_summary_rows}</tbody>
  </table>
  <h2>Excluded chains</h2>
  <table>
    <thead><tr><th>Signal ID</th><th>Reason code</th><th>Reason message</th></tr></thead>
    <tbody>{excluded_rows}</tbody>
  </table>
  <h2>Trade results</h2>
  <table>
    <thead><tr><th>Signal ID</th><th>Symbol</th><th>Side</th><th>Status</th><th>Realized PnL</th><th>Warnings</th><th>Ignored events</th><th>Detail</th></tr></thead>
    <tbody>{''.join(trade_rows)}</tbody>
  </table>
</body>
</html>
"""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_doc, encoding="utf-8")
    return path
