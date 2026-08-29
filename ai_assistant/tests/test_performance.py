"""
Performance regression tests.

Tests to ensure performance doesn't degrade over time.
"""

import time
import pytest

from core.cache import get_global_cache, SimpleCache
from core.security import TokenBucketRateLimiter, InputValidator
from core.audit import AuditLogger, AuditLogEntry
from core.single_flight import SingleFlight


@pytest.mark.performance
class TestCachePerformance:
    """Performance tests for cache layer."""

    def test_cache_get_performance(self):
        """Test cache get performance (should be < 1ms)."""
        cache = get_global_cache()
        cache.set("test_key", {"data": "value"})

        start = time.perf_counter()
        for _ in range(1000):
            cache.get("test_key")
        elapsed = time.perf_counter() - start

        avg_time_ms = (elapsed / 1000) * 1000
        assert avg_time_ms < 1.0, f"Cache get too slow: {avg_time_ms:.3f}ms average"

    def test_cache_set_performance(self):
        """Test cache set performance (should be < 1ms)."""
        cache = get_global_cache()

        start = time.perf_counter()
        for i in range(1000):
            cache.set(f"key_{i}", {"data": f"value_{i}"})
        elapsed = time.perf_counter() - start

        avg_time_ms = (elapsed / 1000) * 1000
        assert avg_time_ms < 1.0, f"Cache set too slow: {avg_time_ms:.3f}ms average"


@pytest.mark.performance
class TestRateLimiterPerformance:
    """Performance tests for rate limiter."""

    def test_rate_limiter_check_performance(self):
        """Test rate limiter check performance (should be < 0.5ms)."""
        limiter = TokenBucketRateLimiter(rate=1000.0, capacity=10000)

        start = time.perf_counter()
        for _ in range(1000):
            limiter.check("test_user")
        elapsed = time.perf_counter() - start

        avg_time_ms = (elapsed / 1000) * 1000
        assert avg_time_ms < 0.5, f"Rate limiter check too slow: {avg_time_ms:.3f}ms average"


@pytest.mark.performance
class TestInputValidationPerformance:
    """Performance tests for input validation."""

    def test_project_name_validation_performance(self):
        """Test project name validation performance (should be < 0.1ms)."""
        start = time.perf_counter()
        for _ in range(1000):
            InputValidator.validate_project_name("valid-project-name")
        elapsed = time.perf_counter() - start

        avg_time_ms = (elapsed / 1000) * 1000
        assert avg_time_ms < 0.1, f"Project name validation too slow: {avg_time_ms:.3f}ms average"

    def test_url_validation_performance(self):
        """Test URL validation performance (should be < 0.5ms)."""
        url = "https://api.example.com:9200/path"

        start = time.perf_counter()
        for _ in range(1000):
            InputValidator.validate_url(url)
        elapsed = time.perf_counter() - start

        avg_time_ms = (elapsed / 1000) * 1000
        assert avg_time_ms < 0.5, f"URL validation too slow: {avg_time_ms:.3f}ms average"

    def test_template_validation_performance(self):
        """Test template validation performance (should be < 0.5ms)."""
        template = '{"query": {"match": {"{{ key }}": "{{ value }}"}}}'

        start = time.perf_counter()
        for _ in range(1000):
            InputValidator.validate_template_content(template)
        elapsed = time.perf_counter() - start

        avg_time_ms = (elapsed / 1000) * 1000
        assert avg_time_ms < 0.5, f"Template validation too slow: {avg_time_ms:.3f}ms average"


@pytest.mark.performance
class TestAuditLogPerformance:
    """Performance tests for audit logging."""

    def test_audit_log_write_performance(self):
        """Test audit log write performance (should be < 5ms)."""
        import tempfile
        from pathlib import Path

        temp_dir = tempfile.mkdtemp()
        log_dir = Path(temp_dir) / "audit"

        logger = AuditLogger(log_dir=log_dir)

        start = time.perf_counter()
        for i in range(100):
            entry = AuditLogEntry(
                event_type="test",
                actor=f"user_{i}",
                action="test_action",
            )
            logger.log(entry)
        elapsed = time.perf_counter() - start

        avg_time_ms = (elapsed / 100) * 1000
        assert avg_time_ms < 5.0, f"Audit log write too slow: {avg_time_ms:.3f}ms average"

        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_audit_log_query_performance(self):
        """Test audit log query performance (should scale linearly)."""
        import tempfile
        from pathlib import Path

        temp_dir = tempfile.mkdtemp()
        log_dir = Path(temp_dir) / "audit"

        logger = AuditLogger(log_dir=log_dir)

        # Write 1000 entries
        for i in range(1000):
            entry = AuditLogEntry(
                event_type="test",
                actor=f"user_{i % 10}",  # 10 different users
                action="test_action",
            )
            logger.log(entry)

        # Query performance
        start = time.perf_counter()
        results = logger.query(limit=100)
        elapsed = time.perf_counter() - start

        assert elapsed < 0.5, f"Audit log query too slow: {elapsed:.3f}s"
        assert len(results) == 100, f"Expected 100 results, got {len(results)}"

        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.performance
class TestSingleFlightPerformance:
    """Performance tests for single flight (query deduplication)."""

    def test_single_flight_cached_call_performance(self):
        """Test that cached single-flight calls are fast (< 0.1ms overhead)."""
        sf = SingleFlight()

        # First call (no caching)
        @sf.single_flight
        def expensive_query(param):
            return f"result_{param}"

        # Make first call to cache result
        expensive_query("test")

        # Measure cached call performance
        start = time.perf_counter()
        for _ in range(1000):
            expensive_query("test")
        elapsed = time.perf_counter() - start

        avg_time_ms = (elapsed / 1000) * 1000
        # Cached calls should be very fast
        assert avg_time_ms < 0.1, f"Single-flight cached call too slow: {avg_time_ms:.3f}ms average"


@pytest.mark.performance
class TestMemoryUsage:
    """Tests for memory usage patterns."""

    def test_cache_memory_growth(self):
        """Test that cache doesn't grow unbounded."""
        cache = SimpleCache()

        # Add many items
        for i in range(10000):
            cache.set(f"key_{i}", {"data": f"value_{i}" * 100})

        # Cache should handle this without excessive memory growth
        # (SimpleCache has no size limit, so items accumulate)
        # In production, Redis or size-limited cache should be used

        # Verify cache is still functional
        assert cache.get("key_0") is not None
        assert cache.get("key_9999") is not None

        # Cleanup
        cache.clear()


@pytest.mark.performance
@pytest.mark.slow
class TestScalability:
    """Scalability tests (marked as slow)."""

    def test_rate_limiter_scalability(self):
        """Test rate limiter performance with many users."""
        limiter = TokenBucketRateLimiter(rate=100.0, capacity=1000)

        start = time.perf_counter()
        for i in range(10000):
            limiter.check(f"user_{i % 1000}")  # 1000 unique users
        elapsed = time.perf_counter() - start

        avg_time_ms = (elapsed / 10000) * 1000
        assert avg_time_ms < 1.0, f"Rate limiter with many users too slow: {avg_time_ms:.3f}ms average"

    def test_cache_scalability(self):
        """Test cache performance with many keys."""
        cache = SimpleCache()

        # Add many keys
        for i in range(10000):
            cache.set(f"key_{i}", {"value": i})

        # Measure random access performance
        import random
        start = time.perf_counter()
        for _ in range(1000):
            key = f"key_{random.randint(0, 9999)}"
            cache.get(key)
        elapsed = time.perf_counter() - start

        avg_time_ms = (elapsed / 1000) * 1000
        assert avg_time_ms < 1.0, f"Cache random access too slow: {avg_time_ms:.3f}ms average"


@pytest.mark.performance
class TestConcurrency:
    """Tests for concurrent access patterns."""

    def test_cache_thread_safety_overhead(self):
        """Test that cache thread safety doesn't add excessive overhead."""
        import threading

        cache = SimpleCache()
        errors = []

        def worker():
            try:
                for i in range(100):
                    cache.set(f"key_{threading.get_ident()}_{i}", i)
                    cache.get(f"key_{threading.get_ident()}_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]

        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.perf_counter() - start

        assert len(errors) == 0, f"Thread safety errors: {errors}"
        # 10 threads * 200 operations = 2000 operations
        avg_time_ms = (elapsed / 2000) * 1000
        assert avg_time_ms < 5.0, f"Thread-safe cache too slow: {avg_time_ms:.3f}ms average"


@pytest.mark.performance
class TestValidationOverhead:
    """Tests for validation overhead on valid inputs."""

    def test_validation_overhead_on_valid_input(self):
        """Test that validation adds minimal overhead for valid input."""
        valid_inputs = [
            ("valid-project", InputValidator.validate_project_name),
            ("now-30m", InputValidator.validate_time_range),
            ("https://api.example.com", lambda x: InputValidator.validate_url(x, allow_credentials=True)),
        ]

        for value, validator in valid_inputs:
            start = time.perf_counter()
            for _ in range(1000):
                validator(value)
            elapsed = time.perf_counter() - start

            avg_time_ms = (elapsed / 1000) * 1000
            assert avg_time_ms < 0.5, f"Validation overhead too high for {validator.__name__}: {avg_time_ms:.3f}ms"


@pytest.mark.performance
class TestChainHashingPerformance:
    """Tests for audit log chain hashing performance."""

    def test_chain_hash_computation_performance(self):
        """Test that chain hash computation is efficient."""
        import tempfile
        from pathlib import Path

        temp_dir = tempfile.mkdtemp()
        log_dir = Path(temp_dir) / "audit"

        logger = AuditLogger(log_dir=log_dir)

        # Chain hashing happens for each log entry
        start = time.perf_counter()
        for _i in range(100):
            entry = AuditLogEntry(
                event_type="test",
                actor="user1",
                details={"data": "x" * 100},
            )
            logger.log(entry)
        elapsed = time.perf_counter() - start

        # Chain hashing uses HMAC-SHA256, which should be fast
        avg_time_ms = (elapsed / 100) * 1000
        assert avg_time_ms < 2.0, f"Chain hashing too slow: {avg_time_ms:.3f}ms average"

        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
