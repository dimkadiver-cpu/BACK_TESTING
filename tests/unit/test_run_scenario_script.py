from __future__ import annotations

import argparse
import importlib.util
import typing
from datetime import datetime, timezone
from pathlib import Path

from src.signal_chain_lab.domain.enums import ChainInputMode, EventSource, EventType
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent
from src.signal_chain_lab.domain.results import ScenarioResult


def _load_module() -> object:
    if not hasattr(typing, "Self"):
        typing.Self = object  # type: ignore[attr-defined]
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "run_scenario.py"
    spec = importlib.util.spec_from_file_location("run_scenario_script", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sample_chain() -> CanonicalChain:
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return CanonicalChain(
        signal_id="sig-1",
        trader_id="trader-a",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=False,
        created_at=timestamp,
        events=[
            CanonicalEvent(
                signal_id="sig-1",
                trader_id="trader-a",
                symbol="BTCUSDT",
                side="BUY",
                timestamp=timestamp,
                event_type=EventType.OPEN_SIGNAL,
                source=EventSource.TRADER,
                payload={"entry_prices": [100.0], "tp_levels": [110.0], "sl_price": 90.0},
                sequence=0,
            )
        ],
    )


def test_normalize_policy_names_accepts_single_and_multi() -> None:
    module = _load_module()
    args = argparse.Namespace(policy="original_chain", policies=["signal_only,tp_50_30_20", "signal_only"])
    names = module._normalize_policy_names(args)
    assert names == ["original_chain", "signal_only", "tp_50_30_20"]


def test_main_runs_multi_policy_in_single_flow(monkeypatch, tmp_path: Path) -> None:
    module = _load_module()

    class FakeLoader:
        def load(self, name: str):
            return type("Policy", (), {"name": name})()

    monkeypatch.setattr(
        module,
        "parse_args",
        lambda: argparse.Namespace(
            policy=None,
            policies=["original_chain", "signal_only"],
            db_path="fake.sqlite3",
            market_dir=str(tmp_path / "market"),
            price_basis="last",
            timeframe="1m",
            date_from=None,
            date_to=None,
            trader_id=None,
            max_trades=0,
            output_dir=str(tmp_path / "out"),
        ),
    )
    monkeypatch.setattr(module, "PolicyLoader", lambda: FakeLoader())
    monkeypatch.setattr(module.SignalChainBuilder, "build_all", lambda **kwargs: [_sample_chain()])
    monkeypatch.setattr(module, "adapt_signal_chain", lambda chain: chain)
    monkeypatch.setattr(module, "_build_market_provider", lambda **kwargs: None)

    recorded_policies: list[str] = []

    def _fake_run_scenarios(chains, policies, **kwargs):
        recorded_policies.extend(policy.name for policy in policies)
        return (
            [
                ScenarioResult(
                    policy_name=policy.name,
                    total_pnl=0.0,
                    return_pct=0.0,
                    max_drawdown=0.0,
                    win_rate=0.0,
                    profit_factor=0.0,
                    expectancy=0.0,
                    trades_count=0,
                    simulated_chains_count=0,
                    excluded_chains_count=0,
                    avg_warnings_per_trade=0.0,
                    price_basis="last",
                    exchange_faithful=False,
                )
                for policy in policies
            ],
            {policy.name: [] for policy in policies},
        )

    monkeypatch.setattr(module, "run_scenarios", _fake_run_scenarios)
    monkeypatch.setattr(
        module,
        "write_scenario_artifacts",
        lambda **kwargs: (tmp_path / "out/scenario_results.json", None, None),
    )
    monkeypatch.setattr(
        module,
        "run_policy_report",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        module,
        "_write_comparison_report",
        lambda **kwargs: (tmp_path / "out/comparison_report.html", tmp_path / "out/comparison_summary.json", tmp_path / "out/comparison_summary.csv"),
    )

    rc = module.main()
    assert rc == 0
    assert recorded_policies == ["original_chain", "signal_only"]


def test_main_passes_builder_filters_and_keeps_date_to_inclusive(monkeypatch, tmp_path: Path) -> None:
    module = _load_module()

    class FakeLoader:
        def load(self, name: str):
            return type("Policy", (), {"name": name})()

    noon_on_date_to = datetime(2026, 3, 31, 12, 0, tzinfo=timezone.utc)
    chain = CanonicalChain(
        signal_id="sig-inclusive",
        trader_id="trader_3",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=False,
        created_at=noon_on_date_to,
        events=[
            CanonicalEvent(
                signal_id="sig-inclusive",
                trader_id="trader_3",
                symbol="BTCUSDT",
                side="BUY",
                timestamp=noon_on_date_to,
                event_type=EventType.OPEN_SIGNAL,
                source=EventSource.TRADER,
                payload={"entry_prices": [100.0], "tp_levels": [110.0], "sl_price": 90.0},
                sequence=0,
            )
        ],
    )

    monkeypatch.setattr(
        module,
        "parse_args",
        lambda: argparse.Namespace(
            policy=None,
            policies=["original_chain"],
            db_path="fake.sqlite3",
            market_dir=str(tmp_path / "market"),
            price_basis="last",
            timeframe="1m",
            date_from=datetime(2026, 3, 1, tzinfo=timezone.utc),
            date_to=datetime(2026, 3, 31, tzinfo=timezone.utc),
            trader_id="trader_3",
            max_trades=0,
            output_dir=str(tmp_path / "out"),
        ),
    )
    monkeypatch.setattr(module, "PolicyLoader", lambda: FakeLoader())

    captured_builder_kwargs: dict[str, object] = {}

    def _fake_build_all(**kwargs):
        captured_builder_kwargs.update(kwargs)
        return [chain]

    monkeypatch.setattr(module.SignalChainBuilder, "build_all", _fake_build_all)
    monkeypatch.setattr(module, "adapt_signal_chain", lambda built: built)
    monkeypatch.setattr(module, "_build_market_provider", lambda **kwargs: None)

    captured_chains: list[CanonicalChain] = []

    def _fake_run_scenarios(chains, policies, **kwargs):
        captured_chains.extend(chains)
        return (
            [
                ScenarioResult(
                    policy_name=policy.name,
                    total_pnl=0.0,
                    return_pct=0.0,
                    max_drawdown=0.0,
                    win_rate=0.0,
                    profit_factor=0.0,
                    expectancy=0.0,
                    trades_count=len(chains),
                    simulated_chains_count=len(chains),
                    excluded_chains_count=0,
                    avg_warnings_per_trade=0.0,
                    price_basis="last",
                    exchange_faithful=False,
                )
                for policy in policies
            ],
            {policy.name: [] for policy in policies},
        )

    monkeypatch.setattr(module, "run_scenarios", _fake_run_scenarios)
    monkeypatch.setattr(
        module,
        "write_scenario_artifacts",
        lambda **kwargs: (tmp_path / "out/scenario_results.json", None, None),
    )
    monkeypatch.setattr(module, "run_policy_report", lambda **kwargs: None)
    monkeypatch.setattr(
        module,
        "_write_comparison_report",
        lambda **kwargs: (
            tmp_path / "out/comparison_report.html",
            tmp_path / "out/comparison_summary.json",
            tmp_path / "out/comparison_summary.csv",
        ),
    )

    rc = module.main()

    assert rc == 0
    assert captured_builder_kwargs["trader_id"] == "trader_3"
    assert captured_builder_kwargs["date_from"] == "2026-03-01"
    assert captured_builder_kwargs["date_to"] == "2026-03-31"
    assert len(captured_chains) == 1
    assert captured_chains[0].signal_id == "sig-inclusive"


def test_main_applies_max_trades_before_running(monkeypatch, tmp_path: Path) -> None:
    module = _load_module()

    class FakeLoader:
        def load(self, name: str):
            return type("Policy", (), {"name": name})()

    first = _sample_chain()
    second = CanonicalChain(
        signal_id="sig-2",
        trader_id="trader-a",
        symbol="ETHUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=False,
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        events=[],
    )

    monkeypatch.setattr(
        module,
        "parse_args",
        lambda: argparse.Namespace(
            policy="original_chain",
            policies=None,
            db_path="fake.sqlite3",
            market_dir=str(tmp_path / "market"),
            price_basis="last",
            timeframe="1m",
            date_from=None,
            date_to=None,
            trader_id=None,
            max_trades=1,
            output_dir=str(tmp_path / "out"),
        ),
    )
    monkeypatch.setattr(module, "PolicyLoader", lambda: FakeLoader())
    monkeypatch.setattr(module.SignalChainBuilder, "build_all", lambda **kwargs: [first, second])
    monkeypatch.setattr(module, "adapt_signal_chain", lambda built: built)
    monkeypatch.setattr(module, "_build_market_provider", lambda **kwargs: None)

    captured_chains: list[CanonicalChain] = []

    def _fake_run_scenarios(chains, policies, **kwargs):
        captured_chains.extend(chains)
        return (
            [
                ScenarioResult(
                    policy_name=policies[0].name,
                    total_pnl=0.0,
                    return_pct=0.0,
                    max_drawdown=0.0,
                    win_rate=0.0,
                    profit_factor=0.0,
                    expectancy=0.0,
                    trades_count=len(chains),
                    simulated_chains_count=len(chains),
                    excluded_chains_count=0,
                    avg_warnings_per_trade=0.0,
                    price_basis="last",
                    exchange_faithful=False,
                )
            ],
            {policies[0].name: []},
        )

    monkeypatch.setattr(module, "run_scenarios", _fake_run_scenarios)
    monkeypatch.setattr(
        module,
        "write_scenario_artifacts",
        lambda **kwargs: (tmp_path / "out/scenario_results.json", None, None),
    )

    rc = module.main()

    assert rc == 0
    assert [chain.signal_id for chain in captured_chains] == ["sig-1"]
