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

    for index, event in enumerate(events):
        logs.append(apply_event(state, event, policy=policy))

        if market_provider is None:
            continue

        next_event_ts = events[index + 1].timestamp if index + 1 < len(events) else None
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

    return logs, state


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
            sequence=sequence_seed + 10_000,
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
        sequence=sequence_seed + 10_000,
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
                    sequence=sequence_seed + 10_001,
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
            sequence=sequence_seed + 10_002,
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

        _try_fill_pending_entries(state=state, policy=policy, candle=candle)

        # Cancel all pending if tpN reached before any entry filled
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
            last_replayed_candle_ts = candle.timestamp
            if state.status in {TradeStatus.CLOSED, TradeStatus.CANCELLED, TradeStatus.EXPIRED, TradeStatus.INVALID}:
                break

        timeout_event = check_pending_timeout(state, candle.timestamp, policy, sequence=sequence_seed + 20_000)
        if timeout_event is None:
            timeout_event = check_chain_timeout(state, candle.timestamp, policy, sequence=sequence_seed + 20_001)
        if timeout_event is not None:
            timeout_log = apply_event(state, timeout_event, policy=policy)
            timeout_log.reason = str(timeout_event.payload.get("reason") or "")
            logs.append(timeout_log)
            last_replayed_candle_ts = candle.timestamp
            if state.status in {TradeStatus.CLOSED, TradeStatus.CANCELLED, TradeStatus.EXPIRED, TradeStatus.INVALID}:
                break

        collision = _detect_sl_tp_collision(state=state, candle=candle)
        if collision is None:
            last_replayed_candle_ts = candle.timestamp
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

        is_full_close, close_fraction, close_exit_price, close_qty = _apply_close_resolution(
            state=state, resolution=resolution
        )
        if close_qty > 0 and close_exit_price > 0:
            close_fee = compute_close_fee(close_exit_price, close_qty, policy)
            state.realized_pnl -= close_fee
            state.fees_paid += close_fee
        tp_idx_just_hit = state.next_tp_index - 1  # next_tp_index already incremented
        engine_event = _build_engine_close_event(
            chain=chain,
            resolution=resolution,
            sequence_seed=sequence_seed,
            is_full_close=is_full_close,
            close_pct=close_fraction,
        )
        engine_log = apply_event(state, engine_event, policy=policy)
        engine_log.reason = resolution.reason
        logs.append(engine_log)
        last_replayed_candle_ts = candle.timestamp

        if resolution.outcome == "tp_hit" and not is_full_close:
            _handle_post_tp_partial_actions(
                state=state,
                policy=policy,
                chain=chain,
                resolution=resolution,
                sequence_seed=sequence_seed,
                logs=logs,
                tp_idx_hit=tp_idx_just_hit,
            )

        if state.status in {TradeStatus.CLOSED, TradeStatus.CANCELLED, TradeStatus.EXPIRED, TradeStatus.INVALID}:
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

    pending_plans = [
        plan for index, plan in enumerate(state.entries_planned)
        if index >= len(state.fills) and (plan.price is not None or plan.order_type == "market")
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
