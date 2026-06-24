from fastapi.testclient import TestClient

from bot_helper.api import routes
from bot_helper.core.config import Settings
from bot_helper.main import create_app


def test_health_returns_ok() -> None:
    app = create_app(Settings())

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ok_when_dependencies_are_available(monkeypatch) -> None:
    async def check_ok() -> None:
        return None

    monkeypatch.setattr(routes, "check_database", check_ok)
    monkeypatch.setattr(routes, "check_redis", check_ok)

    app = create_app(
        Settings(
            telegram_bot_token="123456:test-token",
            google_calendar_id="calendar@example.com",
        )
    )

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "components": {
            "database": "ok",
            "redis": "ok",
            "telegram_config": "ok",
            "google_calendar_config": "ok",
        },
    }
