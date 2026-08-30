"""Feedback collection and learning system.

This module tracks action outcomes (approve/reject/success/failure)
to enable continuous learning and confidence improvement.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FeedbackEvent:
    """Represents a feedback event for learning."""

    def __init__(
        self,
        action_id: str,
        event_type: str,
        timestamp: datetime,
        user: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.action_id = action_id
        self.event_type = event_type  # "approved", "rejected", "executed", "failed"
        self.timestamp = timestamp
        self.user = user
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "action_id": self.action_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "user": self.user,
            "details": self.details,
        }


class FeedbackCollector:
    """Collects and stores feedback for continuous learning."""

    def __init__(self, storage_path: str | None = None):
        """Initialize feedback collector.

        Args:
            storage_path: Path to feedback history file (defaults to
                settings.DATA_DIR/feedback_history.json)
        """
        if storage_path is None:
            from app.config import settings

            storage_path = str(Path(settings.DATA_DIR) / "feedback_history.json")
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._feedback: dict[str, list[FeedbackEvent]] = defaultdict(list)
        self._load_feedback()

    def _load_feedback(self):
        """Load feedback history from storage."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)
                for action_id, events in data.items():
                    for event in events:
                        self._feedback[action_id].append(
                            FeedbackEvent(
                                action_id=event["action_id"],
                                event_type=event["event_type"],
                                timestamp=datetime.fromisoformat(event["timestamp"]),
                                user=event.get("user"),
                                details=event.get("details", {}),
                            )
                        )
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to load feedback history: {e}")

    def _save_feedback(self):
        """Save feedback history to storage."""
        try:
            data = {}
            for action_id, events in self._feedback.items():
                data[action_id] = [event.to_dict() for event in events]
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save feedback history: {e}")

    def record_event(self, event: FeedbackEvent):
        """Record a feedback event.

        Args:
            event: Feedback event to record
        """
        self._feedback[event.action_id].append(event)
        self._save_feedback()
        logger.debug(f"Recorded feedback event: {event.event_type} for action {event.action_id}")

    def record_approval(
        self,
        action_id: str,
        user: str,
        approval_details: dict[str, Any] | None = None,
    ):
        """Record an action approval.

        Args:
            action_id: ID of the action that was approved
            user: User who approved
            approval_details: Optional additional details
        """
        event = FeedbackEvent(
            action_id=action_id,
            event_type="approved",
            timestamp=datetime.now(timezone.utc),
            user=user,
            details=approval_details or {},
        )
        self.record_event(event)

    def record_rejection(
        self,
        action_id: str,
        user: str,
        reason: str | None = None,
        rejection_details: dict[str, Any] | None = None,
    ):
        """Record an action rejection.

        Args:
            action_id: ID of the action that was rejected
            user: User who rejected
            reason: Reason for rejection
            rejection_details: Optional additional details
        """
        details = rejection_details or {}
        if reason:
            details["reason"] = reason
        event = FeedbackEvent(
            action_id=action_id,
            event_type="rejected",
            timestamp=datetime.now(timezone.utc),
            user=user,
            details=details,
        )
        self.record_event(event)

    def record_execution(
        self,
        action_id: str,
        success: bool,
        execution_details: dict[str, Any] | None = None,
    ):
        """Record an action execution result.

        Args:
            action_id: ID of the action that was executed
            success: Whether execution was successful
            execution_details: Optional additional details
        """
        details = execution_details or {}
        details["success"] = success
        event = FeedbackEvent(
            action_id=action_id,
            event_type="executed" if success else "failed",
            timestamp=datetime.now(timezone.utc),
            details=details,
        )
        self.record_event(event)

    def get_action_feedback(self, action_id: str) -> list[FeedbackEvent]:
        """Get all feedback events for an action.

        Args:
            action_id: ID of the action

        Returns:
            List of feedback events for the action
        """
        return self._feedback.get(action_id, [])

    def get_all_feedback(self) -> dict[str, list[FeedbackEvent]]:
        """Get all feedback history.

        Returns:
            Dict mapping action_id to list of feedback events
        """
        return dict(self._feedback)

    def get_recent_feedback(
        self,
        limit: int = 100,
        event_type: str | None = None,
    ) -> list[FeedbackEvent]:
        """Get recent feedback events.

        Args:
            limit: Maximum number of events to return
            event_type: Filter by event type (optional)

        Returns:
            List of recent feedback events
        """
        all_events = []
        for events in self._feedback.values():
            all_events.extend(events)

        # Filter by event type if specified
        if event_type:
            all_events = [e for e in all_events if e.event_type == event_type]

        # Sort by timestamp descending
        all_events.sort(key=lambda e: e.timestamp, reverse=True)
        return all_events[:limit]


# Singleton instance
_collector: FeedbackCollector | None = None


def get_feedback_collector() -> FeedbackCollector:
    """Get or create the singleton FeedbackCollector instance.

    Returns:
        FeedbackCollector instance
    """
    global _collector
    if _collector is None:
        _collector = FeedbackCollector()
    return _collector
