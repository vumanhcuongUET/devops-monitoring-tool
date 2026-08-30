"""Shared lazily-created Redis client for the H1 cross-pod features.

Both the alert-engine leader lock (app/alerting/leader.py) and the WS
fanout (app/api/ws/fanout.py) need a Redis client built from settings.
One lazy singleton keeps the connection count at one per process.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_client = None


def get_redis():
    """Return the shared Redis client, creating it on first use."""
    global _client
    if _client is None:
        import redis.asyncio as redis

        from app.approvals.store import build_redis_url
        from app.config import settings

        url, _, _, _ = build_redis_url(db=settings.REDIS_DB_ALERTS)
        _client = redis.Redis.from_url(url, decode_responses=True)
    return _client


def reset_redis_client() -> None:
    """Drop the cached client (test helper)."""
    global _client
    _client = None
