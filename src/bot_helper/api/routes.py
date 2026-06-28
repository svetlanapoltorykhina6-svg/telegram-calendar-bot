import logging
from time import perf_counter

from aiogram import Bot
from aiogram.types import Update
from fastapi import APIRouter, HTTPException, Request, status

from bot_helper.core.config import Settings
from bot_helper.db.session import check_database
from bot_helper.redis.client import check_redis

router = APIRouter()
logger = logging.getLogger("bot_helper.api")


def get_request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    logger.info(
        "healthcheck passed",
        extra={
            "event": "healthcheck_passed",
            "component": "api",
            "request_id": get_request_id(request),
        },
    )
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> dict[str, object]:
    started_at = perf_counter()
    components: dict[str, str] = {}

    try:
        await check_database()
        components["database"] = "ok"
    except Exception as exc:
        components["database"] = "error"
        logger.error(
            "database readiness check failed",
            extra={
                "event": "database_readiness_failed",
                "component": "database",
                "request_id": get_request_id(request),
                "error_code": exc.__class__.__name__,
            },
            exc_info=exc,
        )

    try:
        await check_redis()
        components["redis"] = "ok"
    except Exception as exc:
        components["redis"] = "error"
        logger.error(
            "redis readiness check failed",
            extra={
                "event": "redis_readiness_failed",
                "component": "redis",
                "request_id": get_request_id(request),
                "error_code": exc.__class__.__name__,
            },
            exc_info=exc,
        )

    settings: Settings = request.app.state.settings
    components["telegram_config"] = (
        "ok" if settings.telegram_bot_token else "not_configured"
    )
    components["google_calendar_config"] = (
        "ok" if settings.google_calendar_id else "not_configured"
    )

    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    is_ready = all(value == "ok" for value in components.values())

    logger.info(
        "readiness check completed",
        extra={
            "event": "readiness_check_completed",
            "component": "api",
            "request_id": get_request_id(request),
            "duration_ms": duration_ms,
            "is_ready": is_ready,
        },
    )

    payload = {"status": "ready" if is_ready else "not_ready", "components": components}
    if not is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=payload,
        )
    return payload


@router.post("/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request) -> dict[str, str]:
    settings: Settings = request.app.state.settings
    request_id = get_request_id(request)

    if secret != settings.telegram_webhook_secret:
        logger.warning(
            "telegram webhook forbidden",
            extra={
                "event": "telegram_webhook_forbidden",
                "component": "telegram",
                "request_id": request_id,
            },
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    if not settings.telegram_bot_token:
        logger.error(
            "telegram bot token is not configured",
            extra={
                "event": "telegram_token_missing",
                "component": "telegram",
                "request_id": request_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram bot token is not configured",
        )

    payload = await request.json()
    bot: Bot | None = getattr(request.app.state, "telegram_bot", None)
    dispatcher = getattr(request.app.state, "telegram_dispatcher", None)
    if bot is None or dispatcher is None:
        logger.error(
            "telegram bot runtime is not initialized",
            extra={
                "event": "telegram_runtime_missing",
                "component": "telegram",
                "request_id": request_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram bot runtime is not initialized",
        )

    update = Update.model_validate(payload, context={"bot": bot})
    logger.info(
        "telegram update received",
        extra={
            "event": "telegram_update_received",
            "component": "telegram",
            "request_id": request_id,
            "telegram_update_id": update.update_id,
        },
    )
    await dispatcher.feed_update(bot, update)

    return {"status": "ok"}
