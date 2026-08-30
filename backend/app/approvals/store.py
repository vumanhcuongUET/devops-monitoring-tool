"""Approval store for tracking action approval state (similar to AlertStateTracker)."""

import json
import os
from datetime import datetime, timezone
from typing import Any
import pathlib

from app.models.actions import ActionStatus

from app.config import settings as _settings
STATE_FILE = str(pathlib.Path(_settings.DATA_DIR) / "approval_state.json")
HISTORY_FILE = str(pathlib.Path(_settings.DATA_DIR) / "approval_history.json")


def build_redis_url(db: int | None = None) -> tuple[str, str, int, str | None]:
    """Phase 12 Sprint 3: single source for approval-store Redis URLs.

    Returns (url, host, port, password), honoring REDIS_URL when set,
    falling back to REDIS_HOST/PORT/PASSWORD + REDIS_DB_APPROVALS.
    """
    from urllib.parse import urlparse

    from app.config import settings

    if settings.REDIS_URL:
        parsed = urlparse(settings.REDIS_URL)
        return (
            settings.REDIS_URL,
            parsed.hostname or settings.REDIS_HOST,
            parsed.port or settings.REDIS_PORT,
            parsed.password or settings.REDIS_PASSWORD,
        )
    password_part = f":{settings.REDIS_PASSWORD}@" if settings.REDIS_PASSWORD else ""
    url = f"redis://{password_part}{settings.REDIS_HOST}:{settings.REDIS_PORT}/{db or settings.REDIS_DB_APPROVALS}"
    return url, settings.REDIS_HOST, settings.REDIS_PORT, settings.REDIS_PASSWORD


class ApprovalStateTracker:
    """Track approval state for actions (similar to AlertStateTracker)."""

    def __init__(self, use_redis: bool = False):
        """
        Initialize approval state tracker.

        Args:
            use_redis: If True, use Redis-backed state; otherwise file-based
        """
        self.use_redis = use_redis

        if use_redis:
            from app.approvals.redis_store import (
                RedisApprovalHistory,
                RedisApprovalStore,
            )
            from app.config import settings

            _, host, port, password = build_redis_url()

            self._state = RedisApprovalStore(
                redis_host=host, redis_port=port, redis_password=password,
                redis_db=settings.REDIS_DB_APPROVALS,
            )
            self._history = RedisApprovalHistory(
                redis_host=host, redis_port=port, redis_password=password,
                redis_db=settings.REDIS_DB_APPROVALS,
            )
        else:
            self._state: dict[str, dict[str, Any]] = {}

        self._ws_manager = None

        if not use_redis:
            self._load()

    def set_ws_manager(self, manager):
        """Set the WebSocket manager for real-time updates."""
        self._ws_manager = manager
        if self.use_redis and hasattr(self._state, 'set_ws_manager'):
            self._state.set_ws_manager(manager)

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
        """Get state for a specific action."""
        if self.use_redis:
            return await self._state.get(action_id)
        return self._state.get(action_id)

    async def get_all(self) -> dict[str, dict[str, Any]]:
        """Get all action states."""
        if self.use_redis:
            return await self._state.get_all()
        return self._state.copy()

    async def get_by_status(self, status: ActionStatus) -> list[str]:
        """Get all action IDs with a specific status."""
        if self.use_redis:
            return await self._state.get_by_status(status)
        return [
            action_id
            for action_id, state in self._state.items()
            if state.get("status") == status
        ]

    async def get_pending_count(self) -> int:
        """Get count of pending actions."""
        if self.use_redis:
            return await self._state.get_pending_count()
        return len(await self.get_by_status(ActionStatus.PENDING))

    async def set_status(
        self,
        action_id: str,
        status: ActionStatus,
        user: str | None = None,
        reason: str | None = None,
        command: str | None = None,
        **extra_fields,
    ) -> dict[str, Any]:
        """Set the status of an action."""
        if self.use_redis:
            return await self._state.set_status(
                action_id=action_id,
                status=status,
                user=user,
                reason=reason,
                command=command,
                **extra_fields,
            )

        # File-based path
        now = datetime.now(timezone.utc).isoformat()

        if action_id not in self._state:
            self._state[action_id] = {
                "status": ActionStatus.PENDING,
                "created_at": now,
                "created_by": user,
            }
            # Store command if provided
            if command:
                self._state[action_id]["command"] = command

        self._state[action_id]["status"] = status
        self._state[action_id]["updated_at"] = now
        self._state[action_id]["updated_by"] = user

        # Store command if provided
        if command and "command" not in self._state[action_id]:
            self._state[action_id]["command"] = command

        if status == ActionStatus.APPROVED:
            self._state[action_id]["approved_at"] = now
            self._state[action_id]["approved_by"] = user
        elif status == ActionStatus.REJECTED:
            self._state[action_id]["rejected_at"] = now
            self._state[action_id]["rejected_by"] = user
            self._state[action_id]["rejection_reason"] = reason
        elif status == ActionStatus.EXECUTED:
            self._state[action_id]["executed_at"] = now
            self._state[action_id]["executed_by"] = user
        elif status == ActionStatus.FAILED:
            self._state[action_id]["failed_at"] = now
            self._state[action_id]["failed_by"] = user

        # Store any extra fields
        for key, value in extra_fields.items():
            self._state[action_id][key] = value

        self._save()
        return self._state[action_id]

    async def delete(self, action_id: str) -> bool:
        """Delete an action from state."""
        if self.use_redis:
            return await self._state.delete(action_id)

        if action_id in self._state:
            del self._state[action_id]
            self._save()
            return True
        return False

    def _load(self):
        """Load state from file."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    self._state = json.load(f)
            except (json.JSONDecodeError, ValueError):
                self._state = {}

    def _save(self):
        """Save state to file."""
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(self._state, f, indent=2, default=str)


class ApprovalHistory:
    """Track history of approval events (similar to AlertHistory)."""

    def __init__(self, max_entries: int = 100):
        self._max_entries = max_entries
        self._entries: list[dict] = []
        self._load()

    async def add(self, event: dict):
        """Add an event to history."""
        self._entries.insert(0, event)
        self._entries = self._entries[: self._max_entries]
        self._save()
        # Best-effort PostgreSQL mirror (review F2); file stays primary
        from app.database.mirror import schedule_mirror, mirror_approval_event
        schedule_mirror(mirror_approval_event(event))

    def get_for_action(self, action_id: str) -> list[dict]:
        """Get all events for a specific action."""
        return [e for e in self._entries if e.get("action_id") == action_id]

    def get_recent(self, limit: int = 20) -> list[dict]:
        """Get recent events."""
        return self._entries[:limit]

    @property
    def entries(self) -> list[dict]:
        """Get all entries."""
        return self._entries.copy()

    def _load(self):
        """Load history from file."""
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE) as f:
                    self._entries = json.load(f)
            except (json.JSONDecodeError, ValueError):
                self._entries = []

    def _save(self):
        """Save history to file."""
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        with open(HISTORY_FILE, "w") as f:
            json.dump(self._entries, f, indent=2, default=str)


# Singleton instances
_approval_tracker: ApprovalStateTracker | None = None
_approval_history: ApprovalHistory | None = None


def get_approval_tracker(use_redis: bool = False) -> ApprovalStateTracker:
    """Get or create the singleton ApprovalStateTracker instance."""
    global _approval_tracker
    if _approval_tracker is None:
        _approval_tracker = ApprovalStateTracker(use_redis=use_redis)
    return _approval_tracker


def get_approval_history(use_redis: bool = False) -> ApprovalHistory:
    """Get or create the singleton ApprovalHistory instance."""
    global _approval_history
    if _approval_history is None:
        if use_redis:

            from app.approvals.redis_store import RedisApprovalHistory
            from app.config import settings

            _, host, port, password = build_redis_url()

            _approval_history = RedisApprovalHistory(
                redis_host=host, redis_port=port, redis_password=password,
                redis_db=settings.REDIS_DB_APPROVALS,
            )
        else:
            _approval_history = ApprovalHistory()
    return _approval_history
