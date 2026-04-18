"""Run and write a full dataset report for a single policy."""
from __future__ import annotations

import csv
import json
import re
import shutil
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from src.signal_chain_lab.adapters.validators import validate_chain_for_simulation
from src.signal_chain_lab.domain.events import CanonicalChain
from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult
from src.signal_chain_lab.engine.simulator import simulate_chain
from src.signal_chain_lab.market.data_models import Candle
from src.signal_chain_lab.market.data_models import MarketDataProvider
from src.signal_chain_lab.policies.base import PolicyConfig
from src.signal_chain_lab.policy_report.html_writer import (
    flatten_policy_values,
    write_policy_html_report,
    write_single_trade_html_report,
)
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
    policy_yaml_path: Path
    html_report_path: Path


_TRADE_CHART_CONTEXT_HOURS = 15


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


def _compute_max_drawdown_pct(pct_series: list[float]) -> float:
    """Compute max drawdown from a % series (cumulative equity %)."""
    if not pct_series:
        return 0.0
    peak = pct_series[0]
    max_dd = 0.0
    for val in pct_series:
        if val > peak:
            peak = val
        dd = peak - val
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _aggregate_policy_results(
    *,
    policy_name: str,
    trade_results: list[TradeResult],
    excluded: int,
    price_basis: str,
    exchange_faithful: bool,
    initial_capital: float | None = None,
) -> dict[str, object]:
    trades_count = len(trade_results)
    avg_warnings = (
        sum(item.warnings_count for item in trade_results) / trades_count if trades_count else 0.0
    )

    # ── Raw PnL (debug / internal) ────────────────────────────────────────────
    realized = [item.realized_pnl for item in trade_results]
    total_pnl_raw = sum(realized)
    raw_wins = [pnl for pnl in realized if pnl > 0.0]
    raw_losses = [pnl for pnl in realized if pnl < 0.0]
    gross_profit_raw = sum(raw_wins)
    gross_loss_raw = abs(sum(raw_losses))

    # ── Net % metrics (primary — always available when fills exist) ───────────
    pct_net = [t.trade_return_pct_net for t in trade_results if t.trade_return_pct_net is not None]
    pct_gross = [t.trade_return_pct_gross for t in trade_results if t.trade_return_pct_gross is not None]

    wins_net = [p for p in pct_net if p > 0.0]
    losses_net = [p for p in pct_net if p < 0.0]
    wins_gross = [p for p in pct_gross if p > 0.0]
    losses_gross = [p for p in pct_gross if p < 0.0]

    win_rate_net = len(wins_net) / len(pct_net) if pct_net else 0.0
    avg_trade_return_pct_net = statistics.mean(pct_net) if pct_net else 0.0
    median_trade_return_pct_net = statistics.median(pct_net) if pct_net else 0.0
    expectancy_pct_net = avg_trade_return_pct_net
    profit_factor_net = (sum(wins_net) / abs(sum(losses_net))) if losses_net else 0.0

    avg_trade_return_pct_gross = statistics.mean(pct_gross) if pct_gross else 0.0
    median_trade_return_pct_gross = statistics.median(pct_gross) if pct_gross else 0.0
    expectancy_pct_gross = avg_trade_return_pct_gross
    profit_factor_gross = (sum(wins_gross) / abs(sum(losses_gross))) if losses_gross else 0.0

    # Best / worst single trade (net)
    best_trade_pct: float | None = max(pct_net) if pct_net else None
    worst_trade_pct: float | None = min(pct_net) if pct_net else None

    # ── R-multiple aggregates ─────────────────────────────────────────────────
    r_multiples = [t.r_multiple for t in trade_results if t.r_multiple is not None]
    avg_r_multiple: float | None = statistics.mean(r_multiples) if r_multiples else None
    median_r_multiple: float | None = statistics.median(r_multiples) if r_multiples else None

    # ── Cost diagnostics ──────────────────────────────────────────────────────
    fees_total_raw = sum(t.fees_total_raw for t in trade_results)
    fees_avg_raw = fees_total_raw / trades_count if trades_count else 0.0
    funding_total_raw_net = sum(t.funding_total_raw_net for t in trade_results)
    funding_avg_raw_net = funding_total_raw_net / trades_count if trades_count else 0.0

    cost_drags = [t.cost_drag_pct for t in trade_results if t.cost_drag_pct is not None]
    avg_cost_drag_pct: float | None = statistics.mean(cost_drags) if cost_drags else None

    gross_pos_net_neg = [
        t for t in trade_results
        if t.trade_return_pct_gross is not None
        and t.trade_return_pct_net is not None
        and t.trade_return_pct_gross > 0
        and t.trade_return_pct_net <= 0
    ]
    gross_positive_to_net_negative_count = len(gross_pos_net_neg)
    gross_positive_to_net_negative_pct = (
        gross_positive_to_net_negative_count / trades_count * 100.0 if trades_count else 0.0
    )

    trades_with_funding = [t for t in trade_results if t.funding_total_raw_net != 0.0]
    trades_with_funding_count = len(trades_with_funding)
    trades_with_funding_pct = (
        trades_with_funding_count / trades_count * 100.0 if trades_count else 0.0
    )

    # ── Status / close reason counts ─────────────────────────────────────────
    closed_count = sum(1 for t in trade_results if (t.status or "").lower() == "closed")
    expired_count = sum(1 for t in trade_results if (t.status or "").lower() == "expired")
    cancelled_count = sum(1 for t in trade_results if (t.status or "").lower() in ("cancelled", "canceled"))

    close_reason_distribution: dict[str, int] = dict(
        Counter((t.close_reason or "none") for t in trade_results)
    )

    # ── Symbol contribution (using trade_return_pct_net) ─────────────────────
    symbol_ret_net: dict[str, list[float]] = defaultdict(list)
    symbol_count: dict[str, int] = defaultdict(int)
    for t in trade_results:
        sym = t.symbol or "unknown"
        symbol_count[sym] += 1
        if t.trade_return_pct_net is not None:
            symbol_ret_net[sym].append(t.trade_return_pct_net)

    symbol_contribution: dict[str, object] = {
        sym: {
            "avg_return_pct_net": round(statistics.mean(symbol_ret_net[sym]), 4) if symbol_ret_net[sym] else None,
            "trades_count": symbol_count[sym],
            "win_rate": round(
                sum(1 for r in symbol_ret_net[sym] if r > 0) / len(symbol_ret_net[sym]) * 100, 1
            ) if symbol_ret_net[sym] else 0.0,
        }
        for sym in sorted(symbol_ret_net, key=lambda s: statistics.mean(symbol_ret_net[s]) if symbol_ret_net[s] else 0.0, reverse=True)
    }

    # ── Raw max drawdown (from realized_pnl series) ───────────────────────────
    max_drawdown_raw = _compute_max_drawdown(realized)

    # ── Max drawdown % from cumulative net return % ───────────────────────────
    max_drawdown_pct: float | None = None
    if pct_net:
        cumulative_pct = []
        cum = 0.0
        for p in pct_net:
            cum += p
            cumulative_pct.append(cum)
        max_drawdown_pct = _compute_max_drawdown_pct(cumulative_pct)

    return {
        "policy_name": policy_name,
        # ── raw / debug ───────────────────────────────────────────────────────
        "total_pnl_raw": total_pnl_raw,
        "gross_profit_raw": gross_profit_raw,
        "gross_loss_raw": gross_loss_raw,
        "max_drawdown_raw": max_drawdown_raw,
        # ── net primary ───────────────────────────────────────────────────────
        "win_rate_net": win_rate_net,
        "avg_trade_return_pct_net": avg_trade_return_pct_net,
        "median_trade_return_pct_net": median_trade_return_pct_net,
        "expectancy_pct_net": expectancy_pct_net,
        "profit_factor_net": profit_factor_net,
        "best_trade_pct": best_trade_pct,
        "worst_trade_pct": worst_trade_pct,
        "avg_r_multiple": avg_r_multiple,
        "median_r_multiple": median_r_multiple,
        # ── gross secondary ───────────────────────────────────────────────────
        "avg_trade_return_pct_gross": avg_trade_return_pct_gross,
        "median_trade_return_pct_gross": median_trade_return_pct_gross,
        "expectancy_pct_gross": expectancy_pct_gross,
        "profit_factor_gross": profit_factor_gross,
        # ── cost diagnostics ──────────────────────────────────────────────────
        "fees_total_raw": fees_total_raw,
        "fees_avg_raw": fees_avg_raw,
        "funding_total_raw_net": funding_total_raw_net,
        "funding_avg_raw_net": funding_avg_raw_net,
        "avg_cost_drag_pct": avg_cost_drag_pct,
        "gross_positive_to_net_negative_count": gross_positive_to_net_negative_count,
        "gross_positive_to_net_negative_pct": gross_positive_to_net_negative_pct,
        "trades_with_funding_count": trades_with_funding_count,
        "trades_with_funding_pct": trades_with_funding_pct,
        # ── drawdown ──────────────────────────────────────────────────────────
        "max_drawdown_pct": max_drawdown_pct,
        # ── counts ────────────────────────────────────────────────────────────
        "trades_count": trades_count,
        "simulated_chains_count": trades_count,
        "excluded_chains_count": excluded,
        "avg_warnings_per_trade": avg_warnings,
        "closed_trades_count": closed_count,
        "expired_trades_count": expired_count,
        "cancelled_trades_count": cancelled_count,
        "price_basis": price_basis,
        "exchange_faithful": exchange_faithful,
        # ── distributions ────────────────────────────────────────────────────
        "close_reason_distribution": close_reason_distribution,
        "symbol_contribution": symbol_contribution,
    }


def _build_exclusion_record(chain: CanonicalChain, reason_code: str, reason_message: str) -> dict[str, str]:
    return {
        "signal_id": chain.signal_id,
        "symbol": chain.symbol,
        "reason_code": reason_code,
        "reason_message": reason_message,
        "reason": reason_code,
        "note": reason_message,
        "original_text": str(chain.metadata.get("new_signal_raw_text") or ""),
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
    initial_capital: float | None = None,
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
        trade_results.append(build_trade_result(state, event_log, initial_capital=initial_capital))

    return trade_results, excluded_chains, event_logs_by_signal_id


def _assign_cum_equity_pct(
    trade_results: list[TradeResult],
    initial_capital: float | None = None,
) -> None:
    """Set cum_equity_after_trade_pct on each trade in chronological order.

    Uses trade_return_pct_net (normalized, always available when fills exist).
    Does NOT require initial_capital — the cumulative sum of % returns is already
    a meaningful equity curve per-trade.
    """
    sorted_trades = sorted(
        trade_results,
        key=lambda t: t.closed_at or datetime.max.replace(tzinfo=timezone.utc),
    )
    cumulative = 0.0
    for trade in sorted_trades:
        cumulative += trade.trade_return_pct_net or 0.0
        trade.cum_equity_after_trade_pct = round(cumulative, 4)


def _build_summary(
    *,
    policy_name: str,
    chains_total: int,
    chains_selected: int,
    trade_results: list[TradeResult],
    excluded_chains: list[dict[str, str]],
    price_basis: str,
    exchange_faithful: bool,
    initial_capital: float | None = None,
) -> dict[str, object]:
    aggregated = _aggregate_policy_results(
        policy_name=policy_name,
        trade_results=trade_results,
        excluded=len(excluded_chains),
        price_basis=price_basis,
        exchange_faithful=exchange_faithful,
        initial_capital=initial_capital,
    )
    excluded_reasons = Counter(item["reason_code"] for item in excluded_chains)
    total_ignored_events = sum(item.ignored_events_count for item in trade_results)

    # Build equity curve from cumulative trade_return_pct_net (sorted by closed_at)
    equity_curve_pct: list[dict[str, object]] = []
    drawdown_pct: list[dict[str, object]] = []
    sorted_trades = sorted(
        trade_results,
        key=lambda t: t.closed_at or datetime.max.replace(tzinfo=timezone.utc),
    )
    cumulative_net = 0.0
    peak_net = 0.0
    for t in sorted_trades:
        cumulative_net += t.trade_return_pct_net or 0.0
        eq_pct = round(cumulative_net, 4)
        if eq_pct > peak_net:
            peak_net = eq_pct
        dd_pct = round(peak_net - eq_pct, 4)
        ts = t.closed_at.isoformat() if t.closed_at else ""
        equity_curve_pct.append({"ts": ts, "signal_id": t.signal_id, "equity_pct": eq_pct})
        drawdown_pct.append({"ts": ts, "signal_id": t.signal_id, "drawdown_pct": dd_pct})

    def _flt(key: str) -> float | None:
        v = aggregated.get(key)
        return float(v) if v is not None else None

    return {
        "policy_name": str(aggregated["policy_name"]),
        "initial_capital": initial_capital,
        "chains_total": chains_total,
        "chains_selected": chains_selected,
        "chains_simulated": int(aggregated["simulated_chains_count"]),
        "chains_excluded": int(aggregated["excluded_chains_count"]),
        "excluded_reasons_summary": dict(sorted(excluded_reasons.items())),
        "trades_count": int(aggregated["trades_count"]),
        "closed_trades_count": int(aggregated["closed_trades_count"]),
        "expired_trades_count": int(aggregated["expired_trades_count"]),
        "cancelled_trades_count": int(aggregated["cancelled_trades_count"]),
        # ── net primary ───────────────────────────────────────────────────────
        "win_rate_net": _flt("win_rate_net"),
        "win_rate_pct": (_flt("win_rate_net") or 0.0) * 100.0,
        "avg_trade_return_pct_net": _flt("avg_trade_return_pct_net"),
        "median_trade_return_pct_net": _flt("median_trade_return_pct_net"),
        "expectancy_pct_net": _flt("expectancy_pct_net"),
        "profit_factor_net": _flt("profit_factor_net"),
        "best_trade_pct": aggregated.get("best_trade_pct"),
        "worst_trade_pct": aggregated.get("worst_trade_pct"),
        "avg_r_multiple": aggregated.get("avg_r_multiple"),
        "median_r_multiple": aggregated.get("median_r_multiple"),
        # ── gross secondary ───────────────────────────────────────────────────
        "avg_trade_return_pct_gross": _flt("avg_trade_return_pct_gross"),
        "median_trade_return_pct_gross": _flt("median_trade_return_pct_gross"),
        "expectancy_pct_gross": _flt("expectancy_pct_gross"),
        "profit_factor_gross": _flt("profit_factor_gross"),
        # ── cost diagnostics ──────────────────────────────────────────────────
        "fees_total_raw": _flt("fees_total_raw"),
        "fees_avg_raw": _flt("fees_avg_raw"),
        "funding_total_raw_net": _flt("funding_total_raw_net"),
        "funding_avg_raw_net": _flt("funding_avg_raw_net"),
        "avg_cost_drag_pct": aggregated.get("avg_cost_drag_pct"),
        "gross_positive_to_net_negative_count": int(aggregated.get("gross_positive_to_net_negative_count") or 0),
        "gross_positive_to_net_negative_pct": _flt("gross_positive_to_net_negative_pct"),
        "trades_with_funding_count": int(aggregated.get("trades_with_funding_count") or 0),
        "trades_with_funding_pct": _flt("trades_with_funding_pct"),
        # ── raw / debug ───────────────────────────────────────────────────────
        "total_pnl_raw": _flt("total_pnl_raw"),
        "gross_profit_raw": _flt("gross_profit_raw"),
        "gross_loss_raw": _flt("gross_loss_raw"),
        "max_drawdown_raw": _flt("max_drawdown_raw"),
        # ── backward-compat aliases (deprecated, kept for downstream compat) ──
        "net_profit_pct": _flt("total_pnl_raw"),
        "profit_pct": _flt("gross_profit_raw"),
        "loss_pct": -(_flt("gross_loss_raw") or 0.0),
        "max_drawdown_pct": aggregated.get("max_drawdown_pct"),
        "avg_warnings_per_trade": float(aggregated["avg_warnings_per_trade"]),
        "total_ignored_events": total_ignored_events,
        # ── distributions ────────────────────────────────────────────────────
        "close_reason_distribution": aggregated["close_reason_distribution"],
        "symbol_contribution": aggregated["symbol_contribution"],
        # ── chart data ────────────────────────────────────────────────────────
        "equity_curve_pct": equity_curve_pct,
        "drawdown_pct": drawdown_pct,
        "price_basis": price_basis,
        "exchange_faithful": exchange_faithful,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _write_single_row_csv(row: dict[str, object], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Flatten nested objects for CSV
    flat = {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in row.items()}
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat.keys()))
        writer.writeheader()
        writer.writerow(flat)
    return path


def _write_excluded_chains_csv(excluded_chains: list[dict[str, str]], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["signal_id", "symbol", "reason", "note", "original_text", "reason_code", "reason_message"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in excluded_chains:
            writer.writerow(row)
    return path


_ECHARTS_SOURCE = Path(__file__).parent / "assets" / "echarts.min.js"
_ECHARTS_RELATIVE_PATH = "../../assets/echarts.min.js"


def _copy_chart_assets(output_dir: Path) -> None:
    dest = output_dir / "assets" / "echarts.min.js"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if _ECHARTS_SOURCE.exists() and not dest.exists():
        shutil.copy2(_ECHARTS_SOURCE, dest)


def _count_bars_in_trade(
    candles_by_timeframe: dict[str, list[Candle]],
    first_fill_at: datetime | None,
    closed_at: datetime | None,
) -> int | None:
    """Count candles of the base timeframe that fall within the trade period."""
    if not candles_by_timeframe or first_fill_at is None or closed_at is None:
        return None
    # Use the first (lowest) timeframe in the payload
    candles = next(iter(candles_by_timeframe.values()))
    count = sum(
        1 for c in candles
        if c.timestamp is not None and first_fill_at <= c.timestamp <= closed_at
    )
    return count or None


def _write_trade_artifacts(
    *,
    output_dir: Path,
    trade_results: list[TradeResult],
    event_logs_by_signal_id: dict[str, list[EventLogEntry]],
    chains_by_signal_id: dict[str, CanonicalChain],
    market_provider: MarketDataProvider | None,
    initial_capital: float | None = None,
) -> dict[str, str]:
    _copy_chart_assets(output_dir)
    trade_detail_links: dict[str, str] = {}
    trades_dir = output_dir / "trades"
    # Pre-compute dir names so we can build prev/next links
    dir_names = [_safe_dirname(trade.signal_id) for trade in trade_results]
    for index, trade in enumerate(trade_results):
        signal_dir = trades_dir / dir_names[index]
        event_log = event_logs_by_signal_id.get(trade.signal_id, [])
        chart_candles_by_timeframe = _load_trade_chart_candles_by_timeframe(
            trade=trade,
            chain=chains_by_signal_id.get(trade.signal_id),
            market_provider=market_provider,
            event_log=event_log,
        )
        # Compute bars_in_trade now that we have the candles
        if trade.bars_in_trade is None:
            trade.bars_in_trade = _count_bars_in_trade(
                chart_candles_by_timeframe,
                trade.first_fill_at,
                trade.closed_at,
            )
        prev_link = f"../{dir_names[index - 1]}/detail.html" if index > 0 else None
        next_link = f"../{dir_names[index + 1]}/detail.html" if index < len(trade_results) - 1 else None
        write_event_log_jsonl(event_log, signal_dir / "event_log.jsonl")
        write_trade_results_csv([trade], signal_dir / "trade_result.csv")
        write_chain_plot_png(event_log, signal_dir / "equity_curve.png")
        write_chain_plot_html(
            event_log,
            signal_dir / "equity_curve.html",
            title=f"{trade.signal_id} - {trade.policy_name}",
        )
        write_single_trade_html_report(
            trade=trade,
            event_log=event_log,
            output_path=signal_dir / "detail.html",
            candles_by_timeframe=chart_candles_by_timeframe,
            echarts_asset_path=_ECHARTS_RELATIVE_PATH,
            prev_link=prev_link,
            next_link=next_link,
            trade_index=index + 1,
            trades_total=len(trade_results),
            initial_capital=initial_capital,
        )
        trade_detail_links[trade.signal_id] = f"trades/{signal_dir.name}/detail.html"
    return trade_detail_links


def _higher_timeframes(base_timeframe: str) -> list[str]:
    ordered = ["1m", "5m", "15m", "1h", "4h", "1d"]
    if base_timeframe not in ordered:
        return [base_timeframe]
    start = ordered.index(base_timeframe)
    return ordered[start:]


def _trade_chart_start_anchor(
    trade: TradeResult,
    event_log: list[EventLogEntry],
) -> datetime | None:
    if trade.created_at is not None:
        return trade.created_at
    if event_log:
        timestamps = [entry.timestamp for entry in event_log if entry.timestamp is not None]
        if timestamps:
            return min(timestamps)
    return trade.closed_at


def _trade_chart_end_anchor(
    trade: TradeResult,
    event_log: list[EventLogEntry],
) -> datetime | None:
    if trade.closed_at is not None:
        return trade.closed_at
    if event_log:
        timestamps = [entry.timestamp for entry in event_log if entry.timestamp is not None]
        if timestamps:
            return max(timestamps)
    return trade.created_at


def _load_trade_chart_candles_by_timeframe(
    *,
    trade: TradeResult,
    chain: CanonicalChain | None,
    market_provider: MarketDataProvider | None,
    event_log: list[EventLogEntry] | None = None,
) -> dict[str, list[Candle]]:
    if market_provider is None or chain is None:
        return {}

    if trade.created_at is None:
        return {}

    timeframe = str(chain.metadata.get("timeframe", "1m") or "1m")
    timeframes = _higher_timeframes(timeframe)
    start_anchor = _trade_chart_start_anchor(trade, event_log or [])
    end_anchor = _trade_chart_end_anchor(trade, event_log or [])
    if start_anchor is None:
        start_anchor = trade.created_at
    if end_anchor is None:
        end_anchor = start_anchor
    if end_anchor < start_anchor:
        end_anchor = start_anchor
    start = start_anchor - timedelta(hours=_TRADE_CHART_CONTEXT_HOURS)
    end = end_anchor + timedelta(hours=_TRADE_CHART_CONTEXT_HOURS)
    result: dict[str, list[Candle]] = {}
    for candidate_timeframe in timeframes:
        try:
            candles = market_provider.get_range(trade.symbol, candidate_timeframe, start, end)
        except Exception:
            candles = []
        if candles:
            result[candidate_timeframe] = candles
    return result


def run_policy_report(
    *,
    chains: list[CanonicalChain],
    policy: PolicyConfig,
    output_dir: str | Path,
    market_provider: MarketDataProvider | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    write_trade_artifacts: bool = True,
    dataset_metadata: dict[str, object] | None = None,
    price_basis: str = "last",
    exchange_faithful: bool = True,
    initial_capital: float | None = None,
) -> PolicyReportArtifacts:
    selected_chains = filter_chains_by_date(chains, date_from=date_from, date_to=date_to)
    trade_results, excluded_chains, event_logs_by_signal_id = _run_policy_dataset(
        chains=selected_chains,
        policy=policy,
        market_provider=market_provider,
        initial_capital=initial_capital,
    )

    # Assign cum_equity_after_trade_pct in chronological order (uses trade_return_pct_net)
    _assign_cum_equity_pct(trade_results)

    summary = _build_summary(
        policy_name=policy.name,
        chains_total=len(chains),
        chains_selected=len(selected_chains),
        trade_results=trade_results,
        excluded_chains=excluded_chains,
        price_basis=price_basis,
        exchange_faithful=exchange_faithful,
        initial_capital=initial_capital,
    )

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    summary_json_path = directory / "policy_summary.json"
    summary_json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_csv_path = _write_single_row_csv(summary, directory / "policy_summary.csv")
    excluded_chains_csv_path = _write_excluded_chains_csv(excluded_chains, directory / "excluded_chains.csv")
    policy_yaml_path = directory / "policy.yaml"
    policy_yaml_path.write_text(
        yaml.safe_dump(policy.model_dump(mode="json", by_alias=True), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    metadata = dict(dataset_metadata or {})
    metadata = {
        "Run Id": metadata.get("run_id") or f"policy_{policy.name}",
        "Dataset Name": metadata.get("dataset_name") or metadata.get("db_path") or "dataset",
        "Source Db": metadata.get("db_path") or "-",
        "Trader Filter": metadata.get("trader_filter") or "all",
        "Period Start": metadata.get("date_from") or "-",
        "Period End": metadata.get("date_to") or "-",
        "Input Mode": metadata.get("input_mode") or "mixed",
        "Market Provider": metadata.get("market_provider") or ("bybit" if market_provider is not None else "none"),
        "Timeframe": metadata.get("timeframe") or "-",
        "Price Basis": metadata.get("price_basis") or price_basis,
        "Initial Capital": initial_capital if initial_capital is not None else "-",
        "Selected Chains": len(selected_chains),
        "Simulable Chains": len(trade_results),
        "Excluded Chains": len(excluded_chains),
        "Generated At": summary["generated_at"],
    }
    policy_values = flatten_policy_values(policy.model_dump(mode="json", by_alias=True))
    chains_by_signal_id = {chain.signal_id: chain for chain in selected_chains}

    trade_detail_links = None
    if write_trade_artifacts:
        trade_detail_links = _write_trade_artifacts(
            output_dir=directory,
            trade_results=trade_results,
            event_logs_by_signal_id=event_logs_by_signal_id,
            chains_by_signal_id=chains_by_signal_id,
            market_provider=market_provider,
            initial_capital=initial_capital,
        )

    # Write trade_results.csv AFTER _write_trade_artifacts so bars_in_trade is populated
    trade_results_csv_path = write_trade_results_csv(trade_results, directory / "trade_results.csv")

    html_report_path = write_policy_html_report(
        summary=summary,
        trade_results=trade_results,
        excluded_chains=excluded_chains,
        dataset_metadata=metadata,
        policy_values=policy_values,
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
        policy_yaml_path=policy_yaml_path,
        html_report_path=html_report_path,
    )
