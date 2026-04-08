"""Gap detection utilities: required coverage - already covered coverage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Interval:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("Interval end must be >= start")

    def to_dict(self) -> dict[str, str]:
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}

    @staticmethod
    def from_dict(payload: dict[str, str]) -> "Interval":
        return Interval(
            start=datetime.fromisoformat(payload["start"].replace("Z", "+00:00")),
            end=datetime.fromisoformat(payload["end"].replace("Z", "+00:00")),
        )


def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    if not intervals:
        return []

    ordered = sorted(intervals, key=lambda item: (item.start, item.end))
    merged: list[Interval] = [ordered[0]]
    for current in ordered[1:]:
        previous = merged[-1]
        if current.start <= previous.end:
            merged[-1] = Interval(start=previous.start, end=max(previous.end, current.end))
        else:
            merged.append(current)
    return merged


def detect_gaps(required: list[Interval], covered: list[Interval]) -> list[Interval]:
    """Return missing intervals ordered by start timestamp."""
    required_merged = merge_intervals(required)
    covered_merged = merge_intervals(covered)
    gaps: list[Interval] = []

    for req in required_merged:
        cursor = req.start
        overlaps = [item for item in covered_merged if not (item.end <= req.start or item.start >= req.end)]

        for cov in overlaps:
            if cov.start > cursor:
                gaps.append(Interval(start=cursor, end=min(cov.start, req.end)))
            cursor = max(cursor, cov.end)
            if cursor >= req.end:
                break

        if cursor < req.end:
            gaps.append(Interval(start=cursor, end=req.end))

    return sorted(gaps, key=lambda item: (item.start, item.end))
