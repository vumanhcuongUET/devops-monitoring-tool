"""
Unit Tests for L3 Semantic Cache

Phase 7 - Sprint 1 - Day 6
Tests for semantic caching implementation
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.cache.l3_cache import (
    SemanticCache,
    PatternExtractor,
    SemanticCacheIndex
)


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""

    # Create async iterator helper
    class AsyncIterator:
        def __init__(self, items):
            self.items = items

        def __aiter__(self):
            self.aiter = iter(self.items)
            return self

        async def __anext__(self):
            try:
                return next(self.aiter)
            except StopIteration:
                raise StopAsyncIteration

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.setex = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.zadd = AsyncMock(return_value=1)
    redis.zrange = AsyncMock(return_value=[])
    redis.zrem = AsyncMock(return_value=1)
    redis.zremrangebyscore = AsyncMock(return_value=0)
    redis.expire = AsyncMock(return_value=True)
    redis.exists = AsyncMock(return_value=0)

    # Store items for scan_iter
    scan_items = []

    def make_scan_iter(match=None, count=None):
        return AsyncIterator(scan_items)

    redis.scan_iter = MagicMock(side_effect=make_scan_iter)
    redis._scan_items = scan_items  # Store reference for tests to modify

    return redis


@pytest.fixture
def semantic_cache(mock_redis):
    """Create semantic cache with mock Redis."""
    return SemanticCache(redis_client=mock_redis)


class TestSemanticKeyGeneration:
    """Test semantic key generation."""

    def test_key_generation_basic(self, semantic_cache):
        """Test basic semantic key generation."""
        patterns = ["service:api", "error:timeout"]
        key = semantic_cache._generate_semantic_key("performance", patterns)

        assert key.startswith("semantic:performance:")
        assert len(key.split(":")) == 3  # semantic:type:hash

    def test_key_generation_order_independent(self, semantic_cache):
        """Test key generation is order-independent."""
        patterns1 = ["service:api", "error:timeout"]
        patterns2 = ["error:timeout", "service:api"]  # Different order

        key1 = semantic_cache._generate_semantic_key("performance", patterns1)
        key2 = semantic_cache._generate_semantic_key("performance", patterns2)

        assert key1 == key2

    def test_key_different_types(self, semantic_cache):
        """Test different incident types generate different keys."""
        patterns = ["service:api", "error:timeout"]

        key1 = semantic_cache._generate_semantic_key("performance", patterns)
        key2 = semantic_cache._generate_semantic_key("availability", patterns)

        assert key1 != key2


class TestSemanticCacheBasics:
    """Test basic semantic cache operations."""

    @pytest.mark.asyncio
    async def test_cache_miss(self, semantic_cache, mock_redis):
        """Test cache miss returns None."""
        mock_redis.get.return_value = None

        result = await semantic_cache.get("performance", ["service:api"])

        assert result is None
        assert semantic_cache._stats["misses"] == 1

    @pytest.mark.asyncio
    async def test_set_and_get(self, semantic_cache, mock_redis):
        """Test set and get operations."""
        import json

        analysis = {"recommendation": "scale up"}
        patterns = ["service:api", "error:timeout"]

        # Set
        result = await semantic_cache.set(
            "performance",
            patterns,
            analysis
        )
        assert result is True

        # Get with same patterns
        mock_redis.get.return_value = json.dumps({
            "patterns": patterns,
            "analysis": analysis
        }).encode()

        result = await semantic_cache.get("performance", patterns)

        assert result is not None
        assert result["analysis"] == analysis

    @pytest.mark.asyncio
    async def test_semantic_hit_with_similarity(self, semantic_cache, mock_redis):
        """Test semantic hit with sufficient similarity."""
        import json

        # Use patterns that will exceed the 0.7 threshold
        cached_patterns = ["service:api", "error:timeout", "severity:high"]
        request_patterns = ["service:api", "error:timeout", "severity:high", "metric:cpu"]

        mock_redis.get.return_value = json.dumps({
            "patterns": cached_patterns,
            "analysis": {"recommendation": "check logs"}
        }).encode()

        result = await semantic_cache.get("performance", request_patterns)

        # Should hit due to 3/4 pattern match (75%)
        assert result is not None
        assert result["semantic_hit"] is True
        assert result["match_score"] == 0.75  # Jaccard similarity: 3/4

    @pytest.mark.asyncio
    async def test_semantic_miss_low_similarity(self, semantic_cache, mock_redis):
        """Test semantic miss with insufficient similarity."""
        import json

        cached_patterns = ["service:api", "error:timeout"]
        request_patterns = ["service:database", "error:connection"]

        mock_redis.get.return_value = json.dumps({
            "patterns": cached_patterns,
            "analysis": {"recommendation": "check logs"}
        }).encode()

        result = await semantic_cache.get("performance", request_patterns)

        # Should miss due to 0 pattern match
        assert result is None


class TestPatternMatching:
    """Test pattern matching algorithms."""

    def test_jaccard_similarity_identical(self, semantic_cache):
        """Test Jaccard similarity with identical sets."""
        patterns1 = ["service:api", "error:timeout"]
        patterns2 = ["service:api", "error:timeout"]

        score = semantic_cache._calculate_pattern_match(patterns1, patterns2)

        assert score == 1.0  # Perfect match

    def test_jaccard_similarity_partial(self, semantic_cache):
        """Test Jaccard similarity with partial overlap."""
        patterns1 = ["service:api", "error:timeout", "severity:high"]
        patterns2 = ["service:api", "error:timeout"]

        score = semantic_cache._calculate_pattern_match(patterns1, patterns2)

        # 2 intersection, 3 union = 0.667
        assert round(score, 3) == 0.667

    def test_jaccard_similarity_no_overlap(self, semantic_cache):
        """Test Jaccard similarity with no overlap."""
        patterns1 = ["service:api", "error:timeout"]
        patterns2 = ["service:database", "error:connection"]

        score = semantic_cache._calculate_pattern_match(patterns1, patterns2)

        assert score == 0.0  # No overlap

    def test_jaccard_similarity_empty_sets(self, semantic_cache):
        """Test Jaccard similarity with empty sets."""
        score1 = semantic_cache._calculate_pattern_match([], ["service:api"])
        score2 = semantic_cache._calculate_pattern_match([], [])

        assert score1 == 0.0
        assert score2 == 0.0


class TestFindSimilar:
    """Test finding similar cached incidents."""

    @pytest.mark.asyncio
    async def test_find_similar_no_results(self, semantic_cache, mock_redis):
        """Test find_similar with no matches."""
        mock_redis._scan_items.clear()

        results = await semantic_cache.find_similar(
            "performance",
            ["service:api"],
            threshold=0.5
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_find_similar_with_results(self, semantic_cache, mock_redis):
        """Test find_similar with matching results."""
        import json

        # Mock Redis to return some cached data
        cached_data1 = json.dumps({
            "patterns": ["service:api", "error:timeout"],
            "analysis": {"recommendation": "restart"}
        }).encode()

        cached_data2 = json.dumps({
            "patterns": ["service:api", "error:connection"],
            "analysis": {"recommendation": "check network"}
        }).encode()

        mock_redis._scan_items.extend([
            b"semantic:performance:key1",
            b"semantic:performance:key2"
        ])

        # Configure mock to return different data for each key
        get_results = [cached_data1, cached_data2]
        mock_redis.get.side_effect = lambda k: get_results.pop(0) if get_results else None

        results = await semantic_cache.find_similar(
            "performance",
            ["service:api", "error:timeout"],
            threshold=0.3
        )

        # Should return at least one match
        assert len(results) >= 1
        # Results should be sorted by match score
        if len(results) > 1:
            assert results[0]["match_score"] >= results[1]["match_score"]

    @pytest.mark.asyncio
    async def test_find_similar_max_results(self, semantic_cache, mock_redis):
        """Test find_similar respects max_results limit."""
        import json

        # Mock multiple results
        mock_keys = [f"semantic:performance:key{i}".encode() for i in range(10)]
        mock_redis._scan_items.extend(mock_keys)

        cached_data = json.dumps({
            "patterns": ["service:api"],
            "analysis": {}
        }).encode()

        mock_redis.get.return_value = cached_data

        results = await semantic_cache.find_similar(
            "performance",
            ["service:api"],
            threshold=0.1,
            max_results=5
        )

        assert len(results) <= 5


class TestPatternExtractor:
    """Test pattern extraction from incidents."""

    @pytest.fixture
    def extractor(self):
        return PatternExtractor()

    def test_extract_from_basic_incident(self, extractor):
        """Test extracting patterns from basic incident."""
        incident = {
            "type": "performance",
            "services": ["api-gateway", "redis"],
            "severity": "high",
            "error": "timeout waiting for redis"
        }

        patterns = extractor.extract_patterns(incident)

        assert "type:performance" in patterns
        assert "service:api-gateway" in patterns
        assert "service:redis" in patterns
        assert "severity:high" in patterns
        assert "error:timeout" in patterns

    def test_extract_from_alert(self, extractor):
        """Test extracting patterns from alert data."""
        alert = {
            "alertname": "HighLatency",
            "severity": "warning",
            "labels": {
                "service": "api",
                "region": "us-east-1"
            },
            "annotations": {
                "summary": "API latency above 2s"
            }
        }

        patterns = extractor.extract_alerting_patterns(alert)

        assert "alert:HighLatency" in patterns
        assert "severity:warning" in patterns
        assert "label:service:api" in patterns

    def test_extract_metric_patterns(self, extractor):
        """Test extracting patterns from metrics."""
        metrics = {
            "cpu_usage_percent": 95,
            "memory_usage_percent": 45,
            "latency_p95_ms": 2500
        }

        patterns = extractor._extract_metric_patterns(metrics)

        assert "cpu_usage_percent:high" in patterns
        assert "latency_p95_ms:high" in patterns

    def test_extract_time_patterns(self, extractor):
        """Test extracting time-based patterns."""
        # Morning (10 AM)
        incident1 = {"timestamp": "2026-08-23T10:00:00Z"}
        patterns1 = extractor.extract_patterns(incident1)
        assert "time:morning" in patterns1

        # Evening (8 PM)
        incident2 = {"timestamp": "2026-08-23T20:00:00Z"}
        patterns2 = extractor.extract_patterns(incident2)
        assert "time:evening" in patterns2

    def test_suggest_patterns(self, extractor):
        """Test suggesting common patterns from multiple incidents."""
        incidents = [
            {"services": ["api"], "error": "timeout"},
            {"services": ["api"], "error": "timeout"},
            {"services": ["database"], "error": "timeout"}
        ]

        suggestions = extractor.suggest_patterns(incidents)

        # Should suggest patterns with frequency
        assert any("service:api:2" in s for s in suggestions)
        assert any("error:timeout:3" in s for s in suggestions)


class TestSemanticCacheIndex:
    """Test semantic cache index for fast lookups."""

    @pytest.fixture
    def index(self, mock_redis):
        return SemanticCacheIndex(mock_redis)

    @pytest.mark.asyncio
    async def test_add_to_index(self, index, mock_redis):
        """Test adding cache key to index."""
        patterns = ["service:api", "error:timeout"]
        cache_key = "semantic:performance:test123"

        await index.add_to_index(cache_key, patterns, ttl=3600)

        # Should have created index entries for each pattern
        assert mock_redis.zadd.call_count == 2

    @pytest.mark.asyncio
    async def test_find_by_patterns(self, index, mock_redis):
        """Test finding keys by pattern match."""
        mock_redis.zrange.return_value = [
            b"key1",
            b"key2",
            b"key3"
        ]

        results = await index.find_by_patterns(
            ["service:api", "error:timeout"],
            min_match=1
        )

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_find_by_patterns_min_match(self, index, mock_redis):
        """Test finding with minimum match requirement."""
        # Mock different results for different patterns
        def zrange_side_effect(key, *args):
            if "service:api" in str(key):
                return [b"key1", b"key2"]
            elif "error:timeout" in str(key):
                return [b"key2", b"key3"]
            return []

        mock_redis.zrange.side_effect = zrange_side_effect

        results = await index.find_by_patterns(
            ["service:api", "error:timeout"],
            min_match=2
        )

        # Only key2 appears in both
        assert results == ["key2"]

    @pytest.mark.asyncio
    async def test_remove_from_index(self, index, mock_redis):
        """Test removing key from all indexes."""
        mock_redis._scan_items.extend([
            b"semantic_index:service:api",
            b"semantic_index:error:timeout"
        ])

        await index.remove_from_index("semantic:test123")

        # Should have attempted removal from both indexes
        assert mock_redis.zrem.call_count == 2

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, index, mock_redis):
        """Test cleaning up expired index entries."""
        mock_redis._scan_items.extend([b"semantic_index:service:api"])
        mock_redis.zremrangebyscore.return_value = 5

        cleaned = await index.cleanup_expired(max_age_seconds=3600)

        assert cleaned == 5


class TestSemanticCacheScenarios:
    """Test real-world semantic cache scenarios."""

    @pytest.mark.asyncio
    async def test_incident_similarity_scenario(self, semantic_cache, mock_redis):
        """Test semantic matching for similar incidents."""
        import json

        # Cache previous incident analysis
        cached_incident = {
            "patterns": [
                "service:api-gateway",
                "error:5xx",
                "severity:high",
                "metric:error_rate"
            ],
            "analysis": {
                "recommendation": "Check upstream service",
                "possible_causes": ["backend timeout", "database issue"]
            }
        }

        await semantic_cache.set(
            "availability",
            cached_incident["patterns"],
            cached_incident["analysis"]
        )

        # New incident with similar patterns
        new_patterns = [
            "service:api-gateway",
            "error:timeout",
            "severity:high"
        ]

        # Mock Redis to return cached data
        mock_redis._scan_items.extend([b"semantic:availability:abc123"])
        mock_redis.get.return_value = json.dumps({
            "patterns": cached_incident["patterns"],
            "analysis": cached_incident["analysis"]
        }).encode()

        similar = await semantic_cache.find_similar(
            "availability",
            new_patterns,
            threshold=0.4
        )

        # Should find similar incident due to service and severity match
        assert len(similar) >= 1
        assert similar[0]["match_score"] >= 0.4

    @pytest.mark.asyncio
    async def test_partial_match_for_degraded_mode(self, semantic_cache, mock_redis):
        """Test partial matching for graceful degradation scenarios."""
        import json

        cached_patterns = [
            "service:api",
            "service:database",
            "service:redis",
            "error:timeout"
        ]

        await semantic_cache.set(
            "performance",
            cached_patterns,
            {"recommendation": "check dependencies"}
        )

        # Request with only some patterns (degraded data)
        request_patterns = ["service:api", "error:timeout"]

        mock_redis._scan_items.extend([b"semantic:performance:xyz"])
        mock_redis.get.return_value = json.dumps({
            "patterns": cached_patterns,
            "analysis": {"recommendation": "check dependencies"}
        }).encode()

        result = await semantic_cache.get_partial_match(
            "performance",
            request_patterns,
            min_patterns=2
        )

        # Should get partial hit even with incomplete patterns
        assert result is not None
        assert result["partial_hit"] is True

    @pytest.mark.asyncio
    async def test_invalidate_pattern(self, semantic_cache, mock_redis):
        """Test invalidating all caches with a pattern."""
        import json

        # Mock scan to return multiple keys
        mock_redis._scan_items.extend([
            b"semantic:test:key1",
            b"semantic:test:key2",
            b"semantic:other:key3"
        ])

        # Mock get to check patterns
        def get_side_effect(key):
            if b"key1" in key or b"key2" in key:
                return json.dumps({"patterns": ["service:api"]}).encode()
            return json.dumps({"patterns": ["service:db"]}).encode()

        mock_redis.get.side_effect = get_side_effect
        mock_redis.delete.return_value = 2

        # Invalidate all with service:api pattern
        invalidated = await semantic_cache.invalidate_pattern("service:api")

        assert invalidated == 2  # key1 and key2

    @pytest.mark.asyncio
    async def test_statistics_tracking(self, semantic_cache, mock_redis):
        """Test semantic cache statistics."""
        stats = await semantic_cache.get_stats()

        assert "sets" in stats
        assert "semantic_hits" in stats
        assert "partial_hits" in stats
        assert "misses" in stats
        assert "similarity_queries" in stats
        assert "total_requests" in stats

    def test_reset_stats(self, semantic_cache):
        """Test resetting statistics."""
        semantic_cache._stats["semantic_hits"] = 10
        semantic_cache.reset_stats()

        assert semantic_cache._stats["semantic_hits"] == 0
        assert semantic_cache._stats["sets"] == 0

    @pytest.mark.asyncio
    async def test_custom_ttl(self, semantic_cache, mock_redis):
        """Test setting custom TTL."""
        await semantic_cache.set(
            "test",
            ["pattern"],
            {"data": "test"},
            ttl=3600  # 1 hour
        )

        # Verify setex was called with custom TTL
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        # setex is called with (key, ttl, value)
        assert call_args[0][1] == 3600  # Second positional arg is TTL

    @pytest.mark.asyncio
    async def test_metadata_storage(self, semantic_cache, mock_redis):
        """Test storing metadata with cached analysis."""
        import json
        metadata = {
            "source": "alert",
            "created_by": "system",
            "confidence": 0.9
        }

        await semantic_cache.set(
            "test",
            ["pattern"],
            {"analysis": "result"},
            metadata=metadata
        )

        # Verify metadata is stored
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        # setex is called with (key, ttl, value)
        stored_value = json.loads(call_args[0][2])  # Third positional arg is value
        assert stored_value["metadata"] == metadata
