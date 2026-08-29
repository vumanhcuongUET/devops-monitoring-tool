"""Unit tests for Feedback Collector (Phase 4)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.feedback.collector import (
    FeedbackCollector,
    FeedbackEvent,
    get_feedback_collector,
)


@pytest.fixture
def temp_storage_path(tmp_path):
    """Create temporary storage path for tests."""
    return tmp_path / "test_feedback.json"


@pytest.fixture
def collector(temp_storage_path):
    """Create FeedbackCollector with temporary storage."""
    return FeedbackCollector(storage_path=str(temp_storage_path))


@pytest.fixture
def sample_event():
    """Create sample feedback event."""
    return FeedbackEvent(
        action_id="kubectl_delete_pod_123",
        event_type="approved",
        timestamp=datetime.now(timezone.utc),
        user="test-user",
        details={"reason": "CrashLoopBackOff detected"},
    )


class TestFeedbackEvent:
    """Test FeedbackEvent data class."""

    def test_feedback_event_creation(self):
        """Test creating a feedback event."""
        event = FeedbackEvent(
            action_id="test-action",
            event_type="approved",
            timestamp=datetime.now(timezone.utc),
            user="user1",
        )

        assert event.action_id == "test-action"
        assert event.event_type == "approved"
        assert event.user == "user1"
        assert event.details == {}

    def test_feedback_event_to_dict(self):
        """Test converting event to dictionary."""
        timestamp = datetime.now(timezone.utc)
        event = FeedbackEvent(
            action_id="test-action",
            event_type="approved",
            timestamp=timestamp,
            user="user1",
            details={"key": "value"},
        )

        event_dict = event.to_dict()

        assert event_dict["action_id"] == "test-action"
        assert event_dict["event_type"] == "approved"
        assert event_dict["timestamp"] == timestamp.isoformat()
        assert event_dict["user"] == "user1"
        assert event_dict["details"] == {"key": "value"}


class TestFeedbackCollector:
    """Test FeedbackCollector functionality."""

    def test_collector_creates_storage_directory(self, temp_storage_path):
        """Test that collector creates storage directory."""
        collector = FeedbackCollector(storage_path=str(temp_storage_path))
        assert temp_storage_path.parent.exists()

    def test_collector_initialization_empty(self, collector):
        """Test collector starts with empty feedback."""
        feedback = collector.get_all_feedback()
        assert feedback == {}

    def test_record_event(self, collector, sample_event):
        """Test recording a feedback event."""
        collector.record_event(sample_event)

        feedback = collector.get_action_feedback(sample_event.action_id)
        assert len(feedback) == 1
        assert feedback[0].action_id == sample_event.action_id
        assert feedback[0].event_type == "approved"

    def test_record_approval(self, collector):
        """Test recording an approval."""
        collector.record_approval(
            action_id="test-action",
            user="user1",
            approval_details={"reason": "Valid fix"},
        )

        feedback = collector.get_action_feedback("test-action")
        assert len(feedback) == 1
        assert feedback[0].event_type == "approved"
        assert feedback[0].user == "user1"
        assert feedback[0].details == {"reason": "Valid fix"}

    def test_record_rejection(self, collector):
        """Test recording a rejection."""
        collector.record_rejection(
            action_id="test-action",
            user="user1",
            reason="Unsafe operation",
        )

        feedback = collector.get_action_feedback("test-action")
        assert len(feedback) == 1
        assert feedback[0].event_type == "rejected"
        assert feedback[0].user == "user1"
        assert feedback[0].details["reason"] == "Unsafe operation"

    def test_record_execution_success(self, collector):
        """Test recording successful execution."""
        collector.record_execution(
            action_id="test-action",
            success=True,
            execution_details={"duration_ms": 1500},
        )

        feedback = collector.get_action_feedback("test-action")
        assert len(feedback) == 1
        assert feedback[0].event_type == "executed"
        assert feedback[0].details["success"] is True
        assert feedback[0].details["duration_ms"] == 1500

    def test_record_execution_failure(self, collector):
        """Test recording failed execution."""
        collector.record_execution(
            action_id="test-action",
            success=False,
            execution_details={"error": "Timeout"},
        )

        feedback = collector.get_action_feedback("test-action")
        assert len(feedback) == 1
        assert feedback[0].event_type == "failed"
        assert feedback[0].details["success"] is False
        assert feedback[0].details["error"] == "Timeout"

    def test_multiple_events_same_action(self, collector):
        """Test recording multiple events for same action."""
        collector.record_approval("test-action", "user1")
        collector.record_execution("test-action", success=True)
        collector.record_approval("test-action", "user2")

        feedback = collector.get_action_feedback("test-action")
        assert len(feedback) == 3
        assert feedback[0].event_type == "approved"
        assert feedback[1].event_type == "executed"
        assert feedback[2].event_type == "approved"

    def test_multiple_different_actions(self, collector):
        """Test recording events for different actions."""
        collector.record_approval("action-1", "user1")
        collector.record_approval("action-2", "user2")
        collector.record_rejection("action-3", "user1", "Test")

        all_feedback = collector.get_all_feedback()
        assert len(all_feedback) == 3
        assert "action-1" in all_feedback
        assert "action-2" in all_feedback
        assert "action-3" in all_feedback

    def test_get_action_feedback_nonexistent(self, collector):
        """Test getting feedback for non-existent action."""
        feedback = collector.get_action_feedback("non-existent")
        assert feedback == []

    def test_persistence_save_and_load(self, temp_storage_path):
        """Test saving and loading feedback from storage."""
        # Create collector and add data
        collector1 = FeedbackCollector(storage_path=str(temp_storage_path))
        collector1.record_approval("action-1", "user1")
        collector1.record_execution("action-1", success=True)

        # Create new collector instance - should load saved data
        collector2 = FeedbackCollector(storage_path=str(temp_storage_path))
        feedback = collector2.get_action_feedback("action-1")

        assert len(feedback) == 2
        assert feedback[0].event_type == "approved"
        assert feedback[1].event_type == "executed"

    def test_get_recent_feedback(self, collector):
        """Test getting recent feedback events."""
        # Add events at different times
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=5)

        old_event = FeedbackEvent("action-1", "approved", old_time, "user1")
        recent_event = FeedbackEvent("action-2", "rejected", recent_time, "user2")

        collector.record_event(old_event)
        collector.record_event(recent_event)

        recent = collector.get_recent_feedback(limit=1)

        assert len(recent) == 1
        assert recent[0].action_id == "action-2"

    def test_get_recent_feedback_filtered_by_type(self, collector):
        """Test filtering recent feedback by event type."""
        collector.record_approval("action-1", "user1")
        collector.record_rejection("action-2", "user1", "Test")
        collector.record_approval("action-3", "user2")

        approved = collector.get_recent_feedback(limit=10, event_type="approved")

        assert len(approved) == 2
        assert all(e.event_type == "approved" for e in approved)

    def test_get_recent_feedback_sorted_by_timestamp(self, collector):
        """Test that recent feedback is sorted by timestamp (newest first)."""
        times = [
            datetime.now(timezone.utc) - timedelta(hours=2),
            datetime.now(timezone.utc) - timedelta(hours=1),
            datetime.now(timezone.utc) - timedelta(minutes=30),
        ]

        for i, time in enumerate(times):
            event = FeedbackEvent(f"action-{i}", "approved", time, "user1")
            collector.record_event(event)

        recent = collector.get_recent_feedback(limit=10)

        # Should be sorted newest first
        assert recent[0].action_id == "action-2"
        assert recent[1].action_id == "action-1"
        assert recent[2].action_id == "action-0"

    def test_load_from_invalid_json(self, temp_storage_path):
        """Test handling of invalid JSON file."""
        # Write invalid JSON
        temp_storage_path.write_text("invalid json content")

        collector = FeedbackCollector(storage_path=str(temp_storage_path))
        # Should not crash, should start with empty feedback
        feedback = collector.get_all_feedback()
        assert feedback == {}

    def test_event_details_preserved(self, collector):
        """Test that event details are preserved."""
        details = {
            "reason": "Production issue",
            "severity": "high",
            "affected_services": ["api", "web"],
        }

        collector.record_approval("action-1", "user1", approval_details=details)

        feedback = collector.get_action_feedback("action-1")
        assert feedback[0].details == details


class TestFeedbackCollectorSingleton:
    """Test singleton pattern."""

    def test_get_feedback_collector_returns_singleton(self, temp_storage_path):
        """Test that get_feedback_collector returns same instance."""
        with patch("app.feedback.collector._collector", None):
            collector1 = get_feedback_collector()
            collector2 = get_feedback_collector()

            assert collector1 is collector2

    def test_get_feedback_collector_initializes_new_instance(self):
        """Test that first call initializes the collector."""

        # Reset singleton
        with patch("app.feedback.collector._collector", None):
            collector = get_feedback_collector()
            assert collector is not None
            assert isinstance(collector, FeedbackCollector)
