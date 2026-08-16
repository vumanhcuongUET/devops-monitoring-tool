"""
Unit tests for Alert State Tracker.

Tests the alert state management functionality including:
- Alert state transitions
- Alert history tracking
- State persistence
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


@pytest.mark.unit
@pytest.mark.alerting
class TestAlertStateTracker:
    """Test suite for AlertStateTracker."""

    @pytest.mark.asyncio
    async def test_state_tracker_initialization(self):
        """Test that AlertStateTracker initializes correctly."""
        from app.alerting.state import AlertStateTracker

        tracker = AlertStateTracker()

        assert tracker is not None
        assert tracker.states == {}

    @pytest.mark.asyncio
    async def test_update_state_transitions_to_firing(self):
        """Test that update_state transitions alert to firing state."""
        from app.alerting.state import AlertStateTracker

        tracker = AlertStateTracker()

        tracker.update_state(
            rule_id="test-rule-001",
            state="firing",
            message="Alert condition met"
        )

        assert tracker.states["test-rule-001"]["state"] == "firing"
        assert "message" in tracker.states["test-rule-001"]

    @pytest.mark.asyncio
    async def test_update_state_transitions_to_resolved(self):
        """Test that update_state can transition to resolved state."""
        from app.alerting.state import AlertStateTracker

        tracker = AlertStateTracker()

        # First set to firing
        tracker.update_state(rule_id="test-rule-001", state="firing")

        # Then resolve
        tracker.update_state(
            rule_id="test-rule-001",
            state="resolved",
            message="Condition cleared"
        )

        assert tracker.states["test-rule-001"]["state"] == "resolved"

    @pytest.mark.asyncio
    async def test_get_state_returns_current_state(self):
        """Test that get_state returns current alert state."""
        from app.alerting.state import AlertStateTracker

        tracker = AlertStateTracker()

        tracker.update_state(rule_id="test-rule-001", state="firing")

        state = tracker.get_state(rule_id="test-rule-001")

        assert state is not None
        assert state["state"] == "firing"

    @pytest.mark.asyncio
    async def test_get_state_returns_none_for_unknown_rule(self):
        """Test that get_state returns None for unknown rule ID."""
        from app.alerting.state import AlertStateTracker

        tracker = AlertStateTracker()

        state = tracker.get_state(rule_id="unknown-rule-001")

        assert state is None

    @pytest.mark.asyncio
    async def test_state_includes_timestamp(self):
        """Test that state updates include timestamp."""
        from app.alerting.state import AlertStateTracker

        tracker = AlertStateTracker()

        tracker.update_state(
            rule_id="test-rule-001",
            state="firing"
        )

        state = tracker.get_state(rule_id="test-rule-001")

        assert "timestamp" in state
        assert state["timestamp"] is not None

    @pytest.mark.asyncio
    async def test_multiple_rules_independent_states(self):
        """Test that multiple rules maintain independent states."""
        from app.alerting.state import AlertStateTracker

        tracker = AlertStateTracker()

        tracker.update_state(rule_id="rule-001", state="firing")
        tracker.update_state(rule_id="rule-002", state="resolved")
        tracker.update_state(rule_id="rule-003", state="pending")

        assert tracker.get_state("rule-001")["state"] == "firing"
        assert tracker.get_state("rule-002")["state"] == "resolved"
        assert tracker.get_state("rule-003")["state"] == "pending"


@pytest.mark.unit
@pytest.mark.alerting
class TestAlertHistory:
    """Test suite for AlertHistory."""

    @pytest.mark.asyncio
    async def test_history_initialization(self):
        """Test that AlertHistory initializes correctly."""
        from app.alerting.state import AlertHistory

        history = AlertHistory()

        assert history is not None
        assert history.events == []

    @pytest.mark.asyncio
    async def test_add_event_creates_history_entry(self):
        """Test that add_event creates a history entry."""
        from app.alerting.state import AlertHistory

        history = AlertHistory()

        history.add_event(
            rule_id="test-rule-001",
            event_type="fired",
            message="Alert fired"
        )

        assert len(history.events) == 1
        assert history.events[0]["rule_id"] == "test-rule-001"
        assert history.events[0]["event_type"] == "fired"

    @pytest.mark.asyncio
    async def test_add_event_includes_timestamp(self):
        """Test that add_event includes timestamp in entry."""
        from app.alerting.state import AlertHistory

        history = AlertHistory()

        history.add_event(
            rule_id="test-rule-001",
            event_type="fired"
        )

        assert "timestamp" in history.events[0]

    @pytest.mark.asyncio
    async def test_get_events_filters_by_rule_id(self):
        """Test that get_events can filter by rule ID."""
        from app.alerting.state import AlertHistory

        history = AlertHistory()

        history.add_event(rule_id="rule-001", event_type="fired")
        history.add_event(rule_id="rule-002", event_type="fired")
        history.add_event(rule_id="rule-001", event_type="resolved")

        events = history.get_events(rule_id="rule-001")

        assert len(events) == 2
        assert all(e["rule_id"] == "rule-001" for e in events)

    @pytest.mark.asyncio
    async def test_get_events_with_limit(self):
        """Test that get_events respects limit parameter."""
        from app.alerting.state import AlertHistory

        history = AlertHistory()

        for i in range(10):
            history.add_event(rule_id="test-rule", event_type="fired")

        events = history.get_events(limit=5)

        assert len(events) == 5

    @pytest.mark.asyncio
    async def test_get_events_returns_most_recent_first(self):
        """Test that get_events returns events in descending order."""
        from app.alerting.state import AlertHistory

        history = AlertHistory()

        history.add_event(rule_id="test-rule", event_type="fired")
        history.add_event(rule_id="test-rule", event_type="resolved")

        events = history.get_events(rule_id="test-rule")

        # Most recent should be first
        assert events[0]["event_type"] == "resolved"
