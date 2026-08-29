"""
Redis-backed Approval Store

Phase 9 - Sprint 1 - Day 2
Purpose: Migrate from file-based to Redis-backed approval state management

Features:
- Distributed state management across multiple pods
- TTL-based automatic cleanup (7-day retention for audit trail)
- Distributed locking for concurrent modification prevention
- Separate Redis database for approval state
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from app.models.actions import ActionStatus

logger = logging.getLogger(__name__)


class RedisApprovalStore:
    """
    Redis-backed approval state with distributed locking.

    This replaces the file-based ApprovalStateTracker with a distributed
    Redis-backed implementation that works across multiple pods.

    Features:
    - 7-day TTL for approval state (audit trail retention)
    - Distributed locking (30s lock timeout)
    - Separate Redis DB for approvals
    """

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_password: str | None = None,
        redis_db: int = 1,  # Separate DB for approvals
        ttl_seconds: int = 604800,  # 7 days default
        lock_ttl: int = 30,  # 30 seconds lock timeout
    ):
        """
        Initialize Redis approval store.

        Args:
            redis_host: Redis host
            redis_port: Redis port
            redis_password: Redis password (optional)
            redis_db: Redis database number for approvals
            ttl_seconds: TTL for approval state entries (default 7 days)
            lock_ttl: TTL for distributed locks (default 30 seconds)
        """
        if not REDIS_AVAILABLE:
            raise ImportError("redis package is required for RedisApprovalStore")

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
        self._ws_manager = None

    def set_ws_manager(self, manager):
        """Set the WebSocket manager for real-time updates."""
        self._ws_manager = manager

    async def broadcast_status(self, action_id: str, status: ActionStatus):
        """Broadcast status change via WebSocket."""
        if self._ws_manager:
            await self._ws_manager.broadcast({
                "type": "approval_status_changed",
                "data": {
                    "action_id": action_id,
                    "status": status,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })

    async def get(self, action_id: str) -> dict[str, Any] | None:
        """
        Get approval state for an action.

        Args:
            action_id: Action ID

        Returns:
            Approval state dict or None if not found
        """
        key = f"approval:state:{action_id}"

        try:
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"RedisApprovalStore: Error getting state for {action_id}: {e}")
            return None

    async def get_all(self) -> dict[str, dict[str, Any]]:
        """
        Get all approval states.

        Returns:
            Dictionary mapping action_id to state
        """
        pattern = "approval:state:*"

        try:
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)

            if not keys:
                return {}

            # Fetch all values
            values = await self.redis.mget(keys)

            # Build result dict
            result = {}
            for key, value in zip(keys, values, strict=False):
                if value:
                    key_s = key.decode() if isinstance(key, bytes) else key
                    val_s = value.decode() if isinstance(value, bytes) else value
                    # Extract action_id from key
                    action_id = key_s.replace("approval:state:", "")
                    result[action_id] = json.loads(val_s)

            return result

        except Exception as e:
            logger.error(f"RedisApprovalStore: Error getting all states: {e}")
            return {}

    async def get_by_status(self, status: ActionStatus) -> list[str]:
        """
        Get all action IDs with a specific status.

        Args:
            status: Action status to filter by

        Returns:
            List of action IDs with the specified status
        """
        all_states = await self.get_all()
        return [
            action_id
            for action_id, state in all_states.items()
            if state.get("status") == status
        ]

    async def get_pending_count(self) -> int:
        """
        Get count of pending actions.

        Returns:
            Number of pending actions
        """
        try:
            pending_ids = await self.get_by_status(ActionStatus.PENDING)
            return len(pending_ids)
        except Exception as e:
            logger.error(f"RedisApprovalStore: Error getting pending count: {e}")
            return 0

    async def set_status(
        self,
        action_id: str,
        status: ActionStatus,
        user: str | None = None,
        reason: str | None = None,
        command: str | None = None,
        **extra_fields,
    ) -> dict[str, Any]:
        """
        Set the status of an action.

        Args:
            action_id: Action ID
            status: New status
            user: User making the change
            reason: Reason for rejection (if applicable)
            command: Command to execute
            **extra_fields: Additional fields to store

        Returns:
            Updated approval state
        """
        return await self._update_state(
            action_id=action_id,
            updates={
                "status": status,
                "updated_at": _now(),
                "updated_by": user,
                "reason": reason,
            },
            command=command,
            created_by=user,
            extra_fields=extra_fields,
        )

    async def _update_state(
        self,
        action_id: str,
        updates: dict[str, Any],
        command: str | None = None,
        created_by: str | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Update approval state with atomic operation and distributed lock.

        Args:
            action_id: Action ID
            updates: Fields to update
            command: Command to store
            created_by: Creator of the action
            extra_fields: Additional fields

        Returns:
            Updated approval state
        """
        key = f"approval:state:{action_id}"
        lock_key = f"approval:lock:{action_id}"

        # Phase 10 Sprint 1 Day 1: Bug Fix - Lock acquisition with retry before throwing
        # Try to acquire lock with retries before giving up
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
                f"Could not acquire lock for approval {action_id} after {max_retries} retries. "
                f"Another process may be modifying this approval."
            )

        try:
            # Get existing state
            existing_data = await self.redis.get(key)
            if existing_data:
                state = json.loads(existing_data)
            else:
                # Initialize new state
                state = {
                    "action_id": action_id,
                    "status": ActionStatus.PENDING,
                    "created_at": _now(),
                    "created_by": created_by,
                }
                # Store command if provided
                if command:
                    state["command"] = command

            # Apply status-specific updates
            status = updates.get("status")
            if status:
                # Set the status first
                state["status"] = status

            if status == ActionStatus.APPROVED:
                state["approved_at"] = updates.get("updated_at", _now())
                state["approved_by"] = updates.get("updated_by")
            elif status == ActionStatus.REJECTED:
                state["rejected_at"] = updates.get("updated_at", _now())
                state["rejected_by"] = updates.get("updated_by")
                state["rejection_reason"] = updates.get("reason")
            elif status == ActionStatus.EXECUTED:
                state["executed_at"] = updates.get("updated_at", _now())
                state["executed_by"] = updates.get("updated_by")
            elif status == ActionStatus.FAILED:
                state["failed_at"] = updates.get("updated_at", _now())
                state["failed_by"] = updates.get("updated_by")

            # Apply general updates (excluding status and reason which are handled above)
            for field, value in updates.items():
                if field not in ("reason", "status"):
                    state[field] = value

            # Store command if provided and not already stored
            if command and "command" not in state:
                state["command"] = command

            # Apply extra fields
            if extra_fields:
                for key, value in extra_fields.items():
                    state[key] = value

            # Save with TTL
            await self.redis.setex(
                key,
                self.ttl_seconds,
                json.dumps(state, default=str),
            )

            return state

        finally:
            # Always release lock
            await self.redis.delete(lock_key)

    async def delete(self, action_id: str) -> bool:
        """
        Delete an action from state.

        Args:
            action_id: Action ID

        Returns:
            True if deleted, False otherwise
        """
        key = f"approval:state:{action_id}"
        lock_key = f"approval:lock:{action_id}"

        try:
            # Delete both state and lock
            result = await self.redis.delete(key, lock_key)
            return result > 0
        except Exception as e:
            logger.error(f"RedisApprovalStore: Error deleting {action_id}: {e}")
            return False

    async def acquire_lock(self, action_id: str, ttl: int | None = None) -> bool:
        """
        Acquire distributed lock for approval modification.

        Args:
            action_id: Action ID
            ttl: Lock TTL (uses default if not provided)

        Returns:
            True if lock acquired, False otherwise
        """
        lock_key = f"approval:lock:{action_id}"
        lock_ttl = ttl or self.lock_ttl

        try:
            return await self.redis.set(
                lock_key,
                "locked",
                nx=True,
                ex=lock_ttl,
            )
        except Exception as e:
            logger.error(f"RedisApprovalStore: Error acquiring lock for {action_id}: {e}")
            return False

    async def release_lock(self, action_id: str) -> bool:
        """
        Release distributed lock for approval.

        Args:
            action_id: Action ID

        Returns:
            True if lock was released, False otherwise
        """
        lock_key = f"approval:lock:{action_id}"

        try:
            result = await self.redis.delete(lock_key)
            return result > 0
        except Exception as e:
            logger.error(f"RedisApprovalStore: Error releasing lock for {action_id}: {e}")
            return False

    async def close(self) -> None:
        """Close Redis connection."""
        try:
            await self.redis.close()
        except Exception as e:
            logger.error(f"RedisApprovalStore: Error closing connection: {e}")


class RedisApprovalHistory:
    """
    Redis-backed approval history with automatic cleanup.

    Stores approval events (status changes) with 7-day retention.

    Features:
    - 7-day default retention for history
    - Automatic cleanup via TTL
    - Per-action history tracking
    """

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_password: str | None = None,
        redis_db: int = 1,  # Same DB as approvals
        max_entries: int = 100,
        retention_days: int = 7,
    ):
        """
        Initialize Redis approval history.

        Args:
            redis_host: Redis host
            redis_port: Redis port
            redis_password: Redis password (optional)
            redis_db: Redis database number
            max_entries: Maximum entries to keep in list
            retention_days: Days to retain history (TTL)
        """
        if not REDIS_AVAILABLE:
            raise ImportError("redis package is required for RedisApprovalHistory")

        self.redis = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_password,
            db=redis_db,
            decode_responses=True,
        )
        self.max_entries = max_entries
        self.retention_seconds = retention_days * 86400  # Convert to seconds
        self.global_history_key = "approval:history:events"

    async def add(self, event: dict[str, Any]) -> bool:
        """
        Add event to history.

        Args:
            event: Approval event dict

        Returns:
            True if successful, False otherwise
        """
        try:
            # Serialize event
            event_json = json.dumps(event)

            # Add to global history list (left push for newest first)
            await self.redis.lpush(self.global_history_key, event_json)

            # Trim to max entries
            await self.redis.ltrim(self.global_history_key, 0, self.max_entries - 1)

            # Set TTL on the list key
            await self.redis.expire(self.global_history_key, self.retention_seconds)

            # Also add to per-action history for faster lookups
            action_id = event.get("action_id")
            if action_id:
                action_key = f"approval:history:action:{action_id}"
                await self.redis.lpush(action_key, event_json)
                await self.redis.ltrim(action_key, 0, self.max_entries - 1)
                await self.redis.expire(action_key, self.retention_seconds)

            return True

        except Exception as e:
            logger.error(f"RedisApprovalHistory: Error adding event: {e}")
            return False

    async def get_for_action(self, action_id: str) -> list[dict[str, Any]]:
        """
        Get all events for a specific action.

        Args:
            action_id: Action ID

        Returns:
            List of approval event dicts (newest first)
        """
        key = f"approval:history:action:{action_id}"

        try:
            # Get entries from action-specific list
            raw_entries = await self.redis.lrange(key, 0, -1)

            # Deserialize
            entries = []
            for raw in raw_entries:
                try:
                    entries.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue

            return entries

        except Exception as e:
            logger.error(f"RedisApprovalHistory: Error getting history for {action_id}: {e}")
            return []

    async def get_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        Get recent events.

        Args:
            limit: Maximum entries to return

        Returns:
            List of approval event dicts (newest first)
        """
        try:
            # Get entries from global history list
            end = limit - 1 if limit > 0 else -1
            raw_entries = await self.redis.lrange(self.global_history_key, 0, end)

            # Deserialize
            entries = []
            for raw in raw_entries:
                try:
                    entries.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue

            return entries

        except Exception as e:
            logger.error(f"RedisApprovalHistory: Error getting recent events: {e}")
            return []

    @property
    async def entries(self) -> list[dict[str, Any]]:
        """
        Get all entries.

        Returns:
            All approval event dicts (newest first)
        """
        return await self.get_recent(limit=-1)

    async def clear(self) -> bool:
        """
        Clear all history.

        Returns:
            True if successful, False otherwise
        """
        try:
            # Clear global history
            pattern = "approval:history:*"

            # Find and delete all history keys
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                await self.redis.delete(*keys)

            return True

        except Exception as e:
            logger.error(f"RedisApprovalHistory: Error clearing history: {e}")
            return False

    async def close(self) -> None:
        """Close Redis connection."""
        try:
            await self.redis.close()
        except Exception as e:
            logger.error(f"RedisApprovalHistory: Error closing connection: {e}")


def _now() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()
