"""
Tests for audit logging module.
"""

import json
import tempfile
import time
from pathlib import Path

import pytest

from core.audit import AuditLogEntry, AuditLogger, get_audit_logger, log_event


@pytest.mark.unit
class TestAuditLogEntry:
    """Tests for AuditLogEntry."""

    def test_create_entry(self):
        """Test creating an audit log entry."""
        entry = AuditLogEntry(
            event_type="query",
            actor="user1",
            action="run_query",
            resource="meinvoice",
            status="success",
            details={"timeout": 10},
        )

        assert entry.event_type == "query"
        assert entry.actor == "user1"
        assert entry.action == "run_query"
        assert entry.resource == "meinvoice"
        assert entry.status == "success"
        assert entry.details == {"timeout": 10}
        assert entry.timestamp is not None

    def test_to_dict(self):
        """Test converting entry to dictionary."""
        entry = AuditLogEntry(
            event_type="query",
            actor="user1",
            action="run_query",
        )
        entry_dict = entry.to_dict()

        assert entry_dict["event_type"] == "query"
        assert entry_dict["actor"] == "user1"
        assert entry_dict["action"] == "run_query"
        assert "iso_timestamp" in entry_dict
        assert "timestamp" in entry_dict

    def test_from_dict(self):
        """Test creating entry from dictionary."""
        entry_dict = {
            "event_type": "query",
            "actor": "user1",
            "action": "run_query",
            "resource": "meinvoice",
            "status": "success",
            "details": {"timeout": 10},
            "timestamp": time.time(),
        }

        entry = AuditLogEntry.from_dict(entry_dict)

        assert entry.event_type == "query"
        assert entry.actor == "user1"
        assert entry.action == "run_query"
        assert entry.resource == "meinvoice"


@pytest.mark.unit
class TestAuditLogger:
    """Tests for AuditLogger."""

    def setup_method(self):
        """Create temporary directory for each test."""
        from core.audit import reset_audit_logger
        reset_audit_logger()  # Reset global state

        self.temp_dir = tempfile.mkdtemp()
        self.log_dir = Path(self.temp_dir) / "audit"

    def teardown_method(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_creates_directory(self):
        """Test that initialization creates log directory."""
        _logger = AuditLogger(log_dir=self.log_dir)
        assert self.log_dir.exists()
        assert self.log_dir.is_dir()

    def test_log_entry(self):
        """Test writing an audit log entry."""
        logger = AuditLogger(log_dir=self.log_dir)

        entry = AuditLogEntry(
            event_type="query",
            actor="user1",
            action="run_query",
            resource="meinvoice",
        )

        result = logger.log(entry)

        assert result is True
        assert logger._current_file.exists()

        # Verify file content
        content = logger._current_file.read_text()
        assert content.strip()  # Should have content

    def test_log_multiple_entries(self):
        """Test writing multiple audit log entries."""
        logger = AuditLogger(log_dir=self.log_dir)

        for i in range(5):
            entry = AuditLogEntry(
                event_type="query",
                actor=f"user{i}",
                action="run_query",
                resource=f"project{i}",
            )
            logger.log(entry)

        # Count lines in file
        with open(logger._current_file, "r") as f:
            lines = f.readlines()

        assert len(lines) == 5

    def test_chain_hash_integrity(self):
        """Test that chain hashes are correctly computed."""
        logger = AuditLogger(log_dir=self.log_dir)

        entry1 = AuditLogEntry(event_type="test", actor="user1")
        entry2 = AuditLogEntry(event_type="test", actor="user2")

        logger.log(entry1)
        logger.log(entry2)

        # Read entries back
        with open(logger._current_file, "r") as f:
            lines = f.readlines()

        entry1_data = json.loads(lines[0])
        entry2_data = json.loads(lines[1])

        # Both should have chain hashes
        assert "_chain_hash" in entry1_data
        assert "_chain_hash" in entry2_data

        # Hashes should be different (chained)
        assert entry1_data["_chain_hash"] != entry2_data["_chain_hash"]

    def test_file_rotation(self):
        """Test that file rotation works when max size is reached."""
        logger = AuditLogger(log_dir=self.log_dir, max_file_size=500)

        # Write enough entries to trigger rotation
        # Each entry with large details should be ~300+ bytes
        # With max 500 bytes, rotation should happen after 2-3 entries
        for i in range(10):
            entry = AuditLogEntry(
                event_type="test",
                actor=f"user{i}",
                action=f"action{i}",
                resource=f"resource{i}",
                details={"data": "x" * 200},  # Large entry
            )
            logger.log(entry)

        # Check that multiple files exist
        log_files = list(self.log_dir.glob("audit_*.jsonl"))
        assert len(log_files) >= 2


@pytest.mark.unit
class TestAuditHelpers:
    """Tests for audit helper functions."""

    def setup_method(self):
        """Reset global state before each test."""
        from core.audit import reset_audit_logger
        reset_audit_logger()

    def test_log_event(self):
        """Test log_event convenience function."""
        temp_dir = tempfile.mkdtemp()
        log_dir = Path(temp_dir) / "audit"

        try:
            # Create logger with custom directory and set as global
            from core.audit import AuditLogger, set_global_audit_logger
            logger = AuditLogger(log_dir=log_dir)
            set_global_audit_logger(logger)

            # Use convenience function
            result = log_event(
                event_type="test",
                actor="user1",
                action="test_action",
                resource="test_resource",
            )

            assert result is True

            # Verify entry was written (read the log file directly)
            with open(logger._current_file, "r") as f:
                lines = f.readlines()
            assert len(lines) == 1
            assert json.loads(lines[0])["event_type"] == "test"

        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            _global_audit_logger = None

    def test_get_audit_logger_singleton(self):
        """Test that get_audit_logger returns singleton."""
        from core.audit import _global_audit_logger

        # Reset
        _global_audit_logger = None

        logger1 = get_audit_logger()
        logger2 = get_audit_logger()

        assert logger1 is logger2
