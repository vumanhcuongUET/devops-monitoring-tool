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

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

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
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
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
        self.profiles: list[QueryProfile] = []
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

    def get_stats(self) -> dict[str, Any]:
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

    def get_recent_profiles(self, limit: int = 10) -> list[dict[str, Any]]:
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
    ) -> list[dict[str, datetime]]:
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
        labels: dict[str, str] | None = None,
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

    def get_profiler_stats(self) -> dict[str, Any]:
        """Get profiler statistics."""
        return self.profiler.get_stats()

    def reset_profiler(self):
        """Reset profiler statistics."""
        self.profiler.reset()
