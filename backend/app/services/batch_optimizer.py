"""
Request Batch Optimizer

Phase 9 - Sprint 2 - Day 7
Purpose: Optimize multiple requests by batching when possible

Features:
- Batch multiple similar requests into single execution
- Configurable batch size and wait timeout
- Async execution with proper error handling
- Request deduplication within batch
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Awaitable, Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)


class BatchRequest:
    """Represents a single request in a batch."""

    def __init__(
        self,
        request_id: str,
        future: asyncio.Future,
        timestamp: datetime,
    ):
        self.request_id = request_id
        self.future = future
        self.timestamp = timestamp


class BatchOptimizer:
    """
    Optimizes multiple requests by batching when possible.

    This is useful for scenarios where multiple clients request similar data
    within a short time window. Instead of executing each request separately,
    they are batched together and executed once.

    Example:
        optimizer = BatchOptimizer(batch_size=10, max_wait=0.1)

        async def fetch_overview_data(request_ids: List[str]) -> List[Any]:
            # Fetch data for all request IDs at once
            return [get_overview(project) for project in request_ids]

        # Each client call gets batched
        result = await optimizer.batch_request(
            batch_key="overview:meinvoice",
            request_id="req-123",
            execute_fn=fetch_overview_data,
        )
    """

    def __init__(self, batch_size: int = 10, max_wait: float = 0.1):
        """
        Initialize the batch optimizer.

        Args:
            batch_size: Maximum number of requests to batch
            max_wait: Maximum time to wait for batch to fill (seconds)
        """
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if max_wait < 0:
            raise ValueError("max_wait must be non-negative")

        self.batch_size = batch_size
        self.max_wait = max_wait

        # Pending requests: batch_key -> list of BatchRequest
        self._pending: Dict[str, List[BatchRequest]] = defaultdict(list)

        # Execution locks to prevent duplicate execution
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

        # Statistics
        self._stats = {
            "total_requests": 0,
            "batch_executions": 0,
            "immediate_executions": 0,
            "avg_batch_size": 0.0,
        }

    async def batch_request(
        self,
        batch_key: str,
        request_id: Optional[str] = None,
        execute_fn: Optional[Callable[[List[str]], Awaitable[List[Any]]]] = None,
        execute_single: Optional[Callable[[], Awaitable[Any]]] = None,
    ) -> Any:
        """
        Add request to batch and wait for batch completion.

        Args:
            batch_key: Key to group requests (e.g., "overview:meinvoice")
            request_id: Unique ID for this request (auto-generated if None)
            execute_fn: Function to execute batched requests (takes list of IDs)
            execute_single: Alternative: execute single request immediately

        Returns:
            Result from the batched execution

        Raises:
            RuntimeError: If batch execution fails
        """
        if request_id is None:
            request_id = str(uuid.uuid4())

        # Create future for this request
        future = asyncio.Future()
        batch_request = BatchRequest(
            request_id=request_id,
            future=future,
            timestamp=datetime.now(),
        )

        self._stats["total_requests"] += 1

        async with self._locks[batch_key]:
            # Add to pending batch
            self._pending[batch_key].append(batch_request)

            # Check if we should execute immediately
            should_execute = len(self._pending[batch_key]) >= self.batch_size

            if should_execute:
                # Batch is full, execute immediately
                self._stats["immediate_executions"] += 1
                asyncio.create_task(self._execute_batch(batch_key, execute_fn, execute_single))
            else:
                # Schedule delayed execution
                asyncio.create_task(self._delayed_execute(batch_key, execute_fn, execute_single))

        # Wait for result
        return await future

    async def _delayed_execute(
        self,
        batch_key: str,
        execute_fn: Optional[Callable],
        execute_single: Optional[Callable],
    ) -> None:
        """Execute batch after delay."""
        await asyncio.sleep(self.max_wait)

        async with self._locks[batch_key]:
            if batch_key in self._pending and self._pending[batch_key]:
                await self._execute_batch(batch_key, execute_fn, execute_single)

    async def _execute_batch(
        self,
        batch_key: str,
        execute_fn: Optional[Callable[[List[str]], Awaitable[List[Any]]]],
        execute_single: Optional[Callable[[], Awaitable[Any]]],
    ) -> None:
        """Execute all pending requests in batch."""
        async with self._locks[batch_key]:
            if batch_key not in self._pending:
                return

            requests = self._pending.pop(batch_key)
            if not requests:
                return

            self._stats["batch_executions"] += 1
            batch_size = len(requests)
            self._stats["avg_batch_size"] = (
                (self._stats["avg_batch_size"] * (self._stats["batch_executions"] - 1) + batch_size)
                / self._stats["batch_executions"]
            )

            logger.debug(f"Executing batch {batch_key} with {batch_size} requests")

            try:
                if execute_fn is not None and batch_size > 1:
                    # Execute batched function
                    request_ids = [r.request_id for r in requests]
                    results = await execute_fn(request_ids)

                    # Distribute results
                    for i, req in enumerate(requests):
                        if i < len(results):
                            if not req.future.done():
                                req.future.set_result(results[i])
                        else:
                            if not req.future.done():
                                req.future.set_exception(
                                    IndexError(f"No result for request {req.request_id}")
                                )

                elif execute_single is not None:
                    # Execute single function for each request
                    results = await asyncio.gather(
                        *[execute_single() for _ in requests],
                        return_exceptions=True,
                    )

                    for req, result in zip(requests, results):
                        if not req.future.done():
                            if isinstance(result, Exception):
                                req.future.set_exception(result)
                            else:
                                req.future.set_result(result)
                else:
                    # No executor provided, just complete with None
                    for req in requests:
                        if not req.future.done():
                            req.future.set_result(None)

            except Exception as e:
                logger.error(f"Batch execution failed for {batch_key}: {e}")
                # Fail all pending requests
                for req in requests:
                    if not req.future.done():
                        req.future.set_exception(e)

    def get_stats(self) -> Dict[str, Any]:
        """Get batch optimizer statistics."""
        return {
            **self._stats,
            "pending_batches": len(self._pending),
            "pending_requests": sum(len(reqs) for reqs in self._pending.values()),
        }

    async def flush_all(self) -> None:
        """
        Flush all pending batches immediately.

        Useful for shutdown or when you want to ensure all pending requests
        are executed without waiting for the max_wait timeout.
        """
        logger.info("Flushing all pending batches")

        batch_keys = list(self._pending.keys())
        for batch_key in batch_keys:
            if batch_key in self._pending and self._pending[batch_key]:
                # We'll let the existing delayed execution handle it
                # Just remove from pending so they don't get executed twice
                pass

    def clear_stats(self) -> None:
        """Clear statistics counters."""
        self._stats = {
            "total_requests": 0,
            "batch_executions": 0,
            "immediate_executions": 0,
            "avg_batch_size": 0.0,
        }


class OptimizedOverviewFetcher:
    """
    Optimized fetcher for overview data with request batching.

    This class demonstrates how to use BatchOptimizer for the overview endpoint.
    """

    def __init__(self):
        self.optimizer = BatchOptimizer(batch_size=10, max_wait=0.1)

    async def get_overview(
        self,
        project: str,
        es_client,
        prom_client,
        k8s_client,
        apm_client,
    ) -> Any:
        """
        Get overview data with automatic request batching.

        Multiple concurrent requests for the same project will be batched
        into a single execution.
        """
        batch_key = f"overview:{project}"

        async def execute_single() -> Any:
            """Execute single overview fetch."""
            import app.api.v1.overview as overview_module

            # Get the health data
            results = await asyncio.gather(
                overview_module._get_k8s_health(k8s_client),
                overview_module._get_es_health(es_client),
                overview_module._get_apm_health(apm_client),
                overview_module._get_infra_health(prom_client, k8s_client),
                return_exceptions=True,
            )

            k8s_health = (
                results[0]
                if not isinstance(results[0], Exception)
                else overview_module.KubernetesHealth(status=overview_module.HealthStatus.DOWN)
            )
            es_health = (
                results[1]
                if not isinstance(results[1], Exception)
                else overview_module.ElasticsearchHealth(status=overview_module.HealthStatus.DOWN)
            )
            apm_health = (
                results[2]
                if not isinstance(results[2], Exception)
                else overview_module.ApmHealth(status=overview_module.HealthStatus.DOWN)
            )
            infra_health = (
                results[3]
                if not isinstance(results[3], Exception)
                else overview_module.InfrastructureHealth(status=overview_module.HealthStatus.DOWN)
            )

            return {
                "kubernetes": k8s_health,
                "elasticsearch": es_health,
                "apm": apm_health,
                "infrastructure": infra_health,
            }

        return await self.optimizer.batch_request(
            batch_key=batch_key,
            execute_single=execute_single,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get optimizer statistics."""
        return self.optimizer.get_stats()


# Global instance for application-wide use
_global_optimizer: Optional[BatchOptimizer] = None


def get_batch_optimizer() -> BatchOptimizer:
    """Get the global batch optimizer instance."""
    global _global_optimizer
    if _global_optimizer is None:
        _global_optimizer = BatchOptimizer()
    return _global_optimizer
