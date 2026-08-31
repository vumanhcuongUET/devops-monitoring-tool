"""
Performance regression tests.

Tests to ensure performance doesn't degrade over time.
"""

import threading
import time
import pytest

from core.cache import get_global_cache, SimpleCache
from core.security import InputValidator
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


@pytest.mark.performance
class TestSingleFlightPerformance:
    """Performance tests for single flight (query deduplication)."""

    def test_single_flight_cached_call_performance(self):
        """SingleFlight dedupes concurrent calls; uncontended overhead stays low.

        The old version used a @sf.single_flight decorator that never existed
        (SingleFlight only ever exposed execute(key, func)) — review F3.
        """
        sf = SingleFlight()
        calls = []
        release = threading.Event()

        def slow_query(param):
            calls.append(param)
            release.wait(timeout=5)  # hold the flight open so callers overlap
            return f"result_{param}"

        # Concurrent callers with the same key collapse into one execution
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(sf.execute, "test-key", slow_query, "test") for _ in range(10)]
            # give the followers time to register as waiters before releasing
            import time as _t
            _t.sleep(0.2)
            release.set()
            results = [f.result() for f in futures]

        assert len(calls) == 1, f"expected 1 execution, got {len(calls)}"
        assert all(r == "result_test" for r in results)

        # Uncontended repeated calls stay well under 1ms each
        start = time.perf_counter()
        def cheap_query(param):
            return f"result_{param}"

        for _ in range(1000):
            sf.execute("uncontended-key", cheap_query, "x")
        elapsed = time.perf_counter() - start
        avg_time_ms = (elapsed / 1000) * 1000
        assert avg_time_ms < 1.0, f"Single-flight call too slow: {avg_time_ms:.3f}ms average"


@pytest.mark.performance
class TestMemoryUsage:
    """Tests for memory usage patterns."""

    def test_cache_memory_growth(self):
        """Cache is bounded at max_size — oldest entries evicted, bound holds.

        The old assertions expected unbounded retention from before SimpleCache
        gained max_size eviction; key_0 is correctly evicted now (review F3).
        """
        cache = SimpleCache(max_size=1000)

        for i in range(10000):
            cache.set(f"key_{i}", {"data": f"value_{i}" * 100})

        # Oldest entries evicted, newest retained, size bounded
        assert cache.get("key_0") is None
        assert cache.get("key_9999") is not None
        assert len(cache._cache) <= 1000

        cache.clear()


@pytest.mark.performance
@pytest.mark.slow
class TestScalability:
    """Scalability tests (marked as slow)."""

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
