"""
Unit Tests for L2 Redis Cache

Phase 7 - Sprint 1 - Day 5
Tests for L2 distributed cache implementation
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.cache.l2_cache import (
    L2CacheManager,
    RedisSentinelManager,
    SerializationFormat,
    create_l2_cache_from_env
)


@pytest.fixture
async def mock_redis():
    """Create a mock Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.setex = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.mget = AsyncMock(return_value=[None])
    redis.zadd = AsyncMock(return_value=1)
    redis.zrange = AsyncMock(return_value=[])
    redis.expire = AsyncMock(return_value=True)
    redis.scan_iter = MagicMock(return_value=iter([]))
    return redis


@pytest.fixture
def l2_cache(mock_redis):
    """Create L2 cache manager with mock Redis."""
    return L2CacheManager(redis_client=mock_redis)


class TestL2CacheBasics:
    """Test basic L2 cache operations."""

    def test_initialization(self, mock_redis):
        """Test cache initializes correctly."""
        cache = L2CacheManager(redis_client=mock_redis)
        assert cache.redis == mock_redis
        assert cache.default_ttl == 300
        assert cache.key_prefix == "l2"

    def test_key_generation(self, mock_redis):
        """Test Redis key generation."""
        cache = L2CacheManager(redis_client=mock_redis)

        key1 = cache._get_key("health", {"project": "test"})
        key2 = cache._get_key("health", {"project": "test"})

        assert key1 == key2
        assert key1.startswith("l2:health:")

    def test_key_generation_order_independent(self, mock_redis):
        """Test key generation is order-independent."""
        cache = L2CacheManager(redis_client=mock_redis)

        key1 = cache._get_key("metrics", {"project": "test", "time_range": "1h"})
        key2 = cache._get_key("metrics", {"time_range": "1h", "project": "test"})

        assert key1 == key2

    def test_key_generation_long_value_hashing(self, mock_redis):
        """Test long values are hashed in keys."""
        cache = L2CacheManager(redis_client=mock_redis)

        long_value = "x" * 100
        key = cache._get_key("logs", {"project": long_value})

        # Long value should be hashed
        assert len(key) < len("l2:logs:project:" + long_value)


class TestL2CacheOperations:
    """Test L2 cache get/set/delete operations."""

    @pytest.mark.asyncio
    async def test_get_cache_miss(self, l2_cache, mock_redis):
        """Test get returns None on cache miss."""
        mock_redis.get.return_value = None

        result = await l2_cache.get("health", {"project": "test"})

        assert result is None
        mock_redis.get.assert_called_once()
        assert l2_cache._stats["misses"] == 1

    @pytest.mark.asyncio
    async def test_get_cache_hit(self, l2_cache, mock_redis):
        """Test get returns cached value on hit."""
        cached_data = {"status": "green"}
        mock_redis.get.return_value = l2_cache._serialize(cached_data)

        result = await l2_cache.get("health", {"project": "test"})

        assert result == cached_data
        mock_redis.get.assert_called_once()
        assert l2_cache["hits"] == 1

    @pytest.mark.asyncio
    async def test_set_with_default_ttl(self, l2_cache, mock_redis):
        """Test set with type-specific TTL."""
        await l2_cache.set("health", {"project": "test"}, {"data": "test"})

        # Verify setex was called with health TTL (60s)
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][2] == 60  # TTL for health

    @pytest.mark.asyncio
    async def test_set_with_custom_ttl(self, l2_cache, mock_redis):
        """Test set with custom TTL override."""
        await l2_cache.set("health", {"project": "test"}, {"data": "test"}, ttl=120)

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][2] == 120  # Custom TTL

    @pytest.mark.asyncio
    async def test_set_with_tags(self, l2_cache, mock_redis):
        """Test set with tags for invalidation."""
        await l2_cache.set(
            "health",
            {"project": "test"},
            {"data": "test"},
            tags=["project:test", "type:health"]
        )

        # Verify setex was called
        mock_redis.setex.assert_called_once()
        # Verify zadd was called for tag index
        assert mock_redis.zadd.call_count == 2

    @pytest.mark.asyncio
    async def test_delete(self, l2_cache, mock_redis):
        """Test delete operation."""
        mock_redis.delete.return_value = 1

        result = await l2_cache.delete("health", {"project": "test"})

        assert result == 1
        mock_redis.delete.assert_called_once()
        assert l2_cache._stats["deletes"] == 1

    @pytest.mark.asyncio
    async def test_invalidate_pattern(self, l2_cache, mock_redis):
        """Test pattern-based invalidation."""
        mock_redis.scan_iter.return_value = iter([b"l2:health:test1", b"l2:health:test2"])
        mock_redis.delete.return_value = 2

        result = await l2_cache.invalidate_pattern("l2:health:*")

        assert result == 2

    @pytest.mark.asyncio
    async def test_mget(self, l2_cache, mock_redis):
        """Test multi-get operation."""
        values = [
            l2_cache._serialize({"data": "test1"}),
            None,
            l2_cache._serialize({"data": "test3"})
        ]
        mock_redis.mget.return_value = values

        identifiers = [
            {"project": "test1"},
            {"project": "test2"},
            {"project": "test3"}
        ]
        results = await l2_cache.mget("health", identifiers)

        assert len(results) == 3
        assert results[0] == {"data": "test1"}
        assert results[1] is None
        assert results[2] == {"data": "test3"}

    @pytest.mark.asyncio
    async def test_mset(self, l2_cache, mock_redis):
        """Test multi-set operation."""
        items = [
            ({"project": "test1"}, {"data": "test1"}),
            ({"project": "test2"}, {"data": "test2"})
        ]

        result = await l2_cache.mset("health", items)

        assert result is True
        assert l2_cache._stats["sets"] == 2


class TestL2CacheTagInvalidation:
    """Test tag-based cache invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_by_tag(self, l2_cache, mock_redis):
        """Test invalidation by tag."""
        mock_redis.zrange.return_value = [b"l2:health:test", b"l2:metrics:test"]
        mock_redis.delete.return_value = 2

        result = await l2_cache.invalidate_by_tag("project:test")

        assert result == 2
        mock_redis.zrange.assert_called_once()
        mock_redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_get_by_tag(self, l2_cache, mock_redis):
        """Test getting all values by tag."""
        values = [
            l2_cache._serialize({"data": "test1"}),
            l2_cache._serialize({"data": "test2"})
        ]
        mock_redis.zrange.return_value = [b"key1", b"key2"]
        mock_redis.mget.return_value = values

        result = await l2_cache.get_by_tag("project:test")

        assert len(result) == 2
        assert result[0] == {"data": "test1"}
        assert result[1] == {"data": "test2"}


class TestL2CacheStatistics:
    """Test L2 cache statistics and monitoring."""

    @pytest.mark.asyncio
    async def test_hit_rate_calculation(self, l2_cache, mock_redis):
        """Test hit rate calculation."""
        # Simulate some hits and misses
        mock_redis.get.return_value = None  # Miss
        await l2_cache.get("health", {"project": "test1"})

        mock_redis.get.return_value = l2_cache._serialize({"data": "test"})  # Hit
        await l2_cache.get("health", {"project": "test2"})

        hit_rate = await l2_cache.get_hit_rate()
        assert hit_rate == 50.0  # 1 hit, 1 miss

    @pytest.mark.asyncio
    async def test_get_stats(self, l2_cache, mock_redis):
        """Test getting full statistics."""
        stats = await l2_cache.get_stats()

        assert "hits" in stats
        assert "misses" in stats
        assert "sets" in stats
        assert "deletes" in stats
        assert "errors" in stats
        assert "hit_rate" in stats
        assert "total_requests" in stats

    def test_reset_stats(self, l2_cache):
        """Test resetting statistics."""
        l2_cache._stats["hits"] = 100
        l2_cache.reset_stats()

        assert l2_cache._stats["hits"] == 0
        assert l2_cache._stats["misses"] == 0


class TestL2CacheSerialization:
    """Test serialization formats."""

    def test_json_serialization(self, mock_redis):
        """Test JSON serialization."""
        cache = L2CacheManager(
            redis_client=mock_redis,
            serialization=SerializationFormat.JSON
        )

        value = {"data": "test", "number": 123}
        serialized = cache._serialize(value)

        assert isinstance(serialized, bytes)
        deserialized = cache._deserialize(serialized)
        assert deserialized == value

    def test_msgpack_fallback(self, mock_redis):
        """Test MsgPack falls back to JSON if unavailable."""
        with patch.dict('sys.modules', {'msgpack': None}):
            cache = L2CacheManager(
                redis_client=mock_redis,
                serialization=SerializationFormat.MSGPACK
            )

            value = {"data": "test"}
            serialized = cache._serialize(value)

            # Should fall back to JSON
            assert isinstance(serialized, bytes)

    @pytest.mark.asyncio
    async def test_complex_data_serialization(self, l2_cache, mock_redis):
        """Test serialization of complex data structures."""
        complex_value = {
            "string": "test",
            "number": 123,
            "float": 45.67,
            "bool": True,
            "null": None,
            "list": [1, 2, 3],
            "nested": {"key": "value"}
        }

        await l2_cache.set("test", {"id": "1"}, complex_value)

        # Verify serialization worked
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        serialized_value = call_args[0][1]
        assert isinstance(serialized_value, bytes)


class TestRedisSentinel:
    """Test Redis Sentinel management."""

    @pytest.mark.asyncio
    async def test_sentinel_initialization(self):
        """Test Sentinel manager initialization."""
        with patch('app.cache.l2_cache.redis') as mock_redis_module:
            sentinel = RedisSentinelManager(
                sentinel_hosts=["localhost:26379"],
                master_name="mymaster"
            )

            assert sentinel.master_name == "mymaster"
            assert sentinel.sentinel_hosts == ["localhost:26379"]

    @pytest.mark.asyncio
    async def test_get_master(self):
        """Test getting master address."""
        with patch('app.cache.l2_cache.redis') as mock_redis_module:
            # Mock Sentinel
            mock_sentinel = AsyncMock()
            mock_sentinel.sentinel_master = AsyncMock(return_value={
                "host": "127.0.0.1",
                "port": 6379
            })
            mock_redis_module.sentinel.Sentinel = MagicMock(return_value=mock_sentinel)

            sentinel = RedisSentinelManager(
                sentinel_hosts=["localhost:26379"],
                master_name="mymaster"
            )

            master = await sentinel.get_master()

            assert master == "127.0.0.1:6379"

    @pytest.mark.asyncio
    async def test_check_failover(self):
        """Test failover detection."""
        with patch('app.cache.l2_cache.redis') as mock_redis_module:
            mock_sentinel = AsyncMock()
            mock_sentinel.sentinel_master = AsyncMock(return_value={
                "host": "127.0.0.1",
                "port": 6379
            })
            mock_redis_module.sentinel.Sentinel = MagicMock(return_value=mock_sentinel)

            sentinel = RedisSentinelManager(
                sentinel_hosts=["localhost:26379"],
                master_name="mymaster"
            )

            # First call sets master
            await sentinel.get_master()

            # Simulate failover
            mock_sentinel.sentinel_master = AsyncMock(return_value={
                "host": "127.0.0.2",
                "port": 6379
            })

            changed = await sentinel.check_failover()

            assert changed is True


class TestEnvironmentIntegration:
    """Test environment-based cache creation."""

    @pytest.mark.asyncio
    async def test_create_from_env_url(self):
        """Test creating cache from REDIS_URL."""
        with patch.dict('os.environ', {'REDIS_URL': 'redis://localhost:6379/0'}):
            with patch('app.cache.l2_cache.REDIS_AVAILABLE', True):
                with patch('app.cache.l2_cache.Redis') as mock_redis_class:
                    mock_pool = MagicMock()
                    mock_redis_class.ConnectionPool.from_url.return_value = mock_pool
                    mock_redis_class.return_value = MagicMock()

                    cache = create_l2_cache_from_env()

                    assert cache is not None

    @pytest.mark.asyncio
    async def test_create_from_env_components(self):
        """Test creating cache from component env vars."""
        env_vars = {
            'REDIS_HOST': 'localhost',
            'REDIS_PORT': '6379',
            'REDIS_PASSWORD': 'testpass',
            'REDIS_DB': '1'
        }

        with patch.dict('os.environ', env_vars):
            with patch('app.cache.l2_cache.REDIS_AVAILABLE', True):
                with patch('app.cache.l2_cache.Redis') as mock_redis_class:
                    mock_pool = MagicMock()
                    mock_redis_class.ConnectionPool.from_url.return_value = mock_pool
                    mock_redis_class.return_value = MagicMock()

                    cache = create_l2_cache_from_env()

                    assert cache is not None


class TestL2CacheScenarios:
    """Test real-world L2 cache scenarios."""

    @pytest.mark.asyncio
    async def test_overview_caching_scenario(self, l2_cache, mock_redis):
        """Test caching overview page data."""
        mock_redis.get.return_value = None  # Initial miss

        # First request - cache miss
        overview_data = await l2_cache.get("overview", {"project": "test"})
        assert overview_data is None
        assert l2_cache._stats["misses"] == 1

        # Cache the overview
        overview = {
            "health": {"status": "green"},
            "metrics": {"requests": 100},
            "alerts": []
        }
        await l2_cache.set("overview", {"project": "test"}, overview)

        # Second request - cache hit
        mock_redis.get.return_value = l2_cache._serialize(overview)
        cached_overview = await l2_cache.get("overview", {"project": "test"})
        assert cached_overview == overview
        assert l2_cache._stats["hits"] == 1

    @pytest.mark.asyncio
    async def test_tag_based_invalidation_scenario(self, l2_cache, mock_redis):
        """Test tag-based cache invalidation on deployment."""
        # Cache data with deployment tag
        await l2_cache.set(
            "config",
            {"project": "test", "service": "api"},
            {"config": "value"},
            tags=["project:test", "service:api", "deployment:123"]
        )

        # Simulate deployment invalidation
        mock_redis.zrange.return_value = [b"l2:config:test_api"]
        mock_redis.delete.return_value = 1

        invalidated = await l2_cache.invalidate_by_tag("deployment:123")

        assert invalidated == 1

    @pytest.mark.asyncio
    async def test_ttl_per_data_type(self, l2_cache, mock_redis):
        """Test different TTL for different data types."""
        await l2_cache.set("health", {"project": "test"}, {"data": "test"})
        call_args = mock_redis.setex.call_args
        assert call_args[0][2] == 60  # Health TTL

        mock_redis.reset_mock()
        await l2_cache.set("metrics", {"project": "test"}, {"data": "test"})
        call_args = mock_redis.setex.call_args
        assert call_args[0][2] == 300  # Metrics TTL

        mock_redis.reset_mock()
        await l2_cache.set("semantic", {"project": "test"}, {"data": "test"})
        call_args = mock_redis.setex.call_args
        assert call_args[0][2] == 86400  # Semantic TTL (24h)

    @pytest.mark.asyncio
    async def test_batch_operations(self, l2_cache, mock_redis):
        """Test batch get/set operations."""
        # Set multiple items
        items = [
            ({"id": "1"}, {"data": "value1"}),
            ({"id": "2"}, {"data": "value2"}),
            ({"id": "3"}, {"data": "value3"})
        ]
        await l2_cache.mset("batch", items)

        assert l2_cache._stats["sets"] == 3

        # Get multiple items
        mock_redis.mget.return_value = [
            l2_cache._serialize({"data": "value1"}),
            l2_cache._serialize({"data": "value2"}),
            l2_cache._serialize({"data": "value3"})
        ]

        identifiers = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        results = await l2_cache.mget("batch", identifiers)

        assert len(results) == 3
        assert results[0] == {"data": "value1"}
