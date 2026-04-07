from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.domain.enums import ChainInputMode, EventProcessingStatus
from src.signal_chain_lab.domain.results import EventLogEntry, ScenarioComparison, ScenarioResult, TradeResult
from src.signal_chain_lab.reports.chain_plot import build_equity_curve, write_chain_plot_html, write_chain_plot_png
from src.signal_chain_lab.reports.event_log_report import write_event_log_jsonl
from src.signal_chain_lab.reports.html_report import write_scenario_html_report
from src.signal_chain_lab.reports.trade_report import write_trade_results_csv


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _sample_entries() -> list[EventLogEntry]:
    return [
        EventLogEntry(
            timestamp=_utc("2026-01-01T00:00:00"),
            signal_id="sig-1",
            event_type="OPEN_SIGNAL",
            source="trader",
            requested_action="OPEN_SIGNAL",
            executed_action="OPEN_SIGNAL",
            processing_status=EventProcessingStatus.APPLIED,
            state_after={"realized_pnl": 0.0},
        ),
        EventLogEntry(
            timestamp=_utc("2026-01-01T01:00:00"),
            signal_id="sig-1",
            event_type="CLOSE_FULL",
            source="engine",
            requested_action="CLOSE_FULL",
            executed_action="CLOSE_FULL",
            processing_status=EventProcessingStatus.APPLIED,
            state_after={"realized_pnl": 15.5},
        ),
    ]


def _trade(policy_name: str, signal_id: str, pnl: float) -> TradeResult:
    return TradeResult(
        signal_id=signal_id,
        trader_id="trader-a",
        symbol="BTCUSDT",
        side="BUY",
        status="CLOSED",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        policy_name=policy_name,
        realized_pnl=pnl,
    )


def test_chain_plot_writes_png_and_html(tmp_path) -> None:
    entries = _sample_entries()

    curve = build_equity_curve(entries)
    assert curve[-1][1] == 15.5

    png_path = write_chain_plot_png(entries, tmp_path / "chain.png")
    html_path = write_chain_plot_html(entries, tmp_path / "chain.html")

    assert png_path.exists()
    assert png_path.read_bytes().startswith(b"\x89PNG")
    assert html_path.exists()
    assert "<svg" in html_path.read_text(encoding="utf-8")


def test_html_report_and_advanced_exports(tmp_path) -> None:
    results = [
        ScenarioResult(policy_name="original_chain", total_pnl=10.0, max_drawdown=2.0, win_rate=0.5, expectancy=5.0, trades_count=2),
        ScenarioResult(policy_name="signal_only", total_pnl=8.0, max_drawdown=1.5, win_rate=0.5, expectancy=4.0, trades_count=2),
    ]
    comparisons = [
        ScenarioComparison(
            base_policy_name="original_chain",
            target_policy_name="signal_only",
            delta_pnl=-2.0,
            delta_drawdown=-0.5,
            delta_win_rate=0.0,
            delta_expectancy=-1.0,
        )
    ]
    per_policy = {
        "original_chain": [_trade("original_chain", "sig-1", 3.0), _trade("original_chain", "sig-2", 7.0)],
        "signal_only": [_trade("signal_only", "sig-1", 2.0), _trade("signal_only", "sig-2", 6.0)],
    }

    html_path = write_scenario_html_report(results, comparisons, per_policy, tmp_path / "scenario.html")
    csv_path = write_trade_results_csv(per_policy["original_chain"], tmp_path / "trades.csv")
    jsonl_path = write_event_log_jsonl(_sample_entries(), tmp_path / "event_log.jsonl")

    assert html_path.exists()
    report_text = html_path.read_text(encoding="utf-8")
    assert "Scenario metrics" in report_text
    assert "Comparison visual" in report_text
    assert csv_path.exists()
    assert "signal_id" in csv_path.read_text(encoding="utf-8")
    assert jsonl_path.exists()
    assert len(jsonl_path.read_text(encoding="utf-8").splitlines()) == 2
