"""Main simulation orchestrator: drives signal chains through market data."""
from __future__ import annotations

import logging

from src.signal_chain_lab.domain.enums import EventSource, EventType, TradeStatus
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent
from src.signal_chain_lab.domain.results import EventLogEntry
from src.signal_chain_lab.domain.trade_state import TradeState
from src.signal_chain_lab.engine.state_machine import apply_event
from src.signal_chain_lab.market.data_models import Candle, MarketDataProvider
from src.signal_chain_lab.market.intrabar_resolver import IntrabarResolution, IntrabarResolver
from src.signal_chain_lab.policies.base import PolicyConfig

_logger = logging.getLogger(__name__)


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
    state = build_initial_state(chain, policy)
    logs: list[EventLogEntry] = []

    events = sorted(chain.events, key=lambda evt: (evt.timestamp, evt.sequence))
    intrabar_resolver = IntrabarResolver()

    for event in events:
        logs.append(apply_event(state, event))

        if market_provider is None:
            continue

        timeframe = str(chain.metadata.get("timeframe", "1h"))
        candle = market_provider.get_candle(chain.symbol, timeframe, event.timestamp)
        if candle is None:
            continue

        collision = _detect_sl_tp_collision(state=state, candle=candle)
        if collision is None:
            continue

        resolution = _resolve_collision(
            state=state,
            chain=chain,
            market_provider=market_provider,
            candle=candle,
            intrabar_resolver=intrabar_resolver,
        )

        if resolution.used_fallback:
            state.warnings_count += 1
            _logger.warning(
                "Intrabar fallback applied: signal_id=%s symbol=%s warning_code=%s reason=%s",
                chain.signal_id,
                chain.symbol,
                resolution.warning_code,
                resolution.reason,
            )

        engine_event = _build_engine_close_event(chain=chain, resolution=resolution, sequence_seed=event.sequence)
        engine_log = apply_event(state, engine_event)
        engine_log.reason = resolution.reason
        logs.append(engine_log)

    return logs, state


def _detect_sl_tp_collision(state: TradeState, candle: Candle) -> tuple[bool, bool] | None:
    if state.status in {TradeStatus.CLOSED, TradeStatus.CANCELLED, TradeStatus.EXPIRED, TradeStatus.INVALID}:
        return None
    if state.current_sl is None or not state.tp_levels:
        return None
    if state.pending_size <= 0 and state.open_size <= 0:
        return None

    normalized_side = state.side.upper()
    tp_price = state.tp_levels[min(state.next_tp_index, len(state.tp_levels) - 1)]

    if normalized_side in {"BUY", "LONG"}:
        sl_hit = candle.low <= state.current_sl
        tp_hit = candle.high >= tp_price
    else:
        sl_hit = candle.high >= state.current_sl
        tp_hit = candle.low <= tp_price

    if not sl_hit and not tp_hit:
        return None
    return sl_hit, tp_hit


def _resolve_collision(
    *,
    state: TradeState,
    chain: CanonicalChain,
    market_provider: MarketDataProvider,
    candle: Candle,
    intrabar_resolver: IntrabarResolver,
) -> IntrabarResolution:
    sl_hit, tp_hit = _detect_sl_tp_collision(state=state, candle=candle) or (False, False)
    if sl_hit and not tp_hit:
        return IntrabarResolution(
            outcome="sl_hit",
            reason="parent_candle_only_sl_hit",
            decided_at=candle.timestamp,
        )
    if tp_hit and not sl_hit:
        return IntrabarResolution(
            outcome="tp_hit",
            reason="parent_candle_only_tp_hit",
            decided_at=candle.timestamp,
        )

    child_timeframe_value = chain.metadata.get("intrabar_child_timeframe")
    if child_timeframe_value is None:
        return IntrabarResolution(
            outcome="sl_hit",
            reason="fallback_no_child_timeframe_configured",
            decided_at=candle.timestamp,
            used_fallback=True,
            warning_code=IntrabarResolver.FALLBACK_WARNING_CODE,
        )

    timeframe = str(chain.metadata.get("timeframe", "1h"))
    child_timeframe = str(child_timeframe_value)
    child_candles = market_provider.get_intrabar_range(
        chain.symbol,
        timeframe,
        child_timeframe,
        candle.timestamp,
    )
    return intrabar_resolver.resolve_sl_tp_collision(
        parent_candle=candle,
        child_candles=child_candles,
        side=state.side,
        sl_price=state.current_sl,
        tp_price=state.tp_levels[min(state.next_tp_index, len(state.tp_levels) - 1)],
    )


def _build_engine_close_event(*, chain: CanonicalChain, resolution: IntrabarResolution, sequence_seed: int) -> CanonicalEvent:
    reason = "tp_hit" if resolution.outcome == "tp_hit" else "sl_hit"
    return CanonicalEvent(
        signal_id=chain.signal_id,
        trader_id=chain.trader_id,
        symbol=chain.symbol,
        side=chain.side,
        timestamp=resolution.decided_at,
        event_type=EventType.CLOSE_FULL,
        source=EventSource.ENGINE,
        payload={"reason": reason},
        sequence=sequence_seed + 10_000,
    )
