"""Unit tests for ChainMonitor."""

from datetime import datetime
from unittest.mock import Mock

import pytest

from app.actions.chain_monitor import (
    ChainEvent,
    ChainMonitor,
    ChainMonitorConfig,
    audit_chain_event,
    get_chain_monitor,
    log_chain_event,
)


@pytest.fixture(autouse=True)
def reset_chain_monitor():
    """Reset the global chain monitor before each test.

    Must rebind the module attribute -- ``from ... import _chain_monitor``
    creates a local alias, so assigning to it never reset the singleton and
    leaked ``enabled=False`` config into later test files.
    """
    import app.actions.chain_monitor as chain_monitor_module

    chain_monitor_module._chain_monitor = None
    yield
    chain_monitor_module._chain_monitor = None


class TestChainEvent:
    """Test ChainEvent dataclass."""

    def test_chain_event_creation(self):
        """Test creating a ChainEvent."""
        event = ChainEvent(
            event_type="exceeded",
            project="test-project",
            action_type="restart",
            chain_count=3,
            chain_limit=3,
            user="test-user",
        )

        assert event.event_type == "exceeded"
        assert event.project == "test-project"
        assert event.action_type == "restart"
        assert event.chain_count == 3
        assert event.chain_limit == 3
        assert event.user == "test-user"
        assert isinstance(event.timestamp, datetime)


class TestChainMonitorConfig:
    """Test ChainMonitorConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ChainMonitorConfig()

        assert config.enabled is True
        assert config.warning_threshold_ratio == 0.67
        assert config.alert_on_exceed is True
        assert config.alert_on_reset is False
        assert config.include_chain_in_audit is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = ChainMonitorConfig(
            enabled=False,
            warning_threshold_ratio=0.5,
            alert_on_exceed=False,
            alert_on_reset=True,
            include_chain_in_audit=False,
        )

        assert config.enabled is False
        assert config.warning_threshold_ratio == 0.5
        assert config.alert_on_exceed is False
        assert config.alert_on_reset is True
        assert config.include_chain_in_audit is False


class TestChainMonitor:
    """Test ChainMonitor functionality."""

    def test_initial_state(self):
        """Test that chain monitor starts with clean state."""
        monitor = ChainMonitor()

        assert monitor.config.enabled is True
        assert monitor._alert_callback is None
        assert len(monitor._last_warning) == 0

    def test_check_chain_disabled(self):
        """Test that monitoring is disabled when config.enabled=False."""
        config = ChainMonitorConfig(enabled=False)
        monitor = ChainMonitor(config=config)

        event = monitor.check_chain(
            project="test-project",
            action_type="restart",
            chain_count=3,
            chain_limit=3,
        )

        assert event is None

    def test_check_chain_approaching_limit(self):
        """Test that approaching limit triggers warning."""
        mock_callback = Mock()
        monitor = ChainMonitor(alert_callback=mock_callback)

        # Chain at 2/3 (67% threshold with default config)
        event = monitor.check_chain(
            project="test-project",
            action_type="restart",
            chain_count=2,
            chain_limit=3,
        )

        assert event is not None
        assert event.event_type == "approaching"
        assert event.chain_count == 2
        assert event.chain_limit == 3
        mock_callback.assert_called_once()

    def test_check_chain_exceeded(self):
        """Test that exceeded limit triggers alert."""
        mock_callback = Mock()
        monitor = ChainMonitor(alert_callback=mock_callback)

        event = monitor.check_chain(
            project="test-project",
            action_type="restart",
            chain_count=3,
            chain_limit=3,
        )

        assert event is not None
        assert event.event_type == "exceeded"
        assert event.chain_count == 3
        mock_callback.assert_called_once()

    def test_warning_throttling(self):
        """Test that warnings are throttled to avoid spam."""
        mock_callback = Mock()
        monitor = ChainMonitor(alert_callback=mock_callback)

        project = "test-project"
        action_type = "restart"

        # First warning
        event1 = monitor.check_chain(
            project=project,
            action_type=action_type,
            chain_count=2,
            chain_limit=3,
        )
        assert event1 is not None

        # Immediate second check should not trigger warning (throttled)
        event2 = monitor.check_chain(
            project=project,
            action_type=action_type,
            chain_count=2,
            chain_limit=3,
        )
        assert event2 is None
        assert mock_callback.call_count == 1

    def test_exceed_clears_warning(self):
        """Test that exceeding limit clears the warning timestamp."""
        mock_callback = Mock()
        monitor = ChainMonitor(alert_callback=mock_callback)

        project = "test-project"
        action_type = "restart"

        # Trigger warning
        event1 = monitor.check_chain(
            project=project,
            action_type=action_type,
            chain_count=2,
            chain_limit=3,
        )
        assert event1 is not None
        assert event1.event_type == "approaching"

        # Now exceed limit
        event2 = monitor.check_chain(
            project=project,
            action_type=action_type,
            chain_count=3,
            chain_limit=3,
        )
        assert event2 is not None
        assert event2.event_type == "exceeded"

        # Warning timestamp should be cleared
        key = (project, action_type)
        assert key not in monitor._last_warning

    def test_custom_warning_threshold(self):
        """Test custom warning threshold ratio."""
        config = ChainMonitorConfig(warning_threshold_ratio=0.5)  # 50%
        mock_callback = Mock()
        monitor = ChainMonitor(config=config, alert_callback=mock_callback)

        # At 0/3, should not warn yet (below 50% threshold)
        event1 = monitor.check_chain(
            project="test-project",
            action_type="restart",
            chain_count=0,
            chain_limit=3,
        )
        assert event1 is None

        # At 2/3, should warn (above 50% threshold which is floor(1.5) = 1)
        event2 = monitor.check_chain(
            project="test-project",
            action_type="restart",
            chain_count=2,
            chain_limit=3,
        )
        assert event2 is not None

    def test_reset_tracking_specific(self):
        """Test resetting tracking for specific project/action."""
        mock_callback = Mock()
        config = ChainMonitorConfig(alert_on_reset=True)
        monitor = ChainMonitor(config=config, alert_callback=mock_callback)

        # Set some warnings
        monitor.check_chain("project-1", "restart", 2, 3)
        monitor.check_chain("project-2", "scale", 2, 3)

        assert len(monitor._last_warning) == 2

        # Reset only project-1
        monitor.reset_tracking(project="project-1")

        # Only project-2 should remain
        assert len(monitor._last_warning) == 1
        assert ("project-1", "restart") not in monitor._last_warning
        assert ("project-2", "scale") in monitor._last_warning

    def test_reset_tracking_all(self):
        """Test resetting all tracking."""
        mock_callback = Mock()
        config = ChainMonitorConfig(alert_on_reset=True)
        monitor = ChainMonitor(config=config, alert_callback=mock_callback)

        # Set some warnings
        monitor.check_chain("project-1", "restart", 2, 3)
        monitor.check_chain("project-2", "scale", 2, 3)

        assert len(monitor._last_warning) == 2

        # Reset all
        monitor.reset_tracking()

        assert len(monitor._last_warning) == 0

    def test_update_config(self):
        """Test updating configuration."""
        monitor = ChainMonitor()
        assert monitor.config.enabled is True

        new_config = ChainMonitorConfig(enabled=False)
        monitor.update_config(new_config)

        assert monitor.config.enabled is False

    def test_set_alert_callback(self):
        """Test setting alert callback."""
        monitor = ChainMonitor()
        assert monitor._alert_callback is None

        mock_callback = Mock()
        monitor.set_alert_callback(mock_callback)

        assert monitor._alert_callback == mock_callback

    def test_callback_exception_handling(self):
        """Test that callback exceptions are caught and logged."""
        def failing_callback(event):
            raise RuntimeError("Callback failed")

        monitor = ChainMonitor(alert_callback=failing_callback)

        # Should not raise exception
        event = monitor.check_chain(
            project="test-project",
            action_type="restart",
            chain_count=2,
            chain_limit=3,
        )

        # Event should still be returned even if callback failed
        assert event is not None
        assert event.event_type == "approaching"


class TestDefaultHandlers:
    """Test default alert handlers."""

    def test_log_chain_event(self, caplog):
        """Test log_chain_event handler."""
        event = ChainEvent(
            event_type="exceeded",
            project="test-project",
            action_type="restart",
            chain_count=3,
            chain_limit=3,
        )

        with caplog.at_level("WARNING"):
            log_chain_event(event)

        assert "exceeded" in caplog.text.lower()
        assert "test-project" in caplog.text
        assert "restart" in caplog.text

    def test_audit_chain_event_exceeded(self):
        """Test audit_chain_event handler for exceeded event."""
        import os
        import tempfile

        from app.audit.logger import AUDIT_LOG_FILE, _audit_logger, get_audit_logger
        from app.models.audit import AuditEventType

        # Use a temp file for this test
        temp_dir = tempfile.mkdtemp()
        original_log = AUDIT_LOG_FILE
        import app.actions.chain_monitor
        import app.audit.logger
        app.audit.logger.AUDIT_LOG_FILE = os.path.join(temp_dir, "test_audit.json")
        _audit_logger = None  # Reset audit logger

        event = ChainEvent(
            event_type="exceeded",
            project="test-project",
            action_type="restart",
            chain_count=3,
            chain_limit=3,
            user="test-user",
        )

        audit_chain_event(event)

        # Verify audit log entry was created
        audit_logger = get_audit_logger()
        from app.models.audit import AuditLogQuery
        query = audit_logger.query(
            AuditLogQuery(event_types=[AuditEventType.CHAIN_LIMIT_EXCEEDED], limit=1)
        )

        assert query.total >= 1
        entry = query.entries[0]
        assert entry.event_type == AuditEventType.CHAIN_LIMIT_EXCEEDED
        assert entry.project == "test-project"

        # Cleanup
        app.audit.logger.AUDIT_LOG_FILE = original_log
        _audit_logger = None
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_audit_chain_event_approaching(self):
        """Test audit_chain_event handler for approaching event."""
        import os
        import tempfile

        from app.audit.logger import AUDIT_LOG_FILE, _audit_logger, get_audit_logger
        from app.models.audit import AuditEventType, AuditLogQuery

        # Use a temp file for this test
        temp_dir = tempfile.mkdtemp()
        original_log = AUDIT_LOG_FILE
        import app.actions.chain_monitor
        import app.audit.logger
        app.audit.logger.AUDIT_LOG_FILE = os.path.join(temp_dir, "test_audit2.json")
        _audit_logger = None  # Reset audit logger

        event = ChainEvent(
            event_type="approaching",
            project="test-project",
            action_type="restart",
            chain_count=2,
            chain_limit=3,
            user="test-user",
        )

        audit_chain_event(event)

        # Verify audit log entry was created
        audit_logger = get_audit_logger()
        query = audit_logger.query(
            AuditLogQuery(event_types=[AuditEventType.VALIDATION_CHECK], limit=10)
        )

        # Should have at least one validation check entry
        found = False
        for entry in query.entries:
            if entry.details.get("type") == "chain_warning":
                found = True
                assert entry.project == "test-project"
                break

        assert found, "Chain warning audit entry not found"

        # Cleanup
        app.audit.logger.AUDIT_LOG_FILE = original_log
        _audit_logger = None
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


class TestGlobalChainMonitor:
    """Test global chain monitor singleton."""

    def test_singleton(self):
        """Test that get_chain_monitor returns same instance."""
        monitor1 = get_chain_monitor()
        monitor2 = get_chain_monitor()

        assert monitor1 is monitor2

    def test_singleton_with_config(self):
        """Test that config is applied on first call."""
        # Reset the singleton first
        import app.actions.chain_monitor as chain_monitor_module
        chain_monitor_module._chain_monitor = None

        # Pass both config and a simple callback to avoid default handler
        config = ChainMonitorConfig(enabled=False)
        mock_callback = Mock()
        monitor = get_chain_monitor(config=config, alert_callback=mock_callback)

        assert monitor.config.enabled is False

    def test_singleton_with_callback(self):
        """Test that callback is applied on first call."""
        # Reset the singleton first
        import app.actions.chain_monitor as chain_monitor_module
        chain_monitor_module._chain_monitor = None

        mock_callback = Mock()
        monitor = get_chain_monitor(alert_callback=mock_callback)

        # When callback is provided, it should be set directly
        assert monitor._alert_callback == mock_callback

    def test_singleton_default_callback(self):
        """Test that default combined handler is used when no callback provided."""
        # Reset the singleton first
        import app.actions.chain_monitor as chain_monitor_module
        chain_monitor_module._chain_monitor = None

        monitor = get_chain_monitor()

        # Should have the default combined handler
        assert monitor._alert_callback is not None
        assert callable(monitor._alert_callback)
