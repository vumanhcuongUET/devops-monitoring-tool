"""
Retry logic with exponential backoff and circuit breaker.

Provides decorators and utilities for resilient service calls.
"""

import time
import threading
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union
from dataclasses import dataclass
from enum import Enum

T = TypeVar("T")


# Lazy imports to avoid circular dependency
def _get_logger():
    from core.logging_config import get_logger
    return get_logger(__name__)


def _get_metrics():
    from core.logging_config import get_metrics
    return get_metrics()


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Failing, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes to close circuit
    timeout_seconds: int = 60   # How long to stay open


class CircuitBreaker:
    """
    Circuit breaker for failing services.

    Prevents cascading failures by blocking requests to a service
    that is consistently failing.
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ):
        """
        Initialize circuit breaker.

        Args:
            name: Circuit breaker identifier
            config: Configuration (uses defaults if not provided)
        """
        self._name = name
        self._config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current state."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Get failure count."""
        return self._failure_count

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self._last_failure_time is None:
            return True
        return time.time() - self._last_failure_time >= self._config.timeout_seconds

    def record_success(self):
        """Record a successful call."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    _get_logger().info(f"Circuit breaker closed name={self._name}")
                    _get_metrics().increment("circuit_breaker_closed", labels={"name": self._name})
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    def record_failure(self):
        """Record a failed call."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Immediately reopen
                self._state = CircuitState.OPEN
                _get_logger().warning(f"Circuit breaker reopened name={self._name}")
                _get_metrics().increment("circuit_breaker_reopened", labels={"name": self._name})
            elif self._failure_count >= self._config.failure_threshold:
                self._state = CircuitState.OPEN
                _get_logger().warning(f"Circuit breaker opened name={self._name} failures={self._failure_count}")
                _get_metrics().increment("circuit_breaker_opened", labels={"name": self._name})

    def allow_request(self) -> bool:
        """
        Check if request should be allowed.

        Returns:
            True if request should proceed, False if blocked
        """
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    _get_logger().info(f"Circuit breaker half-open name={self._name}")
                    _get_metrics().increment("circuit_breaker_half_open", labels={"name": self._name})
                    return True
                return False

            # HALF_OPEN - allow limited requests
            return True

    def stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        with self._lock:
            return {
                "name": self._name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "last_failure_time": self._last_failure_time
            }


# Global circuit breaker registry
_circuit_breakers: Dict[str, CircuitBreaker] = {}
_circuit_breakers_lock = threading.Lock()


def get_circuit_breaker(
    name: str,
    config: Optional[CircuitBreakerConfig] = None
) -> CircuitBreaker:
    """
    Get or create circuit breaker by name.

    Args:
        name: Circuit breaker identifier
        config: Configuration (only used on first creation)

    Returns:
        CircuitBreaker instance
    """
    with _circuit_breakers_lock:
        if name not in _circuit_breakers:
            _circuit_breakers[name] = CircuitBreaker(name, config)
        return _circuit_breakers[name]


def reset_circuit_breaker(name: str):
    """Reset a circuit breaker to closed state."""
    with _circuit_breakers_lock:
        if name in _circuit_breakers:
            cb = _circuit_breakers[name]
            with cb._lock:
                cb._state = CircuitState.CLOSED
                cb._failure_count = 0
                cb._success_count = 0
                cb._last_failure_time = None


def with_retry(
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    backoff_max: float = 30.0,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None
):
    """
    Decorator for retry with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        backoff_base: Base backoff time in seconds
        backoff_max: Maximum backoff time in seconds
        exceptions: Tuple of exception types to retry on
        on_retry: Optional callback called before each retry (attempt, exception)

    Example:
        @with_retry(max_attempts=3, exceptions=(ConnectionError,))
        def fetch_data():
            return requests.get("http://example.com")
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            from core.config_loader import get_feature_flags

            flags = get_feature_flags()
            retry_config = flags.get("retry", {})

            # Check if retry is enabled
            if not retry_config.get("enabled", True):
                return func(*args, **kwargs)

            # Use config defaults if not specified in decorator
            cfg_max_attempts = retry_config.get("max_attempts", max_attempts)
            cfg_backoff_base = retry_config.get("backoff_base_seconds", backoff_base)
            cfg_backoff_max = retry_config.get("backoff_max_seconds", backoff_max)

            last_exception = None

            for attempt in range(cfg_max_attempts):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 0:
                        _get_metrics().increment("retry_success", labels={"attempt": str(attempt)})
                        _get_logger().info(f"Retry succeeded func={func.__name__} attempt={attempt}")
                    return result
                except exceptions as e:
                    last_exception = e

                    if attempt < cfg_max_attempts - 1:
                        # Calculate backoff with exponential increase
                        backoff = min(cfg_backoff_base * (2 ** attempt), cfg_backoff_max)

                        _get_metrics().increment("retry_attempt", labels={"func": func.__name__})
                        _get_logger().warning(
                            f"Retry attempt func={func.__name__} attempt={attempt + 1} backoff={backoff} error={e}"
                        )

                        if on_retry:
                            on_retry(attempt + 1, e)

                        time.sleep(backoff)
                    else:
                        _get_metrics().increment("retry_exhausted", labels={"func": func.__name__})
                        _get_logger().error(f"Retry exhausted func={func.__name__} attempts={cfg_max_attempts}")

            # All retries failed
            raise last_exception

        return wrapper
    return decorator


def with_circuit_breaker(
    name: str,
    config: Optional[CircuitBreakerConfig] = None
):
    """
    Decorator for circuit breaker protection.

    Args:
        name: Circuit breaker identifier
        config: Circuit breaker configuration

    Example:
        @with_circuit_breaker("elasticsearch", CircuitBreakerConfig(failure_threshold=10))
        def fetch_from_elasticsearch():
            return es.search(...)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            from core.config_loader import get_feature_flags

            flags = get_feature_flags()
            if not flags.get("retry", {}).get("circuit_breaker_enabled", True):
                return func(*args, **kwargs)

            cb = get_circuit_breaker(name, config)

            if not cb.allow_request():
                _get_metrics().increment("circuit_breaker_rejected", labels={"name": name})
                raise Exception(f"Circuit breaker '{name}' is OPEN - blocking request")

            try:
                result = func(*args, **kwargs)
                cb.record_success()
                return result
            except Exception as _e:
                cb.record_failure()
                raise

        return wrapper
    return decorator


def get_all_circuit_breaker_stats() -> Dict[str, Dict[str, Any]]:
    """Get statistics for all circuit breakers."""
    with _circuit_breakers_lock:
        return {name: cb.stats() for name, cb in _circuit_breakers.items()}
