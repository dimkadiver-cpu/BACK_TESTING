"""Validators for CanonicalChain and chain readiness for simulation."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.signal_chain_lab.domain.events import CanonicalChain


class GapSeverity(str, Enum):
    FATAL = "fatal"
    WARNING = "warning"
    OPTIONAL = "optional"


@dataclass
class ValidationGap:
    field: str
    severity: GapSeverity
    message: str


@dataclass
class ChainValidationResult:
    is_valid_identity: bool
    is_simulable: bool
    gaps: list[ValidationGap] = field(default_factory=list)

    @property
    def fatal_gaps(self) -> list[ValidationGap]:
        return [g for g in self.gaps if g.severity == GapSeverity.FATAL]

    @property
    def warning_gaps(self) -> list[ValidationGap]:
        return [g for g in self.gaps if g.severity == GapSeverity.WARNING]

    @property
    def optional_gaps(self) -> list[ValidationGap]:
        return [g for g in self.gaps if g.severity == GapSeverity.OPTIONAL]


def validate_chain_identity(chain: CanonicalChain) -> list[ValidationGap]:
    """Validate that the chain has the minimum fields required for identification.

    These are non-negotiable: signal_id, symbol, side.
    """
    gaps: list[ValidationGap] = []
    if not chain.signal_id:
        gaps.append(ValidationGap("signal_id", GapSeverity.FATAL, "signal_id is required"))
    if not chain.symbol:
        gaps.append(ValidationGap("symbol", GapSeverity.FATAL, "symbol is required"))
    if not chain.side:
        gaps.append(ValidationGap("side", GapSeverity.FATAL, "side is required"))
    return gaps


def validate_chain_for_simulation(chain: CanonicalChain) -> ChainValidationResult:
    """Validate chain readiness for standard V1 simulation.

    Checks:
    - Identity fields (fatal if missing)
    - OPEN_SIGNAL event with entry, stop_loss, and take_profit in payload (fatal)

    Returns a ChainValidationResult with all gaps classified.
    """
    from src.signal_chain_lab.domain.enums import EventType

    gaps: list[ValidationGap] = []

    # Identity checks (fatal)
    gaps.extend(validate_chain_identity(chain))

    # Must have at least one event
    if not chain.events:
        gaps.append(ValidationGap(
            "events",
            GapSeverity.FATAL,
            "chain has no events — cannot simulate",
        ))
        return ChainValidationResult(
            is_valid_identity=len(gaps) == 0 or all(g.severity != GapSeverity.FATAL for g in gaps[:3]),
            is_simulable=False,
            gaps=gaps,
        )

    # Find the OPEN_SIGNAL event
    open_event = next(
        (e for e in chain.events if e.event_type == EventType.OPEN_SIGNAL),
        None,
    )
    if open_event is None:
        gaps.append(ValidationGap(
            "OPEN_SIGNAL",
            GapSeverity.FATAL,
            "no OPEN_SIGNAL event found in chain",
        ))
    else:
        payload = open_event.payload

        # Entry check
        entries = payload.get("entries") or payload.get("entry_prices") or []
        if not entries:
            gaps.append(ValidationGap(
                "entry",
                GapSeverity.FATAL,
                "OPEN_SIGNAL has no entry prices",
            ))

        # Stop loss check
        sl = payload.get("stop_loss") or payload.get("sl_price")
        if sl is None:
            gaps.append(ValidationGap(
                "stop_loss",
                GapSeverity.FATAL,
                "OPEN_SIGNAL has no stop_loss",
            ))

        # Take profit check
        tps = payload.get("take_profits") or payload.get("tp_levels") or []
        if not tps:
            gaps.append(ValidationGap(
                "take_profit",
                GapSeverity.FATAL,
                "OPEN_SIGNAL has no take_profit levels",
            ))

    identity_gaps = validate_chain_identity(chain)
    is_valid_identity = len(identity_gaps) == 0
    is_simulable = all(g.severity != GapSeverity.FATAL for g in gaps)

    return ChainValidationResult(
        is_valid_identity=is_valid_identity,
        is_simulable=is_simulable,
        gaps=gaps,
    )
