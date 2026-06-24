from __future__ import annotations

from typing import Any

from bot_helper.core.config import Settings


def build_default_settings(settings: Settings) -> dict[str, dict[str, Any]]:
    return {
        "allowed_durations": {"value": settings.allowed_meeting_durations},
        "slot_step_minutes": {"value": min(settings.allowed_meeting_durations)},
        "min_lead_time_minutes": {"value": settings.min_lead_time_minutes},
        "booking_horizon_days": {"value": settings.booking_horizon_days},
        "buffer_before_minutes": {"value": settings.slot_buffer_minutes},
        "buffer_after_minutes": {"value": settings.slot_buffer_minutes},
        "pending_hold_enabled": {"value": True},
        "pending_hold_minutes": {"value": settings.pending_hold_minutes},
        "pending_hold_storage": {"value": settings.pending_hold_storage},
        "default_timezone": {"value": settings.default_timezone},
        "workdays": {"value": settings.workdays},
        "work_start_time": {"value": settings.work_start_time},
        "work_end_time": {"value": settings.work_end_time},
        "google_primary_calendar_id": {"value": settings.google_calendar_id},
        "google_busy_calendar_ids": {
            "value": [settings.google_calendar_id] if settings.google_calendar_id else []
        },
        "google_meet_enabled": {"value": settings.enable_google_meet},
        "access_mode": {"value": "telegram_whitelist"},
    }
