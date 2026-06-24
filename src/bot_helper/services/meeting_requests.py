from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import logging
import re
from typing import Protocol
from uuid import UUID

from redis.asyncio import Redis

from bot_helper.core.config import Settings
from bot_helper.db.models import MeetingRequest, MeetingRequestStatus
from bot_helper.services.availability import AvailabilityService, ensure_utc
from bot_helper.services.calendar import TimeInterval
from bot_helper.services.exceptions import SlotUnavailableError, ValidationError

logger = logging.getLogger("bot_helper.meeting_requests")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class MeetingRequestCreate:
    user_id: UUID
    title: str
    email: str
    start_at: datetime
    description: str | None = None
    timezone: str | None = None


class PendingHoldProvider(Protocol):
    async def hold_slot(self, start_at: datetime, end_at: datetime, ttl_seconds: int) -> str:
        """Temporarily reserve a slot and return the hold key."""

    async def get_held_intervals(
        self,
        range_start: datetime,
        range_end: datetime,
    ) -> list[TimeInterval]:
        """Return active temporary holds that overlap the requested range."""


class InMemoryPendingHoldProvider:
    def __init__(self) -> None:
        self.held_slots: dict[str, tuple[datetime, datetime, int]] = {}

    async def hold_slot(self, start_at: datetime, end_at: datetime, ttl_seconds: int) -> str:
        key = f"pending:{start_at.isoformat()}:{end_at.isoformat()}"
        self.held_slots[key] = (start_at, end_at, ttl_seconds)
        return key

    async def get_held_intervals(
        self,
        range_start: datetime,
        range_end: datetime,
    ) -> list[TimeInterval]:
        requested_range = TimeInterval(ensure_utc(range_start), ensure_utc(range_end))
        intervals = [
            TimeInterval(start_at, end_at)
            for start_at, end_at, _ttl in self.held_slots.values()
        ]
        return [interval for interval in intervals if interval.overlaps(requested_range)]


class RedisPendingHoldProvider:
    def __init__(self, redis: Redis, namespace: str = "pending_hold") -> None:
        self.redis = redis
        self.namespace = namespace

    async def hold_slot(self, start_at: datetime, end_at: datetime, ttl_seconds: int) -> str:
        start_at = ensure_utc(start_at)
        end_at = ensure_utc(end_at)
        key = self._key(start_at, end_at)
        value = json.dumps(
            {
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
            }
        )
        created = await self.redis.set(key, value, ex=ttl_seconds, nx=True)
        if not created:
            logger.warning(
                "slot already held in redis",
                extra={
                    "event": "slot_already_held",
                    "component": "meeting_requests",
                    "start_at": start_at.isoformat(),
                    "end_at": end_at.isoformat(),
                },
            )
            raise SlotUnavailableError("Selected slot is temporarily held")
        return key

    async def get_held_intervals(
        self,
        range_start: datetime,
        range_end: datetime,
    ) -> list[TimeInterval]:
        requested_range = TimeInterval(ensure_utc(range_start), ensure_utc(range_end))
        intervals: list[TimeInterval] = []
        async for key in self.redis.scan_iter(match=f"{self.namespace}:*"):
            raw_value = await self.redis.get(key)
            if not raw_value:
                continue
            try:
                payload = json.loads(raw_value)
                interval = TimeInterval(
                    datetime.fromisoformat(payload["start_at"]),
                    datetime.fromisoformat(payload["end_at"]),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                logger.warning(
                    "invalid pending hold payload",
                    extra={
                        "event": "invalid_pending_hold_payload",
                        "component": "meeting_requests",
                    },
                )
                continue
            if interval.overlaps(requested_range):
                intervals.append(interval)
        return intervals

    def _key(self, start_at: datetime, end_at: datetime) -> str:
        return f"{self.namespace}:{start_at.isoformat()}:{end_at.isoformat()}"


class MeetingRequestService:
    def __init__(
        self,
        settings: Settings,
        availability_service: AvailabilityService,
        hold_provider: PendingHoldProvider,
    ) -> None:
        self.settings = settings
        self.availability_service = availability_service
        self.hold_provider = hold_provider

    async def build_pending_request(
        self,
        data: MeetingRequestCreate,
        *,
        now: datetime | None = None,
    ) -> MeetingRequest:
        title = validate_title(data.title)
        email = validate_email(data.email)
        description = validate_description(data.description)
        start_at = ensure_utc(data.start_at)
        end_at = start_at + timedelta(minutes=self.settings.meeting_duration_minutes)

        is_available = await self.availability_service.is_slot_available(
            start_at,
            now=now,
        )
        if not is_available:
            logger.warning(
                "slot unavailable before request creation",
                extra={
                    "event": "slot_unavailable_before_request_creation",
                    "component": "meeting_requests",
                    "start_at": start_at.isoformat(),
                    "duration_minutes": self.settings.meeting_duration_minutes,
                },
            )
            raise SlotUnavailableError("Selected slot is not available")

        hold_key = await self.hold_provider.hold_slot(
            start_at,
            end_at,
            ttl_seconds=self.settings.pending_hold_minutes * 60,
        )
        request = MeetingRequest(
            user_id=data.user_id,
            status=MeetingRequestStatus.PENDING,
            title=title,
            description=description,
            email=email,
            start_at=start_at,
            end_at=end_at,
            timezone=data.timezone or self.settings.default_timezone,
            duration_minutes=self.settings.meeting_duration_minutes,
            google_calendar_id=self.settings.google_calendar_id,
            idempotency_key=f"{data.user_id}:{start_at.isoformat()}",
            pending_hold_key=hold_key,
        )

        logger.info(
            "pending meeting request built",
            extra={
                "event": "pending_meeting_request_built",
                "component": "meeting_requests",
                "user_id": str(data.user_id),
                "start_at": start_at.isoformat(),
                "duration_minutes": self.settings.meeting_duration_minutes,
            },
        )
        return request


def validate_title(value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 3 or len(normalized) > 120:
        raise ValidationError("Title must contain 3-120 characters")
    return normalized


def validate_email(value: str) -> str:
    normalized = value.strip().lower()
    if not EMAIL_RE.match(normalized):
        raise ValidationError("Email is invalid")
    return normalized


def validate_description(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 2000:
        raise ValidationError("Description is too long")
    return normalized
