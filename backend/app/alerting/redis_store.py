"""
Redis-backed Alert State Store

Phase 9 - Sprint 1 - Day 1
Purpose: Migrate from file-based to Redis-backed alert state management

Features:
- Distributed state management across multiple pods
- TTL-based automatic cleanup
- Distributed locking for concurrent modifications
- Separate Redis database for alert state
"""

import asyncio
import json
import logging
from typing import Any

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

logger = logging.getLogger(__name__)


class RedisAlertStore:
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
        if not REDIS_AVAILABLE:
            raise ImportError("redis package is required for RedisAlertStore")

        self.redis = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_password,
            db=redis_db,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        self.ttl_seconds = ttl_seconds
        self.lock_ttl = lock_ttl

    async def get(self, rule_id: str) -> dict[str, Any] | None:
        """
        Get alert state for a rule.

        Args:
            rule_id: Alert rule ID

        Returns:
            Alert state dict or None if not found
        """
        key = f"alert:state:{rule_id}"

        try:
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"RedisAlertStore: Error getting state for {rule_id}: {e}")
            return None

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
            "last_breached_at": _now()
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
            "fired_at": _now()
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
            "resolved_at": _now()
        })

    async def _update_state(self, rule_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """
        Update alert state with atomic operation.

        Phase 10 Sprint 1 Day 1: Bug Fix - Lock acquisition failure now raises error.

        Args:
            rule_id: Alert rule ID
            updates: Fields to update

        Returns:
            Updated alert state

        Raises:
            RuntimeError: If lock cannot be acquired after retries
        """
        key = f"alert:state:{rule_id}"
        lock_key = f"alert:lock:{rule_id}"

        # Phase 10 Bug Fix: Implement lock acquisition with retry and explicit error
        # Try to acquire lock with a few retries before giving up
        max_retries = 3
        locked = False

        for attempt in range(max_retries):
            locked = await self.redis.set(
                lock_key,
                "locked",
                nx=True,
                ex=self.lock_ttl,
            )

            if locked:
                break

            # Wait a bit before retry (exponential backoff)
            await asyncio.sleep(0.1 * (2 ** attempt))

        # If still not locked after retries, raise explicit error
        if not locked:
            raise RuntimeError(
                f"Could not acquire lock for alert {rule_id} after {max_retries} retries. "
                f"Another process may be modifying this alert."
            )

        try:
            # Get existing state
            existing_data = await self.redis.get(key)
            if existing_data:
                state = json.loads(existing_data)
            else:
                # Initialize new state
                state = {
                    "rule_id": rule_id,
                    "status": "pending",
                    "first_breached_at": _now(),
                    "fired_at": None,
                    "resolved_at": None,
                }

            # Apply updates
            state.update(updates)

            # Save with TTL
            await self.redis.setex(
                key,
                self.ttl_seconds,
                json.dumps(state),
            )

            return state

        finally:
            # Always release lock
            if locked:
                await self.redis.delete(lock_key)

    async def delete(self, rule_id: str) -> int:
        """
        Delete alert state for a rule.

        Args:
            rule_id: Alert rule ID

        Returns:
            Number of keys deleted (0 or 1)
        """
        key = f"alert:state:{rule_id}"
        lock_key = f"alert:lock:{rule_id}"

        try:
            # Delete both state and lock
            result = await self.redis.delete(key, lock_key)
            return 1 if result > 0 else 0
        except Exception as e:
            logger.error(f"RedisAlertStore: Error deleting state for {rule_id}: {e}")
            return 0

    async def get_all_state(self) -> dict[str, dict[str, Any]]:
        """
        Get all alert states.

        Phase 10 Sprint 1 Day 2: Bug Fix - Handle race condition between scan and mget.
        Between collecting keys and fetching values, keys could be deleted or added.
        We handle this by processing each key-value pair safely.

        Returns:
            Dictionary mapping rule_id to state
        """
        pattern = "alert:state:*"

        try:
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)

            if not keys:
                return {}

            # Fetch all values in one call
            values = await self.redis.mget(keys)

            # Phase 10 Bug Fix: Handle race condition more robustly
            # If a key was deleted between scan and mget, its value is None
            # We safely handle this by checking each pair
            result = {}
            for i, key in enumerate(keys):
                # Safely get value even if lengths don't match
                if i < len(values):
                    value = values[i]
                    if value:
                        try:
                            # Extract rule_id from key
                            rule_id = key.replace("alert:state:", "")
                            result[rule_id] = json.loads(value)
                        except (json.JSONDecodeError, KeyError) as e:
                            logger.warning(f"RedisAlertStore: Skipping malformed state for {key}: {e}")
                else:
                    # Race condition: more keys than values (shouldn't happen with mget)
                    logger.warning(f"RedisAlertStore: Missing value for key {key}, skipping")

            return result

        except Exception as e:
            logger.error(f"RedisAlertStore: Error getting all states: {e}")
            return {}

    async def get_firing_count(self) -> int:
        """
        Get count of currently firing alerts.

        Returns:
            Number of firing alerts
        """
        try:
            # Get all states
            all_states = await self.get_all_state()

            # Count firing ones
            return sum(
                1 for state in all_states.values()
                if state.get("status") == "firing"
            )
        except Exception as e:
            logger.error(f"RedisAlertStore: Error getting firing count: {e}")
            return 0

    async def acquire_lock(self, alert_id: str, ttl: int | None = None) -> bool:
        """
        Acquire distributed lock for alert modification.

        Args:
            alert_id: Alert ID
            ttl: Lock TTL (uses default if not provided)

        Returns:
            True if lock acquired, False otherwise
        """
        lock_key = f"alert:lock:{alert_id}"
        lock_ttl = ttl or self.lock_ttl

        try:
            return await self.redis.set(
                lock_key,
                "locked",
                nx=True,
                ex=lock_ttl,
            )
        except Exception as e:
            logger.error(f"RedisAlertStore: Error acquiring lock for {alert_id}: {e}")
            return False

    async def release_lock(self, alert_id: str) -> bool:
        """
        Release distributed lock for alert.

        Args:
            alert_id: Alert ID

        Returns:
            True if lock was released, False otherwise
        """
        lock_key = f"alert:lock:{alert_id}"

        try:
            result = await self.redis.delete(lock_key)
            return result > 0
        except Exception as e:
            logger.error(f"RedisAlertStore: Error releasing lock for {alert_id}: {e}")
            return False

    async def close(self) -> None:
        """Close Redis connection."""
        try:
            await self.redis.close()
        except Exception as e:
            logger.error(f"RedisAlertStore: Error closing connection: {e}")


class RedisAlertHistory:
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
        if not REDIS_AVAILABLE:
            raise ImportError("redis package is required for RedisAlertHistory")

        self.redis = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_password,
            db=redis_db,
            decode_responses=True,
        )
        self.max_entries = max_entries
        self.retention_seconds = retention_days * 86400  # Convert to seconds
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
            # Serialize event
            event_json = json.dumps(event)

            # Add to list (left push for newest first)
            await self.redis.lpush(self.history_key, event_json)

            # Trim to max entries
            await self.redis.ltrim(self.history_key, 0, self.max_entries - 1)

            # Set TTL on the list key
            await self.redis.expire(self.history_key, self.retention_seconds)

            return True

        except Exception as e:
            logger.error(f"RedisAlertHistory: Error adding event: {e}")
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
            # Determine range
            if limit:
                end = limit - 1
            else:
                end = -1  # All entries

            # Get entries from list
            raw_entries = await self.redis.lrange(self.history_key, 0, end)

            # Deserialize
            entries = []
            for raw in raw_entries:
                try:
                    entries.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue

            return entries

        except Exception as e:
            logger.error(f"RedisAlertHistory: Error getting entries: {e}")
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
            logger.error(f"RedisAlertHistory: Error clearing history: {e}")
            return False

    async def close(self) -> None:
        """Close Redis connection."""
        try:
            await self.redis.close()
        except Exception as e:
            logger.error(f"RedisAlertHistory: Error closing connection: {e}")


def _now() -> str:
    """Get current UTC timestamp in ISO format."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
