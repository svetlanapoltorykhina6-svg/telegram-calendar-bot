from datetime import UTC, datetime, time

import pytest

from bot_helper.core.config import Settings
from bot_helper.services.availability import AvailabilityConfig, AvailabilityService
from bot_helper.services.calendar import FakeCalendarBusyProvider, TimeInterval


def make_service(
    *,
    busy: list[TimeInterval] | None = None,
    min_lead_time_minutes: int = 0,
    booking_horizon_days: int = 0,
) -> AvailabilityService:
    settings = Settings(
        min_lead_time_minutes=min_lead_time_minutes,
        booking_horizon_days=booking_horizon_days,
    )
    return AvailabilityService(
        AvailabilityConfig.from_settings(settings),
        FakeCalendarBusyProvider(busy),
    )


@pytest.mark.asyncio
async def test_builds_30_minute_slots_inside_working_hours() -> None:
    service = make_service()
    now = datetime(2026, 6, 22, 6, 0, tzinfo=UTC)  # Monday, 09:00 Moscow

    slots = await service.get_available_slots(now=now)

    assert len(slots) == 18
    assert slots[0].local_start_time == time(10, 0)
    assert slots[0].local_end_time == time(10, 30)
    assert slots[-1].local_start_time == time(18, 30)
    assert slots[-1].local_end_time == time(19, 0)


@pytest.mark.asyncio
async def test_min_lead_time_filters_early_slots() -> None:
    service = make_service(min_lead_time_minutes=120)
    now = datetime(2026, 6, 22, 8, 15, tzinfo=UTC)  # Monday, 11:15 Moscow

    slots = await service.get_available_slots(now=now)

    assert slots[0].local_start_time == time(13, 30)
    assert all(slot.start_at >= datetime(2026, 6, 22, 10, 15, tzinfo=UTC) for slot in slots)


@pytest.mark.asyncio
async def test_busy_intervals_are_removed() -> None:
    busy = [
        TimeInterval(
            datetime(2026, 6, 22, 7, 30, tzinfo=UTC),  # 10:30 Moscow
            datetime(2026, 6, 22, 8, 30, tzinfo=UTC),  # 11:30 Moscow
        )
    ]
    service = make_service(busy=busy)
    now = datetime(2026, 6, 22, 6, 0, tzinfo=UTC)

    slots = await service.get_available_slots(now=now)
    starts = {slot.local_start_time for slot in slots}

    assert time(10, 0) in starts
    assert time(10, 30) not in starts
    assert time(11, 0) not in starts
    assert time(11, 30) in starts


@pytest.mark.asyncio
async def test_blocked_and_pending_intervals_are_removed() -> None:
    service = make_service()
    now = datetime(2026, 6, 22, 6, 0, tzinfo=UTC)
    blocked = [
        TimeInterval(
            datetime(2026, 6, 22, 9, 0, tzinfo=UTC),  # 12:00 Moscow
            datetime(2026, 6, 22, 9, 30, tzinfo=UTC),
        )
    ]
    pending = [
        TimeInterval(
            datetime(2026, 6, 22, 10, 0, tzinfo=UTC),  # 13:00 Moscow
            datetime(2026, 6, 22, 10, 30, tzinfo=UTC),
        )
    ]

    slots = await service.get_available_slots(
        now=now,
        blocked_intervals=blocked,
        pending_intervals=pending,
    )
    starts = {slot.local_start_time for slot in slots}

    assert time(12, 0) not in starts
    assert time(13, 0) not in starts
    assert time(12, 30) in starts


@pytest.mark.asyncio
async def test_weekends_are_not_available() -> None:
    service = make_service()
    now = datetime(2026, 6, 20, 6, 0, tzinfo=UTC)  # Saturday

    slots = await service.get_available_slots(now=now)

    assert slots == []
