from redis.asyncio import Redis

from bot_helper.core.config import get_settings

settings = get_settings()
redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


async def check_redis() -> None:
    await redis_client.ping()


async def close_redis() -> None:
    await redis_client.aclose()
