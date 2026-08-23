"""
Unit Tests for L1 Cache

Phase 7 - Sprint 1 - Day 4
Tests for L1 in-memory cache implementation
"""

import pytest
import asyncio
from contextlib import asynccontextmanager

from app.cache.l1_cache import L1Cache, cached


class TestL1CacheBasicOperations:
    """Test basic L1 cache operations."""

    def test_cache_initialization(self):
        """Test cache initializes empty."""
        cache = L1Cache()
        summary = cache.get_summary()
        assert summary["cache_size"] == 0
        assert summary["total_hits"] == 0
        assert summary["total_misses"] == 0

    def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = L1Cache()
        params = {"project": "test", "time_range": "1h"}

        # Set value
        cache.set("elasticsearch", params, {"data": "test"})

        # Get value
        result = cache.get("elasticsearch", params)
        assert result == {"data": "test"}

    def test_get_missing_key(self):
        """Test getting non-existent key returns None."""
        cache = L1Cache()
        result = cache.get("elasticsearch", {"project": "test"})
        assert result is None

    def test_cache_key_generation(self):
        """Test cache keys are generated consistently."""
        cache = L1Cache()

        params1 = {"project": "test", "time_range": "1h"}
        params2 = {"time_range": "1h", "project": "test"}  # Different order

        key1 = cache._L1Cache__generate_key("elasticsearch", params1)
        key2 = cache._L1Cache__generate_key("elasticsearch", params2)

        # Same params should generate same key regardless of order
        assert key1 == key2

    def test_different_sources_different_keys(self):
        """Test different sources generate different keys."""
        cache = L1Cache()
        params = {"project": "test"}

        key1 = cache._L1Cache__generate_key("elasticsearch", params)
        key2 = cache._L1Cache__generate_key("prometheus", params)

        assert key1 != key2

    def test_cache_stats(self):
        """Test cache statistics tracking."""
        cache = L1Cache()
        params = {"project": "test"}

        # First call is a miss
        cache.get("elasticsearch", params)
        stats = cache.get_stats()
        key = list(stats.keys())[0]
        assert stats[key]["misses"] == 1
        assert stats[key]["hits"] == 0

        # Second call is a hit (after setting)
        cache.set("elasticsearch", params, {"data": "test"})
        cache.get("elasticsearch", params)
        stats = cache.get_stats()
        assert stats[key]["hits"] == 1
        assert stats[key]["misses"] == 1

    def test_cache_summary(self):
        """Test cache summary calculation."""
        cache = L1Cache()
        params = {"project": "test"}

        cache.set("elasticsearch", params, {"data": "test"})
        cache.get("elasticsearch", params)  # Hit
        cache.get("prometheus", params)  # Miss

        summary = cache.get_summary()
        assert summary["total_hits"] == 1
        assert summary["total_misses"] == 1
        assert summary["total_requests"] == 2
        assert summary["hit_rate"] == 0.5

    def test_clear_cache(self):
        """Test clearing cache."""
        cache = L1Cache()
        params = {"project": "test"}

        cache.set("elasticsearch", params, {"data": "test"})
        assert cache.get("elasticsearch", params) == {"data": "test"}

        cache.clear()
        assert cache.get("elasticsearch", params) is None
        assert cache.get_summary()["cache_size"] == 0

    def test_get_or_set_cache_hit(self):
        """Test get_or_set returns cached value on hit."""
        cache = L1Cache()
        params = {"project": "test"}
        cache.set("elasticsearch", params, {"data": "cached"})

        fetch_called = False

        def fetch_func():
            nonlocal fetch_called
            fetch_called = True
            return {"data": "fetched"}

        result = cache.get_or_set("elasticsearch", params, fetch_func)

        assert result == {"data": "cached"}
        assert not fetch_called  # Fetch function not called

    def test_get_or_set_cache_miss(self):
        """Test get_or_set calls fetch function on miss."""
        cache = L1Cache()
        params = {"project": "test"}

        fetch_called = False

        def fetch_func():
            nonlocal fetch_called
            fetch_called = True
            return {"data": "fetched"}

        result = cache.get_or_set("elasticsearch", params, fetch_func)

        assert result == {"data": "fetched"}
        assert fetch_called  # Fetch function was called

        # Second call should hit cache
        fetch_called = False
        result = cache.get_or_set("elasticsearch", params, fetch_func)
        assert result == {"data": "fetched"}
        assert not fetch_called


class TestL1CacheWithAsync:
    """Test L1 cache with async operations."""

    @pytest.mark.asyncio
    async def test_async_get_or_set(self):
        """Test get_or_set with async fetch function."""
        cache = L1Cache()
        params = {"project": "test"}

        async def fetch_func():
            await asyncio.sleep(0.01)
            return {"data": "fetched"}

        result = await cache.get_or_set("elasticsearch", params, fetch_func)
        assert result == {"data": "fetched"}

    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """Test concurrent access to same cache key."""
        cache = L1Cache()
        params = {"project": "test"}

        access_count = 0

        async def fetch_func():
            nonlocal access_count
            access_count += 1
            await asyncio.sleep(0.01)
            return {"data": f"fetch_{access_count}"}

        # Concurrent requests
        tasks = [
            cache.get_or_set("elasticsearch", params, fetch_func)
            for _ in range(5)
        ]

        results = await asyncio.gather(*tasks)

        # All results should be the same (first fetch)
        assert all(r == results[0] for r in results)
        # With L1 cache, fetch could be called multiple times
        # (L1 doesn't prevent duplicate fetches, use SingleFlight for that)


class TestCachedDecorator:
    """Test the @cached decorator."""

    @pytest.mark.asyncio
    async def test_cached_decorator_basic(self):
        """Test @cached decorator caches results."""
        call_count = 0

        @cached("elasticsearch")
        async def get_data(project):
            nonlocal call_count
            call_count += 1
            return {"project": project, "count": call_count}

        # First call
        result1 = await get_data("test-project")
        assert result1["project"] == "test-project"
        assert result1["count"] == 1

        # Second call should use cache
        result2 = await get_data("test-project")
        assert result2["project"] == "test-project"
        assert result2["count"] == 1  # Not incremented

        # Different params should not use cache
        result3 = await get_data("other-project")
        assert result3["count"] == 2  # New call

    @pytest.mark.asyncio
    async def test_cached_decorator_with_kwargs(self):
        """Test @cached decorator with keyword arguments."""
        call_count = 0

        @cached("prometheus")
        async def get_metrics(project, time_range="1h"):
            nonlocal call_count
            call_count += 1
            return {"project": project, "range": time_range, "count": call_count}

        # First call
        result1 = await get_metrics("test", time_range="1h")
        assert result1["count"] == 1

        # Same params should use cache
        result2 = await get_metrics("test", time_range="1h")
        assert result2["count"] == 1

        # Different params should not use cache
        result3 = await get_metrics("test", time_range="24h")
        assert result3["count"] == 2


class TestCacheMiddleware:
    """Test request cache middleware."""

    def test_middleware_initialization(self):
        """Test middleware can be initialized."""
        from app.cache.l1_cache import RequestCacheMiddleware

        async def app(scope, receive, send):
            await send({"type": "http.response.start", "headers": [], "status": 200})

        middleware = RequestCacheMiddleware(app)
        assert middleware is not None

    @pytest.mark.asyncio
    async def test_middleware_clears_cache(self):
        """Test middleware clears cache before each request."""
        from app.cache.l1_cache import RequestCacheMiddleware, L1Cache

        async def app(scope, receive, send):
            # Check cache is clear
            cache = L1Cache()
            summary = cache.get_summary()
            assert summary["cache_size"] == 0
            await send({"type": "http.response.start", "headers": [], "status": 200})

        middleware = RequestCacheMiddleware(app)

        scope = {"type": "http"}
        receive = lambda: None
        send = lambda message: None

        await middleware(scope, receive, send)


class TestCacheScenarios:
    """Test real-world cache scenarios."""

    @pytest.mark.asyncio
    async def test_overview_page_deduplication(self):
        """Test deduplication of overview page data fetches."""
        cache = L1Cache()

        fetch_count = {"es": 0, "prom": 0, "k8s": 0}

        async def fetch_es_health(project):
            fetch_count["es"] += 1
            await asyncio.sleep(0.01)
            return {"status": "green"}

        async def fetch_prom_metrics(project):
            fetch_count["prom"] += 1
            await asyncio.sleep(0.01)
            return {"requests": 100}

        async def fetch_k8s_pods(project):
            fetch_count["k8s"] += 1
            await asyncio.sleep(0.01)
            return {"pods": 3}

        # Simulate overview page fetching data from multiple sources
        # Each source might be called multiple times by different components
        project = "test-project"

        # First set of calls
        await cache.get_or_set("elasticsearch", {"project": project}, fetch_es_health, project)
        await cache.get_or_set("prometheus", {"project": project}, fetch_prom_metrics, project)
        await cache.get_or_set("kubernetes", {"project": project}, fetch_k8s_pods, project)

        # Second set of calls (should use cache)
        await cache.get_or_set("elasticsearch", {"project": project}, fetch_es_health, project)
        await cache.get_or_set("prometheus", {"project": project}, fetch_prom_metrics, project)
        await cache.get_or_set("kubernetes", {"project": project}, fetch_k8s_pods, project)

        # Each source should only be fetched once
        assert fetch_count["es"] == 1
        assert fetch_count["prom"] == 1
        assert fetch_count["k8s"] == 1

        # Cache summary
        summary = cache.get_summary()
        assert summary["total_hits"] == 3
        assert summary["total_misses"] == 3
        assert summary["hit_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_different_params_same_source(self):
        """Test different parameters result in different cache entries."""
        cache = L1Cache()

        fetch_calls = []

        async def fetch_logs(project, time_range):
            fetch_calls.append((project, time_range))
            await asyncio.sleep(0.01)
            return {"logs": f"{project}-{time_range}"}

        # Fetch different time ranges for same project
        result1 = await cache.get_or_set("elasticsearch", {"project": "test", "time_range": "1h"}, fetch_logs, "test", "1h")
        result2 = await cache.get_or_set("elasticsearch", {"project": "test", "time_range": "24h"}, fetch_logs, "test", "24h")
        result3 = await cache.get_or_set("elasticsearch", {"project": "test", "time_range": "1h"}, fetch_logs, "test", "1h")

        # First two should result in fetches, third should use cache
        assert len(fetch_calls) == 2
        assert result1 == result3  # Same result from cache
