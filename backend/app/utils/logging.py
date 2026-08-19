"""Logging utilities with sensitive data sanitization."""
import logging
import re
from typing import Any, Dict, Optional

# Patterns that might contain sensitive data
SENSITIVE_PATTERNS = [
    (r'--token[s=\s]+[^\s]+', '--token=***'),  # Kubernetes tokens
    (r'--password[s=\s]+[^\s]+', '--password=***'),  # Passwords
    (r'-p\s+[^\s]+', '-p ***'),  # MySQL/PostgreSQL passwords
    (r'Bearer\s+[A-Za-z0-9\._-]+', 'Bearer ***'),  # Bearer tokens
    (r'API[_-]?KEY[s=\s]*[:=]\s*[^\s,]+', 'API_KEY=***'),  # API keys
    (r'SECRET[s=\s]*[:=]\s*[^\s,]+', 'SECRET=***'),  # Secrets
    (r'AUTH[_-]?TOKEN[s=\s]*[:=]\s*[^\s,]+', 'AUTH_TOKEN=***'),  # Auth tokens
    (r'basic\s+[A-Za-z0-9+/=]+', 'basic ***'),  # Basic auth
    (r'elasticsearch://[^@]+@', 'elasticsearch://***@'),  # Elasticsearch URLs
    (r'://[^:]+:[^@]+@', '://***:***@'),  # URLs with credentials
]

# Field names that typically contain sensitive data
SENSITIVE_FIELDS = {
    'password', 'passwd', 'pwd', 'secret', 'token', 'apikey', 'api_key',
    'access_key', 'secret_key', 'auth_token', 'bearer', 'credentials',
    'authorization', 'x-api-key', 'slack_signing_secret', 'webhook_secret',
}


def sanitize_dict(data: Dict[str, Any], mask: str = '***') -> Dict[str, Any]:
    """Recursively sanitize sensitive fields in a dictionary.

    Args:
        data: Dictionary to sanitize
        mask: String to use as replacement mask

    Returns:
        Sanitized dictionary
    """
    if not isinstance(data, dict):
        return data

    sanitized = {}
    for key, value in data.items():
        # Check if key name indicates sensitive data
        if isinstance(key, str) and key.lower() in SENSITIVE_FIELDS:
            sanitized[key] = mask
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value, mask)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_dict(item, mask) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value

    return sanitized


def sanitize_command(command: str) -> str:
    """Sanitize a command string by removing sensitive data.

    Args:
        command: Command string that might contain sensitive data

    Returns:
        Sanitized command string
    """
    sanitized = command
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    return sanitized


def sanitize_log_message(message: Any) -> str:
    """Sanitize a log message by removing sensitive data.

    Args:
        message: Message to sanitize (can be any type)

    Returns:
        Sanitized string representation
    """
    # Convert to string if needed
    if not isinstance(message, str):
        # For dict-like objects, sanitize them
        if isinstance(message, dict):
            message = sanitize_dict(message)
        message = str(message)

    # Apply command sanitization
    return sanitize_command(message)


class SensitiveDataFilter(logging.Filter):
    """Logging filter that sanitizes sensitive data from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter and sanitize log record."""
        # Sanitize the message
        if hasattr(record, 'msg') and record.msg:
            record.msg = sanitize_log_message(record.msg)

        # Sanitize args if present
        if hasattr(record, 'args') and record.args:
            sanitized_args = []
            for arg in record.args:
                sanitized_args.append(sanitize_log_message(arg))
            record.args = tuple(sanitized_args)

        return True


def get_logger(name: str) -> logging.Logger:
    """Get a logger with sensitive data filtering enabled.

    Args:
        name: Logger name

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Only add filter once
    if not any(isinstance(f, SensitiveDataFilter) for f in logger.filters):
        logger.addFilter(SensitiveDataFilter())

    return logger
