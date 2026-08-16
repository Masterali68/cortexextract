from __future__ import annotations

import logging
import os
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger("cortexextract.redis")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _client


async def ping() -> bool:
    """Return True when Redis is reachable. Never raises."""
    try:
        client = await get_redis()
        return bool(await client.ping())
    except Exception as exc:
        logger.debug("redis ping failed: %s", exc)
        return False


async def cache_get(key: str) -> Optional[str]:
    try:
        client = await get_redis()
        return await client.get(key)
    except Exception as exc:
        logger.debug("redis get failed: %s", exc)
        return None


async def cache_set(key: str, value: str, ttl_seconds: int) -> bool:
    try:
        client = await get_redis()
        await client.set(key, value, ex=ttl_seconds)
        return True
    except Exception as exc:
        logger.debug("redis set failed: %s", exc)
        return False
