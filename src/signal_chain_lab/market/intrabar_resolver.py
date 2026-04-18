"""Resolve ambiguous same-candle SL/TP collisions using child timeframe candles."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable

from pydantic import BaseModel, Field

from src.signal_chain_lab.market.data_models import Candle
from src.signal_chain_lab.market.runtime_config import MarketRuntimeConfig

_logger = logging.getLogger(__name__)


class IntrabarResolution(BaseModel):
    """Audit-friendly output of intrabar collision resolution."""

    outcome: str
    reason: str
    decided_at: datetime
    child_timeframe_used: bool = False
    used_fallback: bool = False
    warning_code: str | None = None
    examined_child_candles: int = 0
    descended_parent_bars: int = 0
    resolved_events: list[str] = Field(default_factory=list)
    final_event_order: list[str] = Field(default_factory=list)
    candidate_reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class IntrabarResolver:
    """Resolve SL/TP order in same parent candle."""

    FALLBACK_WARNING_CODE = "INTRABAR_CHILD_DATA_UNAVAILABLE"

    def __init__(self, runtime_config: MarketRuntimeConfig | None = None) -> None:
        self._runtime_config = runtime_config

    def select_candidate_reasons(
        self,
        *,
        parent_candle: Candle,
        side: str,
        sl_price: float | None = None,
        tp_price: float | None = None,
        entry_prices: Iterable[float] | None = None,
        has_trader_update: bool = False,
        has_time_boundary: bool = False,
    ) -> list[str]:
        normalized_side = side.upper()
        reasons: list[str] = []

        if any(self._touches_level(parent_candle, float(price)) for price in (entry_prices or []) if price is not None):
            reasons.append("entry_touch_possible")
        if sl_price is not None and self._is_sl_hit(parent_candle, normalized_side, sl_price):
            reasons.append("sl_touch_possible")
        if tp_price is not None and self._is_tp_hit(parent_candle, normalized_side, tp_price):
            reasons.append("tp_touch_possible")
        if sl_price is not None and tp_price is not None:
            sl_hit = self._is_sl_hit(parent_candle, normalized_side, sl_price)
            tp_hit = self._is_tp_hit(parent_candle, normalized_side, tp_price)
            if sl_hit and tp_hit:
                reasons.append("sl_tp_collision")
        if has_trader_update:
            reasons.append("trader_update_inside_parent_bar")
        if has_time_boundary:
            reasons.append("important_time_boundary")
        return reasons

    def should_descend_to_child_timeframe(self, **kwargs) -> bool:
        return bool(self.select_candidate_reasons(**kwargs))

    def resolve_sl_tp_collision(
        self,
        *,
        parent_candle: Candle,
        child_candles: list[Candle],
        side: str,
        sl_price: float,
        tp_price: float,
        runtime_config: MarketRuntimeConfig | None = None,
        candidate_reasons: list[str] | None = None,
    ) -> IntrabarResolution:
        config = runtime_config or self._runtime_config
        ordered_children = sorted(child_candles, key=lambda item: item.timestamp)
        normalized_side = side.upper()
        reasons = candidate_reasons or self.select_candidate_reasons(
            parent_candle=parent_candle,
            side=normalized_side,
            sl_price=sl_price,
            tp_price=tp_price,
        )
        metadata = {
            "parent_timeframe": parent_candle.timeframe,
            "child_timeframe": ordered_children[0].timeframe if ordered_children else "",
        }
        if config is not None:
            metadata["simulation_tf"] = config.simulation_tf
            metadata["detail_tf"] = config.detail_tf

        for child in ordered_children:
            sl_hit = self._is_sl_hit(child, normalized_side, sl_price)
            tp_hit = self._is_tp_hit(child, normalized_side, tp_price)
            if sl_hit and not tp_hit:
                return IntrabarResolution(
                    outcome="sl_hit",
                    reason="child_candle_hit_sl_first",
                    decided_at=child.timestamp,
                    child_timeframe_used=True,
                    examined_child_candles=len(ordered_children),
                    descended_parent_bars=1,
                    resolved_events=["sl_hit"],
                    final_event_order=["sl_hit"],
                    candidate_reasons=reasons,
                    metadata=metadata,
                )
            if tp_hit and not sl_hit:
                return IntrabarResolution(
                    outcome="tp_hit",
                    reason="child_candle_hit_tp_first",
                    decided_at=child.timestamp,
                    child_timeframe_used=True,
                    examined_child_candles=len(ordered_children),
                    descended_parent_bars=1,
                    resolved_events=["tp_hit"],
                    final_event_order=["tp_hit"],
                    candidate_reasons=reasons,
                    metadata=metadata,
                )
            if sl_hit and tp_hit:
                _logger.warning(
                    "INTRABAR_SAME_CHILD_AMBIGUOUS: SL and TP both hit in child candle %s "
                    "(side=%s sl=%.8g tp=%.8g) - conservative fallback to sl_hit",
                    child.timestamp.isoformat(),
                    side,
                    sl_price,
                    tp_price,
                )
                return IntrabarResolution(
                    outcome="sl_hit",
                    reason="ambiguous_same_child_candle_conservative_fallback",
                    decided_at=child.timestamp,
                    child_timeframe_used=True,
                    used_fallback=True,
                    warning_code="INTRABAR_SAME_CHILD_AMBIGUOUS",
                    examined_child_candles=len(ordered_children),
                    descended_parent_bars=1,
                    resolved_events=["sl_hit", "tp_hit"],
                    final_event_order=["sl_hit", "tp_hit"],
                    candidate_reasons=reasons,
                    metadata=metadata,
                )

        _logger.warning(
            "INTRABAR_CHILD_DATA_UNAVAILABLE: no child candle resolved SL/TP collision "
            "(examined=%d, parent=%s, side=%s) - conservative fallback to sl_hit",
            len(ordered_children),
            parent_candle.timestamp.isoformat(),
            side,
        )
        return IntrabarResolution(
            outcome="sl_hit",
            reason="fallback_child_unavailable_or_not_informative",
            decided_at=parent_candle.timestamp,
            child_timeframe_used=False,
            used_fallback=True,
            warning_code=self.FALLBACK_WARNING_CODE,
            examined_child_candles=len(ordered_children),
            descended_parent_bars=1 if reasons else 0,
            resolved_events=["sl_hit"],
            final_event_order=["sl_hit"],
            candidate_reasons=reasons,
            metadata=metadata,
        )

    @staticmethod
    def _is_sl_hit(candle: Candle, side: str, sl_price: float) -> bool:
        if side in {"BUY", "LONG"}:
            return candle.low <= sl_price
        return candle.high >= sl_price

    @staticmethod
    def _is_tp_hit(candle: Candle, side: str, tp_price: float) -> bool:
        if side in {"BUY", "LONG"}:
            return candle.high >= tp_price
        return candle.low <= tp_price

    @staticmethod
    def _touches_level(candle: Candle, price: float) -> bool:
        return candle.low <= price <= candle.high
