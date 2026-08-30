"""
Shared base machinery for the Redis-backed stores.

The approvals and alerting packages each hand-rolled the same plumbing:
client construction, distributed locking (SET NX EX + DEL), JSON
read-modify-write under lock, and list-based history with trim + TTL.
This module centralizes that plumbing. Domain stores subclass it and keep
their own schemas, key namespaces, and public method names.

Locking note: locks use plain ``SET key NX EX ttl`` for acquire and
``DEL`` for release (no Lua / ownership token). A lock is not released by
its holder's identity, so a holder that outlives its TTL can delete a
lock since acquired by someone else. Both stores shipped this exact
behaviour; it is preserved here unchanged.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

logger = logging.getLogger(__name__)

# Distributed lock behaviour shared by all state stores.
LOCK_ATTEMPTS = 3
LOCK_BACKOFF_BASE = 0.1  # seconds; doubles on each retry
LOCK_VALUE = "locked"


def now_utc() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


class BaseRedisStore:
    """Redis client plumbing shared by state and history stores."""

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_password: str | None = None,
        redis_db: int = 0,
        socket_timeouts: bool = False,
    ):
        """
        Initialize the Redis client.

        Args:
            redis_host: Redis host
            redis_port: Redis port
            redis_password: Redis password (optional)
            redis_db: Redis database number
            socket_timeouts: Add 5s connect/socket timeouts (used by state stores)
        """
        if not REDIS_AVAILABLE:
            raise ImportError(f"redis package is required for {type(self).__name__}")

        timeouts: dict[str, int] = (
            {"socket_connect_timeout": 5, "socket_timeout": 5} if socket_timeouts else {}
        )
        self.redis = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_password,
            db=redis_db,
            decode_responses=True,
            **timeouts,
        )

    def _error(self, message: str, exc: Exception) -> None:
        """Log an error prefixed with the concrete store's class name."""
        logger.error(f"{type(self).__name__}: {message}: {exc}")

    async def close(self) -> None:
        """Close Redis connection."""
        try:
            await self.redis.close()
        except Exception as e:
            self._error("Error closing connection", e)


class BaseRedisStateStore(BaseRedisStore):
    """
    Shared machinery for entity-state stores (approval / alert state).

    Provides key building (``<namespace>:state:<id>`` / ``<namespace>:lock:<id>``),
    JSON get, scan-all, distributed locking with retry, and the locked
    read-modify-write cycle. Subclasses define the state schema and the
    public domain methods on top of it.
    """

    def __init__(
        self,
        *,
        namespace: str,
        entity: str,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_password: str | None = None,
        redis_db: int = 0,
        ttl_seconds: int,
        lock_ttl: int,
    ):
        """
        Initialize the state store.

        Args:
            namespace: Key namespace (e.g. "approval", "alert")
            entity: Noun for error messages (e.g. "approval", "alert")
            redis_host: Redis host
            redis_port: Redis port
            redis_password: Redis password (optional)
            redis_db: Redis database number
            ttl_seconds: TTL for state entries
            lock_ttl: TTL for distributed locks
        """
        super().__init__(redis_host, redis_port, redis_password, redis_db, socket_timeouts=True)
        self._namespace = namespace
        self._entity = entity
        self.ttl_seconds = ttl_seconds
        self.lock_ttl = lock_ttl

    # -- Key building -----------------------------------------------------

    def _state_key(self, entity_id: str) -> str:
        return f"{self._namespace}:state:{entity_id}"

    def _lock_key(self, entity_id: str) -> str:
        return f"{self._namespace}:lock:{entity_id}"

    # -- Serialization ----------------------------------------------------

    def _serialize_state(self, state: dict[str, Any]) -> str:
        """Serialize a state dict; subclasses may override (e.g. default=str)."""
        return json.dumps(state)

    # -- Single-entity reads/writes ----------------------------------------

    async def get(self, entity_id: str) -> dict[str, Any] | None:
        """
        Get state for an entity.

        Args:
            entity_id: Entity ID

        Returns:
            State dict or None if not found
        """
        try:
            data = await self.redis.get(self._state_key(entity_id))
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            self._error(f"Error getting state for {entity_id}", e)
            return None

    async def _delete_state_and_lock(self, entity_id: str) -> int:
        """Delete the state and lock keys; returns 0 on error, else the delete count."""
        try:
            return await self.redis.delete(self._state_key(entity_id), self._lock_key(entity_id))
        except Exception as e:
            self._error(f"Error deleting state for {entity_id}", e)
            return 0

    # -- Bulk reads ---------------------------------------------------------

    async def _scan_all_states(self) -> dict[str, dict[str, Any]]:
        """
        Get all states via SCAN + MGET, keyed by entity ID.

        Robust against the scan/mget race: keys deleted between the two
        calls yield None values and are skipped, and malformed entries are
        skipped with a warning instead of failing the whole call.
        """
        prefix = f"{self._namespace}:state:"
        try:
            keys = [key async for key in self.redis.scan_iter(match=f"{prefix}*")]
            if not keys:
                return {}

            values = await self.redis.mget(keys)

            result = {}
            for i, key in enumerate(keys):
                if i >= len(values):
                    logger.warning(f"{type(self).__name__}: Missing value for key {key}, skipping")
                    continue
                value = values[i]
                if not value:
                    continue
                try:
                    result[key.replace(prefix, "")] = json.loads(value)
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(
                        f"{type(self).__name__}: Skipping malformed state for {key}: {e}"
                    )
            return result

        except Exception as e:
            self._error("Error getting all states", e)
            return {}

    # -- Distributed locking ------------------------------------------------

    async def acquire_lock(self, entity_id: str, ttl: int | None = None) -> bool:
        """
        Acquire distributed lock for entity modification (single attempt).

        Args:
            entity_id: Entity ID
            ttl: Lock TTL (uses default if not provided)

        Returns:
            True if lock acquired, False otherwise
        """
        try:
            return await self.redis.set(
                self._lock_key(entity_id),
                LOCK_VALUE,
                nx=True,
                ex=ttl or self.lock_ttl,
            )
        except Exception as e:
            self._error(f"Error acquiring lock for {entity_id}", e)
            return False

    async def release_lock(self, entity_id: str) -> bool:
        """
        Release distributed lock for entity.

        Args:
            entity_id: Entity ID

        Returns:
            True if lock was released, False otherwise
        """
        try:
            result = await self.redis.delete(self._lock_key(entity_id))
            return result > 0
        except Exception as e:
            self._error(f"Error releasing lock for {entity_id}", e)
            return False

    async def _acquire_lock_or_raise(self, entity_id: str) -> None:
        """
        Acquire the distributed lock, retrying with exponential backoff.

        Raises:
            RuntimeError: If the lock cannot be acquired, so a concurrent
                modification is never silently clobbered.
        """
        for attempt in range(LOCK_ATTEMPTS):
            locked = await self.redis.set(
                self._lock_key(entity_id),
                LOCK_VALUE,
                nx=True,
                ex=self.lock_ttl,
            )
            if locked:
                return
            await asyncio.sleep(LOCK_BACKOFF_BASE * (2 ** attempt))

        raise RuntimeError(
            f"Could not acquire lock for {self._entity} {entity_id} after {LOCK_ATTEMPTS} retries. "
            f"The {self._entity} is being modified by another process."
        )

    # -- Locked read-modify-write -------------------------------------------

    async def _locked_update(
        self,
        entity_id: str,
        build_initial_state: Callable[[], dict[str, Any]],
        apply_updates: Callable[[dict[str, Any]], Any],
    ) -> dict[str, Any]:
        """
        Read-modify-write the state under the distributed lock.

        Acquires the lock (retrying, raising on failure), reads the existing
        state (or builds the initial one), applies ``apply_updates`` to it,
        persists it with the TTL, and always releases the lock.

        Args:
            entity_id: Entity ID
            build_initial_state: Builds the initial state when none exists
            apply_updates: Mutates the state dict with the pending updates

        Returns:
            The updated state
        """
        key = self._state_key(entity_id)
        lock_key = self._lock_key(entity_id)

        await self._acquire_lock_or_raise(entity_id)

        try:
            existing = await self.redis.get(key)
            state = json.loads(existing) if existing else build_initial_state()
            apply_updates(state)
            await self.redis.setex(key, self.ttl_seconds, self._serialize_state(state))
            return state
        finally:
            # Always release lock
            await self.redis.delete(lock_key)


class BaseRedisHistory(BaseRedisStore):
    """
    Shared machinery for list-based event history stores.

    Events are LPUSHed (newest first), trimmed to ``max_entries`` and given
    a retention TTL. Subclasses own their key names and public methods.
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
        Initialize the history store.

        Args:
            redis_host: Redis host
            redis_port: Redis port
            redis_password: Redis password (optional)
            redis_db: Redis database number
            max_entries: Maximum entries to keep in the list
            retention_days: Days to retain history (TTL)
        """
        super().__init__(redis_host, redis_port, redis_password, redis_db)
        self.max_entries = max_entries
        self.retention_seconds = retention_days * 86400  # Convert to seconds

    async def _append_event(self, key: str, event_json: str) -> None:
        """LPUSH event, trim the list to max_entries, and refresh the retention TTL."""
        await self.redis.lpush(key, event_json)
        await self.redis.ltrim(key, 0, self.max_entries - 1)
        await self.redis.expire(key, self.retention_seconds)

    async def _read_entries(self, key: str, end: int = -1) -> list[dict[str, Any]]:
        """LRANGE entries (newest first) and deserialize, skipping malformed entries."""
        entries = []
        for raw in await self.redis.lrange(key, 0, end):
            try:
                entries.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        return entries
