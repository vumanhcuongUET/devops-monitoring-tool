"""
Query Optimizer - Phase 7 Sprint 3 Day 18-19

Purpose: Optimize queries to Elasticsearch, Prometheus, and Kubernetes

Features:
- Time-based chunking for large queries
- Query result caching
- Recording rule utilization
- PromQL query optimization
- Common query pattern library
- Performance profiling
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Types of queries."""
    LOGS = "logs"
    METRICS = "metrics"
    EVENTS = "events"
    APM_TRANSACTIONS = "apm_transactions"
    APM_ERRORS = "apm_errors"
    KUBERNETES_PODS = "kubernetes_pods"
    KUBERNETES_EVENTS = "kubernetes_events"


@dataclass
class QueryProfile:
    """Profile of a query execution."""
    query_type: QueryType
    source: str
    function_name: str
    execution_time_ms: float
    result_count: int
    cache_hit: bool
    chunk_count: int = 1
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "query_type": self.query_type.value,
            "source": self.source,
            "function_name": self.function_name,
            "execution_time_ms": self.execution_time_ms,
            "result_count": self.result_count,
            "cache_hit": self.cache_hit,
            "chunk_count": self.chunk_count,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }


class QueryProfiler:
    """
    Profile and analyze query performance.

    Features:
    - Execution time tracking
    - Result count tracking
    - Cache hit/miss tracking
    - Performance metrics
    """

    def __init__(self):
        """Initialize query profiler."""
        self.profiles: List[QueryProfile] = []
        self.stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "total_time_ms": 0,
            "total_results": 0
        }

    async def profile_query(
        self,
        query_type: QueryType,
        source: str,
        function_name: str,
        query_func: Callable,
        cache_hit: bool = False,
        chunk_count: int = 1
    ) -> Any:
        """
        Profile a query execution.

        Args:
            query_type: Type of query
            source: Data source (es, prom, k8s)
            function_name: Name of the function
            query_func: Async function to execute
            cache_hit: Whether result came from cache
            chunk_count: Number of chunks used

        Returns:
            Query result
        """
        start_time = time.time()

        try:
            result = await query_func()

            execution_time_ms = (time.time() - start_time) * 1000
            result_count = len(result) if isinstance(result, list) else 1

            profile = QueryProfile(
                query_type=query_type,
                source=source,
                function_name=function_name,
                execution_time_ms=execution_time_ms,
                result_count=result_count,
                cache_hit=cache_hit,
                chunk_count=chunk_count
            )

            self._add_profile(profile)

            return result

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000

            profile = QueryProfile(
                query_type=query_type,
                source=source,
                function_name=function_name,
                execution_time_ms=execution_time_ms,
                result_count=0,
                cache_hit=cache_hit,
                chunk_count=chunk_count,
                metadata={"error": str(e)}
            )

            self._add_profile(profile)
            raise

    def _add_profile(self, profile: QueryProfile):
        """Add profile to history."""
        self.profiles.append(profile)

        # Keep only last 1000 profiles
        if len(self.profiles) > 1000:
            self.profiles = self.profiles[-1000:]

        # Update stats
        self.stats["total_queries"] += 1
        if profile.cache_hit:
            self.stats["cache_hits"] += 1
        self.stats["total_time_ms"] += profile.execution_time_ms
        self.stats["total_results"] += profile.result_count

    def get_stats(self) -> Dict[str, Any]:
        """Get profiler statistics."""
        stats = self.stats.copy()

        if stats["total_queries"] > 0:
            stats["avg_time_ms"] = stats["total_time_ms"] / stats["total_queries"]
            stats["avg_results"] = stats["total_results"] / stats["total_queries"]
            stats["cache_hit_rate"] = stats["cache_hits"] / stats["total_queries"]
        else:
            stats["avg_time_ms"] = 0
            stats["avg_results"] = 0
            stats["cache_hit_rate"] = 0

        return stats

    def get_recent_profiles(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent query profiles."""
        return [p.to_dict() for p in self.profiles[-limit:]]

    def reset(self):
        """Reset profiler statistics."""
        self.profiles = []
        self.stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "total_time_ms": 0,
            "total_results": 0
        }


class QueryOptimizer:
    """
    Optimize queries to data sources.

    Features:
    - Time-based chunking for large queries
    - Query result caching
    - Recording rule utilization
    - PromQL query optimization
    """

    # Optimal chunk sizes based on time range
    CHUNK_SIZES = {
        timedelta(minutes=15): timedelta(minutes=5),
        timedelta(hours=1): timedelta(minutes=15),
        timedelta(days=1): timedelta(minutes=30),
        timedelta(days=7): timedelta(hours=1),
    }

    # Prometheus step sizes based on time range
    STEP_SIZES = {
        timedelta(hours=1): "1m",
        timedelta(days=1): "5m",
        timedelta(days=3): "15m",
        timedelta(days=7): "1h",
    }

    def __init__(self, es_client=None, prom_client=None, k8s_client=None, l2_cache=None):
        """
        Initialize query optimizer.

        Args:
            es_client: Elasticsearch client
            prom_client: Prometheus client
            k8s_client: Kubernetes client
            l2_cache: L2 cache instance
        """
        self.es = es_client
        self.prom = prom_client
        self.k8s = k8s_client
        self.l2_cache = l2_cache
        self.profiler = QueryProfiler()

        # Recording rules configuration
        self.recording_rules = {}

    async def get_logs_optimized(
        self,
        project: str,
        time_range: timedelta,
        filters: Optional[Dict[str, Any]] = None,
        index_pattern: str = "logs-*"
    ) -> List[Dict]:
        """
        Optimized log query with chunking and caching.

        Args:
            project: Project name
            time_range: Time range for query
            filters: Optional filters to apply
            index_pattern: Elasticsearch index pattern

        Returns:
            List of log entries
        """
        if not self.es:
            logger.warning("ES client not configured")
            return []

        # Calculate optimal chunk size
        chunk_size = self._calculate_optimal_chunk_size(time_range)

        # Split time range
        chunks = self._split_time_range(time_range, chunk_size)

        all_logs = []
        cache_hits = 0

        for chunk in chunks:
            # Check cache first
            cache_key = {
                "type": "logs",
                "project": project,
                "start": chunk["start"].isoformat(),
                "end": chunk["end"].isoformat(),
                "filters": filters
            }

            cached = await self._get_from_cache(cache_key) if self.l2_cache else None
            if cached:
                all_logs.extend(cached)
                cache_hits += 1
                continue

            # Execute query
            logs = await self.profiler.profile_query(
                QueryType.LOGS,
                "elasticsearch",
                "get_logs_optimized",
                lambda: self._execute_es_logs_query(
                    project, chunk, filters, index_pattern
                ),
                cache_hit=False
            )

            all_logs.extend(logs)

            # Cache chunk
            if self.l2_cache:
                await self._store_in_cache(
                    cache_key,
                    logs,
                    ttl=300  # 5 minutes
                )

        logger.info(
            f"Logs query complete: {len(all_logs)} logs, "
            f"{cache_hits}/{len(chunks)} cache hits"
        )

        return all_logs

    async def get_metrics_optimized(
        self,
        project: str,
        metric_name: str,
        time_range: timedelta,
        aggregation: str = "avg",
        labels: Optional[Dict[str, str]] = None
    ) -> List[Dict]:
        """
        Optimized metrics query with recording rules.

        Args:
            project: Project name
            metric_name: Name of the metric
            time_range: Time range for query
            aggregation: Aggregation function (avg, sum, min, max)
            labels: Optional label filters

        Returns:
            List of metric data points
        """
        if not self.prom:
            logger.warning("Prometheus client not configured")
            return []

        # Check for recording rule
        rule_key = f"{metric_name}:{aggregation}"
        if rule_key in self.recording_rules:
            return await self._query_recording_rule(
                project,
                metric_name,
                time_range,
                aggregation
            )

        # Execute optimized query
        return await self.profiler.profile_query(
            QueryType.METRICS,
            "prometheus",
            "get_metrics_optimized",
            lambda: self._query_prometheus_optimized(
                project,
                metric_name,
                time_range,
                aggregation,
                labels
            ),
            cache_hit=False
        )

    async def get_apm_transactions_optimized(
        self,
        project: str,
        service_name: str,
        time_range: timedelta,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict]:
        """
        Optimized APM transaction query.

        Args:
            project: Project name
            service_name: Service name
            time_range: Time range for query
            filters: Optional filters

        Returns:
            List of transaction data
        """
        if not self.es:
            logger.warning("ES client not configured")
            return []

        # APM queries benefit from larger chunks
        chunk_size = self._calculate_optimal_chunk_size(time_range, apm=True)

        chunks = self._split_time_range(time_range, chunk_size)

        all_transactions = []

        for chunk in chunks:
            cache_key = {
                "type": "apm_transactions",
                "project": project,
                "service": service_name,
                "start": chunk["start"].isoformat(),
                "end": chunk["end"].isoformat()
            }

            cached = await self._get_from_cache(cache_key) if self.l2_cache else None
            if cached:
                all_transactions.extend(cached)
                continue

            transactions = await self.profiler.profile_query(
                QueryType.APM_TRANSACTIONS,
                "elasticsearch",
                "get_apm_transactions_optimized",
                lambda: self._execute_es_apm_query(
                    project, service_name, chunk, filters
                ),
                cache_hit=False
            )

            all_transactions.extend(transactions)

            if self.l2_cache:
                await self._store_in_cache(cache_key, transactions, ttl=600)

        return all_transactions

    async def get_pods_optimized(
        self,
        project: str,
        namespace: Optional[str] = None
    ) -> List[Dict]:
        """
        Optimized Kubernetes pod query.

        Args:
            project: Project name
            namespace: Optional namespace filter

        Returns:
            List of pod data
        """
        if not self.k8s:
            logger.warning("K8s client not configured")
            return []

        # Pod queries are fast, use shorter cache
        cache_key = {
            "type": "pods",
            "project": project,
            "namespace": namespace
        }

        cached = await self._get_from_cache(cache_key) if self.l2_cache else None
        if cached:
            return cached

        pods = await self.profiler.profile_query(
            QueryType.KUBERNETES_PODS,
            "kubernetes",
            "get_pods_optimized",
            lambda: self._execute_k8s_pods_query(project, namespace),
            cache_hit=False
        )

        if self.l2_cache:
            await self._store_in_cache(cache_key, pods, ttl=60)  # 1 minute

        return pods

    def _calculate_optimal_chunk_size(
        self,
        time_range: timedelta,
        apm: bool = False
    ) -> timedelta:
        """Calculate optimal chunk size based on time range."""
        total_minutes = int(time_range.total_seconds() / 60)

        # APM queries can use larger chunks
        if apm:
            if total_minutes <= 60:
                return timedelta(minutes=15)
            elif total_minutes <= 360:  # 6 hours
                return timedelta(minutes=30)
            else:
                return timedelta(hours=1)

        # Standard queries
        if total_minutes <= 15:
            return timedelta(minutes=5)
        elif total_minutes <= 60:
            return timedelta(minutes=15)
        elif total_minutes <= 1440:  # 1 day
            return timedelta(minutes=30)
        else:
            return timedelta(hours=1)

    def _split_time_range(
        self,
        time_range: timedelta,
        chunk_size: timedelta
    ) -> List[Dict[str, datetime]]:
        """Split time range into cacheable chunks."""
        chunks = []
        end = datetime.now()
        start = end - time_range

        current_start = start
        while current_start < end:
            current_end = min(current_start + chunk_size, end)

            chunks.append({
                "start": current_start,
                "end": current_end
            })

            current_start = current_end

        return chunks

    def _calculate_step(self, time_range: timedelta) -> str:
        """Calculate appropriate step for PromQL query."""
        total_minutes = int(time_range.total_seconds() / 60)

        if total_minutes <= 60:
            return "1m"
        elif total_minutes <= 1440:  # 1 day
            return "5m"
        elif total_minutes <= 4320:  # 3 days
            return "15m"
        else:
            return "1h"

    def _build_promql_query(
        self,
        metric_name: str,
        aggregation: str,
        labels: Optional[Dict[str, str]] = None,
        step: str = "1m"
    ) -> str:
        """Build optimized PromQL query."""
        # Build label matcher
        label_matcher = ""
        if labels:
            matchers = [f'{k}="{v}"' for k, v in labels.items()]
            label_matcher = "{" + ",".join(matchers) + "}"

        # Build query with appropriate aggregation
        base_metric = f"{metric_name}{label_matcher}"

        if aggregation == "rate":
            return f"rate({base_metric}[{step}])"
        elif aggregation == "avg":
            return f"avg(rate({base_metric}[{step}]))"
        elif aggregation == "sum":
            return f"sum(rate({base_metric}[{step}]))"
        elif aggregation == "max":
            return f"max(rate({base_metric}[{step}]))"
        elif aggregation == "min":
            return f"min(rate({base_metric}[{step}]))"
        else:
            return base_metric

    async def _execute_es_logs_query(
        self,
        project: str,
        chunk: Dict[str, datetime],
        filters: Optional[Dict[str, Any]],
        index_pattern: str
    ) -> List[Dict]:
        """Execute Elasticsearch logs query."""
        # This would call the actual ES client
        # For now, return mock data
        query = {
            "bool": {
                "must": [
                    {"range": {"@timestamp": {
                        "gte": chunk["start"].isoformat(),
                        "lte": chunk["end"].isoformat()
                    }}}
                ]
            }
        }

        if filters:
            for key, value in filters.items():
                query["bool"]["must"].append({"term": {key: value}})

        # Simulate query execution
        await asyncio.sleep(0.05)  # Simulate ES latency

        return [
            {
                "@timestamp": chunk["start"].isoformat(),
                "message": f"Sample log {i}",
                "project": project
            }
            for i in range(10)
        ]

    async def _execute_es_apm_query(
        self,
        project: str,
        service_name: str,
        chunk: Dict[str, datetime],
        filters: Optional[Dict[str, Any]]
    ) -> List[Dict]:
        """Execute Elasticsearch APM query."""
        # Simulate APM query
        await asyncio.sleep(0.03)

        return [
            {
                "@timestamp": chunk["start"].isoformat(),
                "service_name": service_name,
                "transaction_name": f"/api/endpoint{i}",
                "duration_ms": 100 + i * 10
            }
            for i in range(5)
        ]

    async def _execute_k8s_pods_query(
        self,
        project: str,
        namespace: Optional[str]
    ) -> List[Dict]:
        """Execute Kubernetes pods query."""
        # Simulate K8s query
        await asyncio.sleep(0.02)

        return [
            {
                "name": f"pod-{i}",
                "namespace": namespace or "default",
                "status": "Running",
                "ready": "1/1"
            }
            for i in range(3)
        ]

    async def _query_prometheus_optimized(
        self,
        project: str,
        metric_name: str,
        time_range: timedelta,
        aggregation: str,
        labels: Optional[Dict[str, str]] = None
    ) -> List[Dict]:
        """Execute optimized Prometheus query."""
        step = self._calculate_step(time_range)
        query = self._build_promql_query(metric_name, aggregation, labels, step)

        # Simulate query execution
        await asyncio.sleep(0.04)

        return [
            {
                "timestamp": (datetime.now() - timedelta(minutes=i)).isoformat(),
                "value": 100.0 + i,
                "metric": metric_name
            }
            for i in range(10)
        ]

    async def _query_recording_rule(
        self,
        project: str,
        metric_name: str,
        time_range: timedelta,
        aggregation: str
    ) -> List[Dict]:
        """Query from pre-computed recording rule."""
        # Recording rules provide faster queries
        await asyncio.sleep(0.01)  # Faster than raw query

        return [
            {
                "timestamp": (datetime.now() - timedelta(minutes=i)).isoformat(),
                "value": 100.0,
                "metric": f"{metric_name}_recorded"
            }
            for i in range(10)
        ]

    async def _get_from_cache(self, cache_key: Dict[str, Any]) -> Optional[List]:
        """Get data from cache."""
        if not self.l2_cache:
            return None

        try:
            cached = await self.l2_cache.get("optimized_query", cache_key)
            return cached
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None

    async def _store_in_cache(
        self,
        cache_key: Dict[str, Any],
        data: Any,
        ttl: int = 300
    ):
        """Store data in cache."""
        if not self.l2_cache:
            return

        try:
            await self.l2_cache.set("optimized_query", cache_key, data, ttl)
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

    def add_recording_rule(
        self,
        metric_name: str,
        aggregation: str,
        rule_name: str
    ):
        """Add a recording rule configuration."""
        key = f"{metric_name}:{aggregation}"
        self.recording_rules[key] = rule_name
        logger.info(f"Added recording rule: {rule_name} for {key}")

    def get_profiler_stats(self) -> Dict[str, Any]:
        """Get profiler statistics."""
        return self.profiler.get_stats()

    def reset_profiler(self):
        """Reset profiler statistics."""
        self.profiler.reset()
