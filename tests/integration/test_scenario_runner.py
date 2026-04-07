from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.domain.enums import ChainInputMode, EventSource, EventType
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent
from src.signal_chain_lab.policies.policy_loader import PolicyLoader
from src.signal_chain_lab.scenario.runner import compare_scenarios, run_scenarios


def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def _build_chain(signal_id: str, with_tp: bool) -> CanonicalChain:
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
        created_at=_utc("2026-01-01T00:00:00"),
        events=[
            CanonicalEvent(
                signal_id=signal_id,
                trader_id="trader-a",
                symbol="BTCUSDT",
                side="BUY",
                timestamp=_utc("2026-01-01T00:00:00"),
                event_type=EventType.OPEN_SIGNAL,
                source=EventSource.TRADER,
                payload=payload,
                sequence=0,
            )
        ],
    )


def test_scenario_runner_aggregates_and_compares_policies() -> None:
    chains = [_build_chain("sig-valid", with_tp=True), _build_chain("sig-invalid", with_tp=False)]
    policies = [PolicyLoader().load("original_chain"), PolicyLoader().load("signal_only")]

    scenario_results, per_policy_trades = run_scenarios(chains=chains, policies=policies)

    assert len(scenario_results) == 2
    assert {item.policy_name for item in scenario_results} == {"original_chain", "signal_only"}

    original_result = next(item for item in scenario_results if item.policy_name == "original_chain")
    signal_only_result = next(item for item in scenario_results if item.policy_name == "signal_only")

    assert original_result.simulated_chains_count == 1
    assert signal_only_result.simulated_chains_count == 1
    assert original_result.excluded_chains_count == 1
    assert signal_only_result.excluded_chains_count == 1

    assert len(per_policy_trades["original_chain"]) == 1
    assert len(per_policy_trades["signal_only"]) == 1
    assert per_policy_trades["original_chain"][0].policy_name != per_policy_trades["signal_only"][0].policy_name

    comparisons = compare_scenarios(scenario_results, baseline_policy="original_chain")
    assert len(comparisons) == 1
    assert comparisons[0].target_policy_name == "signal_only"
