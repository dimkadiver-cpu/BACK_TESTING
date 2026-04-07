"""Report helpers for simulation artifacts."""
from __future__ import annotations

from src.signal_chain_lab.reports.chain_plot import (
    build_equity_curve,
    write_chain_plot_html,
    write_chain_plot_png,
)
from src.signal_chain_lab.reports.event_log_report import write_event_log_jsonl
from src.signal_chain_lab.reports.html_report import write_scenario_html_report
from src.signal_chain_lab.reports.trade_report import (
    build_trade_result,
    write_trade_result_parquet,
    write_trade_results_csv,
)

__all__ = [
    "build_equity_curve",
    "build_trade_result",
    "write_chain_plot_html",
    "write_chain_plot_png",
    "write_event_log_jsonl",
    "write_scenario_html_report",
    "write_trade_result_parquet",
    "write_trade_results_csv",
]
