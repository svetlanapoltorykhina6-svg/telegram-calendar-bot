from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
import logging
from zoneinfo import ZoneInfo

from bot_helper.core.config import Settings
from bot_helper.services.calendar import CalendarBusyProvider, TimeInterval

logger = logging.getLogger("bot_helper.availability")


@dataclass(frozen=True)
class AvailabilityConfig:
    timezone: str
    workdays: tuple[int, ...]
    work_start_time: time
    work_end_time: time
    duration_minutes: int
    min_lead_time_minutes: int
    booking_horizon_days: int
    buffer_minutes: int

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        duration_minutes: int | None = None,
    ) -> AvailabilityConfig:
        return cls(
            timezone=settings.default_timezone,
            workdays=tuple(settings.workdays),
            work_start_time=parse_hhmm(settings.work_start_time),
            work_end_time=parse_hhmm(settings.work_end_time),
            duration_minutes=duration_minutes or settings.meeting_duration_minutes,
            min_lead_time_minutes=settings.min_lead_time_minutes,
            booking_horizon_days=settings.booking_horizon_days,
            buffer_minutes=settings.slot_buffer_minutes,
        )


@dataclass(frozen=True)
class AvailableSlot:
    start_at: datetime
    end_at: datetime
    local_date: date
    local_start_time: time
    local_end_time: time

    @property
    def interval(self) -> TimeInterval:
        return TimeInterval(self.start_at, self.end_at)


def parse_hhmm(value: str) -> time:
    hour, minute = value.split(":", maxsplit=1)
    return time(hour=int(hour), minute=int(minute))


class AvailabilityService:
    def __init__(
        self,
        config: AvailabilityConfig,
        busy_provider: CalendarBusyProvider,
    ) -> None:
        self.config = config
        self.busy_provider = busy_provider
        self.timezone = ZoneInfo(config.timezone)

    async def get_available_slots(
        self,
        *,
        now: datetime | None = None,
        blocked_intervals: Iterable[TimeInterval] | None = None,
        pending_intervals: Iterable[TimeInterval] | None = None,
    ) -> list[AvailableSlot]:
        now_utc = ensure_utc(now or datetime.now(UTC))
        earliest_start = now_utc + timedelta(minutes=self.config.min_lead_time_minutes)
        now_local = now_utc.astimezone(self.timezone)
        last_local_date = now_local.date() + timedelta(
            days=self.config.booking_horizon_days
        )
        range_end = datetime.combine(
            last_local_date,
            self.config.work_end_time,
            tzinfo=self.timezone,
        ).astimezone(UTC)

        logger.info(
            "availability calculation started",
            extra={
                "event": "availability_calculation_started",
                "component": "availability",
                "range_start": now_utc.isoformat(),
                "range_end": range_end.isoformat(),
                "duration_minutes": self.config.duration_minutes,
            },
        )

        if range_end <= now_utc:
            logger.info(
                "availability calculation completed",
                extra={
                    "event": "availability_calculation_completed",
                    "component": "availability",
                    "slots_count": 0,
                    "busy_intervals_count": 0,
                    "unavailable_intervals_count": 0,
                },
            )
            return []

        busy_intervals = await self.busy_provider.get_busy_intervals(now_utc, range_end)
        unavailable_intervals = [
            interval.with_buffer(
                self.config.buffer_minutes,
                self.config.buffer_minutes,
            )
            for interval in busy_intervals
        ]
        unavailable_intervals.extend(blocked_intervals or [])
        unavailable_intervals.extend(pending_intervals or [])

        slots: list[AvailableSlot] = []
        for day_offset in range(self.config.booking_horizon_days + 1):
            current_local_date = (now_local + timedelta(days=day_offset)).date()
            if current_local_date.isoweekday() not in self.config.workdays:
                continue
            slots.extend(
                self._build_day_slots(
                    local_date=current_local_date,
                    earliest_start=earliest_start,
                    range_end=range_end,
                    unavailable_intervals=unavailable_intervals,
                )
            )

        logger.info(
            "availability calculation completed",
            extra={
                "event": "availability_calculation_completed",
                "component": "availability",
                "slots_count": len(slots),
                "busy_intervals_count": len(busy_intervals),
                "unavailable_intervals_count": len(unavailable_intervals),
            },
        )
        return slots

    async def is_slot_available(
        self,
        start_at: datetime,
        *,
        blocked_intervals: Iterable[TimeInterval] | None = None,
        pending_intervals: Iterable[TimeInterval] | None = None,
        now: datetime | None = None,
    ) -> bool:
        start_at_utc = ensure_utc(start_at)
        end_at_utc = start_at_utc + timedelta(minutes=self.config.duration_minutes)
        target = TimeInterval(start_at_utc, end_at_utc)
        available_slots = await self.get_available_slots(
            now=now,
            blocked_intervals=blocked_intervals,
            pending_intervals=pending_intervals,
        )
        return any(slot.interval == target for slot in available_slots)

    def _build_day_slots(
        self,
        *,
        local_date: date,
        earliest_start: datetime,
        range_end: datetime,
        unavailable_intervals: list[TimeInterval],
    ) -> list[AvailableSlot]:
        work_start_local = datetime.combine(
            local_date,
            self.config.work_start_time,
            tzinfo=self.timezone,
        )
        work_end_local = datetime.combine(
            local_date,
            self.config.work_end_time,
            tzinfo=self.timezone,
        )

        cursor = work_start_local.astimezone(UTC)
        work_end_utc = work_end_local.astimezone(UTC)
        duration = timedelta(minutes=self.config.duration_minutes)
        step = duration

        slots: list[AvailableSlot] = []
        while cursor + duration <= work_end_utc:
            slot_start = cursor
            slot_end = cursor + duration
            slot_interval = TimeInterval(slot_start, slot_end)

            if (
                slot_start >= earliest_start
                and slot_end <= range_end
                and not any(slot_interval.overlaps(interval) for interval in unavailable_intervals)
            ):
                slot_start_local = slot_start.astimezone(self.timezone)
                slot_end_local = slot_end.astimezone(self.timezone)
                slots.append(
                    AvailableSlot(
                        start_at=slot_start,
                        end_at=slot_end,
                        local_date=slot_start_local.date(),
                        local_start_time=slot_start_local.time().replace(tzinfo=None),
                        local_end_time=slot_end_local.time().replace(tzinfo=None),
                    )
                )

            cursor += step

        return slots


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)
