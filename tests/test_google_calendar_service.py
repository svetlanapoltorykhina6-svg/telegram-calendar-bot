from datetime import UTC, datetime
from pathlib import Path

import pytest

from bot_helper.core.config import Settings
from bot_helper.services.google_calendar import (
    GoogleCalendarClient,
    GoogleCalendarConfigurationError,
    GoogleCalendarEventCreate,
    build_event_body,
    extract_meet_link,
)


def test_build_event_body_includes_attendee_and_meet_request() -> None:
    body = build_event_body(
        GoogleCalendarEventCreate(
            request_id="abc123",
            title="Консультация",
            description="Обсудить проект",
            start_at=datetime(2026, 6, 22, 7, 30, tzinfo=UTC),
            end_at=datetime(2026, 6, 22, 8, 0, tzinfo=UTC),
            attendee_email="client@example.com",
            timezone="Europe/Moscow",
        )
    )

    assert body["summary"] == "Консультация"
    assert body["attendees"] == [{"email": "client@example.com"}]
    assert body["conferenceData"]["createRequest"]["requestId"] == "meet-abc123"
    assert body["extendedProperties"]["private"]["request_id"] == "abc123"


def test_build_event_body_can_omit_attendee_and_meet_for_service_account() -> None:
    body = build_event_body(
        GoogleCalendarEventCreate(
            request_id="abc123",
            title="Консультация",
            description="Обсудить проект",
            start_at=datetime(2026, 6, 22, 7, 30, tzinfo=UTC),
            end_at=datetime(2026, 6, 22, 8, 0, tzinfo=UTC),
            attendee_email="",
            timezone="Europe/Moscow",
            enable_google_meet=False,
        )
    )

    assert body["summary"] == "Консультация"
    assert "attendees" not in body
    assert "conferenceData" not in body
    assert body["extendedProperties"]["private"]["request_id"] == "abc123"


def test_extract_meet_link_prefers_hangout_link() -> None:
    link = extract_meet_link(
        {
            "hangoutLink": "https://meet.google.com/aaa-bbbb-ccc",
            "conferenceData": {
                "entryPoints": [
                    {
                        "entryPointType": "video",
                        "uri": "https://meet.google.com/ddd-eeee-fff",
                    }
                ]
            },
        }
    )

    assert link == "https://meet.google.com/aaa-bbbb-ccc"


def test_oauth_refresh_write_failure_reports_configuration_error(
    monkeypatch,
    tmp_path,
) -> None:
    token_file = tmp_path / "google-oauth-token.json"
    token_file.write_text("{}", encoding="utf-8")

    class FakeCredentials:
        valid = False
        expired = True
        refresh_token = "refresh-token"

        def refresh(self, request) -> None:
            return None

        def to_json(self) -> str:
            return "{}"

    monkeypatch.setattr(
        "bot_helper.services.google_calendar.Credentials.from_authorized_user_file",
        lambda *args, **kwargs: FakeCredentials(),
    )
    monkeypatch.setattr(
        Path,
        "write_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("read-only")),
    )

    client = GoogleCalendarClient(
        Settings(
            use_google_calendar_service_account=False,
            google_oauth_token_file=str(token_file),
            google_oauth_client_file="client.json",
        )
    )

    with pytest.raises(GoogleCalendarConfigurationError, match="не удалось сохранить"):
        client._load_oauth_credentials()
