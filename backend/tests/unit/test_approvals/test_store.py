"""Unit tests for Approval Store."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.approvals.store import ApprovalStateTracker, get_approval_tracker
from app.models.actions import ActionStatus


@pytest.fixture
def mock_ws_manager():
    """Mock WebSocket manager."""
    manager = AsyncMock()
    manager.broadcast = AsyncMock()
    return manager


@pytest.fixture
def tracker():
    """Create ApprovalStateTracker instance."""
    return ApprovalStateTracker()


class TestApprovalStateTracker:
    """Test ApprovalStateTracker functionality."""

    def test_tracker_initialization(self, tracker):
        """Test tracker initialization."""
        assert tracker._state == {}
        assert tracker._history == []

    def test_set_status(self, tracker):
        """Test setting action status."""
        tracker.set_status(
            action_id="act-123",
            status=ActionStatus.PENDING,
            user="john.doe",
        )

        state = tracker.get("act-123")
        assert state is not None
        assert state["status"] == ActionStatus.PENDING
        assert state["updated_by"] == "john.doe"
        assert "updated_at" in state

    def test_set_status_with_command(self, tracker):
        """Test setting status with command context."""
        tracker.set_status(
            action_id="act-123",
            status=ActionStatus.APPROVED,
            command="kubectl get pods",
        )

        state = tracker.get("act-123")
        assert state["status"] == ActionStatus.APPROVED
        assert state["command"] == "kubectl get pods"

    def test_set_status_overwrites_existing(self, tracker):
        """Test that set_status overwrites existing state."""
        tracker.set_status(action_id="act-123", status=ActionStatus.PENDING)
        tracker.set_status(
            action_id="act-123",
            status=ActionStatus.APPROVED,
            user="admin",
        )

        state = tracker.get("act-123")
        assert state["status"] == ActionStatus.APPROVED
        assert state["updated_by"] == "admin"

    def test_get_action_exists(self, tracker):
        """Test getting existing action."""
        tracker.set_status(action_id="act-123", status=ActionStatus.PENDING)

        result = tracker.get("act-123")

        assert result is not None
        assert result["id"] == "act-123"

    def test_get_action_not_exists(self, tracker):
        """Test getting non-existent action."""
        result = tracker.get("nonexistent")

        assert result is None

    def test_get_all(self, tracker):
        """Test getting all actions."""
        tracker.set_status(action_id="act-1", status=ActionStatus.PENDING)
        tracker.set_status(action_id="act-2", status=ActionStatus.APPROVED)
        tracker.set_status(action_id="act-3", status=ActionStatus.REJECTED)

        all_state = tracker.get_all()

        assert len(all_state) == 3
        assert "act-1" in all_state
        assert "act-2" in all_state
        assert "act-3" in all_state

    def test_get_all_empty(self, tracker):
        """Test getting all actions when empty."""
        all_state = tracker.get_all()

        assert len(all_state) == 0
        assert all_state == {}

    def test_get_by_status(self, tracker):
        """Test getting actions by status."""
        tracker.set_status(action_id="act-1", status=ActionStatus.PENDING)
        tracker.set_status(action_id="act-2", status=ActionStatus.PENDING)
        tracker.set_status(action_id="act-3", status=ActionStatus.APPROVED)

        pending = tracker.get_by_status(ActionStatus.PENDING)
        approved = tracker.get_by_status(ActionStatus.APPROVED)

        assert len(pending) == 2
        assert "act-1" in pending
        assert "act-2" in pending
        assert len(approved) == 1
        assert "act-3" in approved

    def test_get_by_status_empty(self, tracker):
        """Test getting actions by status when none match."""
        tracker.set_status(action_id="act-1", status=ActionStatus.PENDING)

        approved = tracker.get_by_status(ActionStatus.APPROVED)

        assert len(approved) == 0

    def test_get_pending_count(self, tracker):
        """Test getting count of pending actions."""
        tracker.set_status(action_id="act-1", status=ActionStatus.PENDING)
        tracker.set_status(action_id="act-2", status=ActionStatus.PENDING)
        tracker.set_status(action_id="act-3", status=ActionStatus.APPROVED)

        count = tracker.get_pending_count()

        assert count == 2

    def test_get_pending_count_zero(self, tracker):
        """Test getting pending count when none pending."""
        tracker.set_status(action_id="act-1", status=ActionStatus.APPROVED)

        count = tracker.get_pending_count()

        assert count == 0

    def test_delete_action_exists(self, tracker):
        """Test deleting existing action."""
        tracker.set_status(action_id="act-123", status=ActionStatus.PENDING)

        result = tracker.delete("act-123")

        assert result is True
        assert tracker.get("act-123") is None

    def test_delete_action_not_exists(self, tracker):
        """Test deleting non-existent action."""
        result = tracker.delete("nonexistent")

        assert result is False

    def test_set_ws_manager(self, tracker, mock_ws_manager):
        """Test setting WebSocket manager."""
        tracker.set_ws_manager(mock_ws_manager)

        assert tracker._ws_manager == mock_ws_manager

    @pytest.mark.asyncio
    async def test_broadcast_status_with_ws_manager(
        self, tracker, mock_ws_manager
    ):
        """Test broadcasting status with WebSocket manager."""
        tracker.set_ws_manager(mock_ws_manager)

        await tracker.broadcast_status("act-123", ActionStatus.APPROVED)

        mock_ws_manager.broadcast.assert_called_once()
        call_args = mock_ws_manager.broadcast.call_args
        assert "type" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_broadcast_status_without_ws_manager(self, tracker):
        """Test broadcasting status without WebSocket manager."""
        # Should not raise exception
        await tracker.broadcast_status("act-123", ActionStatus.APPROVED)

    def test_persistence_to_file(self, tracker, tmp_path):
        """Test state persistence to file."""
        import os

        # Set state file to temp directory
        from app.approvals.store import STATE_FILE
        original_file = STATE_FILE
        test_file = tmp_path / "test_state.json"

        # Monkey patch the STATE_FILE
        import app.approvals.store as store_module
        store_module.STATE_FILE = str(test_file)

        try:
            tracker.set_status(action_id="act-123", status=ActionStatus.PENDING)
            tracker._save()  # Save to temp file

            # Verify file created
            assert os.path.exists(test_file)

            # Load and verify content
            import json
            with open(test_file) as f:
                data = json.load(f)
                assert "act-123" in data
                assert data["act-123"]["status"] == ActionStatus.PENDING

        finally:
            # Restore original
            store_module.STATE_FILE = original_file
            if os.path.exists(test_file):
                os.remove(test_file)

    def test_loading_from_file(self, tracker, tmp_path):
        """Test loading state from file."""
        import json
        import os

        # Create test state file
        test_file = tmp_path / "test_load_state.json"
        test_data = {
            "act-456": {
                "id": "act-456",
                "status": ActionStatus.APPROVED,
                "updated_at": "2026-08-18T10:00:00Z",
            }
        }

        with open(test_file, "w") as f:
            json.dump(test_data, f)

        # Monkey patch STATE_FILE
        from app.approvals.store import STATE_FILE
        import app.approvals.store as store_module
        original_file = STATE_FILE
        store_module.STATE_FILE = str(test_file)

        try:
            new_tracker = ApprovalStateTracker()
            new_tracker._load()

            # Verify loaded state
            state = new_tracker.get("act-456")
            assert state is not None
            assert state["status"] == ActionStatus.APPROVED

        finally:
            store_module.STATE_FILE = original_file
            if os.path.exists(test_file):
                os.remove(test_file)


class TestApprovalHistory:
    """Test ApprovalHistory functionality."""

    @pytest.fixture
    def tracker(self):
        """Create tracker for history testing."""
        from app.approvals.store import ApprovalHistory
        return ApprovalHistory()

    def test_add_history_entry(self, tracker):
        """Test adding history entry."""
        entry = {
            "id": "hist-1",
            "action_id": "act-123",
            "event": "approved",
            "timestamp": "2026-08-18T10:00:00Z",
            "user": "john.doe",
        }

        tracker.add(entry)

        history = tracker.get_history("act-123")
        assert len(history) == 1
        assert history[0]["event"] == "approved"

    def test_get_history_for_action(self, tracker):
        """Test getting history for specific action."""
        tracker.add({
            "id": "hist-1",
            "action_id": "act-123",
            "event": "created",
        })
        tracker.add({
            "id": "hist-2",
            "action_id": "act-123",
            "event": "approved",
        })
        tracker.add({
            "id": "hist-3",
            "action_id": "act-456",
            "event": "created",
        })

        history_123 = tracker.get_history("act-123")
        history_456 = tracker.get_history("act-456")

        assert len(history_123) == 2
        assert len(history_456) == 1

    def test_get_history_empty(self, tracker):
        """Test getting history for action with no history."""
        history = tracker.get_history("nonexistent")

        assert len(history) == 0

    def test_get_all_history(self, tracker):
        """Test getting all history."""
        tracker.add({"id": "1", "action_id": "act-1", "event": "created"})
        tracker.add({"id": "2", "action_id": "act-2", "event": "created"})

        all_history = tracker.get_all_history()

        assert len(all_history) == 2

    def test_history_max_entries(self, tracker):
        """Test history max entries limit."""
        from app.approvals.store import MAX_HISTORY_ENTRIES

        # Add more than max entries
        for i in range(MAX_HISTORY_ENTRIES + 10):
            tracker.add({
                "id": f"hist-{i}",
                "action_id": f"act-{i}",
                "event": "created",
            })

        all_history = tracker.get_all_history()

        # Should be limited to max entries
        assert len(all_history) <= MAX_HISTORY_ENTRIES


class TestApprovalTrackerSingleton:
    """Test ApprovalTracker singleton pattern."""

    def test_get_approval_tracker_returns_singleton(self):
        """Test that get_approval_tracker returns same instance."""
        tracker1 = get_approval_tracker()
        tracker2 = get_approval_tracker()

        assert tracker1 is tracker2

    def test_get_approval_tracker_initializes_new_instance(self):
        """Test that first call initializes the tracker."""
        from app.approvals.store import _approval_tracker
        _approval_tracker = None

        tracker = get_approval_tracker()

        assert tracker is not None
        assert isinstance(tracker, ApprovalStateTracker)
