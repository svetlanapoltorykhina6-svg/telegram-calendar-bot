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


def test_telegram_webhook_uses_app_dispatcher() -> None:
    class FakeDispatcher:
        def __init__(self) -> None:
            self.calls = []

        async def feed_update(self, bot, update) -> None:
            self.calls.append((bot, update))

    app = create_app(
        Settings(
            telegram_bot_token="123456:test-token",
            telegram_webhook_secret="test-secret",
        )
    )
    dispatcher = FakeDispatcher()
    app.state.telegram_dispatcher = dispatcher

    payload = {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "date": 0,
            "chat": {"id": 42, "type": "private"},
            "from": {"id": 42, "is_bot": False, "first_name": "Test"},
            "text": "Консультация",
        },
    }

    with TestClient(app) as client:
        response = client.post("/telegram/webhook/test-secret", json=payload)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(dispatcher.calls) == 1
    assert dispatcher.calls[0][0] is app.state.telegram_bot
    assert dispatcher.calls[0][1].update_id == 1
