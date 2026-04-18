"""Coverage planning with adaptive buffers and chart-aware windows by symbol."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal

from src.signal_chain_lab.market.planning.demand_scanner import DemandChain

DurationClass = Literal["intraday", "swing", "position", "unknown"]


@dataclass(frozen=True, slots=True)
class ManualBuffer:
    pre_days: int
    post_days: int
    preset: str = "custom"


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
class SymbolCoverageWindows:
    execution_window: list[CoverageInterval] = field(default_factory=list)
    chart_window: list[CoverageInterval] = field(default_factory=list)
    download_window: list[CoverageInterval] = field(default_factory=list)
    download_windows_by_timeframe: dict[str, list[CoverageInterval]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, list[dict[str, str]]]:
        return {
            "execution_window": [interval.to_dict() for interval in self.execution_window],
            "chart_window": [interval.to_dict() for interval in self.chart_window],
            "download_window": [interval.to_dict() for interval in self.download_window],
            "download_windows_by_timeframe": {
                timeframe: [interval.to_dict() for interval in intervals]
                for timeframe, intervals in sorted(self.download_windows_by_timeframe.items())
            },
            "requested_timeframes": sorted(self.download_windows_by_timeframe.keys()),
            # Backward-compatible alias for downstream scripts.
            "required_intervals": [interval.to_dict() for interval in self.download_window],
        }


@dataclass(frozen=True, slots=True)
class CoveragePlan:
    windows_by_symbol: dict[str, SymbolCoverageWindows] = field(default_factory=dict)

    @property
    def intervals_by_symbol(self) -> dict[str, list[CoverageInterval]]:
        """Backward-compatible view exposing download windows only."""
        return {
            symbol: windows.download_window
            for symbol, windows in self.windows_by_symbol.items()
        }

    def to_dict(self) -> dict[str, dict[str, list[dict[str, str]]]]:
        """Return deterministic JSON-safe output ordered by symbol and start."""
        output: dict[str, dict[str, list[dict[str, str]]]] = {}
        for symbol in sorted(self.windows_by_symbol.keys()):
            windows = self.windows_by_symbol[symbol]
            output[symbol] = SymbolCoverageWindows(
                execution_window=sorted(windows.execution_window, key=lambda interval: (interval.start, interval.end)),
                chart_window=sorted(windows.chart_window, key=lambda interval: (interval.start, interval.end)),
                download_window=sorted(windows.download_window, key=lambda interval: (interval.start, interval.end)),
                download_windows_by_timeframe={
                    timeframe: sorted(intervals, key=lambda interval: (interval.start, interval.end))
                    for timeframe, intervals in windows.download_windows_by_timeframe.items()
                },
            ).to_dict()
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

    def plan(
        self,
        chains: list[DemandChain],
        *,
        manual_buffer: ManualBuffer | None = None,
        timeframes: list[str] | None = None,
    ) -> CoveragePlan:
        execution_intervals: list[CoverageInterval] = []
        chart_intervals: list[CoverageInterval] = []
        requested_timeframes = self._normalize_timeframes(timeframes)
        now_utc = self._utc_now()
        for chain in chains:
            execution_end = (
                chain.timestamp_last_relevant_update
                if chain.timestamp_last_relevant_update is not None
                else chain.timestamp_open
            )
            if execution_end < chain.timestamp_open:
                execution_end = chain.timestamp_open
            execution_interval = CoverageInterval(
                symbol=chain.symbol,
                start=chain.timestamp_open,
                end=min(execution_end, now_utc),
            )

            if manual_buffer is not None:
                pre = timedelta(days=manual_buffer.pre_days)
                post = timedelta(days=manual_buffer.post_days)
                chart_start = execution_interval.start - pre
                chart_end = min(execution_interval.end + post, now_utc)
            else:
                duration_class = self.classify_duration(chain)
                profile = self._config.profile_for(duration_class)
                chart_start = execution_interval.start - profile.pre
                chart_end = min(execution_interval.end + profile.post, now_utc)
                if chain.timestamp_last_relevant_update is None:
                    chart_end = min(chain.timestamp_open + profile.estimated_duration + profile.post, now_utc)

            if chart_end <= chart_start:
                chart_end = chart_start

            execution_intervals.append(execution_interval)
            chart_intervals.append(
                CoverageInterval(
                    symbol=chain.symbol,
                    start=chart_start,
                    end=chart_end,
                )
            )

        windows_by_symbol: dict[str, SymbolCoverageWindows] = {}
        symbols = sorted({interval.symbol for interval in execution_intervals + chart_intervals})
        for symbol in symbols:
            symbol_execution = [interval for interval in execution_intervals if interval.symbol == symbol]
            symbol_chart = [interval for interval in chart_intervals if interval.symbol == symbol]
            merged_execution = self._merge_intervals(symbol_execution)
            merged_chart = self._merge_intervals(symbol_chart)
            merged_download = self._merge_intervals(symbol_execution + symbol_chart)
            download_windows_by_timeframe = {
                timeframe: list(merged_download)
                for timeframe in requested_timeframes
            }
            windows_by_symbol[symbol] = SymbolCoverageWindows(
                execution_window=merged_execution,
                chart_window=merged_chart,
                download_window=merged_download,
                download_windows_by_timeframe=download_windows_by_timeframe,
            )

        return CoveragePlan(windows_by_symbol=windows_by_symbol)

    @staticmethod
    def _normalize_timeframes(timeframes: list[str] | None) -> list[str]:
        if not timeframes:
            return []
        normalized: list[str] = []
        seen: set[str] = set()
        for timeframe in timeframes:
            value = str(timeframe or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

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
