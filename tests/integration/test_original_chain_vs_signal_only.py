from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.domain.enums import ChainInputMode, EventSource, EventType
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent
from src.signal_chain_lab.engine.simulator import simulate_chain
from src.signal_chain_lab.policies.policy_loader import PolicyLoader
from src.signal_chain_lab.reports.trade_report import build_trade_result


def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def test_same_chain_has_distinct_policy_names() -> None:
    chain = CanonicalChain(
        signal_id="sig-policy-1",
        trader_id="trader-a",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=True,
        created_at=_utc("2026-01-01T00:00:00"),
        events=[
            CanonicalEvent(
                signal_id="sig-policy-1",
                trader_id="trader-a",
                symbol="BTCUSDT",
                side="BUY",
                timestamp=_utc("2026-01-01T00:00:00"),
                event_type=EventType.OPEN_SIGNAL,
                source=EventSource.TRADER,
                payload={"entry_prices": [100.0], "sl_price": 90.0, "tp_levels": [110.0]},
                sequence=0,
            )
        ],
    )

    original_policy = PolicyLoader().load("original_chain")
    signal_only_policy = PolicyLoader().load("signal_only")

    original_log, original_state = simulate_chain(chain, original_policy)
    signal_only_log, signal_only_state = simulate_chain(chain, signal_only_policy)

    original_result = build_trade_result(original_state, original_log)
    signal_only_result = build_trade_result(signal_only_state, signal_only_log)

    assert original_result.signal_id == signal_only_result.signal_id
    assert original_result.policy_name == "original_chain"
    assert signal_only_result.policy_name == "signal_only"
    assert original_result.policy_name != signal_only_result.policy_name
