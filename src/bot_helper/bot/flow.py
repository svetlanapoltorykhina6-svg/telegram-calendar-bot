from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5
from uuid import uuid4

from bot_helper.core.config import Settings
from bot_helper.services.availability import AvailabilityConfig, AvailabilityService
from bot_helper.services.calendar import FakeCalendarBusyProvider, TimeInterval
from bot_helper.services.meeting_requests import InMemoryPendingHoldProvider


class LocalFlowContext:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.hold_provider = InMemoryPendingHoldProvider()
        self.busy_provider = FakeCalendarBusyProvider()
        self.availability_service = AvailabilityService(
            AvailabilityConfig.from_settings(settings),
            self.busy_provider,
        )
        self.sent_requests: dict[str, dict[str, Any]] = {}

    def get_availability_service(self, duration_minutes: int) -> AvailabilityService:
        return AvailabilityService(
            AvailabilityConfig.from_settings(
                self.settings,
                duration_minutes=duration_minutes,
            ),
            self.busy_provider,
        )

    async def get_slots(self, duration_minutes: int | None = None) -> list:
        now = datetime.now(UTC)
        pending = await self.hold_provider.get_held_intervals(
            now,
            now.replace(year=now.year + 1),
        )
        availability_service = (
            self.get_availability_service(duration_minutes)
            if duration_minutes
            else self.availability_service
        )
        return await availability_service.get_available_slots(
            now=now,
            pending_intervals=pending,
        )

    async def get_slots_by_date(
        self,
        local_date: date,
        duration_minutes: int | None = None,
    ) -> list:
        slots = await self.get_slots(duration_minutes)
        return [slot for slot in slots if slot.local_date == local_date]

    async def get_slot_by_timestamp(
        self,
        timestamp: int,
        duration_minutes: int | None = None,
    ):
        start_at = datetime.fromtimestamp(timestamp, tz=UTC)
        slots = await self.get_slots(duration_minutes)
        for slot in slots:
            if int(slot.start_at.timestamp()) == int(start_at.timestamp()):
                return slot
        return None

    async def hold_slot(self, interval: TimeInterval) -> str:
        return await self.hold_provider.hold_slot(
            interval.start_at,
            interval.end_at,
            ttl_seconds=self.settings.pending_hold_minutes * 60,
        )

    def add_request(self, request_data: dict[str, Any]) -> dict[str, Any]:
        request_id = uuid4().hex[:12]
        stored_request = {**request_data, "request_id": request_id}
        self.sent_requests[request_id] = stored_request
        return stored_request

    def get_request(self, request_id: str) -> dict[str, Any] | None:
        return self.sent_requests.get(request_id)

    def update_request(self, request_id: str, **values: Any) -> dict[str, Any] | None:
        request = self.sent_requests.get(request_id)
        if request is None:
            return None
        request.update(values)
        return request


def user_uuid_from_telegram_id(telegram_id: int):
    return uuid5(NAMESPACE_URL, f"telegram-user:{telegram_id}")


def group_slots_by_date(slots: list) -> dict[date, list]:
    grouped = defaultdict(list)
    for slot in slots:
        grouped[slot.local_date].append(slot)
    return dict(grouped)
