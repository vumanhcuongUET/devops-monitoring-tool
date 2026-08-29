"""
L3 Semantic Cache Implementation

Phase 7 - Sprint 1 - Day 6
Purpose: Pattern-based semantic caching for similar incidents

This cache layer uses semantic patterns to match similar incidents,
allowing cache hits even when exact parameters don't match.

For example:
- Request: "CPU high on pod X" → May match cached "CPU spike on pod Y"
- Request: "API latency > 2s" → May match cached "slow API response"

Features:
- Pattern extraction from incidents
- Semantic key generation
- Jaccard similarity matching
- Find similar cached incidents
- Long-term caching (1-24 hours)
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class SemanticCache:
    """
    Pattern-based semantic caching for similar incidents.

    Uses semantic patterns extracted from incidents to enable
    cache hits for similar but not identical requests.

    Example:
        cache = SemanticCache(redis_client)

        # Extract patterns from incident
        patterns = [
            "service:api-gateway",
            "error:timeout",
            "metric:latency_p95",
            "severity:high"
        ]

        # Cache with patterns
        await cache.set(
            incident_type="performance",
            patterns=patterns,
            analysis={"recommendation": "scale up"}
        )

        # Later, find similar incidents
        similar = await cache.find_similar(
            incident_type="performance",
            patterns=["service:api-gateway", "error:slow", "metric:latency"],
            threshold=0.5
        )
    """

    def __init__(self, redis_client, default_ttl: int = 86400):
        """
        Initialize semantic cache.

        Args:
            redis_client: Redis client (from L2 cache)
            default_ttl: Default TTL in seconds (default: 24 hours)
        """
        self.redis = redis_client
        self.default_ttl = default_ttl
        self._stats = {
            "sets": 0,
            "semantic_hits": 0,
            "partial_hits": 0,
            "misses": 0,
            "similarity_queries": 0
        }

    def _generate_semantic_key(
        self,
        incident_type: str,
        patterns: List[str]
    ) -> str:
        """
        Generate semantic key from incident type and patterns.

        Args:
            incident_type: Type of incident
            patterns: List of semantic patterns

        Returns:
            Semantic cache key
        """
        # Sort patterns for consistent keys
        patterns_sorted = sorted(patterns)

        # Create semantic signature
        signature = f"{incident_type}:{','.join(patterns_sorted)}"

        # Hash for key (keep length reasonable)
        signature_hash = hashlib.sha256(signature.encode()).hexdigest()[:16]

        return f"semantic:{incident_type}:{signature_hash}"

    async def get(
        self,
        incident_type: str,
        patterns: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached result for semantic pattern.

        Args:
            incident_type: Type of incident
            patterns: List of semantic patterns

        Returns:
            Cached analysis if patterns match sufficiently, None otherwise
        """
        key = self._generate_semantic_key(incident_type, patterns)

        try:
            result = await self.redis.get(key)

            if result:
                cached = json.loads(result)
                # Verify patterns match sufficiently (>70%)
                cached_patterns = cached.get("patterns", [])
                match_score = self._calculate_pattern_match(
                    patterns,
                    cached_patterns
                )

                if match_score > 0.7:
                    self._stats["semantic_hits"] += 1
                    cached["match_score"] = match_score
                    cached["semantic_hit"] = True
                    return cached

            self._stats["misses"] += 1
            return None

        except Exception as e:
            logger.error(f"SemanticCache: Error getting {key}: {e}")
            self._stats["misses"] += 1
            return None

    async def set(
        self,
        incident_type: str,
        patterns: List[str],
        analysis: Dict[str, Any],
        ttl: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Cache analysis with semantic patterns.

        Args:
            incident_type: Type of incident
            patterns: List of semantic patterns
            analysis: Analysis result to cache
            ttl: Override TTL (optional)
            metadata: Additional metadata to store

        Returns:
            True if successful, False otherwise
        """
        key = self._generate_semantic_key(incident_type, patterns)
        ttl = ttl or self.default_ttl

        try:
            value = {
                "incident_type": incident_type,
                "patterns": patterns,
                "analysis": analysis,
                "cached_at": datetime.now().isoformat(),
                "metadata": metadata or {}
            }

            serialized = json.dumps(value)
            await self.redis.setex(key, ttl, serialized)

            self._stats["sets"] += 1
            return True

        except Exception as e:
            logger.error(f"SemanticCache: Error setting {key}: {e}")
            return False

    def _calculate_pattern_match(
        self,
        patterns1: List[str],
        patterns2: List[str]
    ) -> float:
        """
        Calculate pattern match score using Jaccard similarity.

        Args:
            patterns1: First set of patterns
            patterns2: Second set of patterns

        Returns:
            Similarity score between 0 and 1
        """
        if not patterns1 or not patterns2:
            return 0.0

        # Convert to sets
        set1 = set(patterns1)
        set2 = set(patterns2)

        # Jaccard similarity = |intersection| / |union|
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))

        if union == 0:
            return 0.0

        return intersection / union

    async def find_similar(
        self,
        incident_type: str,
        patterns: List[str],
        threshold: float = 0.5,
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Find semantically similar cached incidents.

        Args:
            incident_type: Type of incident to match
            patterns: Patterns to match against
            threshold: Minimum similarity threshold (default: 0.5)
            max_results: Maximum number of results to return

        Returns:
            List of similar cached incidents, sorted by similarity
        """
        self._stats["similarity_queries"] += 1

        try:
            # Scan semantic keys for incident type
            pattern = f"semantic:{incident_type}:*"
            keys = []

            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key.decode() if isinstance(key, bytes) else key)

            if not keys:
                return []

            # Calculate similarity for each
            similar = []

            for key in keys:
                try:
                    cached_data = await self.redis.get(key)
                    if not cached_data:
                        continue

                    cached = json.loads(cached_data)
                    cached_patterns = cached.get("patterns", [])

                    match_score = self._calculate_pattern_match(
                        patterns,
                        cached_patterns
                    )

                    if match_score >= threshold:
                        cached["match_score"] = match_score
                        cached["matched_patterns"] = list(
                            set(patterns).intersection(set(cached_patterns))
                        )
                        similar.append(cached)

                except Exception as e:
                    logger.warning(f"Error processing key {key}: {e}")
                    continue

            # Sort by match score (highest first)
            similar.sort(key=lambda x: x.get("match_score", 0), reverse=True)

            return similar[:max_results]

        except Exception as e:
            logger.error(f"SemanticCache: Error finding similar: {e}")
            return []

    async def get_partial_match(
        self,
        incident_type: str,
        patterns: List[str],
        min_patterns: int = 2
    ) -> Optional[Dict[str, Any]]:
        """
        Get cache with partial pattern match.

        Args:
            incident_type: Type of incident
            patterns: Patterns to match
            min_patterns: Minimum number of patterns to match

        Returns:
            Cached analysis if enough patterns match, None otherwise
        """
        similar = await self.find_similar(
            incident_type=incident_type,
            patterns=patterns,
            threshold=0.3,  # Lower threshold for partial match
            max_results=1
        )

        if similar:
            result = similar[0]
            # Check if enough patterns matched
            matched_count = len(result.get("matched_patterns", []))
            if matched_count >= min_patterns:
                self._stats["partial_hits"] += 1
                result["partial_hit"] = True
                result["matched_pattern_count"] = matched_count
                return result

        return None

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all caches containing a specific pattern.

        Args:
            pattern: Pattern to invalidate

        Returns:
            Number of keys invalidated
        """
        try:
            # Find all semantic keys
            keys = []
            async for key in self.redis.scan_iter(match="semantic:*"):
                keys.append(key)

            # Check each key for the pattern
            to_delete = []
            for key in keys:
                try:
                    cached_data = await self.redis.get(key)
                    if cached_data:
                        cached = json.loads(cached_data)
                        cached_patterns = cached.get("patterns", [])
                        if pattern in cached_patterns:
                            to_delete.append(key)
                except Exception:
                    continue

            if to_delete:
                return await self.redis.delete(*to_delete)

            return 0

        except Exception as e:
            logger.error(f"SemanticCache: Error invalidating pattern: {e}")
            return 0

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get semantic cache statistics.

        Returns:
            Statistics dictionary
        """
        return {
            **self._stats,
            "total_requests": (
                self._stats["semantic_hits"] +
                self._stats["partial_hits"] +
                self._stats["misses"]
            )
        }

    def reset_stats(self) -> None:
        """Reset semantic cache statistics."""
        self._stats = {
            "sets": 0,
            "semantic_hits": 0,
            "partial_hits": 0,
            "misses": 0,
            "similarity_queries": 0
        }


class PatternExtractor:
    """
    Extract semantic patterns from incidents for caching.

    Analyzes incidents to extract key patterns that can be used
    for semantic matching and caching.
    """

    # Common pattern templates
    ERROR_PATTERNS = [
        "timeout",
        "connection_refused",
        "connection_reset",
        "5xx",
        "4xx",
        "out_of_memory",
        "disk_full",
        "permission_denied"
    ]

    METRIC_PATTERNS = [
        "cpu_high",
        "memory_high",
        "latency_p95",
        "latency_p99",
        "error_rate",
        "throughput",
        "queue_depth"
    ]

    SERVICE_PATTERNS = [
        "api",
        "database",
        "cache",
        "queue",
        "worker",
        "gateway"
    ]

    def __init__(self):
        self._pattern_cache = defaultdict(set)

    def extract_patterns(
        self,
        incident: Dict[str, Any]
    ) -> List[str]:
        """
        Extract key patterns from incident.

        Args:
            incident: Incident data dictionary

        Returns:
            List of semantic patterns
        """
        patterns = []

        # Extract from error messages
        if "error" in incident or "error_message" in incident:
            error_msg = incident.get("error") or incident.get("error_message", "")
            patterns.extend(self._extract_error_patterns(str(error_msg)))

        # Extract from affected services
        if "services" in incident:
            services = incident["services"]
            if isinstance(services, list):
                for service in services:
                    patterns.append(f"service:{service}")
            elif isinstance(services, str):
                patterns.append(f"service:{services}")

        # Extract from metrics
        if "metrics" in incident:
            patterns.extend(self._extract_metric_patterns(incident["metrics"]))

        # Extract from severity
        if "severity" in incident:
            patterns.append(f"severity:{incident['severity'].lower()}")

        # Extract from incident type
        if "type" in incident or "incident_type" in incident:
            inc_type = incident.get("type") or incident.get("incident_type")
            if inc_type:
                patterns.append(f"type:{inc_type}")

        # Extract from labels/tags
        if "labels" in incident:
            for key, value in incident["labels"].items():
                patterns.append(f"label:{key}:{value}")

        if "tags" in incident:
            if isinstance(incident["tags"], list):
                patterns.extend([f"tag:{t}" for t in incident["tags"]])
            elif isinstance(incident["tags"], dict):
                for k, v in incident["tags"].items():
                    patterns.append(f"tag:{k}:{v}")

        # Extract time patterns
        if "timestamp" in incident or "created_at" in incident:
            ts = incident.get("timestamp") or incident.get("created_at")
            if ts:
                patterns.append(self._extract_time_pattern(ts))

        # Deduplicate and return
        return list(set(patterns))

    def _extract_error_patterns(self, error_msg: str) -> List[str]:
        """Extract patterns from error message."""
        patterns = []
        error_lower = error_msg.lower()

        for error_pattern in self.ERROR_PATTERNS:
            if error_pattern in error_lower:
                patterns.append(f"error:{error_pattern}")

        return patterns

    def _extract_metric_patterns(self, metrics: Dict[str, Any]) -> List[str]:
        """Extract patterns from metrics data."""
        patterns = []

        for metric_name, metric_value in metrics.items():
            # Check if metric name matches known patterns
            for metric_pattern in self.METRIC_PATTERNS:
                if metric_pattern in metric_name.lower():
                    patterns.append(f"metric:{metric_pattern}")

            # Check if value indicates issue
            if isinstance(metric_value, (int, float)):
                if metric_value > 90:  # High percentage
                    patterns.append(f"{metric_name}:high")
                elif metric_value < 10:  # Low percentage
                    patterns.append(f"{metric_name}:low")

        return patterns

    def _extract_time_pattern(self, timestamp: str) -> str:
        """Extract time-based pattern."""
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

            # Time of day
            hour = dt.hour
            if 6 <= hour < 12:
                return "time:morning"
            elif 12 <= hour < 18:
                return "time:afternoon"
            elif 18 <= hour < 22:
                return "time:evening"
            else:
                return "time:night"

        except Exception:
            return "time:unknown"

    def extract_alerting_patterns(
        self,
        alert: Dict[str, Any]
    ) -> List[str]:
        """
        Extract patterns specifically from alerting data.

        Args:
            alert: Alert dictionary

        Returns:
            List of semantic patterns
        """
        patterns = []

        # Alert name/type
        if "name" in alert:
            patterns.append(f"alert:{alert['name']}")

        if "alertname" in alert:
            patterns.append(f"alert:{alert['alertname']}")

        # Severity
        if "severity" in alert:
            patterns.append(f"severity:{alert['severity'].lower()}")

        # Labels
        if "labels" in alert:
            for key, value in alert["labels"].items():
                patterns.append(f"label:{key}:{value}")

        # Annotations
        if "annotations" in alert:
            for key, value in alert["annotations"].items():
                if isinstance(value, str) and len(value) < 50:
                    patterns.append(f"annotation:{key}:{value}")

        # State
        if "state" in alert:
            patterns.append(f"state:{alert['state'].lower()}")

        return patterns

    def suggest_patterns(
        self,
        incidents: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Suggest common patterns from multiple incidents.

        Args:
            incidents: List of incidents to analyze

        Returns:
            List of suggested patterns with frequency
        """
        pattern_counts = defaultdict(int)

        for incident in incidents:
            patterns = self.extract_patterns(incident)
            for pattern in patterns:
                pattern_counts[pattern] += 1

        # Return patterns sorted by frequency
        sorted_patterns = sorted(
            pattern_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Format as "pattern:count"
        return [f"{p}:{c}" for p, c in sorted_patterns]

    def get_pattern_stats(self) -> Dict[str, int]:
        """
        Get statistics about extracted patterns.

        Returns:
            Dictionary with pattern frequencies
        """
        return {k: len(v) for k, v in self._pattern_cache.items()}

