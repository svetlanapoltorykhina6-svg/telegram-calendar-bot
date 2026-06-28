from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from aiogram import Bot
from fastapi import FastAPI

from bot_helper.api.middleware import CorrelationIdMiddleware
from bot_helper.api.routes import router
from bot_helper.bot.dispatcher import create_dispatcher
from bot_helper.core.config import Settings, get_settings
from bot_helper.core.logging import setup_logging
from bot_helper.db.session import close_database
from bot_helper.redis.client import close_redis


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    logger = logging.getLogger("bot_helper.lifecycle")
    logger.info(
        "application startup",
        extra={
            "event": "app_startup",
            "component": "lifecycle",
            "app_env": settings.app_env,
        },
    )
    try:
        yield
    finally:
        bot: Bot | None = getattr(app.state, "telegram_bot", None)
        if bot is not None:
            await bot.session.close()
        await close_redis()
        await close_database()
        logger.info(
            "application shutdown",
            extra={"event": "app_shutdown", "component": "lifecycle"},
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.telegram_dispatcher = create_dispatcher(settings)
    app.state.telegram_bot = (
        Bot(token=settings.telegram_bot_token)
        if settings.telegram_bot_token
        else None
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.include_router(router)
    return app


app = create_app()
