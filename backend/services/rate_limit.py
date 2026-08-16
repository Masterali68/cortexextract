from __future__ import annotations

import logging
import os
import time
from collections import defaultdict

from services.redis_client import cache_get, cache_set

logger = logging.getLogger("cortexextract.ratelimit")

RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
_WINDOW = 60

_memory: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))


async def check_rate_limit(client_ip: str) -> tuple[bool, int]:
    """Fixed-window rate limit. Returns (allowed, retry_after_seconds)."""
    key = f"ratelimit:{client_ip}:{int(time.time()) // _WINDOW}"
    count = await cache_get(key)
    if count is not None:
        current = int(count)
        if current >= RATE_LIMIT_PER_MINUTE:
            return False, _WINDOW
        await _cache_incr(key, current + 1)
        return True, 0

    count, window_start = _memory[client_ip]
    if time.time() - window_start >= _WINDOW:
        _memory[client_ip] = (1, time.time())
        return True, 0
    if count >= RATE_LIMIT_PER_MINUTE:
        return False, int(_WINDOW - (time.time() - window_start))
    _memory[client_ip] = (count + 1, window_start)
    return True, 0


async def _cache_incr(key: str, value: int) -> None:
    try:
        await cache_set(key, str(value), _WINDOW)
    except Exception as exc:
        logger.debug("ratelimit cache write failed: %s", exc)