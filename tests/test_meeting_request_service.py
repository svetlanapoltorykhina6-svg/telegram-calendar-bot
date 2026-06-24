from datetime import UTC, datetime
from uuid import uuid4

import pytest

from bot_helper.core.config import Settings
from bot_helper.db.models import MeetingRequestStatus
from bot_helper.services.availability import AvailabilityConfig, AvailabilityService
from bot_helper.services.calendar import FakeCalendarBusyProvider, TimeInterval
from bot_helper.services.exceptions import SlotUnavailableError, ValidationError
from bot_helper.services.meeting_requests import (
    InMemoryPendingHoldProvider,
    MeetingRequestCreate,
    MeetingRequestService,
)


def make_request_service(
    *,
    busy: list[TimeInterval] | None = None,
) -> tuple[MeetingRequestService, InMemoryPendingHoldProvider]:
    settings = Settings(google_calendar_id="calendar@example.com")
    availability_service = AvailabilityService(
        AvailabilityConfig.from_settings(settings),
        FakeCalendarBusyProvider(busy),
    )
    hold_provider = InMemoryPendingHoldProvider()
    return MeetingRequestService(settings, availability_service, hold_provider), hold_provider


@pytest.mark.asyncio
async def test_builds_pending_request_and_holds_slot() -> None:
    service, hold_provider = make_request_service()
    user_id = uuid4()
    now = datetime(2026, 6, 22, 6, 0, tzinfo=UTC)  # 09:00 Moscow
    start_at = datetime(2026, 6, 22, 8, 0, tzinfo=UTC)  # 11:00 Moscow

    request = await service.build_pending_request(
        MeetingRequestCreate(
            user_id=user_id,
            title="Тестовая встреча",
            email="USER@Example.COM",
            start_at=start_at,
            description="  Обсудить задачу  ",
        ),
        now=now,
    )

    assert request.status == MeetingRequestStatus.PENDING
    assert request.user_id == user_id
    assert request.email == "user@example.com"
    assert request.title == "Тестовая встреча"
    assert request.description == "Обсудить задачу"
    assert request.duration_minutes == 30
    assert request.google_calendar_id == "calendar@example.com"
    assert request.pending_hold_key in hold_provider.held_slots
    assert hold_provider.held_slots[request.pending_hold_key][2] == 15 * 60
    held = await hold_provider.get_held_intervals(
        datetime(2026, 6, 22, 7, 0, tzinfo=UTC),
        datetime(2026, 6, 22, 9, 0, tzinfo=UTC),
    )
    assert len(held) == 1
    assert held[0].start_at == start_at


@pytest.mark.asyncio
async def test_rejects_unavailable_slot() -> None:
    busy = [
        TimeInterval(
            datetime(2026, 6, 22, 8, 0, tzinfo=UTC),
            datetime(2026, 6, 22, 8, 30, tzinfo=UTC),
        )
    ]
    service, _ = make_request_service(busy=busy)

    with pytest.raises(SlotUnavailableError):
        await service.build_pending_request(
            MeetingRequestCreate(
                user_id=uuid4(),
                title="Тестовая встреча",
                email="user@example.com",
                start_at=datetime(2026, 6, 22, 8, 0, tzinfo=UTC),
            ),
            now=datetime(2026, 6, 22, 6, 0, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    ("title", "email"),
    [
        ("  ", "user@example.com"),
        ("ok", "user@example.com"),
        ("Тестовая встреча", "wrong-email"),
    ],
)
@pytest.mark.asyncio
async def test_validates_request_input(title: str, email: str) -> None:
    service, _ = make_request_service()

    with pytest.raises(ValidationError):
        await service.build_pending_request(
            MeetingRequestCreate(
                user_id=uuid4(),
                title=title,
                email=email,
                start_at=datetime(2026, 6, 22, 8, 0, tzinfo=UTC),
            ),
            now=datetime(2026, 6, 22, 6, 0, tzinfo=UTC),
        )
