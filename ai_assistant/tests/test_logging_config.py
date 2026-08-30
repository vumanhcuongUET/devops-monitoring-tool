"""
Tests for logging_config module.
"""

import pytest
import logging

from core.logging_config import (
    get_log_context,
    set_log_context,
    log_context,
    CredentialSanitizer,
    MetricsCollector,
    setup_logging,
)


@pytest.mark.unit
class TestLogContext:
    """Tests for log context management."""

    def test_get_log_context_default(self):
        """Test default log context."""
        context = get_log_context()
        assert context.request_id is None
        assert context.project is None

    def test_set_log_context(self):
        """Test setting log context."""
        set_log_context(project="test", section="errors")
        context = get_log_context()
        assert context.project == "test"
        assert context.section == "errors"

    def test_log_context_manager(self):
        """Test log context as context manager."""
        set_log_context(project="outer")
        with log_context(project="inner"):
            context = get_log_context()
            assert context.project == "inner"
        context = get_log_context()
        assert context.project == "outer"  # Restored


@pytest.mark.unit
class TestCredentialSanitizer:
    """Tests for credential sanitization."""

    def test_sanitize_dict_with_password(self):
        """Test sanitization of password field."""
        data = {"username": "user", "password": "secret123"}
        result = CredentialSanitizer.sanitize_dict(data)
        assert result["username"] == "user"
        assert result["password"] == "***REDACTED***"

    def test_sanitize_dict_nested(self):
        """Test sanitization of nested dictionaries."""
        data = {
            "config": {
                "api_key": "secret-key",
                "timeout": 30
            }
        }
        result = CredentialSanitizer.sanitize_dict(data)
        assert result["config"]["api_key"] == "***REDACTED***"
        assert result["config"]["timeout"] == 30

    def test_sanitize_dict_with_list(self):
        """Test sanitization of list items."""
        data = {
            "servers": [
                {"name": "srv1", "token": "tok1"},
                {"name": "srv2", "token": "tok2"}
            ]
        }
        result = CredentialSanitizer.sanitize_dict(data)
        assert result["servers"][0]["token"] == "***REDACTED***"
        assert result["servers"][0]["name"] == "srv1"

    def test_sanitize_string_with_basic_auth(self):
        """Test sanitization of Basic auth in string."""
        result = CredentialSanitizer.sanitize_string("Authorization: Basic dGVzdDpwYXNz")
        assert "***REDACTED***" in result
        assert "Basic " not in result

    def test_sanitize_string_with_bearer_token(self):
        """Test sanitization of Bearer token in string."""
        result = CredentialSanitizer.sanitize_string("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
        assert "***REDACTED***" in result
        assert "Bearer " not in result

    def test_sanitize_string_with_api_key(self):
        """Test sanitization of API key pattern."""
        result = CredentialSanitizer.sanitize_string("sk-ant-api03-1234567890")
        assert "***KEY-REDACTED***" in result
        assert "sk-ant-" not in result


@pytest.mark.unit
class TestMetricsCollector:
    """Tests for metrics collector."""

    def test_counter_increment(self):
        """Test counter increment."""
        metrics = MetricsCollector()
        metrics.increment("test_counter")
        assert metrics._counters["test_counter"] == 1

        metrics.increment("test_counter", value=5)
        assert metrics._counters["test_counter"] == 6

    def test_counter_with_labels(self):
        """Test counter with labels."""
        metrics = MetricsCollector()
        metrics.increment("test_counter", labels={"status": "ok"})
        assert "test_counter{status=ok}" in metrics._counters

    def test_gauge_set(self):
        """Test gauge setting."""
        metrics = MetricsCollector()
        metrics.set_gauge("test_gauge", 42.5)
        assert metrics._gauges["test_gauge"] == 42.5

    def test_histogram_observe(self):
        """Test histogram observation."""
        metrics = MetricsCollector()
        metrics.observe("test_histogram", 1.0)
        metrics.observe("test_histogram", 2.0)
        metrics.observe("test_histogram", 3.0)

        assert len(metrics._histograms["test_histogram"]) == 3

    def test_get_metrics(self):
        """Test getting all metrics."""
        metrics = MetricsCollector()
        metrics.increment("counter1")
        metrics.set_gauge("gauge1", 10.0)
        metrics.observe("hist1", 5.0)

        all_metrics = metrics.get_metrics()
        assert "counters" in all_metrics
        assert "gauges" in all_metrics
        assert "histograms" in all_metrics
        assert all_metrics["counters"]["counter1"] == 1

    def test_histogram_stats(self):
        """Test histogram statistics calculation."""
        metrics = MetricsCollector()
        for i in [1, 2, 3, 4, 5]:
            metrics.observe("test_hist", float(i))

        all_metrics = metrics.get_metrics()
        hist_stats = all_metrics["histograms"]["test_hist"]
        assert hist_stats["count"] == 5
        assert hist_stats["sum"] == 15.0
        assert hist_stats["min"] == 1.0
        assert hist_stats["max"] == 5.0
        assert hist_stats["avg"] == 3.0

    def test_reset(self):
        """Test resetting metrics."""
        metrics = MetricsCollector()
        metrics.increment("counter1")
        metrics.reset()
        assert len(metrics._counters) == 0
        assert len(metrics._gauges) == 0
        assert len(metrics._histograms) == 0


@pytest.mark.unit
class TestSetupLogging:
    """Tests for logging setup."""

    def test_setup_logging_creates_logger(self):
        """Test that setup_logging creates a logger."""
        logger = setup_logging(level=logging.DEBUG)
        assert logger.name == "ai_assistant"
        assert logger.level == logging.DEBUG

    def test_setup_logging_adds_handlers(self):
        """Test that setup_logging adds handlers."""
        logger = setup_logging()
        assert len(logger.handlers) > 0

    def test_get_logger(self):
        """Test getting logger instance."""
        from core.logging_config import get_logger
        logger = get_logger("test_logger")
        assert logger.name == "test_logger"
