from __future__ import annotations

import argparse
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

from src.signal_chain_lab.domain.enums import ChainInputMode, EventSource, EventType
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent


def _load_module() -> object:
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "run_policy_report.py"
    spec = importlib.util.spec_from_file_location("run_policy_report_script", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sample_chain(signal_id: str, created_at: datetime) -> CanonicalChain:
    return CanonicalChain(
        signal_id=signal_id,
        trader_id="trader-a",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=False,
        created_at=created_at,
        events=[
            CanonicalEvent(
                signal_id=signal_id,
                trader_id="trader-a",
                symbol="BTCUSDT",
                side="BUY",
                timestamp=created_at,
                event_type=EventType.OPEN_SIGNAL,
                source=EventSource.TRADER,
                payload={"entry_prices": [100.0], "tp_levels": [110.0], "sl_price": 90.0},
                sequence=0,
            )
        ],
    )


def test_main_applies_max_trades(monkeypatch, tmp_path: Path) -> None:
    module = _load_module()

    class FakeLoader:
        def load(self, name: str):
            return type("Policy", (), {"name": name})()

    first = _sample_chain("sig-1", datetime(2026, 1, 1, tzinfo=timezone.utc))
    second = _sample_chain("sig-2", datetime(2026, 1, 2, tzinfo=timezone.utc))

    monkeypatch.setattr(
        module,
        "parse_args",
        lambda: argparse.Namespace(
            policy="original_chain",
            db_path="fake.sqlite3",
            market_dir=str(tmp_path / "market"),
            price_basis="last",
            timeframe="1m",
            date_from=None,
            date_to=None,
            trader_id=None,
            max_trades=1,
            output_dir=str(tmp_path / "out"),
            write_trade_artifacts=True,
        ),
    )
    monkeypatch.setattr(module, "PolicyLoader", lambda: FakeLoader())
    monkeypatch.setattr(module.SignalChainBuilder, "build_all", lambda **kwargs: [first, second])
    monkeypatch.setattr(module, "adapt_signal_chain", lambda chain: chain)
    monkeypatch.setattr(module, "_build_market_provider", lambda **kwargs: None)

    captured_chains: list[CanonicalChain] = []

    class _Artifacts:
        output_dir = tmp_path / "out"
        summary_json_path = tmp_path / "out" / "summary.json"
        summary_csv_path = tmp_path / "out" / "summary.csv"
        trade_results_csv_path = tmp_path / "out" / "trades.csv"
        excluded_chains_csv_path = tmp_path / "out" / "excluded.csv"
        html_report_path = tmp_path / "out" / "report.html"

    def _fake_run_policy_report(*, chains, **kwargs):
        captured_chains.extend(chains)
        return _Artifacts()

    monkeypatch.setattr(module, "run_policy_report", _fake_run_policy_report)

    rc = module.main()

    assert rc == 0
    assert [chain.signal_id for chain in captured_chains] == ["sig-1"]
