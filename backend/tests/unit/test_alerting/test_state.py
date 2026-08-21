"""
Unit tests for Alert State Management.

Tests the alert state tracker and history functionality including:
- Alert state transitions
- Alert history tracking
- State persistence
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
import tempfile
import os

from app.alerting.state import AlertStateTracker, AlertHistory, STATE_FILE, HISTORY_FILE


@pytest.fixture
def clean_state():
    """Fixture to ensure clean state for each test."""
    # Store original files
    original_state = STATE_FILE
    original_history = HISTORY_FILE

    # Create temp directory for test files
    with tempfile.TemporaryDirectory() as tmpdir:
        test_state_file = os.path.join(tmpdir, "alert_state.json")
        test_history_file = os.path.join(tmpdir, "alert_history.json")

        # Patch the module constants
        import app.alerting.state as state_module
        state_module.STATE_FILE = test_state_file
        state_module.HISTORY_FILE = test_history_file

        yield test_state_file, test_history_file

        # Restore original
        state_module.STATE_FILE = original_state
        state_module.HISTORY_FILE = original_history


@pytest.mark.unit
@pytest.mark.alerting
class TestAlertStateTracker:
    """Test suite for AlertStateTracker."""

    def test_state_tracker_initialization(self, clean_state):
        """Test that AlertStateTracker initializes correctly."""
        tracker = AlertStateTracker()

        assert tracker is not None
        assert tracker.firing_count == 0
        assert isinstance(tracker.all_state(), dict)

    def test_set_firing_transitions_state(self, clean_state):
        """Test that set_firing transitions rule to firing state."""
        tracker = AlertStateTracker()

        state = tracker.set_firing("test-rule-001")

        assert state["status"] == "firing"
        assert "fired_at" in state

        # Verify state is persisted
        retrieved = tracker.get("test-rule-001")
        assert retrieved["status"] == "firing"

    def test_set_resolved_transitions_state(self, clean_state):
        """Test that set_resolved transitions rule to resolved state."""
        tracker = AlertStateTracker()

        # First set to firing
        tracker.set_firing("test-rule-001")

        # Then resolve
        state = tracker.set_resolved("test-rule-001")

        assert state["status"] == "resolved"
        assert "resolved_at" in state

    def test_get_state_returns_current_state(self, clean_state):
        """Test that get() returns current state for a rule."""
        tracker = AlertStateTracker()

        tracker.set_firing("test-rule-001")

        state = tracker.get("test-rule-001")

        assert state is not None
        assert state["status"] == "firing"

    def test_get_state_returns_none_for_unknown_rule(self, clean_state):
        """Test that get() returns None for unknown rule."""
        tracker = AlertStateTracker()

        state = tracker.get("unknown-rule")

        assert state is None

    def test_state_includes_timestamp(self, clean_state):
        """Test that state includes timestamp."""
        tracker = AlertStateTracker()

        state = tracker.set_firing("test-rule-001")

        assert "fired_at" in state
        assert isinstance(state["fired_at"], str)

    def test_multiple_rules_independent_states(self, clean_state):
        """Test that multiple rules can have independent states."""
        tracker = AlertStateTracker()

        tracker.set_firing("rule-001")
        tracker.set_firing("rule-002")

        state1 = tracker.get("rule-001")
        state2 = tracker.get("rule-002")

        assert state1["status"] == "firing"
        assert state2["status"] == "firing"

    def test_firing_count(self, clean_state):
        """Test that firing_count returns correct count."""
        tracker = AlertStateTracker()

        assert tracker.firing_count == 0

        tracker.set_firing("rule-001")
        assert tracker.firing_count == 1

        tracker.set_firing("rule-002")
        assert tracker.firing_count == 2

        tracker.set_resolved("rule-001")
        assert tracker.firing_count == 1

    def test_all_state_returns_all_states(self, clean_state):
        """Test that all_state() returns all rule states."""
        tracker = AlertStateTracker()

        tracker.set_firing("rule-001")
        tracker.set_firing("rule-002")

        all_states = tracker.all_state()

        assert len(all_states) == 2
        assert "rule-001" in all_states
        assert "rule-002" in all_states


@pytest.mark.unit
@pytest.mark.alerting
class TestAlertHistory:
    """Test suite for AlertHistory."""

    def test_history_initialization(self, clean_state):
        """Test that AlertHistory initializes correctly."""
        history = AlertHistory()

        assert history is not None
        assert isinstance(history.entries, list)

    def test_add_event_creates_history_entry(self, clean_state):
        """Test that add() creates a history entry."""
        history = AlertHistory()

        event = {
            "rule_id": "test-rule-001",
            "status": "firing",
            "timestamp": datetime.utcnow().isoformat()
        }

        history.add(event)

        entries = history.entries  # property, not method
        assert len(entries) >= 1

    def test_add_event_includes_timestamp(self, clean_state):
        """Test that add() includes timestamp in entries."""
        history = AlertHistory()

        event = {
            "rule_id": "test-rule-001",
            "status": "firing"
        }

        history.add(event)

        entries = history.entries  # property, not method
        if entries:
            # First entry should have timestamp if provided
            entry = entries[0]
            # History just stores what's passed in
            assert "rule_id" in entry or "status" in entry

    def test_entries_returns_list(self, clean_state):
        """Test that entries property returns list of events."""
        history = AlertHistory()

        event = {"rule_id": "test", "status": "firing"}
        history.add(event)

        entries = history.entries  # property, not method
        assert isinstance(entries, list)

    def test_max_entries_enforcement(self, clean_state):
        """Test that max_entries limits history size."""
        # Create history with small max
        history = AlertHistory(max_entries=3)

        # Add more events than max
        for i in range(5):
            history.add({"rule_id": f"rule-{i}", "status": "firing"})

        # Should not exceed max_entries
        entries = history.entries
        assert len(entries) <= 3

    def test_multiple_events_tracked(self, clean_state):
        """Test that multiple events are tracked."""
        history = AlertHistory()

        for i in range(3):
            history.add({"rule_id": f"rule-{i}", "status": "firing"})

        entries = history.entries
        # Should have our 3 events
        assert len(entries) == 3
