from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "local"
    app_name: str = "telegram-calendar-bot-helper"
    app_base_url: str = "http://localhost:8000"
    log_level: str = "INFO"
    default_timezone: str = "Europe/Moscow"

    database_url: str = (
        "postgresql+asyncpg://bot_helper:bot_helper@postgres:5432/bot_helper"
    )
    redis_url: str = "redis://redis:6379/0"

    telegram_bot_token: str | None = None
    telegram_webhook_secret: str = "change-this-secret"
    admin_telegram_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    allowed_telegram_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    workdays: Annotated[list[int], NoDecode] = Field(
        default_factory=lambda: [1, 2, 3, 4, 5]
    )
    work_start_time: str = "10:00"
    work_end_time: str = "19:00"
    meeting_duration_minutes: int = 30
    allowed_meeting_durations: Annotated[list[int], NoDecode] = Field(
        default_factory=lambda: [15, 30, 45, 60, 90]
    )
    min_lead_time_minutes: int = 120
    booking_horizon_days: int = 14
    slot_buffer_minutes: int = 0
    pending_hold_minutes: int = 15
    pending_hold_storage: str = "redis"
    enable_google_meet: bool = True

    use_google_calendar_service_account: bool = True
    google_calendar_id: str | None = None
    google_service_account_file: str | None = None
    google_service_account_json: str | None = None
    google_oauth_client_file: str | None = "./secrets/google-oauth-client.json"
    google_oauth_token_file: str = "./secrets/google-oauth-token.json"

    @field_validator(
        "admin_telegram_ids",
        "allowed_telegram_ids",
        "workdays",
        "allowed_meeting_durations",
        mode="before",
    )
    @classmethod
    def parse_int_list(cls, value: str | list[int] | None) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [int(item) for item in value]
        return [int(item.strip()) for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
