"""
Redis-backed Approval Store

Phase 9 - Sprint 1 - Day 2
Purpose: Migrate from file-based to Redis-backed approval state management

Features:
- Distributed state management across multiple pods
- TTL-based automatic cleanup (7-day retention for audit trail)
- Distributed locking for concurrent modification prevention
- Separate Redis database for approval state

Redis plumbing (client, locking, JSON read-modify-write, history lists)
lives in app.redis_store_base; this module holds the approval schema.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.models.actions import ActionStatus
from app.redis_store_base import BaseRedisHistory, BaseRedisStateStore, now_utc

logger = logging.getLogger(__name__)


class RedisApprovalStore(BaseRedisStateStore):
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
        super().__init__(
            namespace="approval",
            entity="approval",
            redis_host=redis_host,
            redis_port=redis_port,
            redis_password=redis_password,
            redis_db=redis_db,
            ttl_seconds=ttl_seconds,
            lock_ttl=lock_ttl,
        )
        self._ws_manager = None

    def _serialize_state(self, state: dict[str, Any]) -> str:
        """Serialize with default=str so enum/datetime fields never fail."""
        return json.dumps(state, default=str)

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

    async def get_all(self) -> dict[str, dict[str, Any]]:
        """
        Get all approval states.

        Returns:
            Dictionary mapping action_id to state
        """
        return await self._scan_all_states()

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
            self._error("Error getting pending count", e)
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
                "updated_at": now_utc(),
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

        def build_initial_state() -> dict[str, Any]:
            state = {
                "action_id": action_id,
                "status": ActionStatus.PENDING,
                "created_at": now_utc(),
                "created_by": created_by,
            }
            if command:
                state["command"] = command
            return state

        def apply_updates(state: dict[str, Any]) -> None:
            # Apply status-specific updates
            status = updates.get("status")
            if status:
                state["status"] = status

            if status == ActionStatus.APPROVED:
                state["approved_at"] = updates.get("updated_at", now_utc())
                state["approved_by"] = updates.get("updated_by")
            elif status == ActionStatus.REJECTED:
                state["rejected_at"] = updates.get("updated_at", now_utc())
                state["rejected_by"] = updates.get("updated_by")
                state["rejection_reason"] = updates.get("reason")
            elif status == ActionStatus.EXECUTED:
                state["executed_at"] = updates.get("updated_at", now_utc())
                state["executed_by"] = updates.get("updated_by")
            elif status == ActionStatus.FAILED:
                state["failed_at"] = updates.get("updated_at", now_utc())
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
                state.update(extra_fields)

        return await self._locked_update(action_id, build_initial_state, apply_updates)

    async def delete(self, action_id: str) -> bool:
        """
        Delete an action from state.

        Args:
            action_id: Action ID

        Returns:
            True if deleted, False otherwise
        """
        return (await self._delete_state_and_lock(action_id)) > 0


class RedisApprovalHistory(BaseRedisHistory):
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
        super().__init__(
            redis_host=redis_host,
            redis_port=redis_port,
            redis_password=redis_password,
            redis_db=redis_db,
            max_entries=max_entries,
            retention_days=retention_days,
        )
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
            event_json = json.dumps(event)

            # Add to global history list
            await self._append_event(self.global_history_key, event_json)

            # Also add to per-action history for faster lookups
            action_id = event.get("action_id")
            if action_id:
                await self._append_event(
                    f"approval:history:action:{action_id}", event_json
                )

            return True

        except Exception as e:
            self._error("Error adding event", e)
            return False

    async def get_for_action(self, action_id: str) -> list[dict[str, Any]]:
        """
        Get all events for a specific action.

        Args:
            action_id: Action ID

        Returns:
            List of approval event dicts (newest first)
        """
        try:
            return await self._read_entries(f"approval:history:action:{action_id}")
        except Exception as e:
            self._error(f"Error getting history for {action_id}", e)
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
            end = limit - 1 if limit > 0 else -1
            return await self._read_entries(self.global_history_key, end)
        except Exception as e:
            self._error("Error getting recent events", e)
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
        Clear all history (global and per-action lists).

        Returns:
            True if successful, False otherwise
        """
        try:
            # Find and delete all history keys
            keys = [key async for key in self.redis.scan_iter(match="approval:history:*")]
            if keys:
                await self.redis.delete(*keys)
            return True
        except Exception as e:
            self._error("Error clearing history", e)
            return False
