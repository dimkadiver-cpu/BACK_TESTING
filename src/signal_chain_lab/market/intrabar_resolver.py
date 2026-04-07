"""Resolve ambiguous same-candle SL/TP collisions using child timeframe candles."""
from __future__ import annotations

import logging
from datetime import datetime

from pydantic import BaseModel, Field

from src.signal_chain_lab.market.data_models import Candle

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
    metadata: dict[str, str] = Field(default_factory=dict)


class IntrabarResolver:
    """Resolve SL/TP order in same parent candle."""

    FALLBACK_WARNING_CODE = "INTRABAR_CHILD_DATA_UNAVAILABLE"

    def resolve_sl_tp_collision(
        self,
        *,
        parent_candle: Candle,
        child_candles: list[Candle],
        side: str,
        sl_price: float,
        tp_price: float,
    ) -> IntrabarResolution:
        ordered_children = sorted(child_candles, key=lambda item: item.timestamp)
        normalized_side = side.upper()

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
                )
            if tp_hit and not sl_hit:
                return IntrabarResolution(
                    outcome="tp_hit",
                    reason="child_candle_hit_tp_first",
                    decided_at=child.timestamp,
                    child_timeframe_used=True,
                    examined_child_candles=len(ordered_children),
                )
            if sl_hit and tp_hit:
                _logger.warning(
                    "INTRABAR_SAME_CHILD_AMBIGUOUS: SL and TP both hit in child candle %s "
                    "(side=%s sl=%.8g tp=%.8g) — conservative fallback to sl_hit",
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
                )

        _logger.warning(
            "INTRABAR_CHILD_DATA_UNAVAILABLE: no child candle resolved SL/TP collision "
            "(examined=%d, parent=%s, side=%s) — conservative fallback to sl_hit",
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
