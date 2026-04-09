from __future__ import annotations

import csv
import json
from datetime import datetime, timezone

from src.signal_chain_lab.domain.enums import ChainInputMode, EventSource, EventType
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent
from src.signal_chain_lab.policies.policy_loader import PolicyLoader
from src.signal_chain_lab.policy_report.runner import run_policy_report


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
