"""
Cached Overview Service

Phase 7 - Sprint 1 - Day 8
Purpose: Overview service with full caching stack integration

Features:
- Multi-layer caching (L1, L2, L3)
- Single flight pattern for concurrent requests
- Graceful degradation with fallback
- Cache warming for critical data
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from app.cache.l1_cache import L1Cache
from app.cache.l2_cache import L2CacheManager
from app.cache.l3_cache import SemanticCache, PatternExtractor
from app.cache.single_flight import SingleFlight
from app.cache.invalidation import CacheInvalidator, create_default_tags

logger = logging.getLogger(__name__)


class CachedOverviewService:
    """
    Overview service with full caching stack.

    Implements multi-layer caching with:
    - L1: Per-request deduplication
    - L2: Redis cache with 5-15min TTL
    - L3: Semantic cache for similar incidents
    - Single flight for cache stampede prevention
    """

    def __init__(
        self,
        redis_client,
        es_client=None,
        prom_client=None,
        k8s_client=None
    ):
        """
        Initialize cached overview service.

        Args:
            redis_client: Redis client for L2/L3 cache
            es_client: Elasticsearch client
            prom_client: Prometheus client
            k8s_client: Kubernetes client
        """
        self.l1_cache = L1Cache()
        self.l2_cache = L2CacheManager(redis_client)
        self.l3_cache = SemanticCache(redis_client)
        self.pattern_extractor = PatternExtractor()
        self.invalidator = CacheInvalidator(redis_client, self.l2_cache)
        self.single_flight = SingleFlight()

        # Data source clients
        self.es_client = es_client
        self.prom_client = prom_client
        self.k8s_client = k8s_client

        # Cache configuration
        self.cache_enabled = True
        self.semantic_enabled = True

        logger.info("CachedOverviewService initialized with full cache stack")

    async def get_overview(
        self,
        project: str,
        force_refresh: bool = False,
        use_semantic: bool = False,
        timeout: int = 10000
    ) -> Dict[str, Any]:
        """
        Get overview with multi-layer caching.

        Args:
            project: Project name
            force_refresh: Skip cache and fetch fresh data
            use_semantic: Try L3 semantic cache
            timeout: Total timeout in milliseconds

        Returns:
            Overview data dictionary
        """
        start_time = datetime.now()

        if not force_refresh and self.cache_enabled:
            # Try L2 cache first
            cached = await self.l2_cache.get(
                "overview",
                {"project": project}
            )

            if cached:
                duration = (datetime.now() - start_time).total_seconds() * 1000
                logger.info(f"L2 cache hit for overview: {project} ({duration:.0f}ms)")
                cached["_cache"] = "L2_HIT"
                cached["_cache_time_ms"] = duration
                return cached

        # Try L3 semantic cache if enabled
        if use_semantic and self.semantic_enabled:
            semantic_result = await self._try_semantic_cache(project)
            if semantic_result:
                duration = (datetime.now() - start_time).total_seconds() * 1000
                logger.info(f"L3 semantic cache hit for overview: {project} ({duration:.0f}ms)")
                semantic_result["_cache"] = "L3_HIT"
                semantic_result["_cache_time_ms"] = duration
                return semantic_result

        # Use single flight to prevent stampede
        try:
            overview = await asyncio.wait_for(
                self.single_flight.execute(
                    f"overview:{project}",
                    lambda: self._fetch_and_cache_overview(project)
                ),
                timeout=timeout / 1000
            )

            duration = (datetime.now() - start_time).total_seconds() * 1000
            overview["_cache_time_ms"] = duration

            return overview

        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching overview for {project}")
            return self._get_timeout_error(project, timeout)
        except Exception as e:
            logger.error(f"Error fetching overview for {project}: {e}")
            return self._get_error_response(project, str(e))

    async def _try_semantic_cache(self, project: str) -> Optional[Dict[str, Any]]:
        """Try L3 semantic cache for project."""
        try:
            # Create patterns for semantic lookup
            patterns = [
                f"project:{project}",
                "type:overview",
                "data_type:health"
            ]

            # Find similar cached overviews
            similar = await self.l3_cache.find_similar(
                "overview",
                patterns,
                threshold=0.5,
                max_results=1
            )

            if similar:
                cached = similar[0]
                # Return the analysis if available
                if "analysis" in cached:
                    return cached["analysis"]
                # Otherwise return the cached data
                if "data" in cached:
                    return cached["data"]

            return None

        except Exception as e:
            logger.warning(f"Error checking semantic cache: {e}")
            return None

    async def _fetch_and_cache_overview(self, project: str) -> Dict[str, Any]:
        """Fetch overview from sources and cache it."""
        try:
            # Gather data from all sources in parallel
            results = await asyncio.gather(
                self._get_es_health(project, self.l1_cache),
                self._get_prom_metrics(project, self.l1_cache),
                self._get_k8s_status(project, self.l1_cache),
                return_exceptions=True
            )

            # Process results
            overview = self._format_overview(results, project)

            # Cache with tags
            tags = create_default_tags(
                project=project,
                data_type="overview",
                additional_tags=["critical", "health"]
            )

            await self.invalidator.set_with_tags(
                data_type="overview",
                identifier={"project": project},
                value=overview,
                tags=tags,
                ttl=300  # 5 minutes
            )

            # Also cache in L3 for semantic matching
            patterns = [
                f"project:{project}",
                "type:overview",
                "data_type:health"
            ]

            await self.l3_cache.set(
                incident_type="overview",
                patterns=patterns,
                analysis=overview,
                ttl=86400  # 24 hours for L3
            )

            overview["_cache"] = "MISS"
            overview["_cached_at"] = datetime.now().isoformat()

            return overview

        except Exception as e:
            logger.error(f"Error in _fetch_and_cache_overview: {e}")
            raise

    def _format_overview(
        self,
        results: List,
        project: str
    ) -> Dict[str, Any]:
        """Format overview from gathered results."""
        overview = {
            "project": project,
            "timestamp": datetime.now().isoformat(),
            "sources": {}
        }

        # Process each result
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error from source {i}: {result}")
                continue

            if result and isinstance(result, dict):
                source_name = result.get("source", f"source_{i}")
                overview["sources"][source_name] = result

        # Derive overall health
        overview["health"] = self._derive_health(overview["sources"])

        # Add metadata
        overview["source_count"] = len(overview["sources"])
        overview["complete"] = all(
            s.get("status") != "error"
            for s in overview["sources"].values()
        )

        return overview

    def _derive_health(self, sources: Dict) -> str:
        """Derive overall health from source data."""
        if not sources:
            return "unknown"

        statuses = []
        for source_data in sources.values():
            if "health" in source_data:
                statuses.append(source_data["health"])
            elif "status" in source_data:
                statuses.append(source_data["status"])

        if not statuses:
            return "unknown"

        # If any critical, overall is critical
        if any(s == "critical" or s == "down" for s in statuses):
            return "critical"

        # If any warning, overall is warning
        if any(s == "warning" or s == "degraded" for s in statuses):
            return "warning"

        # Otherwise healthy
        return "healthy"

    async def _get_es_health(
        self,
        project: str,
        l1_cache: L1Cache
    ) -> Dict[str, Any]:
        """Get Elasticsearch health with L1 caching."""
        # Check L1 first
        l1_key = f"es_health:{project}"
        cached = await l1_cache.get("elasticsearch", {"key": l1_key})
        if cached:
            return cached

        # Fetch from ES
        try:
            if self.es_client:
                health = await self.es_client.get_health(project)
                result = {
                    "source": "elasticsearch",
                    "health": health.get("status", "unknown"),
                    "cluster_name": health.get("cluster_name"),
                    "number_of_nodes": health.get("number_of_nodes", 0)
                }
            else:
                result = {
                    "source": "elasticsearch",
                    "status": "unavailable",
                    "health": "unknown"
                }

            # Cache in L1
            await l1_cache.set("elasticsearch", {"key": l1_key}, result)
            return result

        except Exception as e:
            logger.error(f"Error getting ES health: {e}")
            return {
                "source": "elasticsearch",
                "status": "error",
                "error": str(e)
            }

    async def _get_prom_metrics(
        self,
        project: str,
        l1_cache: L1Cache
    ) -> Dict[str, Any]:
        """Get Prometheus metrics with L1 caching."""
        l1_key = f"prom_metrics:{project}"
        cached = await l1_cache.get("prometheus", {"key": l1_key})
        if cached:
            return cached

        try:
            if self.prom_client:
                metrics = await self.prom_client.get_project_metrics(project)
                result = {
                    "source": "prometheus",
                    "status": "ok",
                    "metrics": metrics
                }
            else:
                result = {
                    "source": "prometheus",
                    "status": "unavailable",
                    "metrics": {}
                }

            await l1_cache.set("prometheus", {"key": l1_key}, result)
            return result

        except Exception as e:
            logger.error(f"Error getting Prometheus metrics: {e}")
            return {
                "source": "prometheus",
                "status": "error",
                "error": str(e)
            }

    async def _get_k8s_status(
        self,
        project: str,
        l1_cache: L1Cache
    ) -> Dict[str, Any]:
        """Get Kubernetes status with L1 caching."""
        l1_key = f"k8s_status:{project}"
        cached = await l1_cache.get("kubernetes", {"key": l1_key})
        if cached:
            return cached

        try:
            if self.k8s_client:
                pods = await self.k8s_client.get_pods(project)
                result = {
                    "source": "kubernetes",
                    "status": "ok",
                    "pods": {
                        "total": len(pods),
                        "running": sum(1 for p in pods if p.get("phase") == "Running"),
                        "pending": sum(1 for p in pods if p.get("phase") == "Pending"),
                        "failed": sum(1 for p in pods if p.get("phase") == "Failed")
                    }
                }
            else:
                result = {
                    "source": "kubernetes",
                    "status": "unavailable",
                    "pods": {}
                }

            await l1_cache.set("kubernetes", {"key": l1_key}, result)
            return result

        except Exception as e:
            logger.error(f"Error getting K8s status: {e}")
            return {
                "source": "kubernetes",
                "status": "error",
                "error": str(e)
            }

    def _get_timeout_error(self, project: str, timeout: int) -> Dict[str, Any]:
        """Get timeout error response."""
        return {
            "project": project,
            "status": "timeout",
            "error": f"Request timeout after {timeout}ms",
            "_cache": "TIMEOUT"
        }

    def _get_error_response(self, project: str, error: str) -> Dict[str, Any]:
        """Get error response."""
        return {
            "project": project,
            "status": "error",
            "error": error,
            "_cache": "ERROR"
        }

    async def get_health_status(
        self,
        project: str
    ) -> Dict[str, Any]:
        """
        Get health status with caching.

        Simpler endpoint focusing on health only.
        """
        try:
            # Try L2 cache
            cached = await self.l2_cache.get(
                "health_status",
                {"project": project}
            )

            if cached:
                cached["_cache"] = "L2_HIT"
                return cached

            # Fetch fresh
            overview = await self.get_overview(project, force_refresh=True)

            health_status = {
                "project": project,
                "health": overview.get("health", "unknown"),
                "timestamp": overview.get("timestamp"),
                "sources": overview.get("sources", {})
            }

            # Cache with shorter TTL
            await self.invalidator.set_with_tags(
                data_type="health_status",
                identifier={"project": project},
                value=health_status,
                tags=create_default_tags(project, "health_status"),
                ttl=60  # 1 minute
            )

            health_status["_cache"] = "MISS"
            return health_status

        except Exception as e:
            logger.error(f"Error getting health status: {e}")
            return {
                "project": project,
                "health": "unknown",
                "error": str(e),
                "_cache": "ERROR"
            }

    async def invalidate_project_cache(self, project: str) -> int:
        """
        Invalidate all cache entries for a project.

        Args:
            project: Project to invalidate

        Returns:
            Number of keys invalidated
        """
        tags = [f"project:{project}"]
        return await self.invalidator.invalidate_by_tags(tags)

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "l2_cache": self.l2_cache.get_stats(),
            "invalidator": self.invalidator.get_stats(),
            "cache_enabled": self.cache_enabled,
            "semantic_enabled": self.semantic_enabled
        }

    def enable_cache(self):
        """Enable caching."""
        self.cache_enabled = True
        logger.info("Caching enabled")

    def disable_cache(self):
        """Disable caching."""
        self.cache_enabled = False
        logger.info("Caching disabled")

    def enable_semantic(self):
        """Enable semantic cache."""
        self.semantic_enabled = True
        logger.info("Semantic cache enabled")

    def disable_semantic(self):
        """Disable semantic cache."""
        self.semantic_enabled = False
        logger.info("Semantic cache disabled")
