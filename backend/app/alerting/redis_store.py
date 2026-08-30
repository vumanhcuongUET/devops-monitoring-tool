"""
Redis-backed Alert State Store

Phase 9 - Sprint 1 - Day 1
Purpose: Migrate from file-based to Redis-backed alert state management

Features:
- Distributed state management across multiple pods
- TTL-based automatic cleanup
- Distributed locking for concurrent modifications
- Separate Redis database for alert state

Redis plumbing (client, locking, JSON read-modify-write, history lists)
lives in app.redis_store_base; this module holds the alert schema.
"""

import json
import logging
from typing import Any

from app.redis_store_base import BaseRedisHistory, BaseRedisStateStore, now_utc

logger = logging.getLogger(__name__)


class RedisAlertStore(BaseRedisStateStore):
    """
    Redis-backed alert state with proper locking and TTL.

    This replaces the file-based AlertStateTracker with a distributed
    Redis-backed implementation that works across multiple pods.

    Features:
    - 24-hour TTL for alert state (auto-cleanup)
    - Distributed locking (30s lock timeout)
    - Separate Redis DB for alerts
    """

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_password: str | None = None,
        redis_db: int = 0,
        ttl_seconds: int = 86400,  # 24 hours default
        lock_ttl: int = 30,  # 30 seconds lock timeout
    ):
        """
        Initialize Redis alert store.

        Args:
            redis_host: Redis host
            redis_port: Redis port
            redis_password: Redis password (optional)
            redis_db: Redis database number for alerts
            ttl_seconds: TTL for alert state entries (default 24 hours)
            lock_ttl: TTL for distributed locks (default 30 seconds)
        """
        super().__init__(
            namespace="alert",
            entity="alert",
            redis_host=redis_host,
            redis_port=redis_port,
            redis_password=redis_password,
            redis_db=redis_db,
            ttl_seconds=ttl_seconds,
            lock_ttl=lock_ttl,
        )

    async def set_breached(self, rule_id: str) -> dict[str, Any]:
        """
        Mark rule as breached (threshold crossed but not firing yet).

        Args:
            rule_id: Alert rule ID

        Returns:
            Updated alert state
        """
        return await self._update_state(rule_id, {
            "status": "pending",
            "last_breached_at": now_utc()
        })

    async def set_firing(self, rule_id: str) -> dict[str, Any]:
        """
        Mark rule as firing (alert sent).

        Args:
            rule_id: Alert rule ID

        Returns:
            Updated alert state
        """
        return await self._update_state(rule_id, {
            "status": "firing",
            "fired_at": now_utc()
        })

    async def set_resolved(self, rule_id: str) -> dict[str, Any]:
        """
        Mark rule as resolved (back to normal).

        Args:
            rule_id: Alert rule ID

        Returns:
            Updated alert state
        """
        return await self._update_state(rule_id, {
            "status": "resolved",
            "resolved_at": now_utc()
        })

    async def _update_state(self, rule_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """
        Update alert state with atomic operation.

        Raises RuntimeError if the lock cannot be acquired after retries,
        so concurrent modifications are never silently clobbered.

        Args:
            rule_id: Alert rule ID
            updates: Fields to update

        Returns:
            Updated alert state
        """

        def build_initial_state() -> dict[str, Any]:
            return {
                "rule_id": rule_id,
                "status": "pending",
                "first_breached_at": now_utc(),
                "fired_at": None,
                "resolved_at": None,
            }

        def apply_updates(state: dict[str, Any]) -> None:
            state.update(updates)

        return await self._locked_update(rule_id, build_initial_state, apply_updates)

    async def delete(self, rule_id: str) -> int:
        """
        Delete alert state for a rule.

        Args:
            rule_id: Alert rule ID

        Returns:
            Number of keys deleted (0 or 1)
        """
        result = await self._delete_state_and_lock(rule_id)
        return 1 if result > 0 else 0

    async def get_all_state(self) -> dict[str, dict[str, Any]]:
        """
        Get all alert states.

        Returns:
            Dictionary mapping rule_id to state
        """
        return await self._scan_all_states()

    async def get_firing_count(self) -> int:
        """
        Get count of currently firing alerts.

        Returns:
            Number of firing alerts
        """
        try:
            all_states = await self.get_all_state()
            return sum(
                1 for state in all_states.values()
                if state.get("status") == "firing"
            )
        except Exception as e:
            self._error("Error getting firing count", e)
            return 0


class RedisAlertHistory(BaseRedisHistory):
    """
    Redis-backed alert history with automatic cleanup.

    Stores alert events (firing, resolved) with configurable retention.

    Features:
    - 7-day default retention for history
    - Automatic cleanup via TTL
    - List-based storage with max entries
    """

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_password: str | None = None,
        redis_db: int = 0,
        max_entries: int = 100,
        retention_days: int = 7,
    ):
        """
        Initialize Redis alert history.

        Args:
            redis_host: Redis host
            redis_port: Redis port
            redis_password: Redis password (optional)
            redis_db: Redis database number
            max_entries: Maximum entries to keep in list
            retention_days: Days to retain history (TTL)
        """
        super().__init__(
            redis_host=redis_host,
            redis_port=redis_port,
            redis_password=redis_password,
            redis_db=redis_db,
            max_entries=max_entries,
            retention_days=retention_days,
        )
        self.history_key = "alert:history:events"

    async def add(self, event: dict[str, Any]) -> bool:
        """
        Add event to history.

        Args:
            event: Alert event dict

        Returns:
            True if successful, False otherwise
        """
        try:
            await self._append_event(self.history_key, json.dumps(event))
            return True
        except Exception as e:
            self._error("Error adding event", e)
            return False

    async def get_entries(self, limit: int | None = None) -> list[dict[str, Any]]:
        """
        Get recent history entries.

        Args:
            limit: Maximum entries to return (all if not specified)

        Returns:
            List of alert event dicts (newest first)
        """
        try:
            end = limit - 1 if limit else -1  # All entries when no limit
            return await self._read_entries(self.history_key, end)
        except Exception as e:
            self._error("Error getting entries", e)
            return []

    async def clear(self) -> bool:
        """
        Clear all history.

        Returns:
            True if successful, False otherwise
        """
        try:
            await self.redis.delete(self.history_key)
            return True
        except Exception as e:
            self._error("Error clearing history", e)
            return False
