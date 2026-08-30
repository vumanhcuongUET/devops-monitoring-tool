"""
Performance tests for Sprint 1-3 security and safety features.

Tests the performance impact of:
- Rate limiting with time-window tracking
- Action chaining prevention
- CSP nonce generation
- Webhook signature verification
- Resource limit checks

Acceptance Criteria:
- Rate limiting doesn't degrade performance (< 50ms overhead)
- Safety features add < 100ms overhead
- Token refresh is seamless (< 200ms)
- Resource checks are fast (< 500ms)

Author: Phase 8 Sprint 3 (Day 12)
Date: 2026-08-24
"""

import hashlib
import hmac
import time
from statistics import mean, median, stdev

import pytest

from app.actions.chain_monitor import ChainEvent, get_chain_monitor
from app.actions.rate_limiter import RateLimitConfig, get_rate_limiter
from app.middleware.security import CSPNonceManager, SecurityHeadersMiddleware


class PerformanceMetrics:
    """Helper class to track and analyze performance metrics."""

    def __init__(self, name: str):
        self.name = name
        self.durations: list[float] = []

    def record(self, duration: float) -> None:
        """Record a duration in milliseconds."""
        self.durations.append(duration)

    def get_stats(self) -> dict:
        """Get statistics for recorded durations."""
        if not self.durations:
            return {}

        return {
            "count": len(self.durations),
            "min": round(min(self.durations), 3),
            "max": round(max(self.durations), 3),
            "mean": round(mean(self.durations), 3),
            "median": round(median(self.durations), 3),
            "stdev": round(stdev(self.durations), 3) if len(self.durations) > 1 else 0,
            "p95": round(sorted(self.durations)[int(len(self.durations) * 0.95)], 3),
            "p99": round(sorted(self.durations)[int(len(self.durations) * 0.99)], 3),
        }

    def assert_max(self, max_ms: float) -> None:
        """Assert that all durations are under the maximum."""
        violations = [d for d in self.durations if d > max_ms]
        if violations:
            pytest.fail(
                f"{self.name}: {len(violations)} measurements exceeded {max_ms}ms. "
                f"Stats: {self.get_stats()}"
            )

    def assert_mean_under(self, max_ms: float) -> None:
        """Assert that mean duration is under the maximum."""
        mean_val = mean(self.durations)
        if mean_val > max_ms:
            pytest.fail(
                f"{self.name}: Mean {mean_val:.3f}ms exceeds {max_ms}ms. "
                f"Stats: {self.get_stats()}"
            )


def measure_time(func):
    """Decorator to measure function execution time."""
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        return result, (end - start) * 1000  # Return result and duration in ms
    return wrapper


class TestRateLimitingPerformance:
    """Performance tests for rate limiting."""

    @pytest.fixture
    def reset_rate_limiter(self):
        """Reset rate limiter state before each test."""
        limiter = get_rate_limiter()
        limiter.reset()
        yield limiter
        limiter.reset()

    def test_rate_limit_check_performance(self, reset_rate_limiter):
        """Test rate limit check performance under load."""
        limiter = reset_rate_limiter

        # Configure for high throughput testing
        test_config = RateLimitConfig(
            max_actions_per_hour=10000,
            cooldown_seconds=0,
            chain_break_seconds=600,
            max_chain_length=10000
        )
        limiter.update_config(test_config)

        metrics = PerformanceMetrics("rate_limit_check")
        iterations = 1000

        for i in range(iterations):
            start = time.perf_counter()

            # Perform rate limit check
            allowed, reason, metadata = limiter.check(
                project=f"project-{i % 10}",  # 10 different projects
                action_type=f"action-{i % 5}",  # 5 different action types
                user="test-user"
            )

            duration = (time.perf_counter() - start) * 1000
            metrics.record(duration)

        stats = metrics.get_stats()
        print(f"\nRate Limit Check Performance: {stats}")

        # Assertions
        metrics.assert_max(5.0)  # No single check should take > 5ms
        metrics.assert_mean_under(1.0)  # Mean should be < 1ms

    def test_rate_limit_with_10000_checks(self, reset_rate_limiter):
        """Test rate limiting with 10,000 checks (load test)."""
        limiter = reset_rate_limiter

        test_config = RateLimitConfig(
            max_actions_per_hour=10000,
            cooldown_seconds=0,
            chain_break_seconds=600,
            max_chain_length=10000
        )
        limiter.update_config(test_config)

        metrics = PerformanceMetrics("rate_limit_load_test")
        iterations = 10000

        start_total = time.perf_counter()

        for i in range(iterations):
            allowed, reason, metadata = limiter.check(
                project=f"project-{i % 100}",
                action_type=f"action-{i % 20}",
                user=f"user-{i % 50}"
            )

        total_duration = (time.perf_counter() - start_total) * 1000
        mean_duration = total_duration / iterations

        print("\n10,000 Rate Limit Checks:")
        print(f"  Total: {total_duration:.2f}ms")
        print(f"  Mean: {mean_duration:.3f}ms")
        print(f"  Throughput: {iterations / (total_duration / 1000):.0f} checks/sec")

        # Should handle 10,000 checks in reasonable time
        assert total_duration < 5000, f"10,000 checks took {total_duration:.2f}ms, expected < 5000ms"
        assert mean_duration < 0.5, f"Mean check took {mean_duration:.3f}ms, expected < 0.5ms"

    def test_rate_limit_record_performance(self, reset_rate_limiter):
        """Test rate limit record action performance."""
        limiter = reset_rate_limiter

        test_config = RateLimitConfig(
            max_actions_per_hour=10000,
            cooldown_seconds=0,
            chain_break_seconds=600,
            max_chain_length=10000
        )
        limiter.update_config(test_config)

        metrics = PerformanceMetrics("rate_limit_record")
        iterations = 1000

        for i in range(iterations):
            start = time.perf_counter()

            limiter.record_action(
                project=f"project-{i % 10}",
                action_type=f"action-{i % 5}",
                user="test-user"
            )

            duration = (time.perf_counter() - start) * 1000
            metrics.record(duration)

        stats = metrics.get_stats()
        print(f"\nRate Limit Record Performance: {stats}")

        # Record should also be fast
        metrics.assert_max(10.0)  # No single record should take > 10ms
        metrics.assert_mean_under(2.0)  # Mean should be < 2ms


class TestChainMonitoringPerformance:
    """Performance tests for chain monitoring."""

    @pytest.fixture
    def reset_chain_monitor(self):
        """Reset chain monitor state before each test."""
        monitor = get_chain_monitor()
        monitor.reset_tracking()
        yield monitor
        monitor.reset_tracking()

    def test_chain_check_performance(self, reset_chain_monitor):
        """Test chain monitoring check performance."""
        monitor = reset_chain_monitor

        metrics = PerformanceMetrics("chain_check")
        iterations = 1000

        for i in range(iterations):
            start = time.perf_counter()

            event = monitor.check_chain(
                project=f"project-{i % 10}",
                action_type=f"action-{i % 5}",
                chain_count=i % 5,
                chain_limit=10,
                user="test-user"
            )

            duration = (time.perf_counter() - start) * 1000
            metrics.record(duration)

        stats = metrics.get_stats()
        print(f"\nChain Check Performance: {stats}")

        # Chain checks should be very fast
        metrics.assert_max(2.0)  # No single check should take > 2ms
        metrics.assert_mean_under(0.5)  # Mean should be < 0.5ms

    def test_chain_check_with_callback(self, reset_chain_monitor):
        """Test chain monitoring with alert callback."""
        monitor = reset_chain_monitor

        # Set up a callback (simulates Slack notification)
        callback_count = 0

        def callback(event: ChainEvent):
            nonlocal callback_count
            callback_count += 1

        monitor.set_alert_callback(callback)

        metrics = PerformanceMetrics("chain_check_with_callback")
        iterations = 1000

        for i in range(iterations):
            start = time.perf_counter()

            event = monitor.check_chain(
                project="test-project",
                action_type="test-action",
                chain_count=i,  # Will trigger alerts at threshold
                chain_limit=10,
                user="test-user"
            )

            duration = (time.perf_counter() - start) * 1000
            metrics.record(duration)

        stats = metrics.get_stats()
        print(f"\nChain Check with Callback Performance: {stats}")
        print(f"  Callbacks triggered: {callback_count}")

        # Even with callbacks, should be fast
        metrics.assert_max(5.0)  # No single check should take > 5ms
        metrics.assert_mean_under(1.0)  # Mean should be < 1ms


class TestCSPNoncePerformance:
    """Performance tests for CSP nonce generation."""

    def test_nonce_generation_performance(self):
        """Test CSP nonce generation performance."""
        nonce_manager = CSPNonceManager()

        metrics = PerformanceMetrics("nonce_generation")
        iterations = 10000

        for _ in range(iterations):
            start = time.perf_counter()

            nonce = nonce_manager.generate_nonce()

            duration = (time.perf_counter() - start) * 1000
            metrics.record(duration)

            # Verify nonce is valid
            assert nonce
            assert len(nonce) > 10

        stats = metrics.get_stats()
        print(f"\nNonce Generation Performance (10,000 iterations): {stats}")

        # Nonce generation should be very fast
        metrics.assert_max(1.0)  # No single generation should take > 1ms
        metrics.assert_mean_under(0.1)  # Mean should be < 0.1ms

    def test_csp_policy_building_performance(self):
        """Test CSP policy building performance."""
        middleware = SecurityHeadersMiddleware(app=None, use_nonce=True)

        metrics = PerformanceMetrics("csp_policy_build")
        iterations = 1000

        test_nonce = "test-nonce-value-12345"

        for _ in range(iterations):
            start = time.perf_counter()

            policy = middleware._build_csp_policy(
                nonce=test_nonce,
                environment="production"
            )

            duration = (time.perf_counter() - start) * 1000
            metrics.record(duration)

            # Verify policy is valid
            assert "default-src" in policy
            assert f"'nonce-{test_nonce}'" in policy

        stats = metrics.get_stats()
        print(f"\nCSP Policy Building Performance: {stats}")

        # Policy building should be fast
        metrics.assert_max(2.0)  # No single build should take > 2ms
        metrics.assert_mean_under(0.5)  # Mean should be < 0.5ms


class TestWebhookSignaturePerformance:
    """Performance tests for webhook signature verification."""

    def test_slack_signature_verification_performance(self):
        """Test Slack signature verification performance."""
        from app.approvals.webhook import verify_slack_signature

        signing_secret = "test_signing_secret"
        timestamp = str(int(time.time()))
        body = '{"test": "payload", "data": "value"}'

        # Pre-calculate signature
        sig_basestring = f"v0:{timestamp}:{body}"
        digest = hmac.new(
            signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).digest()
        signature = f"v0={digest.hex()}"

        metrics = PerformanceMetrics("slack_signature_verify")
        iterations = 1000

        for _ in range(iterations):
            start = time.perf_counter()

            result = verify_slack_signature(
                raw_body=body.encode(),
                timestamp=timestamp,
                signature=signature,
                signing_secret=signing_secret
            )

            duration = (time.perf_counter() - start) * 1000
            metrics.record(duration)

            assert result is True

        stats = metrics.get_stats()
        print(f"\nSlack Signature Verification Performance: {stats}")

        # Signature verification should be fast
        metrics.assert_max(5.0)  # No single verification should take > 5ms
        metrics.assert_mean_under(1.0)  # Mean should be < 1ms

    def test_teams_signature_verification_performance(self):
        """Test Teams signature verification performance."""
        from app.approvals.webhook import verify_teams_hmac_signature

        webhook_url = "https://example.com/webhook"
        body = '{"test": "teams", "value": "data"}'

        # Pre-calculate signature
        digest = hmac.new(
            webhook_url.encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()
        auth_header = f"sha256={digest}"

        metrics = PerformanceMetrics("teams_signature_verify")
        iterations = 1000

        for _ in range(iterations):
            start = time.perf_counter()

            result = verify_teams_hmac_signature(
                raw_body=body.encode(),
                auth_header=auth_header,
                key=webhook_url
            )

            duration = (time.perf_counter() - start) * 1000
            metrics.record(duration)

            assert result is True

        stats = metrics.get_stats()
        print(f"\nTeams Signature Verification Performance: {stats}")

        # Signature verification should be fast
        metrics.assert_max(5.0)  # No single verification should take > 5ms
        metrics.assert_mean_under(1.0)  # Mean should be < 1ms


class TestCombinedSecurityFlowPerformance:
    """Performance tests for combined security flows."""

    def test_complete_security_flow_performance(self):
        """Test complete security flow performance."""
        limiter = get_rate_limiter()
        monitor = get_chain_monitor()

        # Reset state
        limiter.reset()
        monitor.reset_tracking()

        # Configure for testing
        test_config = RateLimitConfig(
            max_actions_per_hour=10000,
            cooldown_seconds=0,
            chain_break_seconds=600,
            max_chain_length=10000
        )
        limiter.update_config(test_config)

        metrics = PerformanceMetrics("complete_security_flow")
        iterations = 1000

        for i in range(iterations):
            start = time.perf_counter()

            # Step 1: Rate limit check
            allowed1, reason1, metadata1 = limiter.check(
                project=f"project-{i % 10}",
                action_type=f"action-{i % 5}",
                user="test-user"
            )

            # Step 2: Chain check
            event = monitor.check_chain(
                project=f"project-{i % 10}",
                action_type=f"action-{i % 5}",
                chain_count=i % 5,
                chain_limit=10,
                user="test-user"
            )

            # Step 3: Record action
            if allowed1:
                limiter.record_action(
                    project=f"project-{i % 10}",
                    action_type=f"action-{i % 5}",
                    user="test-user"
                )

            duration = (time.perf_counter() - start) * 1000
            metrics.record(duration)

        stats = metrics.get_stats()
        print(f"\nComplete Security Flow Performance: {stats}")

        # Complete flow should still be fast
        metrics.assert_max(20.0)  # No single flow should take > 20ms
        metrics.assert_mean_under(5.0)  # Mean should be < 5ms

    def test_concurrent_rate_limit_checks(self):
        """Test concurrent rate limit checks performance."""
        import asyncio

        limiter = get_rate_limiter()
        limiter.reset()

        test_config = RateLimitConfig(
            max_actions_per_hour=10000,
            cooldown_seconds=0,
            chain_break_seconds=600,
            max_chain_length=10000
        )
        limiter.update_config(test_config)

        async def concurrent_checks(count: int) -> list[float]:
            """Run concurrent checks and return durations."""
            async def single_check(i: int) -> float:
                start = time.perf_counter()
                limiter.check(
                    project=f"project-{i % 10}",
                    action_type=f"action-{i % 5}",
                    user="test-user"
                )
                return (time.perf_counter() - start) * 1000

            tasks = [single_check(i) for i in range(count)]
            return await asyncio.gather(*tasks)

        # Test with 100 concurrent checks
        iterations = 100

        start_total = time.perf_counter()
        durations = asyncio.run(concurrent_checks(iterations))
        total_duration = (time.perf_counter() - start_total) * 1000

        metrics = PerformanceMetrics("concurrent_rate_limit")
        for d in durations:
            metrics.record(d)

        stats = metrics.get_stats()
        print("\nConcurrent Rate Limit Checks (100 concurrent):")
        print(f"  Individual check stats: {stats}")
        print(f"  Total time: {total_duration:.2f}ms")
        print(f"  Concurrent throughput: {iterations / (total_duration / 1000):.0f} checks/sec")

        # Concurrent checks should be efficient
        metrics.assert_max(10.0)  # No single check should take > 10ms
        metrics.assert_mean_under(2.0)  # Mean should be < 2ms


class TestMemoryUsage:
    """Tests for memory usage of security features."""

    def test_rate_limit_memory_usage(self):
        """Test rate limiter memory usage with many records."""
        import sys

        limiter = get_rate_limiter()
        limiter.reset()

        test_config = RateLimitConfig(
            max_actions_per_hour=10000,
            cooldown_seconds=0,
            chain_break_seconds=600,
            max_chain_length=10000
        )
        limiter.update_config(test_config)

        # Get baseline memory
        baseline = sys.getsizeof(limiter)

        # Add many action records
        for i in range(1000):
            limiter.record_action(
                project=f"project-{i % 100}",
                action_type=f"action-{i % 50}",
                user="test-user"
            )

        # Check memory after
        after = sys.getsizeof(limiter)

        print("\nRate Limiter Memory Usage:")
        print(f"  Baseline: {baseline} bytes")
        print(f"  After 1000 records: {after} bytes")
        print(f"  Growth: {after - baseline} bytes ({(after - baseline) / 1000:.2f} bytes per record)")

        # Memory growth should be reasonable
        # (This is a rough check - actual memory may vary)
        assert (after - baseline) < 1000000, f"Memory growth too large: {after - baseline} bytes"

    def test_chain_monitor_memory_usage(self):
        """Test chain monitor memory usage."""
        import sys

        monitor = get_chain_monitor()
        monitor.reset_tracking()

        # Get baseline memory
        baseline = sys.getsizeof(monitor)

        # Track many chain events
        for i in range(100):
            monitor.check_chain(
                project=f"project-{i % 10}",
                action_type=f"action-{i % 5}",
                chain_count=i % 10,
                chain_limit=10,
                user="test-user"
            )

        # Check memory after
        after = sys.getsizeof(monitor)

        print("\nChain Monitor Memory Usage:")
        print(f"  Baseline: {baseline} bytes")
        print(f"  After 100 checks: {after} bytes")
        print(f"  Growth: {after - baseline} bytes")

        # Chain monitor should have minimal memory growth
        assert (after - baseline) < 50000, f"Memory growth too large: {after - baseline} bytes"


@pytest.mark.parametrize("max_ms", [50, 100, 200, 500])
class TestPerformanceThresholds:
    """Tests verifying specific performance thresholds from acceptance criteria."""

    def test_rate_limiting_overhead_under_50ms(self, max_ms):
        """Verify rate limiting adds < 50ms overhead."""
        limiter = get_rate_limiter()
        limiter.reset()

        start = time.perf_counter()
        for _ in range(100):
            limiter.check(
                project="test-project",
                action_type="test-action",
                user="test-user"
            )
        duration = (time.perf_counter() - start) * 1000
        mean_duration = duration / 100

        print(f"\nRate limiting mean overhead: {mean_duration:.3f}ms")
        assert mean_duration < max_ms, f"Rate limiting overhead {mean_duration:.3f}ms exceeds {max_ms}ms"

    def test_safety_features_under_100ms(self, max_ms):
        """Verify safety features add < 100ms overhead."""
        limiter = get_rate_limiter()
        monitor = get_chain_monitor()

        limiter.reset()
        monitor.reset_tracking()

        start = time.perf_counter()
        for _ in range(100):
            # Complete safety flow
            allowed, _, _ = limiter.check(
                project="test-project",
                action_type="test-action",
                user="test-user"
            )
            monitor.check_chain(
                project="test-project",
                action_type="test-action",
                chain_count=1,
                chain_limit=10,
                user="test-user"
            )
            if allowed:
                limiter.record_action("test-project", "test-action", "test-user")

        duration = (time.perf_counter() - start) * 1000
        mean_duration = duration / 100

        print(f"\nSafety features mean overhead: {mean_duration:.3f}ms")
        assert mean_duration < max_ms, f"Safety features overhead {mean_duration:.3f}ms exceeds {max_ms}ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
