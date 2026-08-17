"""Approval store for tracking action approval state (similar to AlertStateTracker)."""

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from app.models.actions import Action, ActionStatus

STATE_FILE = "data/approval_state.json"
HISTORY_FILE = "data/approval_history.json"


class ApprovalStateTracker:
    """Track approval state for actions (similar to AlertStateTracker)."""

    def __init__(self):
        self._state: dict[str, dict[str, Any]] = {}
        self._ws_manager = None
        self._load()

    def set_ws_manager(self, manager):
        """Set the WebSocket manager for real-time updates."""
        self._ws_manager = manager

    async def broadcast_status(self, action_id: str, status: ActionStatus):
        """Broadcast status change via WebSocket."""
        if self._ws_manager:
            import json
            await self._ws_manager.broadcast({
                "type": "approval_status_changed",
                "data": {
                    "action_id": action_id,
                    "status": status,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })

    def get(self, action_id: str) -> Optional[dict[str, Any]]:
        """Get state for a specific action."""
        return self._state.get(action_id)

    def get_all(self) -> dict[str, dict[str, Any]]:
        """Get all action states."""
        return self._state.copy()

    def get_by_status(self, status: ActionStatus) -> list[str]:
        """Get all action IDs with a specific status."""
        return [
            action_id
            for action_id, state in self._state.items()
            if state.get("status") == status
        ]

    def get_pending_count(self) -> int:
        """Get count of pending actions."""
        return len(self.get_by_status(ActionStatus.PENDING))

    def set_status(
        self,
        action_id: str,
        status: ActionStatus,
        user: Optional[str] = None,
        reason: Optional[str] = None,
        command: Optional[str] = None,
        **extra_fields,
    ) -> dict[str, Any]:
        """Set the status of an action."""
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

    def delete(self, action_id: str) -> bool:
        """Delete an action from state."""
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
            json.dump(self._state, f, indent=2)


class ApprovalHistory:
    """Track history of approval events (similar to AlertHistory)."""

    def __init__(self, max_entries: int = 100):
        self._max_entries = max_entries
        self._entries: list[dict] = []
        self._load()

    def add(self, event: dict):
        """Add an event to history."""
        self._entries.insert(0, event)
        self._entries = self._entries[: self._max_entries]
        self._save()

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
            json.dump(self._entries, f, indent=2)


# Singleton instances
_approval_tracker: Optional[ApprovalStateTracker] = None
_approval_history: Optional[ApprovalHistory] = None


def get_approval_tracker() -> ApprovalStateTracker:
    """Get or create the singleton ApprovalStateTracker instance."""
    global _approval_tracker
    if _approval_tracker is None:
        _approval_tracker = ApprovalStateTracker()
    return _approval_tracker


def get_approval_history() -> ApprovalHistory:
    """Get or create the singleton ApprovalHistory instance."""
    global _approval_history
    if _approval_history is None:
        _approval_history = ApprovalHistory()
    return _approval_history
