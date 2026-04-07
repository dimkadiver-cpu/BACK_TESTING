"""src.parser.models — canonical Pydantic models for the parser output.

Public surface:

    # Price normalisation
    from src.signal_chain_lab.parser.models import Price, normalize_price

    # NEW_SIGNAL entities
    from src.signal_chain_lab.parser.models import (
        EntryLevel, StopLoss, TakeProfit,
        NewSignalEntities, compute_completeness,
    )

    # UPDATE entities
    from src.signal_chain_lab.parser.models import UpdateEntities

    # Intent, target reference, top-level result
    from src.signal_chain_lab.parser.models import Intent, TargetRef, TraderParseResult
"""

from __future__ import annotations

from src.signal_chain_lab.parser.models.canonical import (
    Intent,
    Price,
    TargetRef,
    TraderParseResult,
    normalize_price,
)
from src.signal_chain_lab.parser.models.new_signal import (
    EntryLevel,
    NewSignalEntities,
    StopLoss,
    TakeProfit,
    compute_completeness,
)
from src.signal_chain_lab.parser.models.update import UpdateEntities

__all__ = [
    # canonical
    "normalize_price",
    "Price",
    "Intent",
    "TargetRef",
    "TraderParseResult",
    # new_signal
    "EntryLevel",
    "StopLoss",
    "TakeProfit",
    "NewSignalEntities",
    "compute_completeness",
    # update
    "UpdateEntities",
]
