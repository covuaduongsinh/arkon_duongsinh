"""Tiny Redis fixed-window rate limiter (used to throttle public auth endpoints).

Best-effort: if Redis is unavailable the limiter fails OPEN (allows the request)
so an infra hiccup never locks users out — auth endpoints still have their own
validation. Keys are namespaced and auto-expire via the window TTL.
"""

from loguru import logger

from app.config import settings

_redis = None


async def _get_redis():
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis
        _redis = aioredis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            db=settings.redis_db,
            socket_connect_timeout=2,
            decode_responses=True,
        )
    return _redis


async def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """Return True if the call is allowed, False if the limit is exceeded.

    Fixed window: the first call in a window sets a TTL; subsequent calls
    increment. Allows up to `limit` calls per `window_seconds`.
    """
    if limit <= 0:
        return True
    try:
        r = await _get_redis()
        full_key = f"ratelimit:{key}"
        count = await r.incr(full_key)
        if count == 1:
            await r.expire(full_key, window_seconds)
        return count <= limit
    except Exception as e:  # fail open
        logger.warning(f"Rate limiter unavailable ({e}); allowing request")
        return True
