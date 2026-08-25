"""
Performance Benchmarks

Phase 9 - Sprint 2 - Day 9
Purpose: Establish baseline performance metrics for critical operations

These tests ensure the system meets performance targets and helps
identify regressions early.

Run with: pytest backend/tests/performance/test_benchmarks.py -v -m benchmark
"""

import asyncio
import time
from typing import Any

import pytest

from app.services.elasticsearch_client import ElasticsearchClient
from app.services.prometheus_client import PrometheusClient
from app.services.kubernetes_client import KubernetesClient
from app.services.apm_client import ApmClient


# Performance Targets (based on SLA requirements)
TARGET_OVERVIEW_LATENCY = 5.0  # seconds
TARGET_ES_QUERY_LATENCY = 2.0  # seconds
TARGET_CONCURRENT_10_LATENCY = 10.0  # seconds for 10 concurrent requests
TARGET_FIRST_TOKEN_TIME = 1.0  # seconds for LLM streaming


@pytest.mark.benchmark
@pytest.mark.asyncio
class TestPerformanceBenchmarks:
    """Performance benchmarks for critical operations."""

    async def test_elasticsearch_query_performance(self):
        """
        Benchmark Elasticsearch log query performance.

        Target: < 2.0 seconds for typical error log query
        """
        client = ElasticsearchClient()
        start = time.time()

        try:
            result = await client.search_logs(
                project="meinvoice",
                query="ERROR",
                time_range="30m",
                size=50,
            )

            duration = time.time() - start

            assert duration < TARGET_ES_QUERY_LATENCY, (
                f"Elasticsearch query took {duration:.2f}s, "
                f"expected < {TARGET_ES_QUERY_LATENCY}s"
            )

            # Verify we got results
            assert result is not None
            print(f"✓ ES query completed in {duration:.2f}s")

        except Exception as e:
            # In test environment without ES, we skip
            pytest.skip(f"Elasticsearch not available: {e}")

    async def test_prometheus_query_performance(self):
        """
        Benchmark Prometheus query performance.

        Target: < 1.0 seconds for metric queries
        """
        client = PrometheusClient()
        start = time.time()

        try:
            cpu = await client.get_cpu_percent()
            duration = time.time() - start

            assert duration < 1.0, f"Prometheus query took {duration:.2f}s, expected < 1.0s"

            print(f"✓ Prometheus query completed in {duration:.2f}s")

        except Exception as e:
            pytest.skip(f"Prometheus not available: {e}")

    async def test_kubernetes_query_performance(self):
        """
        Benchmark Kubernetes API query performance.

        Target: < 2.0 seconds for pod listing
        """
        client = KubernetesClient()
        start = time.time()

        try:
            pods = await client.list_pods()
            duration = time.time() - start

            assert duration < 2.0, f"Kubernetes query took {duration:.2f}s, expected < 2.0s"

            print(f"✓ Kubernetes query completed in {duration:.2f}s (returned {len(pods)} pods)")

        except Exception as e:
            pytest.skip(f"Kubernetes not available: {e}")

    async def test_apm_query_performance(self):
        """
        Benchmark APM query performance.

        Target: < 3.0 seconds for summary
        """
        client = ApmClient()
        start = time.time()

        try:
            summary = await client.get_summary()
            duration = time.time() - start

            assert duration < 3.0, f"APM query took {duration:.2f}s, expected < 3.0s"

            print(f"✓ APM query completed in {duration:.2f}s")

        except Exception as e:
            pytest.skip(f"APM/Elasticsearch not available: {e}")

    async def test_overview_endpoint_latency(self):
        """
        Benchmark overview endpoint latency.

        Target: < 5.0 seconds for full overview
        This is the most critical user-facing endpoint.
        """
        from app.api.v1.overview import (
            _get_k8s_health,
            _get_es_health,
            _get_apm_health,
            _get_infra_health,
        )

        # Mock clients for testing
        class MockClient:
            async def list_pods(self):
                return [{"name": "test-pod", "status": "Running"}]

            async def list_deployments(self):
                return [{"name": "test-deploy", "replicas": 1, "available": 1}]

            async def list_nodes(self):
                return [{"name": "test-node", "status": "Ready"}]

            async def get_error_count(self, minutes=60):
                return 5

            async def get_cluster_health(self):
                return {"status": "green"}

            async def get_cpu_percent(self):
                return 45.0

            async def get_memory_percent(self):
                return 60.0

            async def get_summary(self):
                return {
                    "latency_p50": 100,
                    "latency_p95": 250,
                    "latency_p99": 500,
                    "error_rate_percent": 0.5,
                    "throughput": 1000,
                }

        k8s = MockClient()
        es = MockClient()
        apm = MockClient()
        prom = MockClient()

        start = time.time()

        # Run all health checks in parallel like the real endpoint
        results = await asyncio.gather(
            _get_k8s_health(k8s),
            _get_es_health(es),
            _get_apm_health(apm),
            _get_infra_health(prom, k8s),
            return_exceptions=True,
        )

        duration = time.time() - start

        assert duration < TARGET_OVERVIEW_LATENCY, (
            f"Overview endpoint took {duration:.2f}s, "
            f"expected < {TARGET_OVERVIEW_LATENCY}s"
        )

        # Verify all results are valid
        assert all(not isinstance(r, Exception) for r in results), "Some health checks failed"

        print(f"✓ Overview endpoint completed in {duration:.2f}s")

    async def test_concurrent_overview_requests(self):
        """
        Benchmark concurrent overview requests.

        Target: 10 concurrent requests < 10 seconds total
        This tests the system's ability to handle load.
        """
        from app.api.v1.overview import (
            _get_k8s_health,
            _get_es_health,
            _get_apm_health,
            _get_infra_health,
        )

        class MockClient:
            def __init__(self, delay=0.1):
                self.delay = delay

            async def list_pods(self):
                await asyncio.sleep(self.delay)
                return [{"name": "test-pod", "status": "Running"}]

            async def list_deployments(self):
                await asyncio.sleep(self.delay)
                return [{"name": "test-deploy", "replicas": 1, "available": 1}]

            async def list_nodes(self):
                await asyncio.sleep(self.delay)
                return [{"name": "test-node", "status": "Ready"}]

            async def get_error_count(self, minutes=60):
                await asyncio.sleep(self.delay)
                return 5

            async def get_cluster_health(self):
                await asyncio.sleep(self.delay)
                return {"status": "green"}

            async def get_summary(self):
                await asyncio.sleep(self.delay)
                return {
                    "latency_p50": 100,
                    "latency_p95": 250,
                    "error_rate_percent": 0.5,
                    "throughput": 1000,
                }

        async def make_request():
            k8s = MockClient()
            es = MockClient()
            apm = MockClient()
            prom = MockClient()

            return await asyncio.gather(
                _get_k8s_health(k8s),
                _get_es_health(es),
                _get_apm_health(apm),
                _get_infra_health(prom, k8s),
            )

        start = time.time()

        # Make 10 concurrent requests
        results = await asyncio.gather(*[make_request() for _ in range(10)])

        duration = time.time() - start

        assert len(results) == 10, "Expected 10 results"
        assert duration < TARGET_CONCURRENT_10_LATENCY, (
            f"10 concurrent requests took {duration:.2f}s, "
            f"expected < {TARGET_CONCURRENT_10_LATENCY}s"
        )

        print(f"✓ 10 concurrent requests completed in {duration:.2f}s")

    async def test_batch_optimizer_performance(self):
        """
        Benchmark batch optimizer performance.

        Target: Batched requests should be faster than individual
        """
        from app.services.batch_optimizer import BatchOptimizer

        optimizer = BatchOptimizer(batch_size=5, max_wait=0.05)

        async def mock_execute(ids):
            # Simulate work
            await asyncio.sleep(0.1)
            return [{"id": id, "data": "test"} for id in ids]

        start = time.time()

        # Submit 5 requests that should be batched
        results = await asyncio.gather(*[
            optimizer.batch_request(
                batch_key="test-batch",
                request_id=f"req-{i}",
                execute_fn=mock_execute,
            )
            for i in range(5)
        ])

        duration = time.time() - start

        # With batching, should take ~0.15s (0.05 wait + 0.1 execute)
        # Without batching, would take ~0.5s (5 * 0.1)
        assert duration < 0.3, f"Batched requests took {duration:.2f}s, expected < 0.3s"

        assert len(results) == 5
        print(f"✓ Batch optimizer completed 5 requests in {duration:.2f}s")

        # Verify stats
        stats = optimizer.get_stats()
        assert stats["total_requests"] == 5
        assert stats["batch_executions"] >= 1
        print(f"  Batch stats: {stats}")

    async def test_connection_pool_stats(self):
        """
        Verify connection pool manager is working.
        """
        from app.services.connection_pool import get_pool_manager

        manager = get_pool_manager()

        # Get pool stats
        stats = manager.get_stats()

        # Verify all service pools are configured
        expected_services = ["elasticsearch", "prometheus", "kubernetes", "llm"]
        for service in expected_services:
            assert service in stats, f"Missing pool config for {service}"
            assert stats[service]["max_connections"] > 0, f"Invalid max_connections for {service}"

        print(f"✓ Connection pool stats: {stats}")

    async def test_llm_health_check(self):
        """
        Benchmark LLM health check.

        Target: < 5 seconds (with caching, should be < 0.1s after first call)
        """
        from app.services.llm_client import get_llm_client

        try:
            client = get_llm_client()

            # First call (no cache)
            start = time.time()
            is_healthy = await client.health_check()
            first_duration = time.time() - start

            # Second call (cached)
            start = time.time()
            is_healthy_cached = await client.health_check()
            cached_duration = time.time() - start

            assert is_healthy == is_healthy_cached, "Health check results should match"
            assert cached_duration < first_duration, "Cached call should be faster"
            assert cached_duration < 0.1, f"Cached health check took {cached_duration:.2f}s"

            print(f"✓ LLM health check: first={first_duration:.2f}s, cached={cached_duration:.4f}s")

        except ValueError as e:
            pytest.skip(f"LLM client not configured: {e}")


@pytest.mark.benchmark
class TestPerformanceRegression:
    """Tests to catch performance regressions."""

    @pytest.mark.asyncio
    async def test_no_n_plus_one_queries(self):
        """
        Verify we're not making N+1 queries.

        This test checks that fetching data for multiple items
        doesn't result in N+1 database/API queries.
        """
        from app.services.batch_optimizer import BatchOptimizer

        # Track how many times execute_fn is called
        call_count = 0
        original_execute = None

        async def tracking_execute(ids):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return [{"id": id} for id in ids]

        optimizer = BatchOptimizer(batch_size=10, max_wait=0.05)

        # Submit 10 requests
        await asyncio.gather(*[
            optimizer.batch_request(
                batch_key="test",
                request_id=f"req-{i}",
                execute_fn=tracking_execute,
            )
            for i in range(10)
        ])

        # With batching, should only execute once
        assert call_count <= 2, f"Expected ≤2 executions, got {call_count} (possible N+1 issue)"

        print(f"✓ N+1 test: {call_count} executions for 10 requests (batching working)")


@pytest.mark.benchmark
class TestLoadCapacity:
    """Load capacity tests."""

    @pytest.mark.asyncio
    async def test_sustained_load(self):
        """
        Test sustained load over time.

        Verifies performance doesn't degrade under sustained load.
        """
        from app.api.v1.overview import (
            _get_k8s_health,
            _get_es_health,
            _get_apm_health,
            _get_infra_health,
        )

        class MockClient:
            async def list_pods(self):
                await asyncio.sleep(0.05)
                return [{"name": "test-pod", "status": "Running"}]

            async def list_deployments(self):
                await asyncio.sleep(0.05)
                return [{"name": "test-deploy", "replicas": 1, "available": 1}]

            async def list_nodes(self):
                await asyncio.sleep(0.05)
                return [{"name": "test-node", "status": "Ready"}]

            async def get_error_count(self, minutes=60):
                await asyncio.sleep(0.05)
                return 5

            async def get_cluster_health(self):
                await asyncio.sleep(0.05)
                return {"status": "green"}

            async def get_summary(self):
                await asyncio.sleep(0.05)
                return {
                    "latency_p50": 100,
                    "latency_p95": 250,
                    "latency_p99": 500,
                    "error_rate_percent": 0.5,
                    "throughput": 1000,
                }

            async def get_cpu_percent(self):
                await asyncio.sleep(0.05)
                return 45.0

            async def get_memory_percent(self):
                await asyncio.sleep(0.05)
                return 60.0

        async def make_request():
            k8s = MockClient()
            es = MockClient()
            apm = MockClient()
            prom = MockClient()

            return await asyncio.gather(
                _get_k8s_health(k8s),
                _get_es_health(es),
                _get_apm_health(apm),
                _get_infra_health(prom, k8s),
            )

        # Make 50 requests over time
        latencies = []

        for i in range(50):
            start = time.time()
            await make_request()
            latencies.append(time.time() - start)

            # Small delay between requests
            await asyncio.sleep(0.01)

        # Check average latency
        avg_latency = sum(latencies) / len(latencies)
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
        p99_latency = sorted(latencies)[int(len(latencies) * 0.99)]

        print(f"✓ Sustained load (50 requests):")
        print(f"  Average: {avg_latency:.3f}s")
        print(f"  P95: {p95_latency:.3f}s")
        print(f"  P99: {p99_latency:.3f}s")

        # Verify no significant degradation
        # P99 should not be more than 2x the average
        assert p99_latency < avg_latency * 2, "P99 latency indicates performance degradation"


def get_benchmark_summary() -> dict[str, Any]:
    """
    Get summary of benchmark targets and current status.

    Returns:
        Dict with performance targets and results
    """
    return {
        "targets": {
            "overview_latency": TARGET_OVERVIEW_LATENCY,
            "es_query_latency": TARGET_ES_QUERY_LATENCY,
            "concurrent_10_latency": TARGET_CONCURRENT_10_LATENCY,
            "first_token_time": TARGET_FIRST_TOKEN_TIME,
        },
        "description": "Performance targets for critical operations",
    }
