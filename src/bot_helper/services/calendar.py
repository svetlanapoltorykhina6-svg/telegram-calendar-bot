from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class TimeInterval:
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("TimeInterval boundaries must be timezone-aware")
        if self.end_at <= self.start_at:
            raise ValueError("TimeInterval end_at must be after start_at")

    def overlaps(self, other: TimeInterval) -> bool:
        return self.start_at < other.end_at and other.start_at < self.end_at

    def with_buffer(self, minutes_before: int, minutes_after: int) -> TimeInterval:
        from datetime import timedelta

        return TimeInterval(
            start_at=self.start_at - timedelta(minutes=minutes_before),
            end_at=self.end_at + timedelta(minutes=minutes_after),
        )


class CalendarBusyProvider(Protocol):
    async def get_busy_intervals(
        self,
        range_start: datetime,
        range_end: datetime,
    ) -> list[TimeInterval]:
        """Return busy intervals in UTC for the requested range."""


class FakeCalendarBusyProvider:
    def __init__(self, busy_intervals: Iterable[TimeInterval] | None = None) -> None:
        self._busy_intervals = list(busy_intervals or [])

    async def get_busy_intervals(
        self,
        range_start: datetime,
        range_end: datetime,
    ) -> list[TimeInterval]:
        requested_range = TimeInterval(range_start, range_end)
        return [
            interval
            for interval in self._busy_intervals
            if interval.overlaps(requested_range)
        ]
