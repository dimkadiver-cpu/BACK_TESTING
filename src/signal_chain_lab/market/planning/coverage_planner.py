"""Coverage planning with adaptive buffers and interval merge by symbol."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal

from src.signal_chain_lab.market.planning.demand_scanner import DemandChain

DurationClass = Literal["intraday", "swing", "position", "unknown"]


@dataclass(frozen=True, slots=True)
class BufferProfile:
    pre: timedelta
    post: timedelta
    estimated_duration: timedelta


@dataclass(frozen=True, slots=True)
class PlannerConfig:
    """Config for adaptive buffers and interval merge threshold."""

    merge_threshold: timedelta = timedelta(minutes=30)
    intraday: BufferProfile = BufferProfile(
        pre=timedelta(hours=24),
        post=timedelta(days=3),
        estimated_duration=timedelta(days=1),
    )
    swing: BufferProfile = BufferProfile(
        pre=timedelta(days=2),
        post=timedelta(days=14),
        estimated_duration=timedelta(days=7),
    )
    position: BufferProfile = BufferProfile(
        pre=timedelta(days=5),
        post=timedelta(days=45),
        estimated_duration=timedelta(days=21),
    )
    unknown: BufferProfile = BufferProfile(
        pre=timedelta(days=2),
        post=timedelta(days=14),
        estimated_duration=timedelta(days=14),
    )

    def profile_for(self, duration_class: DurationClass) -> BufferProfile:
        return getattr(self, duration_class)


@dataclass(frozen=True, slots=True)
class CoverageInterval:
    symbol: str
    start: datetime
    end: datetime

    def to_dict(self) -> dict[str, str]:
        return {
            "symbol": self.symbol,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class CoveragePlan:
    intervals_by_symbol: dict[str, list[CoverageInterval]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, list[dict[str, str]]]:
        """Return deterministic JSON-safe output ordered by symbol and start."""
        output: dict[str, list[dict[str, str]]] = {}
        for symbol in sorted(self.intervals_by_symbol.keys()):
            ordered = sorted(
                self.intervals_by_symbol[symbol],
                key=lambda interval: (interval.start, interval.end),
            )
            output[symbol] = [interval.to_dict() for interval in ordered]
        return output


class CoveragePlanner:
    """Build required market coverage windows with adaptive buffers and merge."""

    OPEN_STATUSES = {"NEW", "PENDING", "ACTIVE", "PARTIALLY_CLOSED", "OPEN"}

    def __init__(
        self,
        config: PlannerConfig | None = None,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config or PlannerConfig()
        self._now_provider = now_provider

    def classify_duration(self, chain: DemandChain) -> DurationClass:
        """Classify duration into intraday/swing/position/unknown."""
        if chain.timestamp_last_relevant_update is None:
            if chain.chain_status.upper() in self.OPEN_STATUSES:
                return "position"
            return "unknown"

        observed = chain.timestamp_last_relevant_update - chain.timestamp_open
        if observed <= timedelta(days=2):
            return "intraday"
        if observed <= timedelta(days=14):
            return "swing"
        return "position"

    def plan(self, chains: list[DemandChain]) -> CoveragePlan:
        intervals: list[CoverageInterval] = []
        now_utc = self._utc_now()
        for chain in chains:
            duration_class = self.classify_duration(chain)
            profile = self._config.profile_for(duration_class)

            start = chain.timestamp_open - profile.pre
            if chain.timestamp_last_relevant_update is not None:
                raw_end = chain.timestamp_last_relevant_update
            else:
                raw_end = chain.timestamp_open + profile.estimated_duration
            end = min(raw_end + profile.post, now_utc)
            if end <= start:
                end = start

            intervals.append(CoverageInterval(symbol=chain.symbol, start=start, end=end))

        merged_by_symbol: dict[str, list[CoverageInterval]] = {}
        for symbol in sorted({interval.symbol for interval in intervals}):
            symbol_intervals = [interval for interval in intervals if interval.symbol == symbol]
            merged_by_symbol[symbol] = self._merge_intervals(symbol_intervals)

        return CoveragePlan(intervals_by_symbol=merged_by_symbol)

    def _merge_intervals(self, intervals: list[CoverageInterval]) -> list[CoverageInterval]:
        if not intervals:
            return []

        ordered = sorted(intervals, key=lambda interval: (interval.start, interval.end))
        merged: list[CoverageInterval] = [ordered[0]]

        for current in ordered[1:]:
            previous = merged[-1]
            threshold_end = previous.end + self._config.merge_threshold
            if current.start <= threshold_end:
                merged[-1] = CoverageInterval(
                    symbol=previous.symbol,
                    start=previous.start,
                    end=max(previous.end, current.end),
                )
            else:
                merged.append(current)

        return merged

    def _utc_now(self) -> datetime:
        current = self._now_provider() if self._now_provider is not None else datetime.now(tz=timezone.utc)
        if current.tzinfo is None:
            return current.replace(tzinfo=timezone.utc)
        return current.astimezone(timezone.utc)
