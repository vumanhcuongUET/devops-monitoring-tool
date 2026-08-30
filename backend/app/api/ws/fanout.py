"""Cross-pod WebSocket fanout via Redis pub/sub (Phase 12 H1).

ConnectionManager.broadcast is pod-local. With backend replicas >= 2, an
event broadcast on the pod that evaluated the alert never reaches WS clients
connected to another pod. When WS_FANOUT_USE_REDIS is on, every broadcast is
published to a Redis channel; each pod runs a subscriber that delivers to
its own local connections. Publisher and subscribers are uniform: every pod
delivers everything it receives to local sockets only — single delivery
path, no double-send on the originating pod.

Redis down => publish() returns False => broadcast falls back to pod-local
delivery (events still reach clients on the pod that produced them).
"""

from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger(__name__)

CHANNEL = "ws:live:fanout"


def fanout_enabled() -> bool:
    from app.config import settings

    return settings.WS_FANOUT_USE_REDIS


async def publish(data: dict) -> bool:
    """Publish a broadcast to Redis. True = published (local send is handled
    by the subscriber), False = disabled or failed (caller falls back to
    pod-local delivery)."""
    if not fanout_enabled():
        return False
    try:
        from app.redis_client import get_redis

        await get_redis().publish(CHANNEL, json.dumps(data, default=str))
        return True
    except Exception as e:
        logger.warning("WS fanout publish failed, falling back to local: %s", e)
        return False


async def subscribe_loop(on_event) -> None:
    """Deliver Redis-published events to this pod's local WS connections.

    on_event is an async callable taking the decoded dict. Runs until
    cancelled; reconnects on connection loss (pubsub.listen() ends on
    connection error, the loop re-subscribes after a short sleep).
    """
    from app.redis_client import get_redis

    while True:
        pubsub = get_redis().pubsub()
        try:
            await pubsub.subscribe(CHANNEL)
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                try:
                    await on_event(json.loads(msg["data"]))
                except Exception:
                    logger.exception("WS fanout delivery failed")
        except asyncio.CancelledError:
            await pubsub.aclose()
            raise
        except Exception as e:
            logger.warning("WS fanout subscriber disconnected (%s); reconnecting", e)
            await asyncio.sleep(3)

