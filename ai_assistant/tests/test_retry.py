"""
Tests for retry module.
"""

import pytest
import time
from unittest.mock import patch

from core.retry import (
    with_retry,
    with_circuit_breaker,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    get_circuit_breaker,
    reset_circuit_breaker,
    get_all_circuit_breaker_stats
)


@pytest.mark.unit
class TestWithRetry:
    """Tests for @with_retry decorator."""

    def test_retry_success_on_first_attempt(self):
        """Test function that succeeds immediately."""
        call_count = [0]

        @with_retry(max_attempts=3)
        def func():
            call_count[0] += 1
            return "success"

        result = func()
        assert result == "success"
        assert call_count[0] == 1

    def test_retry_retries_on_failure(self):
        """Test that function is retried on failure."""
        call_count = [0]

        @with_retry(max_attempts=3, exceptions=(ValueError,))
        def func():
            call_count[0] += 1
            if call_count[0] < 2:
                raise ValueError("Not yet")
            return "success"

        result = func()
        assert result == "success"
        assert call_count[0] == 2

    def test_retry_exhausted(self):
        """Test that retry gives up after max attempts."""
        call_count = [0]

        @with_retry(max_attempts=3, exceptions=(ValueError,))
        def func():
            call_count[0] += 1
            raise ValueError("Always fails")

        with pytest.raises(ValueError, match="Always fails"):
            func()

        assert call_count[0] == 3

    def test_retry_only_retries_specific_exceptions(self):
        """Test that only specified exceptions trigger retry."""
        call_count = [0]

        @with_retry(max_attempts=3, exceptions=(ValueError,))
        def func():
            call_count[0] += 1
            if call_count[0] == 1:
                raise TypeError("Different exception")
            return "success"

        with pytest.raises(TypeError):
            func()

        assert call_count[0] == 1  # Not retried

    def test_retry_disabled_via_config(self):
        """Test that retry can be disabled via feature flags."""
        with patch("core.config_loader.get_feature_flags", return_value={"retry": {"enabled": False}}):
            call_count = [0]

            @with_retry(max_attempts=3)
            def func():
                call_count[0] += 1
                raise ValueError("Fails")

            with pytest.raises(ValueError):
                func()

            # Should only be called once (no retry)
            assert call_count[0] == 1

    def test_retry_uses_config_defaults(self):
        """Test that retry uses config defaults when not specified."""
        flags = {
            "retry": {
                "enabled": True,
                "max_attempts": 5,
                "backoff_base_seconds": 0.1,
                "backoff_max_seconds": 1.0
            }
        }

        with patch("core.config_loader.get_feature_flags", return_value=flags):
            call_count = [0]

            @with_retry(max_attempts=2)  # Decorator value, config should override
            def func():
                call_count[0] += 1
                if call_count[0] < 4:
                    raise ValueError("Not yet")
                return "success"

            # Config has max_attempts=5, so should succeed
            result = func()
            assert result == "success"
            assert call_count[0] == 4


@pytest.mark.unit
class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    def test_circuit_breaker_initial_state(self):
        """Test initial state is closed."""
        cb = CircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_circuit_breaker_opens_after_threshold(self):
        """Test circuit opens after failure threshold."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))

        for _i in range(3):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 3

    def test_circuit_breaker_blocks_requests_when_open(self):
        """Test requests are blocked when circuit is open."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2))

        cb.record_failure()
        cb.record_failure()

        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_circuit_breaker_half_open_after_timeout(self):
        """Test circuit goes half-open after timeout."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2, timeout_seconds=0))

        cb.record_failure()
        cb.record_failure()

        assert cb.state == CircuitState.OPEN

        # Should allow one request to test recovery
        assert cb.allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_circuit_breaker_closes_after_successes(self):
        """Test circuit closes after success threshold in half-open."""
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(failure_threshold=2, success_threshold=2, timeout_seconds=0)
        )

        # Open circuit
        cb.record_failure()
        cb.record_failure()

        # Transition to half-open
        cb.allow_request()
        assert cb.state == CircuitState.HALF_OPEN

        # Record successes
        cb.record_success()
        cb.record_success()

        assert cb.state == CircuitState.CLOSED

    def test_circuit_breaker_reopens_on_failure_in_half_open(self):
        """Test circuit reopens if failure occurs in half-open."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2, timeout_seconds=0))

        # Open circuit
        cb.record_failure()
        cb.record_failure()

        # Transition to half-open by calling allow_request
        cb.allow_request()
        assert cb.state == CircuitState.HALF_OPEN

        # Record failure in half-open
        cb.record_failure()

        assert cb.state == CircuitState.OPEN

    def test_circuit_breaker_stats(self):
        """Test circuit breaker statistics."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=5))

        cb.record_failure()
        # Success in CLOSED state doesn't increment success_count
        cb.record_success()

        stats = cb.stats()
        assert stats["name"] == "test"
        assert stats["failure_count"] == 0  # Reset by success in CLOSED state
        # success_count is only tracked in HALF_OPEN state


@pytest.mark.unit
class TestWithCircuitBreakerDecorator:
    """Tests for @with_circuit_breaker decorator."""

    def test_circuit_breaker_allows_success(self):
        """Test successful calls are allowed."""
        @with_circuit_breaker("test_service")
        def func():
            return "success"

        result = func()
        assert result == "success"

    def test_circuit_breaker_blocks_when_open(self):
        """Test requests are blocked when circuit is open."""
        cb = get_circuit_breaker("test_blocking")
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()  # Opens circuit (default threshold=5)

        @with_circuit_breaker("test_blocking")
        def func():
            return "success"

        with pytest.raises(Exception, match="Circuit breaker"):
            func()

    def test_circuit_breaker_records_failures(self):
        """Test circuit breaker records failures."""
        @with_circuit_breaker("test_failures")
        def func():
            raise ValueError("Service error")

        with pytest.raises(ValueError):
            func()

        cb = get_circuit_breaker("test_failures")
        assert cb.failure_count > 0

    def test_circuit_breaker_disabled_via_config(self):
        """Test circuit breaker can be disabled."""
        with patch("core.config_loader.get_feature_flags", return_value={"retry": {"circuit_breaker_enabled": False}}):
            cb = get_circuit_breaker("test_disabled")
            cb.record_failure()
            cb.record_failure()
            cb.record_failure()
            cb.record_failure()
            cb.record_failure()

            @with_circuit_breaker("test_disabled")
            def func():
                return "success"

            # Should not be blocked even though circuit is open
            result = func()
            assert result == "success"


@pytest.mark.unit
class TestCircuitBreakerRegistry:
    """Tests for circuit breaker registry."""

    def test_get_circuit_breaker_returns_same_instance(self):
        """Test that same name returns same instance."""
        cb1 = get_circuit_breaker("shared")
        cb2 = get_circuit_breaker("shared")

        assert cb1 is cb2

    def test_reset_circuit_breaker(self):
        """Test resetting circuit breaker."""
        cb = get_circuit_breaker("reset_test", CircuitBreakerConfig(failure_threshold=3))
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()

        # Circuit should be OPEN after 3 failures
        assert cb.state == CircuitState.OPEN

        reset_circuit_breaker("reset_test")

        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_get_all_circuit_breaker_stats(self):
        """Test getting stats for all circuit breakers."""
        get_circuit_breaker("stats_test1")
        get_circuit_breaker("stats_test2")

        stats = get_all_circuit_breaker_stats()

        assert "stats_test1" in stats
        assert "stats_test2" in stats
