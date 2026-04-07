"""Main simulation orchestrator: drives signal chains through market data."""
from __future__ import annotations

from src.signal_chain_lab.domain.enums import TradeStatus
from src.signal_chain_lab.domain.events import CanonicalChain
from src.signal_chain_lab.domain.results import EventLogEntry
from src.signal_chain_lab.domain.trade_state import TradeState
from src.signal_chain_lab.market.data_models import MarketDataProvider
from src.signal_chain_lab.engine.state_machine import apply_event
from src.signal_chain_lab.policies.base import PolicyConfig


def build_initial_state(chain: CanonicalChain, policy: PolicyConfig) -> TradeState:
    return TradeState(
        signal_id=chain.signal_id,
        trader_id=chain.trader_id,
        symbol=chain.symbol,
        side=chain.side,
        status=TradeStatus.NEW,
        input_mode=chain.input_mode,
        policy_name=policy.name,
    )


def simulate_chain(
    chain: CanonicalChain,
    policy: PolicyConfig,
    market_provider: MarketDataProvider | None = None,
) -> tuple[list[EventLogEntry], TradeState]:
    del market_provider
    state = build_initial_state(chain, policy)
    logs: list[EventLogEntry] = []
    for event in sorted(chain.events, key=lambda evt: (evt.timestamp, evt.sequence)):
        logs.append(apply_event(state, event))
    return logs, state
