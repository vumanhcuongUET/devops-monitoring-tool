"""
Query Patterns Library - Phase 7 Sprint 3 Day 18-19

Purpose: Library of common optimized query patterns

Features:
- High error rate detection
- High latency detection
- Resource exhaustion patterns
- Pod crash loops
- Deployment anomalies
- SLO violations
"""

from typing import Any


class QueryPatterns:
    """
    Library of common optimized query patterns.

    Provides pre-built, optimized query templates for common
    monitoring and alerting scenarios.
    """

    @staticmethod
    def high_error_rate_threshold(threshold: float = 0.05) -> str:
        """
        PromQL query for high error rate detection.

        Args:
            threshold: Error rate threshold (default 5%)

        Returns:
            PromQL query string
        """
        return f"""
        (rate(http_requests_total{{status=~"5.."}}[5m])
         /
         rate(http_requests_total[5m]))
        > {threshold}
        """.strip()

    @staticmethod
    def high_latency_p95(percentile: float = 95) -> str:
        """
        PromQL query for high latency detection (P95).

        Args:
            percentile: Percentile threshold (default 95)

        Returns:
            PromQL query string
        """
        return f"""
        histogram_quantile({percentile / 100},
          sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
        ) > 1
        """.strip()

    @staticmethod
    def pod_crash_loop(restarts: int = 5) -> str:
        """
        PromQL query for detecting pod crash loops.

        Args:
            restarts: Number of restarts threshold

        Returns:
            PromQL query string
        """
        return f"""
        rate(kube_pod_container_status_restarts_total[5m]) * 300
        > {restarts}
        """.strip()

    @staticmethod
    def cpu_exhaustion(threshold: float = 0.9) -> str:
        """
        PromQL query for CPU exhaustion detection.

        Args:
            threshold: CPU usage threshold (default 90%)

        Returns:
            PromQL query string
        """
        return f"""
        sum(rate(container_cpu_usage_seconds_total{{name!=""}}[5m]))
        /
        sum(machine_cpu_cores)
        > {threshold}
        """.strip()

    @staticmethod
    def memory_exhaustion(threshold: float = 0.9) -> str:
        """
        PromQL query for memory exhaustion detection.

        Args:
            threshold: Memory usage threshold (default 90%)

        Returns:
            PromQL query string
        """
        return f"""
        sum(container_memory_working_set_bytes)
        /
        sum(machine_memory_bytes)
        > {threshold}
        """.strip()

    @staticmethod
    def disk_space_high(threshold: float = 0.85) -> str:
        """
        PromQL query for high disk space usage.

        Args:
            threshold: Disk usage threshold (default 85%)

        Returns:
            PromQL query string
        """
        return f"""
        1 - (node_filesystem_avail_bytes{{mountpoint="/"}}
        /
        node_filesystem_size_bytes{{mountpoint="/"}})
        > {threshold}
        """.strip()

    @staticmethod
    def slo_error_budget_burn(slo_name: str, service: str) -> str:
        """
        PromQL query for SLO error budget burn rate.

        Args:
            slo_name: Name of the SLO
            service: Service name

        Returns:
            PromQL query string
        """
        return f"""
        (
        (1 - (sum(rate(http_requests_total{{status!~"5..",service="{service}"}}[5d]))
        /
        sum(rate(http_requests_total{{service="{service}"}}[5d]))))
        *
        (1 - (sum(rate(http_requests_total{{status!~"5..",service="{service}"}}[1h]))
        /
        sum(rate(http_requests_total{{service="{service}"}}[1h]))))
        ) * 100
        """.strip()

    @staticmethod
    def elasticsearch_logs_error_filter(project: str, error_keywords: list[str]) -> dict[str, Any]:
        """
        Elasticsearch query for error logs filtering.

        Args:
            project: Project name
            error_keywords: List of error keywords to match

        Returns:
            Elasticsearch query DSL
        """
        keyword_clauses = [
            {"wildcard": {"message": f"*{keyword}*"}}
            for keyword in error_keywords
        ]

        return {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"project": project}},
                        {"range": {"@timestamp": {
                            "gte": "now-1h"
                        }}},
                        {"bool": {"should": keyword_clauses}}
                    ]
                }
            },
            "size": 100,
            "sort": [{"@timestamp": {"order": "desc"}}]
        }

    @staticmethod
    def elasticsearch_slow_transactions(
        service: str,
        threshold_ms: float = 1000
    ) -> dict[str, Any]:
        """
        Elasticsearch query for slow transaction detection.

        Args:
            service: Service name
            threshold_ms: Latency threshold in milliseconds

        Returns:
            Elasticsearch query DSL
        """
        return {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"service.name": service}},
                        {"term": {"processor.event": "transaction"}},
                        {"range": {"transaction.duration.value": {
                            "gte": threshold_ms / 1000  # Convert to seconds
                        }}},
                        {"range": {"@timestamp": {
                            "gte": "now-1h"
                        }}}
                    ]
                }
            },
            "size": 50,
            "sort": [{"transaction.duration.value": {"order": "desc"}}]
        }

    @staticmethod
    def kubernetes_deployment_status(namespace: str) -> dict[str, Any]:
        """
        Kubernetes label selector for deployment status.

        Args:
            namespace: Namespace to query

        Returns:
            Label selector for pods
        """
        return {
            "namespace": namespace,
            "label_selector": "app.kubernetes.io/part-of"
        }

    @staticmethod
    def prometheus_rate_query(
        metric_name: str,
        window: str = "5m",
        labels: dict[str, str] | None = None
    ) -> str:
        """
        Generic PromQL rate query.

        Args:
            metric_name: Name of the metric
            window: Time window for rate calculation
            labels: Optional label filters

        Returns:
            PromQL query string
        """
        label_matcher = ""
        if labels:
            matchers = [f'{k}="{v}"' for k, v in labels.items()]
            label_matcher = "{" + ",".join(matchers) + "}"

        return f"rate({metric_name}{label_matcher}[{window}])"

    @staticmethod
    def prometheus_increase_query(
        metric_name: str,
        window: str = "5m",
        labels: dict[str, str] | None = None
    ) -> str:
        """
        Generic PromQL increase query.

        Args:
            metric_name: Name of the metric
            window: Time window for increase calculation
            labels: Optional label filters

        Returns:
            PromQL query string
        """
        label_matcher = ""
        if labels:
            matchers = [f'{k}="{v}"' for k, v in labels.items()]
            label_matcher = "{" + ",".join(matchers) + "}"

        return f"increase({metric_name}{label_matcher}[{window}])"

    @staticmethod
    def slo_latency_query(
        service: str,
        threshold_ms: float = 500,
        percentile: float = 95
    ) -> str:
        """
        PromQL query for SLO latency measurement.

        Args:
            service: Service name
            threshold_ms: Latency threshold in milliseconds
            percentile: Percentile to measure

        Returns:
            PromQL query string
        """
        return f"""
        (
        histogram_quantile({percentile / 100},
          sum(rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m]))
          by (le))
        )
        > {threshold_ms / 1000}
        """.strip()

    @staticmethod
    def slo_availability_query(
        service: str,
        window: str = "7d"
    ) -> str:
        """
        PromQL query for SLO availability measurement.

        Args:
            service: Service name
            window: Time window for calculation

        Returns:
            PromQL query string
        """
        return f"""
        (
        sum(rate(http_requests_total{{status!~"5..",service="{service}"}}[{window}]))
        /
        sum(rate(http_requests_total{{service="{service}"}}[{window}]))
        )
        """.strip()

    @staticmethod
    def container_restart_pattern(threshold: int = 3) -> str:
        """
        Pattern for detecting container restart issues.

        Args:
            threshold: Restart count threshold

        Returns:
            PromQL query string
        """
        return f"""
        increase(kube_pod_container_status_restarts_total[1h])
        > {threshold}
        """.strip()

    @staticmethod
    def network_connection_errors() -> str:
        """
        Pattern for detecting network connection errors.

        Returns:
            PromQL query string
        """
        return """
        rate(container_network_tcp_connections_total[5m])
        """.strip()

    @staticmethod
    def queue_depth_builtup(queue_name: str, threshold: float = 1000) -> str:
        """
        Pattern for detecting queue depth buildup.

        Args:
            queue_name: Name of the queue metric
            threshold: Depth threshold

        Returns:
            PromQL query string
        """
        return f"""
        {queue_name}_depth > {threshold}
        """.strip()

    @staticmethod
    def cache_hit_rate(cache_name: str) -> str:
        """
        Pattern for cache hit rate measurement.

        Args:
            cache_name: Name of the cache

        Returns:
            PromQL query string
        """
        return f"""
        (
        rate(cache_hits_total{{cache="{cache_name}"}}[5m])
        /
        (rate(cache_hits_total{{cache="{cache_name}"}}[5m])
         + rate(cache_misses_total{{cache="{cache_name}"}}[5m]))
        )
        """.strip()

    @staticmethod
    def database_connection_pool_exhaustion(pool_name: str) -> str:
        """
        Pattern for database connection pool exhaustion.

        Args:
            pool_name: Name of the connection pool

        Returns:
            PromQL query string
        """
        return f"""
        {pool_name}_active_connections
        /
        {pool_name}_max_connections
        > 0.9
        """.strip()

    @staticmethod
    def api_error_rate_by_endpoint(service: str, threshold: float = 0.05) -> str:
        """
        Pattern for API error rate by endpoint.

        Args:
            service: Service name
            threshold: Error rate threshold

        Returns:
            PromQL query string
        """
        return f"""
        (
        sum(rate(http_requests_total{{status=~"5..",service="{service}"}}[5m])) by (endpoint)
        /
        sum(rate(http_requests_total{{service="{service}"}}[5m])) by (endpoint)
        )
        > {threshold}
        """.strip()


class QueryPatternLibrary:
    """
    Centralized library for query patterns.

    Provides categorized access to all query patterns.
    """

    # Error detection patterns
    ERROR_PATTERNS = {
        "high_error_rate": QueryPatterns.high_error_rate_threshold,
        "error_logs_filter": QueryPatterns.elasticsearch_logs_error_filter,
        "api_error_rate": QueryPatterns.api_error_rate_by_endpoint,
    }

    # Performance patterns
    PERFORMANCE_PATTERNS = {
        "high_latency_p95": QueryPatterns.high_latency_p95,
        "slow_transactions": QueryPatterns.elasticsearch_slow_transactions,
        "slo_latency": QueryPatterns.slo_latency_query,
    }

    # Resource patterns
    RESOURCE_PATTERNS = {
        "cpu_exhaustion": QueryPatterns.cpu_exhaustion,
        "memory_exhaustion": QueryPatterns.memory_exhaustion,
        "disk_space_high": QueryPatterns.disk_space_high,
        "container_restart": QueryPatterns.container_restart_pattern,
    }

    # Availability patterns
    AVAILABILITY_PATTERNS = {
        "slo_availability": QueryPatterns.slo_availability_query,
        "pod_crash_loop": QueryPatterns.pod_crash_loop,
    }

    # Database patterns
    DATABASE_PATTERNS = {
        "connection_pool": QueryPatterns.database_connection_pool_exhaustion,
    }

    # Cache patterns
    CACHE_PATTERNS = {
        "hit_rate": QueryPatterns.cache_hit_rate,
    }

    @classmethod
    def get_pattern(cls, category: str, pattern_name: str, **kwargs) -> Any:
        """
        Get a query pattern by category and name.

        Args:
            category: Category (error, performance, resource, etc.)
            pattern_name: Name of the pattern
            **kwargs: Arguments for the pattern function

        Returns:
            Query pattern result
        """
        category_map = {
            "error": cls.ERROR_PATTERNS,
            "performance": cls.PERFORMANCE_PATTERNS,
            "resource": cls.RESOURCE_PATTERNS,
            "availability": cls.AVAILABILITY_PATTERNS,
            "database": cls.DATABASE_PATTERNS,
            "cache": cls.CACHE_PATTERNS,
        }

        if category not in category_map:
            raise ValueError(f"Unknown category: {category}")

        patterns = category_map[category]
        if pattern_name not in patterns:
            raise ValueError(f"Unknown pattern: {pattern_name} in category {category}")

        pattern_func = patterns[pattern_name]
        return pattern_func(**kwargs)

    @classmethod
    def list_patterns(cls, category: str | None = None) -> dict[str, list[str]]:
        """
        List all available patterns.

        Args:
            category: Optional category to filter by

        Returns:
            Dictionary of category -> pattern names
        """
        if category:
            category_map = {
                "error": cls.ERROR_PATTERNS,
                "performance": cls.PERFORMANCE_PATTERNS,
                "resource": cls.RESOURCE_PATTERNS,
                "availability": cls.AVAILABILITY_PATTERNS,
                "database": cls.DATABASE_PATTERNS,
                "cache": cls.CACHE_PATTERNS,
            }
            return {category: list(category_map[category].keys())}

        return {
            "error": list(cls.ERROR_PATTERNS.keys()),
            "performance": list(cls.PERFORMANCE_PATTERNS.keys()),
            "resource": list(cls.RESOURCE_PATTERNS.keys()),
            "availability": list(cls.AVAILABILITY_PATTERNS.keys()),
            "database": list(cls.DATABASE_PATTERNS.keys()),
            "cache": list(cls.CACHE_PATTERNS.keys()),
        }
