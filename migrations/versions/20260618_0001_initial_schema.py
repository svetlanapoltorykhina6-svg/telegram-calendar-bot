"""initial schema

Revision ID: 20260618_0001
Revises:
Create Date: 2026-06-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260618_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

meeting_status_enum = postgresql.ENUM(
    "draft",
    "pending",
    "approved",
    "rejected",
    "cancelled_by_user",
    "cancelled_by_admin",
    "conflict",
    "failed",
    name="meetingrequeststatus",
)

user_role_enum = postgresql.ENUM(
    "client",
    "admin",
    "superadmin",
    name="userrole",
)


def upgrade() -> None:
    bind = op.get_bind()
    user_role_enum.create(bind, checkfirst=True)
    meeting_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(length=255), nullable=True),
        sa.Column("telegram_first_name", sa.String(length=255), nullable=True),
        sa.Column("telegram_last_name", sa.String(length=255), nullable=True),
        sa.Column("display_first_name", sa.String(length=80), nullable=True),
        sa.Column("display_last_name", sa.String(length=80), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column(
            "role",
            postgresql.ENUM(
                "client",
                "admin",
                "superadmin",
                name="userrole",
                create_type=False,
            ),
            nullable=False,
            server_default="client",
        ),
        sa.Column("is_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "meeting_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "draft",
                "pending",
                "approved",
                "rejected",
                "cancelled_by_user",
                "cancelled_by_admin",
                "conflict",
                "failed",
                name="meetingrequeststatus",
                create_type=False,
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("admin_comment", sa.Text(), nullable=True),
        sa.Column("google_calendar_id", sa.String(length=512), nullable=True),
        sa.Column("google_event_id", sa.String(length=512), nullable=True),
        sa.Column("google_event_link", sa.String(length=2048), nullable=True),
        sa.Column("google_meet_link", sa.String(length=2048), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("pending_hold_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_meeting_requests_start_at", "meeting_requests", ["start_at"])
    op.create_index("ix_meeting_requests_status", "meeting_requests", ["status"])
    op.create_index("ix_meeting_requests_user_id", "meeting_requests", ["user_id"])
    op.create_index(
        "uq_meeting_requests_google_event_id",
        "meeting_requests",
        ["google_event_id"],
        unique=True,
        postgresql_where=sa.text("google_event_id IS NOT NULL"),
    )

    op.create_table(
        "availability_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("weekday BETWEEN 1 AND 7", name="ck_availability_weekday"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_availability_rules_owner_weekday",
        "availability_rules",
        ["owner_user_id", "weekday"],
    )

    op.create_table(
        "blocked_intervals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("end_at > start_at", name="ck_blocked_intervals_time_order"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_blocked_intervals_time_range",
        "blocked_intervals",
        ["start_at", "end_at"],
    )

    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "google_calendar_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("calendar_id", sa.String(length=512), nullable=False),
        sa.Column("service_account_email", sa.String(length=320), nullable=True),
        sa.Column("credentials_source", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_google_calendar_connections_calendar_id",
        "google_calendar_connections",
        ["calendar_id"],
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index(
        "ix_google_calendar_connections_calendar_id",
        table_name="google_calendar_connections",
    )
    op.drop_table("google_calendar_connections")
    op.drop_table("settings")
    op.drop_index("ix_blocked_intervals_time_range", table_name="blocked_intervals")
    op.drop_table("blocked_intervals")
    op.drop_index(
        "ix_availability_rules_owner_weekday",
        table_name="availability_rules",
    )
    op.drop_table("availability_rules")
    op.drop_index(
        "uq_meeting_requests_google_event_id",
        table_name="meeting_requests",
        postgresql_where=sa.text("google_event_id IS NOT NULL"),
    )
    op.drop_index("ix_meeting_requests_user_id", table_name="meeting_requests")
    op.drop_index("ix_meeting_requests_status", table_name="meeting_requests")
    op.drop_index("ix_meeting_requests_start_at", table_name="meeting_requests")
    op.drop_table("meeting_requests")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    meeting_status_enum.drop(bind, checkfirst=True)
    user_role_enum.drop(bind, checkfirst=True)
