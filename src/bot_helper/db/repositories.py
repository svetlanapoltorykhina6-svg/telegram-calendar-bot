from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot_helper.db.models import MeetingRequest, MeetingRequestStatus, Setting, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def add(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user


class MeetingRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, request_id: UUID) -> MeetingRequest | None:
        result = await self.session.execute(
            select(MeetingRequest).where(MeetingRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    async def add(self, meeting_request: MeetingRequest) -> MeetingRequest:
        self.session.add(meeting_request)
        await self.session.flush()
        return meeting_request

    async def list_pending_between(
        self,
        start_at: datetime,
        end_at: datetime,
    ) -> list[MeetingRequest]:
        result = await self.session.execute(
            select(MeetingRequest).where(
                MeetingRequest.status == MeetingRequestStatus.PENDING,
                MeetingRequest.start_at < end_at,
                MeetingRequest.end_at > start_at,
            )
        )
        return list(result.scalars())


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_many(self, keys: Iterable[str]) -> dict[str, Setting]:
        result = await self.session.execute(select(Setting).where(Setting.key.in_(keys)))
        return {setting.key: setting for setting in result.scalars()}

    async def upsert(self, setting: Setting) -> Setting:
        merged = await self.session.merge(setting)
        await self.session.flush()
        return merged
