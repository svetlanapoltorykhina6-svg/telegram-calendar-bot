from __future__ import annotations

import json
import logging
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from bot_helper.core.config import get_settings
from bot_helper.core.logging import setup_logging
from bot_helper.services.google_calendar import CALENDAR_SCOPE

logger = logging.getLogger("bot_helper.google_oauth_authorize")


def main() -> None:
    setup_logging()
    settings = get_settings()

    client_file = settings.google_oauth_client_file
    if not client_file:
        raise SystemExit("В .env не указан GOOGLE_OAUTH_CLIENT_FILE.")

    client_path = Path(client_file).expanduser()
    if not client_path.exists():
        raise SystemExit(f"OAuth client JSON не найден: {client_path}")

    token_path = Path(settings.google_oauth_token_file).expanduser()
    token_path.parent.mkdir(parents=True, exist_ok=True)

    _validate_client_file(client_path)
    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_path),
        scopes=[CALENDAR_SCOPE],
    )
    credentials = flow.run_local_server(
        host="localhost",
        port=8080,
        authorization_prompt_message=(
            "Откройте ссылку в браузере и разрешите доступ к Google Calendar:\n{url}\n"
        ),
        success_message=(
            "Авторизация Google Calendar завершена. Можно закрыть эту вкладку."
        ),
        open_browser=True,
    )
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    logger.info(
        "google oauth token saved",
        extra={
            "event": "google_oauth_token_saved",
            "component": "google_calendar",
            "token_path": str(token_path),
        },
    )
    print(f"OAuth-токен сохранен: {token_path}")


def _validate_client_file(client_path: Path) -> None:
    try:
        data = json.loads(client_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"OAuth client JSON поврежден: {client_path}") from exc

    if "installed" in data:
        return

    if "web" in data:
        return

    raise SystemExit(
        "OAuth client JSON должен содержать раздел installed или web. "
        "Скачайте JSON у созданного OAuth Client ID."
    )


if __name__ == "__main__":
    main()
