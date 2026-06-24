from __future__ import annotations

from datetime import datetime, time
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index
from sqlalchemy import Integer, String, Text, Time, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot_helper.db.base import Base


class UserRole(StrEnum):
    CLIENT = "client"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


class MeetingRequestStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED_BY_USER = "cancelled_by_user"
    CANCELLED_BY_ADMIN = "cancelled_by_admin"
    CONFLICT = "conflict"
    FAILED = "failed"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    telegram_username: Mapped[str | None] = mapped_column(String(255))
    telegram_first_name: Mapped[str | None] = mapped_column(String(255))
    telegram_last_name: Mapped[str | None] = mapped_column(String(255))
    display_first_name: Mapped[str | None] = mapped_column(String(80))
    display_last_name: Mapped[str | None] = mapped_column(String(80))
    email: Mapped[str | None] = mapped_column(String(320))
    role: Mapped[UserRole] = mapped_column(default=UserRole.CLIENT, nullable=False)
    is_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    meeting_requests: Mapped[list[MeetingRequest]] = relationship(
        back_populates="user",
        cascade="save-update, merge",
    )

    __table_args__ = (Index("ix_users_role", "role"),)


class MeetingRequest(TimestampMixin, Base):
    __tablename__ = "meeting_requests"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[MeetingRequestStatus] = mapped_column(
        default=MeetingRequestStatus.DRAFT,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    admin_comment: Mapped[str | None] = mapped_column(Text)
    google_calendar_id: Mapped[str | None] = mapped_column(String(512))
    google_event_id: Mapped[str | None] = mapped_column(String(512))
    google_event_link: Mapped[str | None] = mapped_column(String(2048))
    google_meet_link: Mapped[str | None] = mapped_column(String(2048))
    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
    )
    pending_hold_key: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="meeting_requests")

    __table_args__ = (
        Index("ix_meeting_requests_start_at", "start_at"),
        Index("ix_meeting_requests_status", "status"),
        Index("ix_meeting_requests_user_id", "user_id"),
        Index(
            "uq_meeting_requests_google_event_id",
            "google_event_id",
            unique=True,
            postgresql_where=google_event_id.is_not(None),
        ),
        UniqueConstraint("idempotency_key"),
    )


class AvailabilityRule(TimestampMixin, Base):
    __tablename__ = "availability_rules"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint("weekday BETWEEN 1 AND 7", name="ck_availability_weekday"),
        Index("ix_availability_rules_owner_weekday", "owner_user_id", "weekday"),
    )


class BlockedInterval(TimestampMixin, Base):
    __tablename__ = "blocked_intervals"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        CheckConstraint("end_at > start_at", name="ck_blocked_intervals_time_order"),
        Index("ix_blocked_intervals_time_range", "start_at", "end_at"),
    )


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class GoogleCalendarConnection(TimestampMixin, Base):
    __tablename__ = "google_calendar_connections"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    calendar_id: Mapped[str] = mapped_column(String(512), nullable=False)
    service_account_email: Mapped[str | None] = mapped_column(String(320))
    credentials_source: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_google_calendar_connections_calendar_id", "calendar_id"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(128))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_audit_log_created_at", "created_at"),
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
    )
