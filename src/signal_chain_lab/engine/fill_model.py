"""Fill model: determines order execution price and slippage."""
from __future__ import annotations

from datetime import datetime

from src.signal_chain_lab.domain.trade_state import FillRecord
from src.signal_chain_lab.engine.latency_model import apply_latency, policy_latency_ms
from src.signal_chain_lab.market.data_models import Candle
from src.signal_chain_lab.policies.base import PolicyConfig


LIMIT_TOUCH_ASSUMPTION_WARNING = "LIMIT_TOUCH_FILLED_V1_ASSUMPTION"


def fill_market_order(
    *,
    qty: float,
    reference_price: float,
    event_timestamp: datetime,
    policy: PolicyConfig,
    source_event_sequence: int | None = None,
) -> FillRecord:
    """Fill a market order after policy latency using reference_price."""
    latency_ms = policy_latency_ms(policy)
    return FillRecord(
        price=reference_price,
        qty=qty,
        timestamp=apply_latency(event_timestamp, latency_ms),
        source_event_sequence=source_event_sequence,
        fee_paid=0.0,
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
        fee_paid=0.0,
    )
