"""
Structured logging configuration for AI Assistant.

Provides JSON-formatted logs with context tracking, credential sanitization,
and metrics collection.
"""

import json
import logging
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Optional, List
from threading import local

# Thread-local storage for request context
_context = local()


@dataclass
class LogContext:
    """Context for log correlation."""
    request_id: Optional[str] = None
    project: Optional[str] = None
    section: Optional[str] = None
    user: Optional[str] = None


def get_log_context() -> LogContext:
    """Get current log context."""
    return getattr(_context, "value", LogContext())


def set_log_context(**kwargs):
    """Set log context values."""
    current = get_log_context()
    for key, value in kwargs.items():
        if hasattr(current, key):
            setattr(current, key, value)
    _context.value = current


@contextmanager
def log_context(**kwargs):
    """Context manager for log context."""
    old_context = get_log_context()
    new_context = LogContext(**{**old_context.__dict__, **kwargs})
    _context.value = new_context
    try:
        yield
    finally:
        _context.value = old_context


class CredentialSanitizer:
    """Sanitizes sensitive data in logs."""

    SENSITIVE_KEYS = {
        "password", "passwd", "pwd", "secret", "token", "api_key",
        "apikey", "authorization", "auth", "credential", "Bearer"
    }

    SENSITIVE_PATTERNS = [
        ("Basic ", "***REDACTED***"),
        ("Bearer ", "***REDACTED***"),
        ("sk-ant-", "***KEY-REDACTED***"),
    ]

    @classmethod
    def sanitize_dict(cls, data: Dict[str, Any], max_depth: int = 10) -> Dict[str, Any]:
        """
        Recursively sanitize sensitive keys in dictionary.

        Args:
            data: Dictionary to sanitize
            max_depth: Maximum recursion depth

        Returns:
            Sanitized dictionary
        """
        if max_depth <= 0:
            return {"***TRUNCATED***": "max depth exceeded"}

        result = {}
        for key, value in data.items():
            # Check if key is sensitive
            if any(sensitive in key.lower() for sensitive in cls.SENSITIVE_KEYS):
                result[key] = "***REDACTED***"
            elif isinstance(value, dict):
                result[key] = cls.sanitize_dict(value, max_depth - 1)
            elif isinstance(value, list):
                result[key] = [
                    cls.sanitize_dict(item, max_depth - 1) if isinstance(item, dict) else item
                    for item in value
                ]
            elif isinstance(value, str):
                # Check for sensitive patterns
                result[key] = cls.sanitize_string(value)
            else:
                result[key] = value
        return result

    @classmethod
    def sanitize_string(cls, value: str) -> str:
        """Sanitize sensitive patterns in string."""
        result = value
        for pattern, replacement in cls.SENSITIVE_PATTERNS:
            result = result.replace(pattern, replacement)
        return result


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Base log data
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add context
        context = get_log_context()
        if context.request_id:
            log_data["request_id"] = context.request_id
        if context.project:
            log_data["project"] = context.project
        if context.section:
            log_data["section"] = context.section

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields from record
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data, default=str)


class MetricsCollector:
    """Simple metrics collector for monitoring."""

    def __init__(self):
        self._counters: Dict[str, int] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = {}
        self._lock = local()

    def increment(self, name: str, value: int = 1, labels: Optional[Dict[str, str]] = None):
        """Increment a counter metric."""
        key = self._make_key(name, labels)
        self._counters[key] = self._counters.get(key, 0) + value

    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Set a gauge metric value."""
        key = self._make_key(name, labels)
        self._gauges[key] = value

    def observe(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Observe a value for histogram metric."""
        key = self._make_key(name, labels)
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)

    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """Create metric key from name and labels."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def get_metrics(self) -> Dict[str, Any]:
        """Get all current metrics."""
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                k: {
                    "count": len(v),
                    "sum": sum(v),
                    "min": min(v) if v else 0,
                    "max": max(v) if v else 0,
                    "avg": sum(v) / len(v) if v else 0
                }
                for k, v in self._histograms.items()
            }
        }

    def reset(self):
        """Reset all metrics."""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()


# Global metrics instance
_metrics: MetricsCollector = None


def get_metrics() -> MetricsCollector:
    """Get global metrics collector."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


def setup_logging(
    level: int = logging.INFO,
    json_output: bool = True,
    log_file: Optional[Path] = None
) -> logging.Logger:
    """
    Setup logging for AI Assistant.

    Args:
        level: Logging level (default: INFO)
        json_output: Whether to output JSON logs
        log_file: Optional file path for log output

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("ai_assistant")
    logger.setLevel(level)

    # Remove existing handlers
    logger.handlers.clear()

    # Console handler
    if json_output:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)

    return logger


def track_time(metric_name: str, labels: Optional[Dict[str, str]] = None):
    """
    Decorator to track function execution time.

    Args:
        metric_name: Name of the metric
        labels: Optional labels for the metric

    Example:
        @track_time("elasticsearch_query_duration", {"source": "production"})
        def query_elk(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                get_metrics().observe(f"{metric_name}_duration_seconds", duration, labels)
                get_metrics().increment(f"{metric_name}_total", labels=labels)
                return result
            except Exception as _e:
                duration = time.time() - start_time
                get_metrics().observe(f"{metric_name}_duration_seconds", duration, labels)
                get_metrics().increment(f"{metric_name}_errors", labels=labels)
                raise
        return wrapper
    return decorator


def track_counter(metric_name: str, labels: Optional[Dict[str, str]] = None):
    """
    Decorator to track function call count.

    Args:
        metric_name: Name of the metric
        labels: Optional labels for the metric
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            get_metrics().increment(metric_name, labels=labels)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def get_logger(name: str = "ai_assistant") -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)


def log_with_context(logger: logging.Logger, level: int, msg: str, **extra_fields):
    """Log with extra context fields."""
    extra = {"extra_fields": extra_fields}
    logger.log(level, msg, extra=extra)


# Convenience functions
def log_debug(msg: str, **kwargs):
    """Log at DEBUG level with optional context."""
    get_logger().debug(msg, extra={"extra_fields": kwargs})


def log_info(msg: str, **kwargs):
    """Log at INFO level with optional context."""
    get_logger().info(msg, extra={"extra_fields": kwargs})


def log_warning(msg: str, **kwargs):
    """Log at WARNING level with optional context."""
    get_logger().warning(msg, extra={"extra_fields": kwargs})


def log_error(msg: str, **kwargs):
    """Log at ERROR level with optional context."""
    get_logger().error(msg, extra={"extra_fields": kwargs}, exc_info=kwargs.pop("exc_info", False))
