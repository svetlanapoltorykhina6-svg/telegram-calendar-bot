from bot_helper.core.config import Settings
from bot_helper.db.defaults import build_default_settings


def test_default_mvp_settings_match_final_inputs() -> None:
    defaults = build_default_settings(
        Settings(
            meeting_duration_minutes=30,
            allowed_meeting_durations=[15, 30, 45, 60, 90],
            min_lead_time_minutes=120,
            booking_horizon_days=14,
            pending_hold_minutes=15,
            google_calendar_id="calendar@example.com",
            enable_google_meet=True,
        )
    )

    assert defaults["allowed_durations"]["value"] == [15, 30, 45, 60, 90]
    assert defaults["slot_step_minutes"]["value"] == 15
    assert defaults["min_lead_time_minutes"]["value"] == 120
    assert defaults["booking_horizon_days"]["value"] == 14
    assert defaults["pending_hold_minutes"]["value"] == 15
    assert defaults["pending_hold_storage"]["value"] == "redis"
    assert defaults["google_primary_calendar_id"]["value"] == "calendar@example.com"
    assert defaults["google_meet_enabled"]["value"] is True
    assert defaults["access_mode"]["value"] == "telegram_whitelist"
