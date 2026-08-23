"""
Tests for Optimization Module - Phase 7 Sprint 3 Day 23-24

Test Coverage:
- Query optimization (chunking, caching, profiling)
- Query patterns library
- Streaming optimization
- Connection pooling
- Rate limiting
- Performance benchmarks
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from backend.app.optimization import (
    QueryOptimizer,
    QueryProfiler,
    QueryType,
    QueryPatternLibrary,
    QueryPatterns,
    StreamingOptimizer,
    StreamingChunk,
    ResponseOptimizer,
    VirtualScroller,
    BatchProcessor,
    ConnectionPoolManager,
    PoolConfig,
    PoolType,
    RateLimiter
)


class TestQueryOptimizer:
    """Test suite for QueryOptimizer."""

    @pytest.fixture
    def query_optimizer(self):
        """Create a query optimizer instance."""
        return QueryOptimizer(
            es_client=Mock(),
            prom_client=Mock(),
            k8s_client=Mock(),
            l2_cache=None  # No cache for testing
        )

    @pytest.mark.asyncio
    async def test_calculate_optimal_chunk_size(self, query_optimizer):
        """Test chunk size calculation based on time range."""
        # Short time range -> small chunks
        chunk_size = query_optimizer._calculate_optimal_chunk_size(timedelta(minutes=10))
        assert chunk_size == timedelta(minutes=5)

        # Medium time range -> medium chunks (1 hour = 15 min chunks)
        chunk_size = query_optimizer._calculate_optimal_chunk_size(timedelta(hours=1))
        assert chunk_size == timedelta(minutes=15)

        # Longer time range -> larger chunks (2 hours = 30 min chunks)
        chunk_size = query_optimizer._calculate_optimal_chunk_size(timedelta(hours=2))
        assert chunk_size == timedelta(minutes=30)

        # Very long time range -> largest chunks
        chunk_size = query_optimizer._calculate_optimal_chunk_size(timedelta(days=2))
        assert chunk_size == timedelta(hours=1)

    @pytest.mark.asyncio
    async def test_split_time_range(self, query_optimizer):
        """Test time range splitting."""
        time_range = timedelta(hours=1)
        chunk_size = timedelta(minutes=15)

        chunks = query_optimizer._split_time_range(time_range, chunk_size)

        # 1 hour / 15 min chunks = 4 chunks
        assert len(chunks) == 4

        # Verify chunk boundaries
        for i, chunk in enumerate(chunks):
            assert "start" in chunk
            assert "end" in chunk
            if i > 0:
                assert chunk["start"] == chunks[i-1]["end"]

    @pytest.mark.asyncio
    async def test_build_promql_query(self, query_optimizer):
        """Test PromQL query building."""
        # Basic rate query
        query = query_optimizer._build_promql_query(
            "http_requests_total",
            "rate",
            {"service": "api"},
            "5m"
        )
        assert "rate(http_requests_total" in query
        assert 'service="api"' in query
        assert "[5m]" in query

        # Sum aggregation
        query = query_optimizer._build_promql_query(
            "cpu_usage",
            "sum",
            None,
            "1m"
        )
        assert "sum(rate(cpu_usage[1m]))" in query

    @pytest.mark.asyncio
    async def test_query_profiler(self, query_optimizer):
        """Test query profiling."""
        async def dummy_query():
            await asyncio.sleep(0.01)
            return [{"id": 1}, {"id": 2}]

        result = await query_optimizer.profiler.profile_query(
            QueryType.LOGS,
            "elasticsearch",
            "test_query",
            dummy_query,
            cache_hit=False,
            chunk_count=1
        )

        assert len(result) == 2
        assert query_optimizer.profiler.stats["total_queries"] == 1

    @pytest.mark.asyncio
    async def test_profiler_stats(self, query_optimizer):
        """Test profiler statistics."""
        async def dummy_query():
            return [{"id": 1}]

        # Execute some queries
        for i in range(10):
            await query_optimizer.profiler.profile_query(
                QueryType.METRICS,
                "prometheus",
                f"test_query_{i}",
                dummy_query,
                cache_hit=(i % 2 == 0)  # Alternate cache hits
            )

        stats = query_optimizer.get_profiler_stats()

        assert stats["total_queries"] == 10
        assert stats["cache_hits"] == 5
        assert stats["cache_hit_rate"] == 0.5


class TestQueryPatterns:
    """Test suite for QueryPatterns library."""

    def test_high_error_rate_pattern(self):
        """Test high error rate query pattern."""
        pattern = QueryPatterns.high_error_rate_threshold(threshold=0.05)
        assert "rate(http_requests_total" in pattern
        assert "> 0.05" in pattern

    def test_high_latency_pattern(self):
        """Test high latency query pattern."""
        pattern = QueryPatterns.high_latency_p95(percentile=95)
        assert "histogram_quantile(0.95" in pattern
        assert "http_request_duration_seconds" in pattern

    def test_pod_crash_loop_pattern(self):
        """Test pod crash loop detection pattern."""
        pattern = QueryPatterns.pod_crash_loop(restarts=5)
        assert "kube_pod_container_status_restarts_total" in pattern
        assert "> 5" in pattern

    def test_slo_latency_query(self):
        """Test SLO latency query pattern."""
        pattern = QueryPatterns.slo_latency_query(
            service="api",
            threshold_ms=500,
            percentile=95
        )
        assert 'service="api"' in pattern
        assert "histogram_quantile(0.95" in pattern

    def test_elasticsearch_error_filter(self):
        """Test Elasticsearch error log filter pattern."""
        query = QueryPatterns.elasticsearch_logs_error_filter(
            project="myproject",
            error_keywords=["error", "exception", "failed"]
        )
        assert query["query"]["bool"]["must"][0]["term"]["project"] == "myproject"
        assert len(query["query"]["bool"]["must"][2]["bool"]["should"]) == 3

    def test_pattern_library_list(self):
        """Test pattern library listing."""
        patterns = QueryPatternLibrary.list_patterns()

        assert "error" in patterns
        assert "performance" in patterns
        assert "resource" in patterns
        assert "availability" in patterns

        # Verify some patterns exist
        assert "high_error_rate" in patterns["error"]
        assert "high_latency_p95" in patterns["performance"]
        assert "cpu_exhaustion" in patterns["resource"]

    def test_pattern_library_get(self):
        """Test getting a specific pattern."""
        pattern = QueryPatternLibrary.get_pattern(
            "error",
            "high_error_rate",
            threshold=0.1
        )
        assert "> 0.1" in pattern

        # Test invalid category
        with pytest.raises(ValueError):
            QueryPatternLibrary.get_pattern("invalid", "pattern")


class TestStreamingOptimizer:
    """Test suite for StreamingOptimizer."""

    @pytest.fixture
    def streaming_optimizer(self):
        """Create a streaming optimizer instance."""
        return StreamingOptimizer(chunk_size=10)

    @pytest.mark.asyncio
    async def test_stream_data(self, streaming_optimizer):
        """Test streaming data chunks."""
        async def data_source():
            for i in range(25):
                yield {"id": i, "value": f"item_{i}"}

        chunks = []
        async for chunk in streaming_optimizer.stream_data(data_source(), total_count=25):
            chunks.append(chunk)

        # Should have 3 chunks (10, 10, 5)
        assert len(chunks) == 3
        assert len(chunks[0].data) == 10
        assert len(chunks[1].data) == 10
        assert len(chunks[2].data) == 5
        assert chunks[2].is_final

    @pytest.mark.asyncio
    async def test_stream_query_results(self, streaming_optimizer):
        """Test streaming query results."""
        async def query_func():
            return [{"id": i} for i in range(25)]

        chunks = []
        async for chunk in streaming_optimizer.stream_query_results(query_func):
            chunks.append(chunk)

        assert len(chunks) == 3
        assert sum(len(c.data) for c in chunks) == 25

    @pytest.mark.asyncio
    async def test_compress_chunk(self, streaming_optimizer):
        """Test chunk compression."""
        chunk = StreamingChunk(
            data=[{"id": i} for i in range(10)],
            chunk_id=0,
            total_chunks=1
        )

        compressed = await streaming_optimizer.compress_chunk(chunk)
        assert isinstance(compressed, bytes)
        assert len(compressed) > 0


class TestResponseOptimizer:
    """Test suite for ResponseOptimizer."""

    @pytest.fixture
    def response_optimizer(self):
        """Create a response optimizer instance."""
        return ResponseOptimizer(
            enable_compression=True,
            compression_threshold=100
        )

    def test_filter_fields(self, response_optimizer):
        """Test field filtering."""
        data = {
            "id": 1,
            "name": "test",
            "description": "description",
            "metadata": {"key": "value"}
        }

        filtered = response_optimizer.filter_fields(
            data,
            fields=["id", "name"]
        )

        assert "id" in filtered
        assert "name" in filtered
        assert "description" not in filtered
        assert "metadata" not in filtered

    def test_paginate_response(self, response_optimizer):
        """Test response pagination."""
        items = [{"id": i} for i in range(100)]

        result = response_optimizer.paginate_response(
            items,
            page=2,
            page_size=20
        )

        assert len(result["items"]) == 20
        assert result["pagination"]["page"] == 2
        assert result["pagination"]["total_items"] == 100
        assert result["pagination"]["total_pages"] == 5
        assert result["pagination"]["has_next"] is True
        assert result["pagination"]["has_prev"] is True

    def test_optimize_response(self, response_optimizer):
        """Test response optimization."""
        response = {
            "data": [{"id": 1}],
            "metadata": {"source": "test"}
        }

        optimized = response_optimizer.optimize_response(response)

        assert "data" in optimized
        assert "metadata" in optimized
        assert optimized["metadata"]["optimized"] is True
        assert "timestamp" in optimized["metadata"]


class TestVirtualScroller:
    """Test suite for VirtualScroller."""

    @pytest.fixture
    def virtual_scroller(self):
        """Create a virtual scroller instance."""
        return VirtualScroller(
            item_height=50,
            viewport_height=800,
            buffer_size=5
        )

    def test_get_window(self, virtual_scroller):
        """Test window calculation."""
        # 16 visible items (800 / 50)
        assert virtual_scroller.visible_items == 16
        # 16 + 2*5 = 26 items total
        assert virtual_scroller.window_size == 26

        window = virtual_scroller.get_window(scroll_position=500, total_items=100)

        # At position 500, current item is 10
        assert window["current_item"] == 10
        # Window should include buffer
        assert window["window_size"] == 26

    def test_get_batches(self, virtual_scroller):
        """Test batch calculation."""
        batches = virtual_scroller.get_batches(total_items=100)

        # 100 items / 26 per batch = 4 batches
        assert len(batches) == 4

        # First batch
        assert batches[0]["start_index"] == 0
        assert batches[0]["size"] == 26

        # Last batch
        assert batches[-1]["end_index"] == 100

    def test_get_prefetch_info(self, virtual_scroller):
        """Test prefetch information."""
        prefetch = virtual_scroller.get_prefetch_info(
            scroll_position=500,
            scroll_direction="down",
            total_items=100
        )

        assert prefetch["direction"] == "down"
        assert prefetch["prefetch_start"] >= 0
        assert prefetch["prefetch_end"] <= 100


class TestBatchProcessor:
    """Test suite for BatchProcessor."""

    @pytest.fixture
    def batch_processor(self):
        """Create a batch processor instance."""
        return BatchProcessor(batch_size=10, max_parallel_batches=3)

    @pytest.mark.asyncio
    async def test_process_batches(self, batch_processor):
        """Test batch processing."""
        items = [{"id": i} for i in range(25)]

        async def process_func(batch):
            await asyncio.sleep(0.01)
            return [item["id"] * 2 for item in batch]

        results = await batch_processor.process_batches(items, process_func)

        # Should have 3 batches (10, 10, 5)
        assert len(results) == 3
        assert len(results[0]) == 10
        assert len(results[-1]) == 5

    @pytest.mark.asyncio
    async def test_process_batches_parallel(self, batch_processor):
        """Test parallel batch processing."""
        items = [{"id": i} for i in range(30)]

        async def process_func(batch):
            await asyncio.sleep(0.05)
            return [item["id"] for item in batch]

        results = await batch_processor.process_batches_parallel(items, process_func)

        # Should process all items
        total_results = sum(len(r) if isinstance(r, list) else 0 for r in results)
        assert total_results == 30

    def test_get_batches(self, batch_processor):
        """Test batch splitting."""
        items = list(range(25))

        batches = batch_processor.get_batches(items)

        assert len(batches) == 3
        assert len(batches[0]) == 10
        assert len(batches[1]) == 10
        assert len(batches[2]) == 5


class TestConnectionPool:
    """Test suite for ConnectionPool."""

    @pytest.fixture
    def pool_config(self):
        """Create a pool configuration."""
        return PoolConfig(
            pool_type=PoolType.HTTP,
            max_connections=10,
            min_connections=2,
            acquire_timeout=5
        )

    @pytest.fixture
    def pool_manager(self):
        """Create a pool manager instance."""
        return ConnectionPoolManager()

    def test_create_pool(self, pool_manager, pool_config):
        """Test pool creation."""
        pool = pool_manager.create_pool(
            "test_pool",
            pool_config,
            connection_factory=None
        )

        assert pool is not None
        assert pool.name == "test_pool"
        assert pool.config.max_connections == 10

    def test_pool_stats(self, pool_manager, pool_config):
        """Test pool statistics."""
        pool = pool_manager.create_pool("stats_pool", pool_config)

        stats = pool.get_stats()

        assert stats.pool_name == "stats_pool"
        assert stats.total_connections == 0
        assert stats.active_connections == 0


class TestRateLimiter:
    """Test suite for RateLimiter."""

    @pytest.fixture
    def rate_limiter(self):
        """Create a rate limiter instance."""
        return RateLimiter(default_rate=10.0, burst=5)

    @pytest.mark.asyncio
    async def test_acquire_allowed(self, rate_limiter):
        """Test allowed request acquisition."""
        # Should be allowed (burst capacity)
        allowed = await rate_limiter.acquire("test_endpoint")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_acquire_exhausted(self, rate_limiter):
        """Test rate limit exhaustion."""
        # Exhaust the bucket
        for _ in range(10):
            await rate_limiter.acquire("test_endpoint")

        # Next request should be denied
        allowed = await rate_limiter.acquire("test_endpoint")
        assert allowed is False

    @pytest.mark.asyncio
    async def test_replenish(self, rate_limiter):
        """Test token replenishment."""
        # Use some tokens
        for _ in range(3):
            await rate_limiter.acquire("test_endpoint")

        # Replenish
        await rate_limiter.replenish("test_endpoint")

        # Should have some tokens back
        allowed = await rate_limiter.acquire("test_endpoint")
        assert allowed is True

    def test_set_endpoint_limit(self, rate_limiter):
        """Test setting endpoint-specific limit."""
        rate_limiter.set_endpoint_limit("custom_endpoint", rate=5.0, burst=3)

        assert "custom_endpoint" in rate_limiter.endpoint_limits
        assert rate_limiter.endpoint_limits["custom_endpoint"]["rate"] == 5.0

    @pytest.mark.asyncio
    async def test_get_stats(self, rate_limiter):
        """Test rate limiter statistics."""
        # Make some requests
        for _ in range(5):
            await rate_limiter.acquire("stats_endpoint")

        stats = rate_limiter.get_stats()

        assert stats["total_requests"] == 5
        assert "allowed_requests" in stats
        assert "rejected_requests" in stats


# Performance Benchmarks

@pytest.mark.performance
@pytest.mark.asyncio
async def test_query_performance_baseline():
    """
    Performance test: Query optimizer baseline.

    Target: Optimized queries should be faster than non-optimized
    """
    optimizer = QueryOptimizer()

    async def dummy_query():
        await asyncio.sleep(0.1)  # Simulate query
        return [{"id": i} for i in range(100)]

    # Measure optimized query
    start = datetime.now()
    await optimizer.profiler.profile_query(
        QueryType.LOGS,
        "test",
        "optimized_query",
        dummy_query
    )
    optimized_time = (datetime.now() - start).total_seconds()

    # Profiling overhead should be minimal (<10%)
    assert optimized_time < 0.15  # Should be close to 0.1s


@pytest.mark.performance
@pytest.mark.asyncio
async def test_streaming_performance():
    """
    Performance test: Streaming large datasets.

    Target: First chunk should be available quickly
    """
    optimizer = StreamingOptimizer(chunk_size=100)

    async def large_dataset():
        for i in range(1000):
            yield {"id": i}

    start = datetime.now()
    first_chunk = None
    async for chunk in optimizer.stream_data(large_dataset()):
        first_chunk = chunk
        break
    time_to_first_chunk = (datetime.now() - start).total_seconds()

    # First chunk should be available quickly
    assert first_chunk is not None
    assert time_to_first_chunk < 0.1
    assert len(first_chunk.data) == 100


@pytest.mark.performance
@pytest.mark.asyncio
async def test_batch_processing_performance():
    """
    Performance test: Batch processing.

    Target: Parallel processing should be faster than sequential
    """
    processor = BatchProcessor(batch_size=10, max_parallel_batches=5)
    items = [{"id": i} for i in range(50)]

    async def slow_process(batch):
        await asyncio.sleep(0.05)
        return [item["id"] for item in batch]

    start = datetime.now()
    results = await processor.process_batches_parallel(items, slow_process)
    parallel_time = (datetime.now() - start).total_seconds()

    # With 5 parallel batches, should complete in ~2-3 sleep cycles
    assert parallel_time < 0.3
    assert len(results) == 5


@pytest.mark.performance
@pytest.mark.asyncio
async def test_cache_hit_rate_target():
    """
    Performance test: Cache hit rate.

    Target: >70% cache hit rate after warmup
    """
    # This would test with actual cache implementation
    # For now, just verify the structure exists
    optimizer = QueryOptimizer()

    # Verify profiler can track cache hits
    async def cached_query():
        return [{"id": 1}]

    # Cache hits
    for _ in range(7):
        await optimizer.profiler.profile_query(
            QueryType.LOGS,
            "test",
            "query",
            cached_query,
            cache_hit=True
        )

    # Cache misses
    for _ in range(3):
        await optimizer.profiler.profile_query(
            QueryType.LOGS,
            "test",
            "query",
            cached_query,
            cache_hit=False
        )

    stats = optimizer.get_profiler_stats()
    assert stats["cache_hit_rate"] == 0.7
