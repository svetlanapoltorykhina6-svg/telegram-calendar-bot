from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from bot_helper.bot.dispatcher import create_dispatcher
from bot_helper.core.config import get_settings
from bot_helper.core.logging import setup_logging

logger = logging.getLogger("bot_helper.telegram.polling")


async def run_polling() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    if not settings.telegram_bot_token or settings.telegram_bot_token.startswith("PUT_"):
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured in .env")
    if not settings.allowed_telegram_ids and not settings.admin_telegram_ids:
        raise RuntimeError(
            "ALLOWED_TELEGRAM_IDS or ADMIN_TELEGRAM_IDS is not configured in .env"
        )

    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = create_dispatcher(settings)

    me = await bot.get_me()
    logger.info(
        "telegram polling started",
        extra={
            "event": "telegram_polling_started",
            "component": "telegram",
            "bot_id": me.id,
            "bot_username": me.username,
        },
    )

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


def main() -> None:
    asyncio.run(run_polling())


if __name__ == "__main__":
    main()
