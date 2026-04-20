from __future__ import annotations

from pathlib import Path

import pytest

from src.signal_chain_lab.ui.blocks import block_backtest as panel
from src.signal_chain_lab.ui.state import UiState


class DummyLogPanel:
    def __init__(self) -> None:
        self._lines: list[str] = []

    def clear(self) -> None:
        self._lines.clear()

    def push(self, line: str) -> None:
        self._lines.append(line)

    def lines(self) -> list[str]:
        return list(self._lines)


def _write_plan(path: Path, *, symbols: int, complete: int, gaps: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            "{"
            f'"summary":{{"symbols":{symbols},"symbols_complete":{complete},"required_intervals":8,"gaps":{gaps}}}'
            "}"
        ),
        encoding="utf-8",
    )


def _make_state(tmp_path: Path) -> UiState:
    state = UiState()
    parsed_db = tmp_path / "parsed.sqlite3"
    parsed_db.write_text("db", encoding="utf-8")
    market_dir = tmp_path / "market"
    market_dir.mkdir()
    plan_path = tmp_path / "artifacts" / "market_data" / "plan_market_data.json"
    _write_plan(plan_path, symbols=2, complete=2, gaps=0)

    state.parsed_db_path = str(parsed_db)
    state.market.market_data_dir = str(market_dir)
    state.market.latest_market_plan_path = str(plan_path)
    state.market.market_validation_status = "validated"
    state.market.price_basis = "last"
    state.market.simulation_tf = "1h"
    state.market.detail_tf = "15m"
    return state


@pytest.mark.asyncio
async def test_single_policy_backtest_populates_summary_and_html_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(panel.ui, "notify", lambda *args, **kwargs: None)
    state = _make_state(tmp_path)
    log_panel = DummyLogPanel()
    html_report = tmp_path / "artifacts" / "policy_reports" / "report.html"
    html_report.parent.mkdir(parents=True, exist_ok=True)
    html_report.write_text("<html></html>", encoding="utf-8")

    async def runner(command, target_log_panel, process_started=None):  # noqa: ANN001, ANN202
        if process_started is not None:
            process_started(object())
        target_log_panel.push("chains_selected=1")
        target_log_panel.push(
            "- original_chain: pnl=12.5, win_rate=55.0%, expectancy=0.45, trades=11, excluded=2"
        )
        target_log_panel.push(f"policy_report_html={html_report}")
        return 0

    summaries, html_path = await panel._handle_backtest(
        state=state,
        db_path=state.parsed_db_path,
        policies=["original_chain"],
        trader_filter="all",
        date_from_str="2026-01-01",
        date_to_str="2026-01-31",
        max_trades=10,
        report_dir=str(html_report.parent),
        timeout_seconds=300,
        log_panel=log_panel,
        run_streaming_command=runner,
    )

    assert len(summaries) == 1
    assert summaries[0]["policy"] == "original_chain"
    assert summaries[0]["trades"] == "11"
    assert html_path == str(html_report)
    assert state.timeout_seconds == 300
    assert any("[check] Copertura dataset: 100.0%" in line for line in log_panel.lines())


@pytest.mark.asyncio
async def test_multi_policy_backtest_returns_multiple_rows_and_warning_gate(tmp_path: Path, monkeypatch) -> None:
    notifications: list[tuple[str, str | None]] = []
    monkeypatch.setattr(panel.ui, "notify", lambda message, color=None: notifications.append((message, color)))
    state = _make_state(tmp_path)
    state.market.market_validation_status = "ready_unvalidated"
    log_panel = DummyLogPanel()
    html_report = tmp_path / "artifacts" / "scenarios" / "scenario.html"
    html_report.parent.mkdir(parents=True, exist_ok=True)
    html_report.write_text("<html></html>", encoding="utf-8")

    async def runner(command, target_log_panel, process_started=None):  # noqa: ANN001, ANN202
        if process_started is not None:
            process_started(object())
        target_log_panel.push(
            "- original_chain: pnl=4.0, win_rate=50.0%, expectancy=0.10, trades=8, excluded=1"
        )
        target_log_panel.push(
            "- signal_only: pnl=7.5, win_rate=62.5%, expectancy=0.30, trades=9, excluded=0"
        )
        target_log_panel.push(f"scenario_html={html_report}")
        return 0

    summaries, html_path = await panel._handle_backtest(
        state=state,
        db_path=state.parsed_db_path,
        policies=["original_chain", "signal_only"],
        trader_filter="all",
        date_from_str="",
        date_to_str="",
        max_trades=0,
        report_dir=str(html_report.parent),
        timeout_seconds=120,
        log_panel=log_panel,
        run_streaming_command=runner,
    )

    assert [item["policy"] for item in summaries] == ["original_chain", "signal_only"]
    assert html_path == str(html_report)
    assert any("run consentito con warning" in message for message, _ in notifications)
    assert any(color == "warning" for _, color in notifications)
