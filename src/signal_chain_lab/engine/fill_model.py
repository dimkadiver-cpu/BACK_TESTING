"""Fill model: determines order execution price and slippage."""
from __future__ import annotations

import logging
from datetime import datetime

from src.signal_chain_lab.domain.trade_state import FillRecord
from src.signal_chain_lab.engine.latency_model import apply_latency, policy_latency_ms
from src.signal_chain_lab.market.data_models import Candle
from src.signal_chain_lab.policies.base import PolicyConfig

_logger = logging.getLogger(__name__)

LIMIT_TOUCH_ASSUMPTION_WARNING = "LIMIT_TOUCH_FILLED_V1_ASSUMPTION"


def _compute_fee(price: float, qty: float, policy: PolicyConfig, liquidity_role: str | None = None) -> float:
    """Compute the trading fee for a fill based on the configured fee model.

    Supported models:
      - ``"none"`` / ``""`` → zero fee (default)
      - ``"fixed_bps"``     → ``price * qty * fee_bps / 10_000``

    Fee is always non-negative. Unknown model names fall back to zero with a log warning.
    """
    model = (policy.execution.fee_model or "none").strip().lower()
    if model in {"none", ""}:
        return 0.0
    if model == "fixed_bps":
        role = (liquidity_role or "").strip().lower()
        bps_value: float | None = None
        if role == "maker" and policy.execution.maker_fee_bps is not None:
            bps_value = float(policy.execution.maker_fee_bps)
        elif role == "taker" and policy.execution.taker_fee_bps is not None:
            bps_value = float(policy.execution.taker_fee_bps)
        else:
            bps_value = float(policy.execution.fee_bps)
        bps = float(bps_value)
        if bps <= 0:
            return 0.0
        return price * qty * bps / 10_000.0
    _logger.warning("Unknown fee_model '%s' — no fee applied", model)
    return 0.0


def _apply_slippage(price: float, policy: PolicyConfig, side: str) -> float:
    """Apply the configured slippage model to a fill price.

    Supported models:
      - ``"none"`` / ``""`` → no adjustment (default)
      - ``"fixed_bps"``     → shift price by ``execution.slippage_bps`` basis points
                              in the adverse direction (long pays more, short receives less)

    Unknown model names fall back to no slippage with a log warning.
    """
    model = (policy.execution.slippage_model or "none").strip().lower()
    if model in {"none", ""}:
        return price

    if model == "fixed_bps":
        bps = float(policy.execution.slippage_bps)
        if bps <= 0:
            return price
        normalized_side = side.upper()
        if normalized_side in {"BUY", "LONG"}:
            return price * (1.0 + bps / 10_000.0)
        else:
            return price * (1.0 - bps / 10_000.0)

    _logger.warning("Unknown slippage_model '%s' — no slippage applied", model)
    return price


def fill_market_order(
    *,
    qty: float,
    reference_price: float,
    event_timestamp: datetime,
    policy: PolicyConfig,
    side: str = "long",
    source_event_sequence: int | None = None,
) -> FillRecord:
    """Fill a market order after policy latency, applying any configured slippage."""
    latency_ms = policy_latency_ms(policy)
    fill_price = _apply_slippage(reference_price, policy, side)
    return FillRecord(
        price=fill_price,
        qty=qty,
        timestamp=apply_latency(event_timestamp, latency_ms),
        source_event_sequence=source_event_sequence,
        fee_paid=_compute_fee(fill_price, qty, policy, liquidity_role="taker"),
    )


def try_fill_limit_order_touch(
    *,
    qty: float,
    limit_price: float,
    candle: Candle,
    side: str,
    policy: PolicyConfig,
    source_event_sequence: int | None = None,
) -> FillRecord | None:
    """Touch-based limit fill model for V1.

    Long side fills when candle low <= limit.
    Short side fills when candle high >= limit.
    """
    normalized_side = side.upper()
    touched = False
    if normalized_side == "LONG":
        touched = candle.low <= limit_price
    elif normalized_side == "SHORT":
        touched = candle.high >= limit_price

    if not touched:
        return None

    latency_ms = policy_latency_ms(policy)
    return FillRecord(
        price=limit_price,
        qty=qty,
        timestamp=apply_latency(candle.timestamp, latency_ms),
        source_event_sequence=source_event_sequence,
        fee_paid=_compute_fee(limit_price, qty, policy, liquidity_role="maker"),
    )


def compute_close_fee(
    exit_price: float,
    close_qty: float,
    policy: PolicyConfig,
    *,
    liquidity_role: str | None = None,
) -> float:
    """Compute the trading fee for a TP or SL close event.

    Uses the same fee model as entry fills. Call this after resolving a close
    and deduct the result from ``state.realized_pnl`` / add to ``state.fees_paid``.
    """
    return _compute_fee(exit_price, close_qty, policy, liquidity_role=liquidity_role)
