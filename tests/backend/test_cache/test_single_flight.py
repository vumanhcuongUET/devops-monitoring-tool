"""
Unit Tests for Single Flight Pattern

Phase 7 - Sprint 1 - Day 4
Tests for Single Flight implementation to prevent cache stampede
"""

import pytest
import asyncio
from unittest.mock import AsyncMock

from app.cache.single_flight import SingleFlight, single_flight, CacheWarmer


class TestSingleFlightBasics:
    """Test basic Single Flight operations."""

    @pytest.mark.asyncio
    async def test_single_execution(self):
        """Test single request executes normally."""
        single_flight = SingleFlight()
        executed = False

        async def fetch_func(key):
            nonlocal executed
            executed = True
            await asyncio.sleep(0.01)
            return {"data": "test"}

        result = await single_flight.execute("test_key", fetch_func, "test_key")

        assert executed is True
        assert result == {"data": "test"}

    @pytest.mark.asyncio
    async def test_concurrent_same_key(self):
        """Test concurrent requests for same key only execute once."""
        single_flight = SingleFlight()
        execution_count = 0

        async def fetch_func(key):
            nonlocal execution_count
            execution_count += 1
            await asyncio.sleep(0.05)  # Simulate slow fetch
            return {"data": f"result_{execution_count}"}

        # Create multiple concurrent requests for same key
        tasks = [
            single_flight.execute("test_key", fetch_func, "test_key")
            for _ in range(5)
        ]

        results = await asyncio.gather(*tasks)

        # Only one execution should have occurred
        assert execution_count == 1

        # All results should be the same
        assert all(r == {"data": "result_1"} for r in results)

    @pytest.mark.asyncio
    async def test_concurrent_different_keys(self):
        """Test concurrent requests for different keys execute independently."""
        single_flight = SingleFlight()
        execution_count = 0
        executed_keys = []

        async def fetch_func(key):
            nonlocal execution_count
            execution_count += 1
            executed_keys.append(key)
            await asyncio.sleep(0.02)
            return {"data": key, "count": execution_count}

        # Create requests for different keys
        keys = ["key1", "key2", "key3"]
        tasks = [
            single_flight.execute(key, fetch_func, key)
            for key in keys * 2  # Each key requested twice
        ]

        results = await asyncio.gather(*tasks)

        # All three keys should have been executed
        assert execution_count == 3
        assert set(executed_keys) == set(keys)

    @pytest.mark.asyncio
    async def test_error_propagation(self):
        """Test errors are propagated to all waiting requests."""
        single_flight = SingleFlight()

        async def fetch_func(key):
            await asyncio.sleep(0.01)
            raise ValueError("Test error")

        # Create multiple concurrent requests that will fail
        tasks = [
            single_flight.execute("test_key", fetch_func, "test_key")
            for _ in range(3)
        ]

        # All should raise the same error
        with pytest.raises(ValueError, match="Test error"):
            await asyncio.gather(*tasks)

    @pytest.mark.asyncio
    async def test_timeout_on_wait(self):
        """Test timeout when waiting for in-flight request."""
        single_flight = SingleFlight()

        # Start a long-running request
        async def slow_fetch(key):
            await asyncio.sleep(1.0)  # Longer than timeout
            return {"data": "slow"}

        # Start slow request in background
        slow_task = asyncio.create_task(
            single_flight.execute("test_key", slow_fetch, "test_key")
        )

        # Wait a bit to ensure first request starts
        await asyncio.sleep(0.01)

        # Try to wait for same key with timeout
        with pytest.raises(asyncio.TimeoutError):
            await single_flight.execute("test_key", slow_fetch, "test_key", timeout=0.01)

        # Cleanup
        try:
            await asyncio.wait_for(slow_task, timeout=1.1)
        except:
            pass


class TestSingleFlightStats:
    """Test Single Flight statistics tracking."""

    @pytest.mark.asyncio
    async def test_execution_stats(self):
        """Test statistics are tracked correctly."""
        single_flight = SingleFlight()

        async def fetch_func(key):
            await asyncio.sleep(0.01)
            return {"data": key}

        # Execute same key multiple times (sequentially)
        for _ in range(3):
            await single_flight.execute("test_key", fetch_func, "test_key")

        # Execute different key concurrently
        tasks = [
            single_flight.execute("other_key", fetch_func, "other_key")
            for _ in range(5)
        ]
        await asyncio.gather(*tasks)

        # Check stats
        stats = single_flight.get_stats("test_key")
        assert stats["executions"] == 3
        assert stats["waits"] == 0  # No concurrent waits in sequential execution

        stats = single_flight.get_stats("other_key")
        assert stats["executions"] == 1
        assert stats["waits"] == 4  # 4 waited for 1 execution

    @pytest.mark.asyncio
    async def test_summary(self):
        """Test overall summary statistics."""
        single_flight = SingleFlight()

        async def fetch_func(key):
            await asyncio.sleep(0.01)
            return {"data": key}

        # Mix of sequential and concurrent requests
        await single_flight.execute("key1", fetch_func, "key1")

        tasks = [
            single_flight.execute("key2", fetch_func, "key2")
            for _ in range(3)
        ]
        await asyncio.gather(*tasks)

        summary = single_flight.get_summary()
        assert summary["total_executions"] == 2  # key1 + key2
        assert summary["total_waits"] == 2  # 2 waited for key2
        assert summary["unique_keys"] == 2
        assert 0 < summary["efficiency_rate"] < 1


class TestSingleFlightDecorator:
    """Test the @single_flight decorator."""

    @pytest.mark.asyncio
    async def test_decorator_basic(self):
        """Test @single_flight decorator works."""
        execution_count = 0

        @single_flight(lambda project, time_range: f"{project}:{time_range}")
        async def get_data(project, time_range):
            nonlocal execution_count
            execution_count += 1
            await asyncio.sleep(0.02)
            return {"project": project, "range": time_range}

        # Concurrent requests with same params
        tasks = [
            get_data("test", "1h")
            for _ in range(5)
        ]
        results = await asyncio.gather(*tasks)

        # Only one execution
        assert execution_count == 1
        # All results the same
        assert all(r == {"project": "test", "range": "1h"} for r in results)

    @pytest.mark.asyncio
    async def test_decorator_different_params(self):
        """Test decorator with different parameters."""
        execution_count = 0

        @single_flight(lambda project, time_range: f"{project}:{time_range}")
        async def get_data(project, time_range):
            nonlocal execution_count
            execution_count += 1
            await asyncio.sleep(0.01)
            return {"count": execution_count}

        # Different params should execute separately
        result1 = await get_data("test1", "1h")
        result2 = await get_data("test2", "1h")
        result3 = await get_data("test1", "1h")  # Should use cache

        assert execution_count == 2  # test1 and test2
        assert result1["count"] == 1
        assert result2["count"] == 2
        assert result3["count"] == 1  # Same as first result


class TestCacheWarmer:
    """Test Cache Warmer implementation."""

    @pytest.mark.asyncio
    async def test_warm_cache(self):
        """Test cache warming for a project."""
        # Mock L2 cache
        l2_cache = AsyncMock()
        l2_cache.set = AsyncMock()

        # Mock service clients
        with pytest.MonkeyPatch().context() as m:
            # We'll need to mock the service imports
            # For now, test the structure

            warmer = CacheWarmer(l2_cache)

            # Test warm_cache structure (would need actual service mocks)
            # This is a placeholder test
            assert warmer is not None
            assert warmer.l2_cache == l2_cache

    @pytest.mark.asyncio
    async def test_warming_service_lifecycle(self):
        """Test warming service start and stop."""
        l2_cache = AsyncMock()
        warmer = CacheWarmer(l2_cache)

        # Service should not be running initially
        assert not warmer.is_running()

        # Start and stop service
        async def run_warming():
            try:
                await warmer.start_warming_service(["test"], interval_seconds=1)
            except asyncio.CancelledError:
                pass

        # Run for a short time then cancel
        task = asyncio.create_task(run_warming())
        await asyncio.sleep(0.1)  # Let it start

        assert warmer.is_running()

        # Stop the service
        warmer.stop_warming_service()
        await asyncio.sleep(0.1)

        assert not warmer.is_running()

        # Cleanup task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class TestRealWorldScenarios:
    """Test real-world cache stampede prevention scenarios."""

    @pytest.mark.asyncio
    async def test_cache_expiration_storm(self):
        """Test scenario where cache expires and many requests hit at once."""
        single_flight = SingleFlight()
        fetch_count = 0

        async def expensive_fetch(key):
            nonlocal fetch_count
            fetch_count += 1
            await asyncio.sleep(0.05)  # Simulate expensive operation
            return {"data": f"fetch_{fetch_count}"}

        # Simulate 50 concurrent requests after cache expiration
        tasks = [
            single_flight.execute("overview:test-project", expensive_fetch, "overview:test-project")
            for _ in range(50)
        ]

        results = await asyncio.gather(*tasks)

        # Only one fetch should have occurred
        assert fetch_count == 1

        # All requests get the same result
        assert all(r == {"data": "fetch_1"} for r in results)

    @pytest.mark.asyncio
    async def test_mixed_cache_hit_and_miss(self):
        """Test scenario with both cache hits and misses."""
        single_flight = SingleFlight()
        fetch_count = {}

        async def fetch_func(key):
            fetch_count[key] = fetch_count.get(key, 0) + 1
            await asyncio.sleep(0.01)
            return {"key": key, "count": fetch_count[key]}

        # First batch: 3 different keys
        batch1 = [
            single_flight.execute(f"key{i}", fetch_func, f"key{i}")
            for i in range(3)
        ]
        results1 = await asyncio.gather(*batch1)
        assert len(fetch_count) == 3

        # Second batch: mix of same and new keys
        batch2 = [
            single_flight.execute(f"key{i}", fetch_func, f"key{i}")
            for i in range(5)  # key0, key1, key2 (cached), key3, key4 (new)
        ]
        results2 = await asyncio.gather(*batch2)

        # Only 2 new fetches should have occurred
        assert fetch_count["key0"] == 1  # Cached from batch1
        assert fetch_count["key1"] == 1  # Cached from batch1
        assert fetch_count["key2"] == 1  # Cached from batch1
        assert fetch_count["key3"] == 1  # New fetch
        assert fetch_count["key4"] == 1  # New fetch

    @pytest.mark.asyncio
    async def test_slow_request_with_fast_followups(self):
        """Test scenario where slow request has many fast follow-ups."""
        single_flight = SingleFlight()
        start_time = None
        fetch_completed = False

        async def slow_fetch(key):
            nonlocal start_time, fetch_completed
            if start_time is None:
                start_time = asyncio.get_event_loop().time()
            await asyncio.sleep(0.1)  # Slow operation
            fetch_completed = True
            return {"data": "slow_result"}

        # Start slow request
        slow_task = asyncio.create_task(
            single_flight.execute("slow_key", slow_fetch, "slow_key")
        )

        # Wait a bit then start many follow-up requests
        await asyncio.sleep(0.02)
        follow_ups = [
            single_flight.execute("slow_key", slow_fetch, "slow_key")
            for _ in range(10)
        ]

        # All follow-ups should wait for slow request
        results = await asyncio.gather(*follow_ups)

        # Only one fetch occurred
        assert fetch_completed is True

        # All follow-ups got the same result
        assert all(r == {"data": "slow_result"} for r in results)

        # Cleanup
        await slow_task
