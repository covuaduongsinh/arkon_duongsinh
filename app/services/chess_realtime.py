"""Realtime match updates over Redis pub/sub.

Moves are still applied via REST (so validation + commit stay in one place); after
each change the new match state is published here, and the WebSocket endpoint
(app/routers/chess_ws.py) relays it to connected clients. Best-effort: publish
failures never break the REST request.
"""

import json

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
            decode_responses=True,
        )
    return _redis


def channel(match_id: str) -> str:
    return f"chess:match:{match_id}"


async def _publish(match_id: str, envelope: dict) -> None:
    """Publish a typed envelope to the match channel. Best-effort."""
    try:
        r = await _get_redis()
        await r.publish(channel(match_id), json.dumps(envelope, default=str))
    except Exception as e:  # never break the caller
        logger.warning(f"chess_realtime publish failed for {match_id}: {e}")


async def publish_match(match_id: str, payload: dict) -> None:
    """Publish a match state update (envelope type 'state'). Best-effort."""
    await _publish(match_id, {"type": "state", "match": payload})


async def publish_chat(match_id: str, message: dict) -> None:
    """Publish a chat message (envelope type 'chat'). Best-effort."""
    await _publish(match_id, {"type": "chat", "message": message})


async def subscribe(match_id: str):
    """Return a Redis PubSub subscribed to the match channel (or None on error)."""
    try:
        r = await _get_redis()
        ps = r.pubsub()
        await ps.subscribe(channel(match_id))
        return ps
    except Exception as e:
        logger.warning(f"chess_realtime subscribe failed for {match_id}: {e}")
        return None
