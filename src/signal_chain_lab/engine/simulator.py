"""Main simulation orchestrator: drives signal chains through market data."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.signal_chain_lab.domain.enums import EventSource, EventType, TradeStatus
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent
from src.signal_chain_lab.domain.results import EventLogEntry
from src.signal_chain_lab.domain.trade_state import TradeState
from src.signal_chain_lab.engine.fill_model import compute_close_fee, fill_market_order, try_fill_limit_order_touch
from src.signal_chain_lab.engine.state_machine import apply_event
from src.signal_chain_lab.engine.timeout_manager import check_chain_timeout, check_pending_timeout
from src.signal_chain_lab.market.data_models import Candle, MarketDataProvider
from src.signal_chain_lab.market.intrabar_resolver import IntrabarResolution, IntrabarResolver
from src.signal_chain_lab.policies.base import PolicyConfig

_logger = logging.getLogger(__name__)

_TERMINAL_STATUSES: frozenset[TradeStatus] = frozenset({
    TradeStatus.CLOSED,
    TradeStatus.CANCELLED,
    TradeStatus.EXPIRED,
    TradeStatus.INVALID,
})


class SimulationInvariantError(RuntimeError):
    """Raised when a same-candle drain loop iteration produces no observable state progress.

    This indicates a bug in the simulation engine: a collision was detected but
    none of the guarded fields (next_tp_index, open_size, current_sl, status)
    changed after a complete resolution cycle, which would cause an infinite loop.
    """


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
    last_replayed_candle_ts: datetime | None = None

    timeframe = str(chain.metadata.get("timeframe", "1h"))
    child_timeframe = _get_effective_child_timeframe(chain, policy)
    intrabar_enabled = (
        market_provider is not None
        and policy.intrabar.event_aware_replay_enabled
        and child_timeframe is not None
    )

    i = 0
    while i < len(events):
        event = events[i]

        # ── Intrabar event-aware path ─────────────────────────────────────────
        # Activated when:
        #   1. intrabar replay is enabled with a valid child timeframe
        #   2. the event falls strictly inside a parent candle (not on its boundary)
        #   3. that parent candle has not yet been fully replayed
        if intrabar_enabled:
            parent_candle_ts = _floor_to_timeframe(event.timestamp, timeframe)
            is_intra_candle = parent_candle_ts < event.timestamp
            not_yet_processed = (
                last_replayed_candle_ts is None
                or last_replayed_candle_ts < parent_candle_ts
            )

            if is_intra_candle and not_yet_processed:
                # Collect all consecutive events that share the same parent candle
                # (they will all be handled together via child-candle replay).
                group: list[CanonicalEvent] = []
                j = i
                while j < len(events):
                    if _floor_to_timeframe(events[j].timestamp, timeframe) == parent_candle_ts:
                        group.append(events[j])
                        j += 1
                    else:
                        break

                assert child_timeframe is not None  # guaranteed by intrabar_enabled check
                _replay_parent_candle_with_events(
                    chain=chain,
                    state=state,
                    policy=policy,
                    market_provider=market_provider,
                    intrabar_resolver=intrabar_resolver,
                    logs=logs,
                    parent_candle_ts=parent_candle_ts,
                    events_in_candle=group,
                    child_timeframe=child_timeframe,
                    same_child_event_policy=policy.intrabar.same_child_event_policy,
                )

                # The parent candle is now fully accounted for via child candles.
                last_replayed_candle_ts = parent_candle_ts
                i = j  # advance past all grouped events

                # Continue with parent-level replay for the remainder of the segment
                # (candles after this parent candle, up to the next event).
                if state.status not in _TERMINAL_STATUSES:
                    next_event_ts = events[i].timestamp if i < len(events) else None
                    last_replayed_candle_ts = _replay_market_segment(
                        chain=chain,
                        state=state,
                        policy=policy,
                        market_provider=market_provider,
                        intrabar_resolver=intrabar_resolver,
                        logs=logs,
                        sequence_seed=group[-1].sequence,
                        segment_start=parent_candle_ts,
                        next_event_ts=next_event_ts,
                        last_replayed_candle_ts=last_replayed_candle_ts,
                    )
                continue

        # ── Standard path ─────────────────────────────────────────────────────
        logs.append(apply_event(state, event, policy=policy))

        if market_provider is not None:
            next_event_ts = events[i + 1].timestamp if i + 1 < len(events) else None
            last_replayed_candle_ts = _replay_market_segment(
                chain=chain,
                state=state,
                policy=policy,
                market_provider=market_provider,
                intrabar_resolver=intrabar_resolver,
                logs=logs,
                sequence_seed=event.sequence,
                segment_start=event.timestamp,
                next_event_ts=next_event_ts,
                last_replayed_candle_ts=last_replayed_candle_ts,
            )

        i += 1

    return logs, state


# ── Intrabar event-aware replay ───────────────────────────────────────────────


def _get_effective_child_timeframe(chain: CanonicalChain, policy: PolicyConfig) -> str | None:
    """Return the child timeframe for intrabar replay.

    Chain metadata ``intrabar_child_timeframe`` takes precedence over the
    policy-level ``intrabar.child_timeframe`` setting.
    """
    chain_override = chain.metadata.get("intrabar_child_timeframe")
    if chain_override is not None:
        return str(chain_override)
    return policy.intrabar.child_timeframe


def _replay_parent_candle_with_events(
    *,
    chain: CanonicalChain,
    state: TradeState,
    policy: PolicyConfig,
    market_provider: MarketDataProvider,
    intrabar_resolver: IntrabarResolver,
    logs: list[EventLogEntry],
    parent_candle_ts: datetime,
    events_in_candle: list[CanonicalEvent],
    child_timeframe: str,
    same_child_event_policy: str,
) -> None:
    """Replay a parent candle that contains one or more intra-candle events.

    Algorithm (supports N events in the same parent candle):
      for each event E_i (sorted by timestamp, sequence):
        1. replay child candles that precede E_i (respecting same_child_event_policy)
        2. apply E_i to the trade state
      then replay remaining child candles after the last event.

    Fallback: if no child candles are available, events are applied without
    intrabar splitting and ``state.warnings_count`` is incremented.
    """
    timeframe = str(chain.metadata.get("timeframe", "1h"))

    child_candles = market_provider.get_intrabar_range(
        chain.symbol, timeframe, child_timeframe, parent_candle_ts
    )

    if not child_candles:
        _logger.warning(
            "INTRABAR_EVENT_AWARE: no child candles for parent=%s symbol=%s child_tf=%s "
            "— applying %d event(s) without intrabar split",
            parent_candle_ts.isoformat(),
            chain.symbol,
            child_timeframe,
            len(events_in_candle),
        )
        for ev in events_in_candle:
            state.warnings_count += 1
            logs.append(apply_event(state, ev, policy=policy))
            if state.status in _TERMINAL_STATUSES:
                return
        return

    sorted_children = sorted(child_candles, key=lambda c: c.timestamp)
    child_idx = 0

    for ev in events_in_candle:
        # Determine which child candle contains the event timestamp.
        child_event_boundary = _floor_to_timeframe(ev.timestamp, child_timeframe)

        # Replay children that belong to the pre-event window.
        while child_idx < len(sorted_children):
            child = sorted_children[child_idx]
            if same_child_event_policy == "conservative_pre_event":
                # Include the child candle that contains the event (<=):
                # the event will only take effect from the *next* child candle.
                if child.timestamp > child_event_boundary:
                    break
            else:
                # conservative_post_event: exclude the child candle that contains
                # the event; that candle is processed with the post-event state.
                if child.timestamp >= child_event_boundary:
                    break

            terminal = _process_single_candle(
                chain=chain,
                state=state,
                policy=policy,
                market_provider=market_provider,
                intrabar_resolver=intrabar_resolver,
                logs=logs,
                candle=child,
                sequence_seed=ev.sequence,
            )
            child_idx += 1
            if terminal:
                return

        # Apply the trader event.
        logs.append(apply_event(state, ev, policy=policy))
        if state.status in _TERMINAL_STATUSES:
            return

    # Replay remaining children after the last event.
    last_seq = events_in_candle[-1].sequence
    while child_idx < len(sorted_children):
        child = sorted_children[child_idx]
        terminal = _process_single_candle(
            chain=chain,
            state=state,
            policy=policy,
            market_provider=market_provider,
            intrabar_resolver=intrabar_resolver,
            logs=logs,
            candle=child,
            sequence_seed=last_seq,
        )
        child_idx += 1
        if terminal:
            return


# ── Per-candle processing (shared by parent-level and child-level replay) ─────


def _process_single_candle(
    *,
    chain: CanonicalChain,
    state: TradeState,
    policy: PolicyConfig,
    market_provider: MarketDataProvider,
    intrabar_resolver: IntrabarResolver,
    logs: list[EventLogEntry],
    candle: Candle,
    sequence_seed: int,
) -> bool:
    """Process fills, timeouts, and SL/TP collisions for a single candle.

    Encapsulates the per-candle logic that is shared between parent-level replay
    (``_replay_market_segment``) and intrabar child-candle replay
    (``_replay_parent_candle_with_events``).

    Returns:
        True if the trade reached a terminal status; False otherwise.
    """
    _try_fill_pending_entries(state=state, policy=policy, candle=candle)

    # Cancel all pending entries if a TP level is reached before any fill.
    cancel_unfilled_idx = _tp_ref_to_index(policy.pending.cancel_unfilled_pending_after)
    if (
        policy.pending.cancel_pending_by_engine
        and cancel_unfilled_idx is not None
        and state.pending_size > 0
        and state.open_size == 0
        and _detect_tp_before_fill(state=state, candle=candle, tp_idx=cancel_unfilled_idx)
    ):
        tp_label = f"tp{cancel_unfilled_idx + 1}"
        unfilled_cancel_event = CanonicalEvent(
            signal_id=chain.signal_id,
            trader_id=chain.trader_id,
            symbol=chain.symbol,
            side=chain.side,
            timestamp=candle.timestamp,
            event_type=EventType.CANCEL_PENDING,
            source=EventSource.ENGINE,
            payload={
                "reason": f"{tp_label}_reached_before_fill",
                "raw_text": f"Engine: {tp_label.upper()} reached before entry fill — cancel pending.",
            },
            sequence=sequence_seed + 20_010,
        )
        unfilled_cancel_log = apply_event(state, unfilled_cancel_event, policy=policy)
        unfilled_cancel_log.reason = f"{tp_label}_reached_before_fill"
        logs.append(unfilled_cancel_log)
        if state.status in _TERMINAL_STATUSES:
            return True

    timeout_event = check_pending_timeout(state, candle.timestamp, policy, sequence=sequence_seed + 20_000)
    if timeout_event is None:
        timeout_event = check_chain_timeout(state, candle.timestamp, policy, sequence=sequence_seed + 20_001)
    if timeout_event is not None:
        timeout_log = apply_event(state, timeout_event, policy=policy)
        timeout_log.reason = str(timeout_event.payload.get("reason") or "")
        logs.append(timeout_log)
        if state.status in _TERMINAL_STATUSES:
            return True

    # Inner loop: drain all valid SL/TP collisions on the current candle.
    # After each partial close or SL move the state may change (new TP level,
    # new SL, reduced open_size), so the same candle must be re-evaluated until
    # no further collision exists or the trade terminates.
    loop_iter = 0
    while True:
        if state.status in _TERMINAL_STATUSES:
            break
        if state.open_size <= 0:
            break

        collision = _detect_sl_tp_collision(state=state, candle=candle)
        if collision is None:
            break

        # Snapshot for progress guard — every iteration must advance state.
        tp_idx_before = state.next_tp_index
        open_size_before = state.open_size
        sl_before = state.current_sl
        status_before = state.status

        sequence_offset = loop_iter * 100

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

        is_full_close, close_fraction, close_exit_price, close_qty = _apply_close_resolution(
            state=state, resolution=resolution
        )
        if close_qty > 0 and close_exit_price > 0:
            close_fee = compute_close_fee(close_exit_price, close_qty, policy)
            state.realized_pnl -= close_fee
            state.fees_paid += close_fee
            state.close_fees_paid += close_fee
        tp_idx_just_hit = state.next_tp_index - 1  # next_tp_index already incremented
        engine_event = _build_engine_close_event(
            chain=chain,
            resolution=resolution,
            sequence_seed=sequence_seed,
            is_full_close=is_full_close,
            close_pct=close_fraction,
            sequence_offset=sequence_offset,
        )
        engine_log = apply_event(state, engine_event, policy=policy)
        engine_log.reason = resolution.reason
        logs.append(engine_log)

        if resolution.outcome == "tp_hit" and state.open_size > 0 and state.status not in _TERMINAL_STATUSES:
            _handle_post_tp_partial_actions(
                state=state,
                policy=policy,
                chain=chain,
                resolution=resolution,
                sequence_seed=sequence_seed,
                logs=logs,
                tp_idx_hit=tp_idx_just_hit,
                sequence_offset=sequence_offset,
            )

        if state.status in _TERMINAL_STATUSES or state.open_size <= 0:
            break

        # Progress guard: if no guarded field changed, the loop would spin
        # forever — this signals a bug in the resolution pipeline.
        progressed = (
            state.next_tp_index != tp_idx_before
            or state.open_size != open_size_before
            or state.current_sl != sl_before
            or state.status != status_before
        )
        if not progressed:
            raise SimulationInvariantError(
                f"No progress in same-candle drain loop: signal_id={chain.signal_id} "
                f"candle_ts={candle.timestamp} tp_idx={state.next_tp_index} "
                f"open_size={state.open_size} sl={state.current_sl}"
            )

        loop_iter += 1

    return state.status in _TERMINAL_STATUSES


# ── Market segment replay (parent timeframe) ──────────────────────────────────


def _detect_tp_before_fill(state: TradeState, candle: Candle, tp_idx: int = 0) -> bool:
    """Return True if the given TP level is reached while no position is open.

    Covers the scenario where the price moves past a take-profit level before
    any pending limit entry is filled — the trade opportunity has expired.

    Args:
        tp_idx: zero-based index into ``state.tp_levels`` (0 = TP1, 1 = TP2, …).
    """
    if state.open_size > 0 or state.pending_size <= 0:
        return False
    if not state.tp_levels or tp_idx >= len(state.tp_levels):
        return False

    tp_price = state.tp_levels[tp_idx]
    normalized_side = state.side.upper()

    if normalized_side in {"BUY", "LONG"}:
        return candle.high >= tp_price
    return candle.low <= tp_price


def _tp_ref_to_index(ref: str | None) -> int | None:
    """Parse a TP reference string to a zero-based index.

    Examples: ``"tp1"`` → 0, ``"tp2"`` → 1. Returns ``None`` for invalid input.
    """
    if ref is None:
        return None
    s = str(ref).strip().lower()
    if s.startswith("tp"):
        try:
            return int(s[2:]) - 1
        except (ValueError, IndexError):
            pass
    return None


def _detect_sl_tp_collision(state: TradeState, candle: Candle) -> tuple[bool, bool] | None:
    if state.status in {TradeStatus.CLOSED, TradeStatus.CANCELLED, TradeStatus.EXPIRED, TradeStatus.INVALID}:
        return None
    if state.current_sl is None or not state.tp_levels:
        return None
    if state.open_size <= 0:
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


def _build_engine_close_event(
    *,
    chain: CanonicalChain,
    resolution: IntrabarResolution,
    sequence_seed: int,
    is_full_close: bool = True,
    close_pct: float = 1.0,
    sequence_offset: int = 0,
) -> CanonicalEvent:
    """Build the engine-generated close event for an SL or TP resolution.

    For partial TP hits (``is_full_close=False``) emits ``CLOSE_PARTIAL`` with
    ``close_pct`` so the state machine reduces ``open_size`` proportionally.
    For SL hits and the final TP emits ``CLOSE_FULL``.
    """
    if resolution.outcome == "tp_hit" and not is_full_close:
        return CanonicalEvent(
            signal_id=chain.signal_id,
            trader_id=chain.trader_id,
            symbol=chain.symbol,
            side=chain.side,
            timestamp=resolution.decided_at,
            event_type=EventType.CLOSE_PARTIAL,
            source=EventSource.ENGINE,
            payload={
                "reason": "tp_hit_partial",
                "close_pct": close_pct,
                "raw_text": "Engine: partial TP close from market data.",
            },
            sequence=sequence_seed + 10_000 + sequence_offset,
        )

    reason = "tp_hit" if resolution.outcome == "tp_hit" else "sl_hit"
    return CanonicalEvent(
        signal_id=chain.signal_id,
        trader_id=chain.trader_id,
        symbol=chain.symbol,
        side=chain.side,
        timestamp=resolution.decided_at,
        event_type=EventType.CLOSE_FULL,
        source=EventSource.ENGINE,
        payload={
            "reason": reason,
            "raw_text": (
                "Engine: final TP close from market data."
                if reason == "tp_hit"
                else "Engine: SL hit from market data."
            ),
        },
        sequence=sequence_seed + 10_000 + sequence_offset,
    )


def _handle_post_tp_partial_actions(
    *,
    state: TradeState,
    policy: PolicyConfig,
    chain: CanonicalChain,
    resolution: IntrabarResolution,
    sequence_seed: int,
    logs: list[EventLogEntry],
    tp_idx_hit: int,
    sequence_offset: int = 0,
) -> None:
    """Emit engine events triggered by a partial TP hit.

    Handles:
    - Break-even SL move when ``sl.be_trigger`` matches the TP just hit.
    - Cancel of remaining pending (averaging) entries when
      ``pending.cancel_averaging_pending_after_tp1`` is True and TP1 was hit.
    """
    if state.open_size <= 0:
        return

    # Break-even trigger
    be_trigger = policy.sl.be_trigger
    if (
        be_trigger is not None
        and state.avg_entry_price is not None
        and state.current_sl != state.avg_entry_price
    ):
        trigger = str(be_trigger).lower()
        if trigger.startswith("tp"):
            try:
                trigger_index = int(trigger[2:]) - 1  # "tp1" → index 0
            except (ValueError, IndexError):
                trigger_index = -1
            if tp_idx_hit == trigger_index:
                be_event = CanonicalEvent(
                    signal_id=chain.signal_id,
                    trader_id=chain.trader_id,
                    symbol=chain.symbol,
                    side=chain.side,
                    timestamp=resolution.decided_at,
                    event_type=EventType.MOVE_STOP_TO_BE,
                    source=EventSource.ENGINE,
                    payload={
                        "reason": "be_trigger",
                        "raw_text": f"Engine: move SL to break-even after tp{tp_idx_hit + 1}.",
                    },
                    sequence=sequence_seed + 10_001 + sequence_offset,
                )
                logs.append(apply_event(state, be_event, policy=policy))

    # Cancel remaining averaging pending entries after tpN
    cancel_after_idx = _tp_ref_to_index(policy.pending.cancel_averaging_pending_after)
    if (
        policy.pending.cancel_pending_by_engine
        and cancel_after_idx is not None
        and state.pending_size > 0
        and tp_idx_hit == cancel_after_idx
    ):
        tp_label = f"tp{cancel_after_idx + 1}"
        cancel_event = CanonicalEvent(
            signal_id=chain.signal_id,
            trader_id=chain.trader_id,
            symbol=chain.symbol,
            side=chain.side,
            timestamp=resolution.decided_at,
            event_type=EventType.CANCEL_PENDING,
            source=EventSource.ENGINE,
            payload={
                "reason": f"cancel_averaging_after_{tp_label}",
                "raw_text": f"Engine: cancel remaining pending entries after {tp_label.upper()}.",
            },
            sequence=sequence_seed + 10_002 + sequence_offset,
        )
        logs.append(apply_event(state, cancel_event, policy=policy))


def _replay_market_segment(
    *,
    chain: CanonicalChain,
    state: TradeState,
    policy: PolicyConfig,
    market_provider: MarketDataProvider,
    intrabar_resolver: IntrabarResolver,
    logs: list[EventLogEntry],
    sequence_seed: int,
    segment_start: datetime,
    next_event_ts: datetime | None,
    last_replayed_candle_ts: datetime | None,
) -> datetime | None:
    timeframe = str(chain.metadata.get("timeframe", "1h"))
    segment_start_bucket = _floor_to_timeframe(segment_start, timeframe)
    chain_timeout_at: datetime | None = None
    if next_event_ts is not None:
        segment_end = _floor_to_timeframe(next_event_ts, timeframe)
    else:
        metadata = market_provider.get_metadata(chain.symbol, timeframe)
        chain_timeout_at = (
            state.created_at + timedelta(hours=policy.pending.chain_timeout_hours)
            if state.created_at is not None
            else segment_start_bucket
        )
        segment_end = min(chain_timeout_at, metadata.end) if metadata and metadata.end else chain_timeout_at

    candles = market_provider.get_range(chain.symbol, timeframe, segment_start_bucket, segment_end)
    for candle in candles:
        if last_replayed_candle_ts is not None and candle.timestamp <= last_replayed_candle_ts:
            continue
        if next_event_ts is not None and candle.timestamp >= _floor_to_timeframe(next_event_ts, timeframe):
            break

        terminal = _process_single_candle(
            chain=chain,
            state=state,
            policy=policy,
            market_provider=market_provider,
            intrabar_resolver=intrabar_resolver,
            logs=logs,
            candle=candle,
            sequence_seed=sequence_seed,
        )
        last_replayed_candle_ts = candle.timestamp
        if terminal:
            break

    if next_event_ts is None:
        last_replayed_candle_ts = _apply_terminal_timeout_if_due(
            state=state,
            policy=policy,
            logs=logs,
            sequence_seed=sequence_seed,
            segment_end=segment_end,
            chain_timeout_at=chain_timeout_at,
            last_replayed_candle_ts=last_replayed_candle_ts,
        )

    return last_replayed_candle_ts


def _apply_terminal_timeout_if_due(
    *,
    state: TradeState,
    policy: PolicyConfig,
    logs: list[EventLogEntry],
    sequence_seed: int,
    segment_end: datetime,
    chain_timeout_at: datetime | None,
    last_replayed_candle_ts: datetime | None,
) -> datetime | None:
    if state.status in {TradeStatus.CLOSED, TradeStatus.CANCELLED, TradeStatus.EXPIRED, TradeStatus.INVALID}:
        return last_replayed_candle_ts
    if state.created_at is None:
        return last_replayed_candle_ts

    pending_timeout_at = state.created_at + timedelta(hours=policy.pending.pending_timeout_hours)
    if (
        state.pending_size > 0
        and pending_timeout_at <= segment_end
        and (last_replayed_candle_ts is None or last_replayed_candle_ts < pending_timeout_at)
    ):
        timeout_event = check_pending_timeout(state, pending_timeout_at, policy, sequence=sequence_seed + 20_000)
        if timeout_event is not None:
            timeout_log = apply_event(state, timeout_event, policy=policy)
            timeout_log.reason = str(timeout_event.payload.get("reason") or "")
            logs.append(timeout_log)
            last_replayed_candle_ts = pending_timeout_at
            if state.status in {TradeStatus.CLOSED, TradeStatus.CANCELLED, TradeStatus.EXPIRED, TradeStatus.INVALID}:
                return last_replayed_candle_ts

    if (
        chain_timeout_at is not None
        and chain_timeout_at <= segment_end
        and (last_replayed_candle_ts is None or last_replayed_candle_ts < chain_timeout_at)
    ):
        timeout_event = check_chain_timeout(state, chain_timeout_at, policy, sequence=sequence_seed + 20_001)
        if timeout_event is not None:
            timeout_log = apply_event(state, timeout_event, policy=policy)
            timeout_log.reason = str(timeout_event.payload.get("reason") or "")
            logs.append(timeout_log)
            last_replayed_candle_ts = chain_timeout_at

    return last_replayed_candle_ts


def _try_fill_pending_entries(state: TradeState, policy: PolicyConfig, candle: Candle) -> None:
    if state.pending_size <= 0 or state.status not in {TradeStatus.PENDING, TradeStatus.ACTIVE}:
        return

    filled_plan_ids = {
        fill.plan_id
        for fill in state.fills
        if fill.plan_id is not None
    }
    pending_plans = [
        plan
        for plan in state.entries_planned
        if plan.plan_id not in filled_plan_ids
        and (plan.price is not None or plan.order_type == "market")
    ]
    if not pending_plans:
        return

    for plan in pending_plans:
        qty = float(plan.size_ratio)
        fill = None
        if plan.order_type == "market":
            reference_price = float(plan.price) if plan.price is not None else float(candle.open)
            fill = fill_market_order(
                qty=qty,
                reference_price=reference_price,
                event_timestamp=plan.activation_ts or candle.timestamp,
                policy=policy,
                side=state.side,
                source_event_sequence=plan.sequence,
            )
        elif plan.order_type == "limit":
            fill = try_fill_limit_order_touch(
                qty=qty,
                limit_price=float(plan.price),
                candle=candle,
                side=_normalize_fill_side(state.side),
                policy=policy,
                source_event_sequence=plan.sequence,
            )

        if fill is None:
            continue

        if plan.plan_id is not None:
            fill = fill.model_copy(update={"plan_id": plan.plan_id})

        previous_notional = (state.avg_entry_price or 0.0) * state.open_size
        new_notional = previous_notional + (fill.price * fill.qty)
        state.fills.append(fill)
        state.pending_size = max(0.0, state.pending_size - fill.qty)
        state.open_size += fill.qty
        state.avg_entry_price = new_notional / state.open_size if state.open_size > 0 else None
        state.max_position_size = max(state.max_position_size, state.open_size)
        state.first_fill_at = state.first_fill_at or fill.timestamp
        state.fees_paid += fill.fee_paid
        state.status = TradeStatus.ACTIVE


def _apply_close_resolution(
    state: TradeState, resolution: IntrabarResolution
) -> tuple[bool, float, float, float]:
    """Realize PnL for an SL or TP resolution and update TP tracking state.

    For TP hits, closes only the policy-defined fraction of the position and
    increments ``state.next_tp_index``.  For SL hits and the last TP, closes
    the full remaining position.

    Returns:
        (is_full_close, close_fraction, exit_price, close_qty)
        ``is_full_close``  — True when the entire remaining position is being closed.
        ``close_fraction`` — fraction of current ``open_size`` being closed (0.0–1.0).
        ``exit_price``     — price at which the close was executed (0.0 if unavailable).
        ``close_qty``      — quantity closed (0.0 if position was empty or price unavailable).
    """
    if state.open_size <= 0 or state.avg_entry_price is None:
        return True, 1.0, 0.0, 0.0

    if resolution.outcome == "sl_hit":
        exit_price = state.current_sl
        if exit_price is None:
            return True, 1.0, 0.0, 0.0
        close_qty = state.open_size
        direction = 1.0 if state.side.upper() in {"BUY", "LONG"} else -1.0
        state.realized_pnl += (float(exit_price) - state.avg_entry_price) * close_qty * direction
        state.unrealized_pnl = 0.0
        return True, 1.0, float(exit_price), close_qty

    # TP hit
    n_tps = len(state.tp_levels)
    if n_tps == 0:
        return True, 1.0, 0.0, 0.0

    tp_idx = state.next_tp_index
    tp_idx_clamped = min(tp_idx, n_tps - 1)
    exit_price = state.tp_levels[tp_idx_clamped]
    is_last_tp = tp_idx_clamped >= n_tps - 1

    if state.tp_close_fractions and tp_idx < len(state.tp_close_fractions):
        close_fraction = state.tp_close_fractions[tp_idx]
    else:
        close_fraction = 1.0  # fallback: close all

    is_full_close = is_last_tp
    close_qty = state.open_size if is_full_close else state.open_size * close_fraction

    direction = 1.0 if state.side.upper() in {"BUY", "LONG"} else -1.0
    state.realized_pnl += (float(exit_price) - state.avg_entry_price) * close_qty * direction
    if is_full_close:
        state.unrealized_pnl = 0.0

    # Advance TP index so the next check uses the subsequent level
    state.next_tp_index = min(tp_idx + 1, n_tps)

    return is_full_close, close_fraction, float(exit_price), close_qty


def _normalize_fill_side(side: str) -> str:
    return "LONG" if side.upper() in {"BUY", "LONG"} else "SHORT"


def _get_event_candle(
    *,
    market_provider: MarketDataProvider,
    symbol: str,
    timeframe: str,
    event_ts: datetime,
) -> Candle | None:
    candle = market_provider.get_candle(symbol, timeframe, event_ts)
    if candle is not None:
        return candle

    bucket_ts = _floor_to_timeframe(event_ts, timeframe)
    if bucket_ts == event_ts:
        return None
    return market_provider.get_candle(symbol, timeframe, bucket_ts)


def _floor_to_timeframe(ts: datetime, timeframe: str) -> datetime:
    delta = _timeframe_to_delta(timeframe)
    if delta is None:
        return ts

    anchor = ts.astimezone(timezone.utc) if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
    if delta >= timedelta(days=1):
        return anchor.replace(hour=0, minute=0, second=0, microsecond=0)

    seconds = int(delta.total_seconds())
    floored = int(anchor.timestamp()) // seconds * seconds
    return datetime.fromtimestamp(floored, tz=timezone.utc)


def _timeframe_to_delta(timeframe: str) -> timedelta | None:
    if not timeframe:
        return None
    unit = timeframe[-1:].lower()
    value = timeframe[:-1]
    if not value.isdigit():
        return None
    amount = int(value)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    return None
