from __future__ import annotations

import csv
import json
from datetime import datetime, timezone

from src.signal_chain_lab.domain.enums import ChainInputMode, EventProcessingStatus, EventSource, EventType
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent
from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult
from src.signal_chain_lab.policies.policy_loader import PolicyLoader
from src.signal_chain_lab.policy_report import runner as runner_module
from src.signal_chain_lab.policy_report.runner import (
    _build_funding_provider,
    _load_trade_chart_candles_by_timeframe,
    _run_policy_dataset,
    run_policy_report,
)


def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def _build_chain(signal_id: str, *, with_tp: bool, created_at: str) -> CanonicalChain:
    payload: dict[str, object] = {"entry_prices": [100.0], "sl_price": 90.0}
    if with_tp:
        payload["tp_levels"] = [110.0]

    return CanonicalChain(
        signal_id=signal_id,
        trader_id="trader-a",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=False,
        created_at=_utc(created_at),
        events=[
            CanonicalEvent(
                signal_id=signal_id,
                trader_id="trader-a",
                symbol="BTCUSDT",
                side="BUY",
                timestamp=_utc(created_at),
                event_type=EventType.OPEN_SIGNAL,
                source=EventSource.TRADER,
                payload=payload,
                sequence=0,
            )
        ],
    )


def test_run_policy_report_writes_dataset_artifacts(tmp_path) -> None:
    chains = [
        _build_chain("sig-valid", with_tp=True, created_at="2026-01-02T00:00:00"),
        _build_chain("sig-invalid", with_tp=False, created_at="2026-01-03T00:00:00"),
        _build_chain("sig-filtered-out", with_tp=True, created_at="2025-12-25T00:00:00"),
    ]
    policy = PolicyLoader().load("original_chain")

    artifacts = run_policy_report(
        chains=chains,
        policy=policy,
        output_dir=tmp_path / "policy_report",
        date_from=_utc("2026-01-01T00:00:00"),
        date_to=_utc("2026-12-31T00:00:00"),
        write_trade_artifacts=True,
        dataset_metadata={"db_path": "db/backtest.sqlite3", "market_dir": "data/market"},
    )

    assert artifacts.summary_json_path.exists()
    assert artifacts.summary_csv_path.exists()
    assert artifacts.trade_results_csv_path.exists()
    assert artifacts.excluded_chains_csv_path.exists()
    assert artifacts.policy_yaml_path.exists()
    assert artifacts.html_report_path.exists()

    summary = json.loads(artifacts.summary_json_path.read_text(encoding="utf-8"))
    assert summary["policy_name"] == "original_chain"
    assert summary["chains_total"] == 3
    assert summary["chains_selected"] == 2
    assert summary["chains_simulated"] == 1
    assert summary["chains_excluded"] == 1
    assert summary["excluded_reasons_summary"] == {"take_profit": 1}
    assert summary["trades_count"] == 1
    assert "net_profit_pct" in summary
    assert "win_rate_pct" in summary
    assert "generated_at" in summary

    with artifacts.trade_results_csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["signal_id"] == "sig-valid"
    assert rows[0]["policy_name"] == "original_chain"

    with artifacts.excluded_chains_csv_path.open("r", encoding="utf-8", newline="") as handle:
        excluded_rows = list(csv.DictReader(handle))
    assert len(excluded_rows) == 1
    assert excluded_rows[0]["signal_id"] == "sig-invalid"
    assert excluded_rows[0]["symbol"] == "BTCUSDT"
    assert excluded_rows[0]["reason"] == "take_profit"
    assert excluded_rows[0]["reason_code"] == "take_profit"
    assert excluded_rows[0]["reason_message"] == "take_profit: OPEN_SIGNAL has no take_profit levels"

    trade_dir = tmp_path / "policy_report" / "trades" / "sig-valid"
    assert (trade_dir / "event_log.jsonl").exists()
    assert (trade_dir / "trade_result.csv").exists()
    assert (trade_dir / "equity_curve.png").exists()
    assert (trade_dir / "equity_curve.html").exists()
    assert (trade_dir / "detail.html").exists()

    html_text = artifacts.html_report_path.read_text(encoding="utf-8")
    assert "Policy Report - original_chain" in html_text
    assert "Policy Summary" in html_text
    assert "Metadata - policy.yaml values" in html_text
    assert "trades/sig-valid/detail.html" in html_text


def test_trade_chart_uses_last_event_for_partially_closed_trade() -> None:
    class FakeProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, datetime, datetime]] = []

        def get_range(self, symbol: str, timeframe: str, start: datetime, end: datetime):
            self.calls.append((symbol, timeframe, start, end))
            return []

    chain = _build_chain("sig-open", with_tp=True, created_at="2026-01-01T00:00:00")
    chain.metadata["timeframe"] = "1m"
    trade = TradeResult(
        signal_id="sig-open",
        trader_id="trader-a",
        symbol="BTCUSDT",
        side="BUY",
        status="PARTIALLY_CLOSED",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        policy_name="original_chain",
        created_at=_utc("2026-01-01T00:00:00"),
        first_fill_at=_utc("2026-01-01T00:05:00"),
        closed_at=None,
    )
    event_log = [
        EventLogEntry(
            timestamp=_utc("2026-01-01T00:00:00"),
            signal_id="sig-open",
            event_type="OPEN_SIGNAL",
            source="trader",
            processing_status=EventProcessingStatus.APPLIED,
        ),
        EventLogEntry(
            timestamp=_utc("2026-01-03T12:00:00"),
            signal_id="sig-open",
            event_type="CLOSE_PARTIAL",
            source="engine",
            processing_status=EventProcessingStatus.APPLIED,
        ),
    ]
    provider = FakeProvider()

    _load_trade_chart_candles_by_timeframe(
        trade=trade,
        chain=chain,
        market_provider=provider,
        event_log=event_log,
    )

    assert provider.calls
    _, _, start, end = provider.calls[0]
    assert start == _utc("2025-12-31T18:00:00")
    assert end == _utc("2026-01-03T18:00:00")


def test_build_funding_provider_returns_none_when_disabled(tmp_path) -> None:
    policy = PolicyLoader().load("original_chain")
    policy.execution.funding_model = "none"

    provider = _build_funding_provider(policy, tmp_path, "BTCUSDT")

    assert provider is None


def test_run_policy_dataset_passes_none_funding_provider_when_disabled(monkeypatch, tmp_path) -> None:
    policy = PolicyLoader().load("original_chain")
    policy.execution.funding_model = "none"

    captured: dict[str, object] = {}

    def fake_simulate_chain(chain, *, policy, market_provider, funding_provider):
        captured["chain"] = chain
        captured["policy"] = policy
        captured["market_provider"] = market_provider
        captured["funding_provider"] = funding_provider
        return [], object()

    def fake_build_trade_result(state, event_log, initial_capital=None):
        del state, event_log, initial_capital
        return TradeResult(
            signal_id="sig-valid",
            trader_id="trader-a",
            symbol="BTCUSDT",
            side="BUY",
            status="closed",
            input_mode=ChainInputMode.CHAIN_COMPLETE,
            policy_name="original_chain",
        )

    monkeypatch.setattr(runner_module, "simulate_chain", fake_simulate_chain)
    monkeypatch.setattr(runner_module, "build_trade_result", fake_build_trade_result)

    trade_results, excluded_chains, event_logs = _run_policy_dataset(
        chains=[_build_chain("sig-valid", with_tp=True, created_at="2026-01-02T00:00:00")],
        policy=policy,
        market_provider=None,
        market_dir=tmp_path,
    )

    assert not excluded_chains
    assert len(trade_results) == 1
    assert event_logs == {"sig-valid": []}
    assert captured["funding_provider"] is None


def test_run_policy_dataset_passes_funding_provider_when_historical_data_exists(monkeypatch, tmp_path) -> None:
    policy = PolicyLoader().load("original_chain")
    policy.execution.funding_model = "historical"
    funding_dir = tmp_path / "bybit" / "futures_linear" / "funding" / "BTCUSDT"
    funding_dir.mkdir(parents=True)

    captured: dict[str, object] = {}

    def fake_simulate_chain(chain, *, policy, market_provider, funding_provider):
        captured["chain"] = chain
        captured["policy"] = policy
        captured["market_provider"] = market_provider
        captured["funding_provider"] = funding_provider
        return [], object()

    def fake_build_trade_result(state, event_log, initial_capital=None):
        del state, event_log, initial_capital
        return TradeResult(
            signal_id="sig-valid",
            trader_id="trader-a",
            symbol="BTCUSDT",
            side="BUY",
            status="closed",
            input_mode=ChainInputMode.CHAIN_COMPLETE,
            policy_name="original_chain",
        )

    monkeypatch.setattr(runner_module, "simulate_chain", fake_simulate_chain)
    monkeypatch.setattr(runner_module, "build_trade_result", fake_build_trade_result)

    trade_results, excluded_chains, event_logs = _run_policy_dataset(
        chains=[_build_chain("sig-valid", with_tp=True, created_at="2026-01-02T00:00:00")],
        policy=policy,
        market_provider=None,
        market_dir=tmp_path,
    )

    assert not excluded_chains
    assert len(trade_results) == 1
    assert event_logs == {"sig-valid": []}
    assert captured["funding_provider"] is not None
    assert captured["funding_provider"].__class__.__name__ == "BybitFundingProvider"


def test_build_funding_provider_logs_warning_when_historical_data_missing(caplog, tmp_path) -> None:
    policy = PolicyLoader().load("original_chain")
    policy.execution.funding_model = "historical"

    with caplog.at_level("WARNING"):
        provider = _build_funding_provider(policy, tmp_path, "BTCUSDT")

    assert provider is None
    assert "Funding storico non disponibile" in caplog.text
