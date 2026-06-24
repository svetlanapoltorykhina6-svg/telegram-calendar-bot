from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, replace
from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from bot_helper.core.config import Settings

logger = logging.getLogger("bot_helper.google_calendar")

CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"


class GoogleCalendarError(Exception):
    """Base Google Calendar integration error."""


class GoogleCalendarConfigurationError(GoogleCalendarError):
    """Google Calendar integration is not configured."""


@dataclass(frozen=True)
class GoogleCalendarEventCreate:
    request_id: str
    title: str
    description: str | None
    start_at: datetime
    end_at: datetime
    attendee_email: str
    timezone: str
    enable_google_meet: bool = True


@dataclass(frozen=True)
class GoogleCalendarEventResult:
    event_id: str
    html_link: str | None
    meet_link: str | None
    attendee_invited: bool = True
    google_meet_requested: bool = True


def build_event_body(data: GoogleCalendarEventCreate) -> dict[str, Any]:
    body: dict[str, Any] = {
        "summary": data.title,
        "description": data.description or "",
        "start": {
            "dateTime": data.start_at.isoformat(),
            "timeZone": data.timezone,
        },
        "end": {
            "dateTime": data.end_at.isoformat(),
            "timeZone": data.timezone,
        },
        "extendedProperties": {
            "private": {
                "request_id": data.request_id,
                "source": "telegram-calendar-bot",
            }
        },
    }
    if data.attendee_email:
        body["attendees"] = [{"email": data.attendee_email}]
    if data.enable_google_meet:
        body["conferenceData"] = {
            "createRequest": {
                "requestId": f"meet-{data.request_id}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }
    return body


def extract_meet_link(event: dict[str, Any]) -> str | None:
    if event.get("hangoutLink"):
        return str(event["hangoutLink"])

    conference_data = event.get("conferenceData") or {}
    for entry_point in conference_data.get("entryPoints") or []:
        if entry_point.get("entryPointType") == "video" and entry_point.get("uri"):
            return str(entry_point["uri"])
    return None


class GoogleCalendarClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def create_event(
        self,
        data: GoogleCalendarEventCreate,
    ) -> GoogleCalendarEventResult:
        return await asyncio.to_thread(self._create_event_sync, data)

    def _create_event_sync(
        self,
        data: GoogleCalendarEventCreate,
    ) -> GoogleCalendarEventResult:
        calendar_id = self.settings.google_calendar_id
        if not calendar_id:
            raise GoogleCalendarConfigurationError(
                "В .env не указан GOOGLE_CALENDAR_ID."
            )

        credentials = self._load_credentials()
        service = build(
            "calendar",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )
        should_use_service_account_fallback = (
            self.settings.use_google_calendar_service_account
        )
        if should_use_service_account_fallback:
            data = replace(data, attendee_email="", enable_google_meet=False)
        body = build_event_body(data)

        logger.info(
            "creating google calendar event",
            extra={
                "event": "google_calendar_event_create_started",
                "component": "google_calendar",
                "request_id": data.request_id,
                "calendar_id_configured": bool(calendar_id),
                "attendee_domain": (
                    data.attendee_email.split("@")[-1] if data.attendee_email else None
                ),
                "service_account_fallback": should_use_service_account_fallback,
            },
        )

        try:
            event = (
                service.events()
                .insert(
                    calendarId=calendar_id,
                    body=body,
                    conferenceDataVersion=1 if data.enable_google_meet else 0,
                    sendUpdates="all" if data.attendee_email else "none",
                )
                .execute()
            )
        except HttpError as exc:
            logger.exception(
                "google calendar event create failed",
                extra={
                    "event": "google_calendar_event_create_failed",
                    "component": "google_calendar",
                    "request_id": data.request_id,
                    "error_code": exc.__class__.__name__,
                },
            )
            raise GoogleCalendarError(
                "Google Calendar отклонил создание события. Проверьте доступ "
                "Service Account к календарю и права на создание встреч."
            ) from exc

        logger.info(
            "google calendar event created",
            extra={
                "event": "google_calendar_event_created",
                "component": "google_calendar",
                "request_id": data.request_id,
                "google_event_id": event.get("id"),
            },
        )
        return GoogleCalendarEventResult(
            event_id=str(event.get("id", "")),
            html_link=event.get("htmlLink"),
            meet_link=extract_meet_link(event),
            attendee_invited=bool(data.attendee_email),
            google_meet_requested=data.enable_google_meet,
        )

    def _load_credentials(self):
        if not self.settings.use_google_calendar_service_account:
            return self._load_oauth_credentials()

        return self._load_service_account_credentials()

    def _load_oauth_credentials(self) -> Credentials:
        token_file = Path(self.settings.google_oauth_token_file).expanduser()
        client_file = self.settings.google_oauth_client_file

        if not token_file.exists():
            raise GoogleCalendarConfigurationError(
                "OAuth-токен Google не найден. Запустите авторизацию: "
                "venv/bin/python -m bot_helper.scripts.google_oauth_authorize"
            )

        credentials = Credentials.from_authorized_user_file(
            str(token_file),
            scopes=[CALENDAR_SCOPE],
        )
        if credentials.valid:
            return credentials

        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text(credentials.to_json(), encoding="utf-8")
            logger.info(
                "google oauth token refreshed",
                extra={
                    "event": "google_oauth_token_refreshed",
                    "component": "google_calendar",
                },
            )
            return credentials

        if client_file:
            raise GoogleCalendarConfigurationError(
                "OAuth-токен Google устарел и не может быть обновлен. "
                "Запустите авторизацию заново: "
                "venv/bin/python -m bot_helper.scripts.google_oauth_authorize"
            )

        raise GoogleCalendarConfigurationError(
            "В .env нужно указать GOOGLE_OAUTH_CLIENT_FILE и пройти OAuth-авторизацию."
        )

    def _load_service_account_credentials(self):
        raw_json = self.settings.google_service_account_json
        file_path = self.settings.google_service_account_file

        if raw_json:
            info = self._parse_service_account_json(raw_json)
            return service_account.Credentials.from_service_account_info(
                info,
                scopes=[CALENDAR_SCOPE],
            )

        if file_path:
            path = Path(file_path).expanduser()
            if not path.exists():
                raise GoogleCalendarConfigurationError(
                    f"Файл Service Account не найден: {path}"
                )
            return service_account.Credentials.from_service_account_file(
                str(path),
                scopes=[CALENDAR_SCOPE],
            )

        raise GoogleCalendarConfigurationError(
            "В .env нужно указать GOOGLE_SERVICE_ACCOUNT_FILE или "
            "GOOGLE_SERVICE_ACCOUNT_JSON."
        )

    def _parse_service_account_json(self, value: str) -> dict[str, Any]:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            try:
                decoded = base64.b64decode(value).decode("utf-8")
                return json.loads(decoded)
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise GoogleCalendarConfigurationError(
                    "GOOGLE_SERVICE_ACCOUNT_JSON должен быть JSON или base64(JSON)."
                ) from exc
