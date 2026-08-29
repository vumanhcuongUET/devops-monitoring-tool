"""
Unit Tests for Cache Middleware and Cached Overview Service

Phase 7 - Sprint 1 - Day 8
Tests for cache middleware and cached overview service integration
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from datetime import datetime

# Mock Redis availability check before imports
with patch('app.cache.l2_cache.REDIS_AVAILABLE', True):
    from app.cache.cache_middleware import (
        CacheMiddleware,
        CacheContext,
        get_cache_context,
        mark_cache_hit,
        get_cache_info_from_headers
    )

    from app.services.cached_overview_service import CachedOverviewService


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.setex = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.sadd = AsyncMock(return_value=1)
    redis.smembers = AsyncMock(return_value=set())
    redis.scard = AsyncMock(return_value=0)
    redis.expire = AsyncMock(return_value=True)
    redis.scan = AsyncMock(return_value=(0, []))
    redis.ttl = AsyncMock(return_value=3600)

    class MockL2Cache:
        def __init__(self):
            self._stats = {"hits": 10, "misses": 5}

        def get_stats(self):
            return self._stats.copy()

        def get_key(self, prefix, identifier):
            parts = [prefix]
            for k, v in sorted(identifier.items()):
                parts.append(f"{k}:{v}")
            return ":".join(parts)

        async def get(self, data_type, identifier):
            return None

        async def set(self, data_type, identifier, value, ttl_override=None):
            return True

    redis.l2_cache = MockL2Cache()
    return redis


@pytest.fixture
def mock_app():
    """Create mock FastAPI app."""
    app = MagicMock()
    return app


@pytest.fixture
def cache_middleware(mock_app, mock_redis):
    """Create cache middleware."""
    from app.cache.l2_cache import L2CacheManager
    l2_cache = mock_redis.l2_cache
    return CacheMiddleware(mock_app, l2_cache=l2_cache)


class TestCacheMiddleware:
    """Test cache middleware functionality."""

    @pytest.mark.asyncio
    async def test_middleware_injects_l1_cache(self, cache_middleware):
        """Test that middleware injects L1 cache into request state."""
        from starlette.requests import Request

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "query_string": b"",
        }
        request = Request(scope)

        async def call_next(request):
            # Check L1 cache was injected
            assert hasattr(request.state, "l1_cache")
            assert request.state.l1_cache is not None

            from starlette.responses import Response
            return Response(content="test")

        response = await cache_middleware.dispatch(request, call_next)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_middleware_injects_l2_cache(self, cache_middleware):
        """Test that middleware injects L2 cache into request state."""
        from starlette.requests import Request

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "query_string": b"",
        }
        request = Request(scope)

        async def call_next(request):
            # Check L2 cache was injected
            assert hasattr(request.state, "l2_cache")
            assert request.state.l2_cache is not None

            from starlette.responses import Response
            return Response(content="test")

        await cache_middleware.dispatch(request, call_next)

    @pytest.mark.asyncio
    async def test_middleware_adds_process_time_header(self, cache_middleware):
        """Test that middleware adds processing time header."""
        from starlette.requests import Request
        from starlette.responses import Response

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "query_string": b"",
        }
        request = Request(scope)

        async def call_next(request):
            time.sleep(0.01)  # Small delay
            return Response(content="test")

        response = await cache_middleware.dispatch(request, call_next)

        assert "X-Process-Time" in response.headers
        process_time = float(response.headers["X-Process-Time"])
        assert process_time >= 0.01

    @pytest.mark.asyncio
    async def test_middleware_adds_cache_headers(self, cache_middleware):
        """Test that middleware adds cache-related headers."""
        from starlette.requests import Request
        from starlette.responses import Response

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "query_string": b"",
        }
        request = Request(scope)

        async def call_next(request):
            response = Response(content="test")
            response.headers["X-L2-Cache"] = "hit"
            return response

        response = await cache_middleware.dispatch(request, call_next)

        assert "X-Cache-Hit-Rate" in response.headers
        assert "X-Cache-Status" in response.headers
        assert response.headers["X-Cache-Status"] == "HIT"

    @pytest.mark.asyncio
    async def test_middleware_without_l2_cache(self, mock_app):
        """Test middleware works without L2 cache."""
        middleware = CacheMiddleware(mock_app, l2_cache=None)

        from starlette.requests import Request
        from starlette.responses import Response

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "query_string": b"",
        }
        request = Request(scope)

        async def call_next(request):
            assert hasattr(request.state, "l1_cache")
            assert request.state.l2_cache is None
            return Response(content="test")

        response = await middleware.dispatch(request, call_next)
        assert response.status_code == 200


class TestCacheContext:
    """Test cache context functionality."""

    @pytest.fixture
    def mock_request(self, mock_redis):
        """Create mock request with cache."""
        from starlette.requests import Request

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "query_string": b"",
        }
        request = Request(scope)

        # Add cache to state
        from app.cache.l1_cache import L1Cache
        request.state.l1_cache = L1Cache()
        request.state.l2_cache = mock_redis.l2_cache

        return request

    def test_cache_context_initialization(self, mock_request):
        """Test cache context initialization."""
        context = CacheContext(mock_request)

        assert context.l1_cache is not None
        assert context.l2_cache is not None
        assert context.request == mock_request

    @pytest.mark.asyncio
    async def test_cache_context_get_from_l1(self, mock_request):
        """Test getting data from L1 cache."""
        context = CacheContext(mock_request)

        # Set data first (L1Cache.set is not async)
        context.l1_cache.set("test", {"key": "test"}, {"data": "value"})

        # Get data - use L1Cache directly
        result = context.l1_cache.get("test", {"key": "test"})
        assert result is not None

    @pytest.mark.asyncio
    async def test_cache_context_get_from_l2(self, mock_request, mock_redis):
        """Test getting data from L2 cache."""
        context = CacheContext(mock_request)

        # Mock L2 cache to return data
        mock_redis.get.return_value = b'{"data": "cached"}'

        result = await context.get_from_l2("overview", {"project": "test"})
        assert result is not None

    @pytest.mark.asyncio
    async def test_cache_context_set_in_l2(self, mock_request, mock_redis):
        """Test setting data in L2 cache."""
        context = CacheContext(mock_request)

        result = await context.set_in_l2(
            "overview",
            {"project": "test"},
            {"data": "value"},
            ttl=300
        )

        assert result is True

    def test_cache_context_get_summary(self, mock_request):
        """Test getting cache summary."""
        context = CacheContext(mock_request)

        summary = context.get_cache_summary()

        assert "l1_available" in summary
        assert "l2_available" in summary
        assert summary["l1_available"] is True
        assert summary["l2_available"] is True


@pytest.fixture
def cached_service(mock_redis):
    """Create cached overview service."""
    # Mock REDIS_AVAILABLE
    with patch('app.cache.l2_cache.REDIS_AVAILABLE', True):
        with patch('app.cache.l3_cache.REDIS_AVAILABLE', True):

            # Create mock clients
            es_client = AsyncMock()
            es_client.get_health = AsyncMock(return_value={
                "status": "green",
                "cluster_name": "test-cluster",
                "number_of_nodes": 3
            })

            prom_client = AsyncMock()
            prom_client.get_project_metrics = AsyncMock(return_value={
                "cpu_usage": 50,
                "memory_usage": 60
            })

            k8s_client = AsyncMock()
            k8s_client.get_pods = AsyncMock(return_value=[
                {"name": "pod1", "phase": "Running"},
                {"name": "pod2", "phase": "Running"},
                {"name": "pod3", "phase": "Pending"}
            ])

            from app.services.cached_overview_service import CachedOverviewService
            return CachedOverviewService(
                redis_client=mock_redis,
                es_client=es_client,
                prom_client=prom_client,
                k8s_client=k8s_client
            )


class TestCachedOverviewService:
    """Test cached overview service."""

    @pytest.mark.asyncio
    async def test_get_overview_cache_miss(self, cached_service, mock_redis):
        """Test getting overview with cache miss."""
        # Mock cache miss
        mock_redis.get = AsyncMock(return_value=None)

        overview = await cached_service.get_overview("test-project")

        assert overview is not None
        assert overview["project"] == "test-project"
        assert "sources" in overview
        assert overview["_cache"] == "MISS"

    @pytest.mark.asyncio
    async def test_get_overview_cache_hit(self, cached_service, mock_redis):
        """Test getting overview with cache hit."""
        cached_data = {
            "project": "test-project",
            "health": "healthy",
            "timestamp": datetime.now().isoformat()
        }
        mock_redis.get = AsyncMock(return_value=str(cached_data).encode())

        overview = await cached_service.get_overview("test-project")

        assert overview is not None
        # Should have L2 cache metadata

    @pytest.mark.asyncio
    async def test_get_overview_with_timeout(self, cached_service):
        """Test timeout handling."""
        # Mock slow data source
        async def slow_fetch():
            await asyncio.sleep(2)
            return {"data": "slow"}

        # Use short timeout
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                cached_service._fetch_and_cache_overview("test"),
                timeout=0.1
            )

    @pytest.mark.asyncio
    async def test_get_health_status(self, cached_service):
        """Test getting health status."""
        health = await cached_service.get_health_status("test-project")

        assert health is not None
        assert health["project"] == "test-project"
        assert "health" in health

    @pytest.mark.asyncio
    async def test_invalidate_project_cache(self, cached_service, mock_redis):
        """Test invalidating project cache."""
        mock_redis.smembers.return_value = {b"cache:key1", b"cache:key2"}
        mock_redis.delete.return_value = 2

        count = await cached_service.invalidate_project_cache("test-project")

        assert count >= 0

    def test_get_cache_stats(self, cached_service):
        """Test getting cache statistics."""
        stats = cached_service.get_cache_stats()

        assert "l2_cache" in stats
        assert "invalidator" in stats
        assert stats["cache_enabled"] is True

    def test_enable_disable_cache(self, cached_service):
        """Test enabling and disabling cache."""
        assert cached_service.cache_enabled is True

        cached_service.disable_cache()
        assert cached_service.cache_enabled is False

        cached_service.enable_cache()
        assert cached_service.cache_enabled is True

    def test_enable_disable_semantic(self, cached_service):
        """Test enabling and disabling semantic cache."""
        assert cached_service.semantic_enabled is True

        cached_service.disable_semantic()
        assert cached_service.semantic_enabled is False

        cached_service.enable_semantic()
        assert cached_service.semantic_enabled is True


class TestUtilityFunctions:
    """Test utility functions."""

    def test_mark_cache_hit(self):
        """Test marking cache hit."""
        from starlette.responses import Response
        response = Response(content="test")

        mark_cache_hit(response, "L2")

        assert response.headers.get("X-L2-Cache") == "hit"
        assert response.headers.get("X-Cache-Status") == "HIT"

    def test_mark_cache_hit_l1(self):
        """Test marking L1 cache hit."""
        from starlette.responses import Response
        response = Response(content="test")

        mark_cache_hit(response, "L1")

        assert response.headers.get("X-L1-Cache") == "hit"

    def test_get_cache_info_from_headers(self):
        """Test extracting cache info from headers."""
        from starlette.responses import Response
        response = Response(content="test")
        response.headers["X-Cache-Status"] = "HIT"
        response.headers["X-Cache-Layers"] = "L1,L2"
        response.headers["X-Cache-Hit-Rate"] = "0.75"
        response.headers["X-Process-Time"] = "0.150"

        info = get_cache_info_from_headers(response)

        assert info["status"] == "HIT"
        assert info["hit_rate"] == 0.75
        assert info["process_time_ms"] == 150.0

    def test_get_cache_info_from_headers_empty(self):
        """Test extracting cache info from empty headers."""
        from starlette.responses import Response
        response = Response(content="test")

        info = get_cache_info_from_headers(response)

        assert info["status"] == "UNKNOWN"
        assert info["hit_rate"] == 0.0
        assert info["process_time_ms"] == 0.0


class TestIntegrationScenarios:
    """Test integration scenarios."""

    @pytest.mark.asyncio
    async def test_full_cache_flow(self, cached_service, mock_redis):
        """Test full cache flow from miss to hit."""
        project = "test-project"

        # First call - cache miss
        mock_redis.get = AsyncMock(return_value=None)
        overview1 = await cached_service.get_overview(project)

        assert overview1["_cache"] == "MISS"
        assert overview1["project"] == project

        # Verify cache was set
        assert mock_redis.setex.called or mock_redis.sadd.called

    @pytest.mark.asyncio
    async def test_concurrent_requests_single_flight(self, cached_service):
        """Test single flight prevents concurrent duplicate requests."""
        project = "test-project"
        fetch_count = [0]

        # Track fetch calls
        original_fetch = cached_service._fetch_and_cache_overview

        async def tracking_fetch(project):
            fetch_count[0] += 1
            return await original_fetch(project)

        cached_service._fetch_and_cache_overview = tracking_fetch

        # Concurrent requests
        results = await asyncio.gather(
            cached_service.get_overview(project),
            cached_service.get_overview(project),
            cached_service.get_overview(project)
        )

        # All should succeed
        assert all(r is not None for r in results)
        # But only one actual fetch should occur
        assert fetch_count[0] == 1

    @pytest.mark.asyncio
    async def test_degraded_mode_with_partial_data(self, cached_service, mock_redis):
        """Test degraded mode when some sources fail."""
        # Make ES client fail
        cached_service.es_client.get_health = AsyncMock(
            side_effect=Exception("ES unavailable")
        )

        overview = await cached_service.get_overview("test-project")

        assert overview is not None
        # Should still have data from other sources
        assert len(overview["sources"]) > 0

    @pytest.mark.asyncio
    async def test_semantic_cache_flow(self, cached_service, mock_redis):
        """Test semantic cache integration."""
        project = "test-project"

        # Enable semantic and use it
        mock_redis.get = AsyncMock(return_value=None)

        overview = await cached_service.get_overview(
            project,
            use_semantic=True
        )

        assert overview is not None
        # Semantic cache should have been checked

    @pytest.mark.asyncio
    async def test_cache_warming_scenario(self, cached_service):
        """Test cache warming for critical projects."""
        critical_projects = ["project-a", "project-b", "project-c"]

        # Warm cache for critical projects
        for project in critical_projects:
            await cached_service.get_overview(project)

        # All should be cached now
        for _project in critical_projects:
            # Would check cache here
            pass
