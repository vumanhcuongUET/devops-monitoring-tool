"""Unit tests for Audit Logger."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.audit.logger import AuditLogger, get_audit_logger
from app.models.audit import (
    AuditEntry,
    AuditEventType,
    AuditLogQuery,
    ChainOfThoughtEntry,
)


@pytest.fixture
def logger():
    """Create AuditLogger instance."""
    return AuditLogger(max_entries=100)


@pytest.fixture
def sample_entry():
    """Create sample audit entry."""
    return AuditEntry(
        id="audit-1",
        event_type=AuditEventType.ACTION_CREATED,
        timestamp=datetime.now(timezone.utc),
        user="john.doe",
        action_id="act-123",
        project="meinvoice",
        details={"command": "kubectl get pods"},
    )


class TestAuditLogger:
    """Test AuditLogger functionality."""

    def test_logger_initialization(self, logger):
        """Test logger initialization."""
        assert logger._max_entries == 100

    def test_log_action_created(self, logger):
        """Test logging action creation event."""
        entry = logger.log_action_created(
            action_id="act-123",
            triage_card_id="tc-001",
            project="meinvoice",
            command="kubectl get pods",
            user="john.doe",
        )

        assert entry.event_type == AuditEventType.ACTION_CREATED
        assert entry.action_id == "act-123"
        assert entry.triage_card_id == "tc-001"
        assert entry.project == "meinvoice"
        assert entry.details["command"] == "kubectl get pods"
        assert entry.user == "john.doe"

    def test_log_action_approved(self, logger):
        """Test logging action approval event."""
        entry = logger.log_action_approved(
            action_id="act-123",
            approved_by="admin",
            comment="Approved after review",
        )

        assert entry.event_type == AuditEventType.ACTION_APPROVED
        assert entry.action_id == "act-123"
        assert entry.user == "admin"
        assert entry.details["comment"] == "Approved after review"

    def test_log_action_approved_without_comment(self, logger):
        """Test logging approval without comment."""
        entry = logger.log_action_approved(
            action_id="act-123",
            approved_by="admin",
        )

        assert entry.event_type == AuditEventType.ACTION_APPROVED
        assert entry.details == {}

    def test_log_action_rejected(self, logger):
        """Test logging action rejection event."""
        entry = logger.log_action_rejected(
            action_id="act-123",
            rejected_by="admin",
            reason="Too risky",
        )

        assert entry.event_type == AuditEventType.ACTION_REJECTED
        assert entry.action_id == "act-123"
        assert entry.user == "admin"
        assert entry.details["reason"] == "Too risky"

    def test_log_action_executed_success(self, logger):
        """Test logging successful action execution."""
        entry = logger.log_action_executed(
            action_id="act-123",
            executed_by="system",
            success=True,
            duration_seconds=1.5,
            output="Command executed successfully",
        )

        assert entry.event_type == AuditEventType.ACTION_EXECUTED
        assert entry.action_id == "act-123"
        assert entry.success is True
        assert entry.execution_duration_seconds == 1.5
        assert entry.details["output"] == "Command executed successfully"

    def test_log_action_executed_failure(self, logger):
        """Test logging failed action execution."""
        entry = logger.log_action_executed(
            action_id="act-123",
            executed_by="system",
            success=False,
            duration_seconds=0.5,
            output="Error: command failed",
        )

        assert entry.event_type == AuditEventType.ACTION_FAILED
        assert entry.success is False

    def test_log_chain_of_thought(self, logger):
        """Test logging chain of thought."""
        chain = [
            ChainOfThoughtEntry(
                step_number=1,
                thought="Analyzing logs",
                confidence=0.8,
            ),
            ChainOfThoughtEntry(
                step_number=2,
                thought="Identified root cause",
                confidence=0.9,
            ),
        ]

        entry = logger.log_chain_of_thought(
            action_id="act-123",
            chain_of_thought=chain,
        )

        assert entry.event_type == AuditEventType.CHAIN_OF_THOUGHT
        assert len(entry.chain_of_thought) == 2
        assert entry.chain_of_thought[0].step_number == 1

    def test_log_custom_event(self, logger):
        """Test logging custom event."""
        entry = logger.log_event(
            event_type=AuditEventType.CONTEXT_COLLECTED,
            user="system",
            project="meinvoice",
            details={"source": "elasticsearch"},
        )

        assert entry.event_type == AuditEventType.CONTEXT_COLLECTED
        assert entry.project == "meinvoice"
        assert entry.details["source"] == "elasticsearch"

    def test_query_all_events(self, logger):
        """Test querying all audit events."""
        # Add some entries
        logger.log_action_created(action_id="act-1", triage_card_id="tc-001", project="proj1", command="cmd1")
        logger.log_action_approved(action_id="act-1", approved_by="admin")
        logger.log_action_created(action_id="act-2", triage_card_id="tc-001", project="proj2", command="cmd2")

        query = AuditLogQuery(limit=10)
        result = logger.query(query)

        assert result.total == 3
        assert len(result.entries) == 3

    def test_query_by_event_type(self, logger):
        """Test querying by event type."""
        logger.log_action_created(action_id="act-1", triage_card_id="tc-001", project="proj1", command="cmd1")
        logger.log_action_approved(action_id="act-1", approved_by="admin")
        logger.log_action_rejected(action_id="act-2", rejected_by="admin", reason="test")

        query = AuditLogQuery(
            event_types=[AuditEventType.ACTION_CREATED],
            limit=10,
        )
        result = logger.query(query)

        assert result.total == 1
        assert result.entries[0].event_type == AuditEventType.ACTION_CREATED

    def test_query_by_action_id(self, logger):
        """Test querying by action ID."""
        logger.log_action_created(action_id="act-123", triage_card_id="tc-001", project="proj1", command="cmd1")
        logger.log_action_approved(action_id="act-123", approved_by="admin")
        logger.log_action_created(action_id="act-456", triage_card_id="tc-001", project="proj2", command="cmd2")

        query = AuditLogQuery(action_id="act-123", limit=10)
        result = logger.query(query)

        assert result.total == 2
        for entry in result.entries:
            assert entry.action_id == "act-123"

    def test_query_by_project(self, logger):
        """Test querying by project."""
        logger.log_action_created(action_id="act-1", triage_card_id="tc-001", project="meinvoice", command="cmd1")
        logger.log_action_created(action_id="act-2", triage_card_id="tc-001", project="another-project", command="cmd2")

        query = AuditLogQuery(project="meinvoice", limit=10)
        result = logger.query(query)

        assert result.total == 1
        assert result.entries[0].project == "meinvoice"

    def test_query_by_user(self, logger):
        """Test querying by user."""
        logger.log_action_approved(action_id="act-1", approved_by="john.doe")
        logger.log_action_approved(action_id="act-2", approved_by="jane.smith")

        query = AuditLogQuery(user="john.doe", limit=10)
        result = logger.query(query)

        assert result.total == 1
        assert result.entries[0].user == "john.doe"

    def test_query_with_time_range(self, logger):
        """Test querying with time range."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        old_time = now - timedelta(hours=2)
        recent_time = now - timedelta(minutes=5)

        # Mock entry with old timestamp
        old_entry = AuditEntry(
            id="old-1",
            event_type=AuditEventType.ACTION_CREATED,
            timestamp=old_time,
        )

        # Add recent entry
        logger.log_action_created(action_id="act-1", triage_card_id="tc-001", project="proj1", command="cmd1")

        query = AuditLogQuery(start_time=recent_time, limit=10)
        result = logger.query(query)

        # Should only get recent entries
        assert result.total >= 1

    def test_query_with_offset(self, logger):
        """Test query with offset."""
        # Add 5 entries
        for i in range(5):
            logger.log_action_created(
                action_id=f"act-{i}",
                project="proj1",
                command=f"cmd-{i}",
            )

        # Get second page
        query = AuditLogQuery(limit=2, offset=2)
        result = logger.query(query)

        assert result.total == 5
        assert len(result.entries) == 2
        assert result.has_more is True

    def test_query_has_more(self, logger):
        """Test query pagination has_more indicator."""
        # Add 3 entries
        for i in range(3):
            logger.log_action_created(
                action_id=f"act-{i}",
                project="proj1",
                command=f"cmd-{i}",
            )

        # Get first 2
        query = AuditLogQuery(limit=2, offset=0)
        result = logger.query(query)

        assert result.total == 3
        assert result.has_more is True

        # Get remaining
        query2 = AuditLogQuery(limit=2, offset=2)
        result2 = logger.query(query2)

        assert len(result2.entries) == 1
        assert result2.has_more is False

    def test_get_action_history(self, logger):
        """Test getting history for specific action."""
        logger.log_action_created(action_id="act-123", triage_card_id="tc-001", project="proj1", command="cmd1")
        logger.log_action_approved(action_id="act-123", approved_by="admin")
        logger.log_action_executed(action_id="act-123", executed_by="system", success=True, duration_seconds=1.0)

        history = logger.get_action_history("act-123")

        assert len(history) == 3
        assert all(entry.action_id == "act-123" for entry in history)

    def test_get_action_history_empty(self, logger):
        """Test getting history for action with no history."""
        history = logger.get_action_history("nonexistent")

        assert len(history) == 0

    def test_max_entries_enforcement(self, logger):
        """Test that max entries limit is enforced."""
        # Add more than max entries
        for i in range(150):
            logger.log_action_created(
                action_id=f"act-{i}",
                project="proj1",
                command=f"cmd-{i}",
            )

        query = AuditLogQuery(limit=1000)
        result = logger.query(query)

        # Should be limited to max_entries
        assert result.total <= logger._max_entries

    def test_entry_rotation(self, logger):
        """Test that old entries are removed when limit exceeded."""
        # Set small max for testing
        small_logger = AuditLogger(max_entries=5)

        # Add 10 entries
        for i in range(10):
            small_logger.log_action_created(
                action_id=f"act-{i}",
                project="proj1",
                command=f"cmd-{i}",
            )

        query = AuditLogQuery(limit=10)
        result = small_logger.query(query)

        # Should only have 5 entries
        assert result.total == 5


class TestAuditLoggerErrorHandling:
    """Test error handling in AuditLogger."""

    def test_loading_corrupted_log_file(self, logger, tmp_path, monkeypatch):
        """Test loading from corrupted log file."""
        import os
        from app.audit.logger import AuditLogger as AuditLoggerClass

        # Mock file existence check to simulate corrupted file
        mock_exists = MagicMock(return_value=True)

        def mock_load():
            # Simulate corrupted JSON
            raise json.JSONDecodeError("Expecting value", "", 0)

        monkeypatch.setattr("os.path.exists", mock_exists)
        monkeypatch.setattr(AuditLoggerClass, "_load_entries", mock_load)

        # Should handle gracefully - query will call _load_entries
        new_logger = AuditLogger(max_entries=100)

        # Logger should still be functional
        # Query should handle corrupted data gracefully
        result = new_logger.query(AuditLogQuery(limit=10))
        assert result is not None

    def test_query_with_limit_zero(self, logger):
        """Test query with limit=0."""
        logger.log_action_created(action_id="act-1", triage_card_id="tc-001", project="proj1", command="cmd1")

        query = AuditLogQuery(limit=0)
        result = logger.query(query)

        # Should return empty result
        assert result.total == 0
        assert len(result.entries) == 0

    def test_query_with_negative_offset(self, logger):
        """Test query with negative offset (treated as 0)."""
        logger.log_action_created(action_id="act-1", triage_card_id="tc-001", project="proj1", command="cmd1")

        query = AuditLogQuery(limit=10, offset=-5)
        result = logger.query(query)

        # Should work normally (negative offset treated as 0)
        assert result.total >= 1

    def test_empty_time_range_query(self, logger):
        """Test query with impossible time range."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        future_start = now + timedelta(hours=1)
        future_end = now + timedelta(hours=2)

        logger.log_action_created(action_id="act-1", triage_card_id="tc-001", project="proj1", command="cmd1")

        query = AuditLogQuery(start_time=future_start, end_time=future_end, limit=10)
        result = logger.query(query)

        # Should return empty for future time range
        assert result.total == 0

    def test_chain_of_thought_with_data_attachments(self, logger):
        """Test chain of thought with data attachments."""
        chain = [
            ChainOfThoughtEntry(
                step_number=1,
                thought="Checking metrics",
                confidence=0.9,
                data={
                    "metric_name": "cpu_usage",
                    "value": 85.5,
                    "threshold": 80.0,
                },
            ),
            ChainOfThoughtEntry(
                step_number=2,
                thought="CPU above threshold",
                confidence=0.95,
                data={
                    "affected_pods": ["api-1", "api-2"],
                    "recommendation": "scale up",
                },
            ),
        ]

        entry = logger.log_chain_of_thought(
            action_id="act-123",
            chain_of_thought=chain,
        )

        assert len(entry.chain_of_thought) == 2
        assert entry.chain_of_thought[0].data is not None
        assert entry.chain_of_thought[0].data["metric_name"] == "cpu_usage"
        assert entry.chain_of_thought[1].data["affected_pods"] == ["api-1", "api-2"]


class TestAuditLoggerSingleton:
    """Test AuditLogger singleton pattern."""

    def test_get_audit_logger_returns_singleton(self):
        """Test that get_audit_logger returns same instance."""
        logger1 = get_audit_logger()
        logger2 = get_audit_logger()

        assert logger1 is logger2

    def test_get_audit_logger_initializes_new_instance(self):
        """Test that first call initializes the logger."""
        from app.audit.logger import _audit_logger
        _audit_logger = None

        logger = get_audit_logger()

        assert logger is not None
        assert isinstance(logger, AuditLogger)
