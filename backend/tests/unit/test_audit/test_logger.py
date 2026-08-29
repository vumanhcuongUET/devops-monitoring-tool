"""Unit tests for AuditLogger."""

import os

import pytest

from app.audit.logger import (
    AUDIT_LOG_FILE,
    AuditLogger,
    get_audit_logger,
)
from app.models.audit import (
    AuditEventType,
    AuditLogQuery,
    ChainOfThoughtEntry,
)


@pytest.fixture
def temp_audit_log(tmp_path):
    """Create a temporary audit log file."""
    original_log = AUDIT_LOG_FILE
    # Override the AUDIT_LOG_FILE for this test
    import app.audit.logger
    app.audit.logger.AUDIT_LOG_FILE = str(tmp_path / "test_audit.json")

    yield

    # Clean up
    app.audit.logger.AUDIT_LOG_FILE = original_log
    if os.path.exists(str(tmp_path / "test_audit.json")):
        os.remove(str(tmp_path / "test_audit.json"))


@pytest.fixture
def reset_audit_logger():
    """Reset the global audit logger before each test."""
    global _audit_logger
    from app.audit.logger import _audit_logger
    _audit_logger = None
    yield
    _audit_logger = None


class TestAuditLogger:
    """Test AuditLogger functionality."""

    def test_initial_state(self, temp_audit_log, reset_audit_logger):
        """Test that audit logger starts with clean state."""
        logger = get_audit_logger()
        assert logger is not None

        # Query should return empty results
        query = AuditLogQuery(limit=10)
        response = logger.query(query)
        assert response.total == 0
        assert len(response.entries) == 0

    def test_log_action_created(self, temp_audit_log, reset_audit_logger):
        """Test logging action creation."""
        logger = get_audit_logger()

        entry = logger.log_action_created(
            action_id="action-123",
            triage_card_id="card-456",
            project="test-project",
            command="kubectl restart pod xyz",
            user="test-user",
        )

        assert entry.event_type == AuditEventType.ACTION_CREATED
        assert entry.action_id == "action-123"
        assert entry.project == "test-project"
        assert entry.user == "test-user"
        assert entry.details["command"] == "kubectl restart pod xyz"

        # Verify it was persisted
        query = AuditLogQuery(limit=10)
        response = logger.query(query)
        assert response.total == 1
        assert response.entries[0].event_type == AuditEventType.ACTION_CREATED

    def test_log_action_approved(self, temp_audit_log, reset_audit_logger):
        """Test logging action approval."""
        logger = get_audit_logger()

        entry = logger.log_action_approved(
            action_id="action-123",
            approved_by="admin",
            comment="Looks good",
        )

        assert entry.event_type == AuditEventType.ACTION_APPROVED
        assert entry.action_id == "action-123"
        assert entry.user == "admin"
        assert entry.details["comment"] == "Looks good"

    def test_log_action_rejected(self, temp_audit_log, reset_audit_logger):
        """Test logging action rejection."""
        logger = get_audit_logger()

        entry = logger.log_action_rejected(
            action_id="action-123",
            rejected_by="admin",
            reason="Too risky",
        )

        assert entry.event_type == AuditEventType.ACTION_REJECTED
        assert entry.action_id == "action-123"
        assert entry.user == "admin"
        assert entry.details["reason"] == "Too risky"

    def test_log_action_executed(self, temp_audit_log, reset_audit_logger):
        """Test logging action execution."""
        logger = get_audit_logger()

        entry = logger.log_action_executed(
            action_id="action-123",
            executed_by="system",
            success=True,
            duration_seconds=5.2,
            output="Pod restarted successfully",
        )

        assert entry.event_type == AuditEventType.ACTION_EXECUTED
        assert entry.action_id == "action-123"
        assert entry.user == "system"
        assert entry.success is True
        assert entry.execution_duration_seconds == 5.2
        assert entry.details["output"] == "Pod restarted successfully"

    def test_log_action_failed(self, temp_audit_log, reset_audit_logger):
        """Test logging action failure."""
        logger = get_audit_logger()

        entry = logger.log_action_executed(
            action_id="action-123",
            executed_by="system",
            success=False,
            duration_seconds=2.1,
            output="Error: pod not found",
        )

        assert entry.event_type == AuditEventType.ACTION_FAILED
        assert entry.success is False

    def test_log_chain_of_thought(self, temp_audit_log, reset_audit_logger):
        """Test logging Chain of Thought."""
        logger = get_audit_logger()

        chain = [
            ChainOfThoughtEntry(
                step_number=1,
                thought="Need to restart the pod",
                confidence=0.9,
            ),
            ChainOfThoughtEntry(
                step_number=2,
                thought="Pod is in CrashLoopBackOff state",
                data={"status": "CrashLoopBackOff"},
                confidence=0.95,
            ),
        ]

        entry = logger.log_chain_of_thought(
            action_id="action-123",
            chain_of_thought=chain,
        )

        assert entry.event_type == AuditEventType.CHAIN_OF_THOUGHT
        assert len(entry.chain_of_thought) == 2
        assert entry.chain_of_thought[0].step_number == 1

    def test_log_chain_limit_exceeded(self, temp_audit_log, reset_audit_logger):
        """Test logging chain limit exceeded event."""
        logger = get_audit_logger()

        entry = logger.log_chain_limit_exceeded(
            action_id="action-123",
            project="test-project",
            action_type="restart",
            chain_count=3,
            chain_limit=3,
            user="test-user",
        )

        assert entry.event_type == AuditEventType.CHAIN_LIMIT_EXCEEDED
        assert entry.action_id == "action-123"
        assert entry.project == "test-project"
        assert entry.user == "test-user"
        assert entry.details["chain_count"] == 3
        assert entry.details["chain_limit"] == 3
        assert "Action chain limit reached" in entry.details["message"]

    def test_log_rate_limit_exceeded(self, temp_audit_log, reset_audit_logger):
        """Test logging rate limit exceeded event."""
        logger = get_audit_logger()

        entry = logger.log_rate_limit_exceeded(
            action_id="action-123",
            project="test-project",
            action_type="restart",
            rate_limit=3,
            user="test-user",
        )

        assert entry.event_type == AuditEventType.RATE_LIMIT_EXCEEDED
        assert entry.project == "test-project"
        assert entry.details["rate_limit"] == 3
        assert "Rate limit exceeded" in entry.details["message"]

    def test_log_cooldown_active(self, temp_audit_log, reset_audit_logger):
        """Test logging cooldown active event."""
        logger = get_audit_logger()

        entry = logger.log_cooldown_active(
            action_id="action-123",
            project="test-project",
            action_type="restart",
            cooldown_remaining=45,
            user="test-user",
        )

        assert entry.event_type == AuditEventType.COOLDOWN_ACTIVE
        assert entry.project == "test-project"
        assert entry.details["cooldown_remaining_seconds"] == 45
        assert "Cooldown active" in entry.details["message"]

    def test_query_by_action_id(self, temp_audit_log, reset_audit_logger):
        """Test querying logs by action ID."""
        logger = get_audit_logger()

        # Log multiple actions
        logger.log_action_created("action-1", "card-1", "proj-a", "cmd1")
        logger.log_action_approved("action-1", "admin")
        logger.log_action_created("action-2", "card-2", "proj-b", "cmd2")

        # Query by action_id
        query = AuditLogQuery(action_id="action-1", limit=10)
        response = logger.query(query)

        assert response.total == 2
        assert all(e.action_id == "action-1" for e in response.entries)

    def test_query_by_project(self, temp_audit_log, reset_audit_logger):
        """Test querying logs by project."""
        logger = get_audit_logger()

        logger.log_action_created("action-1", "card-1", "proj-a", "cmd1")
        logger.log_action_created("action-2", "card-2", "proj-b", "cmd2")
        logger.log_action_created("action-3", "card-3", "proj-a", "cmd3")

        query = AuditLogQuery(project="proj-a", limit=10)
        response = logger.query(query)

        assert response.total == 2
        assert all(e.project == "proj-a" for e in response.entries)

    def test_query_by_event_type(self, temp_audit_log, reset_audit_logger):
        """Test querying logs by event type."""
        logger = get_audit_logger()

        logger.log_action_created("action-1", "card-1", "proj-a", "cmd1")
        logger.log_action_created("action-2", "card-2", "proj-b", "cmd2")
        logger.log_chain_limit_exceeded("action-3", "proj-a", "restart", 3, 3)

        query = AuditLogQuery(
            event_types=[AuditEventType.ACTION_CREATED],
            limit=10
        )
        response = logger.query(query)

        assert response.total == 2
        assert all(e.event_type == AuditEventType.ACTION_CREATED for e in response.entries)

    def test_query_pagination(self, temp_audit_log, reset_audit_logger):
        """Test query pagination."""
        logger = get_audit_logger()

        # Log 5 actions
        for i in range(5):
            logger.log_action_created(f"action-{i}", f"card-{i}", "proj-a", f"cmd{i}")

        # First page
        query1 = AuditLogQuery(limit=2, offset=0)
        response1 = logger.query(query1)
        assert response1.total == 5
        assert len(response1.entries) == 2
        assert response1.has_more is True

        # Second page
        query2 = AuditLogQuery(limit=2, offset=2)
        response2 = logger.query(query2)
        assert len(response2.entries) == 2
        assert response2.has_more is True

        # Third page (last item)
        query3 = AuditLogQuery(limit=2, offset=4)
        response3 = logger.query(query3)
        assert len(response3.entries) == 1
        assert response3.has_more is False

    def test_get_action_history(self, temp_audit_log, reset_audit_logger):
        """Test getting action history."""
        logger = get_audit_logger()

        logger.log_action_created("action-1", "card-1", "proj-a", "cmd1")
        logger.log_action_approved("action-1", "admin")
        logger.log_action_executed("action-1", "system", True, 5.0)

        history = logger.get_action_history("action-1")

        assert len(history) == 3
        events = [e.event_type for e in history]
        assert AuditEventType.ACTION_CREATED in events
        assert AuditEventType.ACTION_APPROVED in events
        assert AuditEventType.ACTION_EXECUTED in events

    def test_max_entries_rotation(self, temp_audit_log, reset_audit_logger):
        """Test that log rotates when max entries is reached."""
        # Create logger with small max
        logger = AuditLogger(max_entries=3)

        # Log 5 actions
        for i in range(5):
            logger.log_action_created(f"action-{i}", f"card-{i}", "proj-a", f"cmd{i}")

        # Should only have 3 entries (most recent)
        query = AuditLogQuery(limit=10)
        response = logger.query(query)

        assert response.total == 3
        action_ids = [e.action_id for e in response.entries]
        assert "action-4" in action_ids  # Most recent
        assert "action-3" in action_ids
        assert "action-2" in action_ids
        assert "action-1" not in action_ids  # Rotated out
        assert "action-0" not in action_ids  # Rotated out


class TestGlobalAuditLogger:
    """Test global audit logger singleton."""

    def test_singleton(self, temp_audit_log, reset_audit_logger):
        """Test that get_audit_logger returns same instance."""
        logger1 = get_audit_logger()
        logger2 = get_audit_logger()

        assert logger1 is logger2
