"""
Security utilities for AI Assistant.

Provides rate limiting, input validation, and security checks.
"""

import hashlib
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from functools import wraps
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class RateLimitResult:
    """Result of rate limit check."""
    allowed: bool
    remaining: int
    reset_time: Optional[float] = None
    retry_after: Optional[float] = None


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter.

    Refills tokens at a constant rate. Allows bursts up to capacity.
    Thread-safe implementation.
    """

    def __init__(self, rate: float = 10.0, capacity: int = 100):
        """
        Initialize rate limiter.

        Args:
            rate: Tokens per second refill rate
            capacity: Maximum bucket capacity (burst size)
        """
        self._rate = rate
        self._capacity = capacity
        self._tokens: Dict[str, float] = defaultdict(lambda: capacity)
        self._last_update: Dict[str, float] = defaultdict(lambda: time.time())
        self._lock = Lock()

    def _refill(self, key: str, now: float):
        """Refill tokens for a key based on elapsed time."""
        elapsed = now - self._last_update[key]
        # Add tokens based on elapsed time, capped at capacity
        self._tokens[key] = min(
            self._capacity,
            self._tokens[key] + elapsed * self._rate
        )
        self._last_update[key] = now

    def check(self, key: str, tokens: int = 1) -> RateLimitResult:
        """
        Check if request is allowed.

        Args:
            key: Identifier to rate limit (e.g., IP, user, source)
            tokens: Number of tokens required

        Returns:
            RateLimitResult with allowed status and metadata
        """
        now = time.time()

        with self._lock:
            self._refill(key, now)

            if self._tokens[key] >= tokens:
                self._tokens[key] -= tokens
                return RateLimitResult(
                    allowed=True,
                    remaining=int(self._tokens[key]),
                    reset_time=now + (self._capacity - self._tokens[key]) / self._rate
                )
            else:
                # Calculate retry after
                retry_after = (tokens - self._tokens[key]) / self._rate
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    retry_after=retry_after
                )

    def reset(self, key: str):
        """Reset rate limit for a key."""
        with self._lock:
            self._tokens[key] = self._capacity
            self._last_update[key] = time.time()


class InputValidator:
    """Validates input for security and safety."""

    # Dangerous patterns that could indicate injection attempts
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # XSS
        r'javascript:',  # JavaScript URI
        r'on\w+\s*=',  # Event handlers
        r'<\?php',  # PHP tags
        r'\$\{.*\}',  # Template injection
        r'\${.*}',  # Shell variable expansion
        r'vbscript:',  # VBScript URI
        r'data:',  # Data URI (potential XSS)
    ]

    # Max lengths for various inputs
    MAX_LENGTHS = {
        "project_name": 100,
        "section_name": 100,
        "time_range": 50,
        "index_pattern": 500,
        "query_body": 10000,  # 10KB max for query body
        "promql_query": 2000,
    }

    @classmethod
    def validate_project_name(cls, name: str) -> Tuple[bool, Optional[str]]:
        """
        Validate project name.

        Args:
            name: Project name to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not name:
            return False, "Project name cannot be empty"

        if len(name) > cls.MAX_LENGTHS["project_name"]:
            return False, f"Project name too long (max {cls.MAX_LENGTHS['project_name']} chars)"

        # Only allow alphanumeric, hyphens, underscores
        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            return False, "Project name can only contain letters, numbers, hyphens, and underscores"

        return True, None

    @classmethod
    def validate_section_name(cls, name: str) -> Tuple[bool, Optional[str]]:
        """Validate section name."""
        if not name:
            return False, "Section name cannot be empty"

        if len(name) > cls.MAX_LENGTHS["section_name"]:
            return False, f"Section name too long (max {cls.MAX_LENGTHS['section_name']} chars)"

        # Only allow alphanumeric, hyphens, underscores (same as project names)
        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            return False, "Section name can only contain letters, numbers, hyphens, and underscores"

        return True, None

    @classmethod
    def validate_time_range(cls, time_range: str) -> Tuple[bool, Optional[str]]:
        """Validate time range format."""
        if not time_range:
            return False, "Time range cannot be empty"

        if len(time_range) > cls.MAX_LENGTHS["time_range"]:
            return False, f"Time range too long (max {cls.MAX_LENGTHS['time_range']} chars)"

        # Validate format: now-<duration> or now
        if time_range != "now" and not re.match(r'^now-\d+[smhd]$', time_range):
            return False, "Invalid time range format (use: now or now-<number><s|m|h|d>)"

        return True, None

    @classmethod
    def validate_query_body(cls, body: Any) -> Tuple[bool, Optional[str]]:
        """Validate query body size and content."""
        if not isinstance(body, dict):
            return False, "Query body must be a dictionary"

        body_str = str(body)
        if len(body_str) > cls.MAX_LENGTHS["query_body"]:
            return False, f"Query body too large (max {cls.MAX_LENGTHS['query_body']} chars)"

        return True, None

    @classmethod
    def validate_promql(cls, promql: str) -> Tuple[bool, Optional[str]]:
        """Validate PromQL query."""
        if not promql:
            return False, "PromQL query cannot be empty"

        if len(promql) > cls.MAX_LENGTHS["promql_query"]:
            return False, f"PromQL query too long (max {cls.MAX_LENGTHS['promql_query']} chars)"

        # Check for dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, promql, re.IGNORECASE):
                return False, f"PromQL contains potentially dangerous pattern: {pattern}"

        return True, None

    @classmethod
    def sanitize_url(cls, url: str) -> str:
        """
        Sanitize URL for logging.

        Removes query parameters and fragments.
        """
        # Remove query parameters and fragment
        sanitized = re.sub(r'[?].*', '', url)
        # Remove potential credentials
        sanitized = re.sub(r'://[^@]*@', '://***@', sanitized)
        return sanitized

    @classmethod
    def validate_url(cls, url: str, allow_credentials: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Validate URL for safety.

        Args:
            url: URL to validate
            allow_credentials: Whether to allow embedded credentials

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not url:
            return False, "URL cannot be empty"

        # Max URL length
        if len(url) > 2000:
            return False, "URL too long (max 2000 chars)"

        # Check for dangerous patterns
        dangerous = [
            r'<script[^>]*>',  # XSS
            r'javascript:',  # JavaScript URI
            r'data:',  # Data URI (potential XSS)
            r'vbscript:',  # VBScript
        ]
        url_lower = url.lower()
        for pattern in dangerous:
            if re.search(pattern, url_lower):
                return False, f"URL contains dangerous pattern: {pattern}"

        # Only allow http/https protocols
        if not url_lower.startswith(('http://', 'https://')):
            return False, "URL must use http:// or https:// protocol"

        # Check for credentials if not allowed
        if not allow_credentials and '://' in url:
            # Extract host part
            after_proto = url.split('://', 1)[1] if '://' in url else ''
            if '@' in after_proto.split('/')[0]:
                return False, "URL must not contain embedded credentials"

        return True, None

    @classmethod
    def validate_template_content(cls, template: str, max_length: int = 10000) -> Tuple[bool, Optional[str]]:
        """
        Validate template content for safety.

        Args:
            template: Template string to validate
            max_length: Maximum allowed template length

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(template, str):
            return False, "Template must be a string"

        if len(template) > max_length:
            return False, f"Template too long (max {max_length} chars)"

        # Check for dangerous injection patterns
        injection_patterns = [
            (r'<\?php', 'PHP tags'),
            (r'<\s*script', 'Script tags'),
            (r'<\?\=', 'PHP short echo'),
            (r'<\s*%\s*@?', 'JSP tags'),
            (r'\$\{', 'Variable expression'),
            (r'`[^`]*`', 'Command substitution'),
        ]

        for pattern, name in injection_patterns:
            if re.search(pattern, template, re.IGNORECASE):
                return False, f"Template contains potentially dangerous {name}"

        # Check for excessive nested brackets (potential DoS)
        depth = 0
        max_depth = 20
        for char in template:
            if char == '{':
                depth += 1
                if depth > max_depth:
                    return False, f"Template nesting too deep (max {max_depth})"
            elif char == '}':
                depth -= 1

        return True, None


class SecurityHeaders:
    """Security headers for HTTP requests."""

    REQUIRED_HEADERS = {
        "Content-Type": "application/json",
    }

    @classmethod
    def validate_headers(cls, headers: Dict[str, str]) -> Tuple[bool, List[str]]:
        """
        Validate request headers.

        Args:
            headers: Headers dictionary

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Check Content-Type
        content_type = headers.get("Content-Type", "")
        if "json" not in content_type.lower() and "application" in content_type.lower():
            errors.append("Content-Type should be application/json for JSON payloads")

        return len(errors) == 0, errors


def rate_limit(rate: float = 10.0, capacity: int = 100, key_func: Optional[Callable] = None):
    """
    Decorator for rate limiting function calls.

    Args:
        rate: Requests per second
        capacity: Burst capacity
        key_func: Function to extract rate limit key from arguments

    Example:
        @rate_limit(rate=5.0, capacity=10)
        def expensive_api_call():
            ...
    """
    limiter = TokenBucketRateLimiter(rate, capacity)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract key for rate limiting
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                key = func.__name__

            result = limiter.check(key)
            if not result.allowed:
                from core.logging_config import get_logger, get_metrics
                get_logger().warning("Rate limit exceeded", key=key, retry_after=result.retry_after)
                get_metrics().increment("rate_limit_exceeded_total", labels={"key": key})
                raise Exception(f"Rate limit exceeded. Retry after {result.retry_after:.1f}s")

            return func(*args, **kwargs)
        return wrapper
    return decorator


def validate_input(validator: Callable, error_message: str = "Invalid input"):
    """
    Decorator for input validation.

    Args:
        validator: Validation function that returns (is_valid, error_msg)
        error_message: Default error message

    Example:
        @validate_input(InputValidator.validate_project_name, "Invalid project")
        def process_project(project_name):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Find the first string argument (usually the input to validate)
            input_value = None
            for arg in args:
                if isinstance(arg, str):
                    input_value = arg
                    break

            if input_value is None:
                input_value = kwargs.get("input")

            if input_value is not None:
                is_valid, error = validator(input_value)
                if not is_valid:
                    from core.logging_config import get_logger, get_metrics
                    get_logger().warning("Input validation failed", input=input_value[:50], error=error)
                    get_metrics().increment("validation_failed_total", labels={"validator": validator.__name__})
                    raise ValueError(f"{error_message}: {error}")

            return func(*args, **kwargs)
        return wrapper
    return decorator


# Global rate limiter instances
_global_rate_limiters: Dict[str, TokenBucketRateLimiter] = {}


def get_rate_limiter(name: str = "default", rate: float = 10.0, capacity: int = 100) -> TokenBucketRateLimiter:
    """Get or create a rate limiter instance."""
    if name not in _global_rate_limiters:
        _global_rate_limiters[name] = TokenBucketRateLimiter(rate, capacity)
    return _global_rate_limiters[name]


def check_rate_limit(
    identifier: str,
    rate: float = 10.0,
    capacity: int = 100,
    limiter_name: str = "default"
) -> RateLimitResult:
    """
    Check rate limit for an identifier.

    Args:
        identifier: Unique identifier (IP, user, source name, etc.)
        rate: Requests per second
        capacity: Burst capacity
        limiter_name: Name of rate limiter to use

    Returns:
        RateLimitResult
    """
    limiter = get_rate_limiter(limiter_name, rate, capacity)
    return limiter.check(identifier)
