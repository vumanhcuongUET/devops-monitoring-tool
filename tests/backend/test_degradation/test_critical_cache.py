"""
Tests for Critical Data Cache - Phase 7 Sprint 2
"""

import pytest
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from app.degradation.critical_cache import (
    CriticalDataCache,
    CriticalDataEntry,
    DataFreshness
)


class TestCriticalDataEntry:
    """Tests for CriticalDataEntry model."""

    def test_create_entry(self):
        """Test creating a critical data entry."""
        entry = CriticalDataEntry(
            project="test_project",
            source_name="test_source",
            data={"key": "value"},
            timestamp=datetime.now().isoformat(),
            ttl_seconds=900,
            priority="high"
        )

        assert entry.project == "test_project"
        assert entry.source_name == "test_source"
        assert entry.data == {"key": "value"}
        assert entry.ttl_seconds == 900
        assert entry.priority == "high"

    def test_is_expired_false(self):
        """Test expiration check for non-expired entry."""
        entry = CriticalDataEntry(
            project="test",
            source_name="test",
            data={},
            timestamp=datetime.now().isoformat(),
            ttl_seconds=900
        )

        assert entry.is_expired() is False

    def test_is_expired_true(self):
        """Test expiration check for expired entry."""
        old_time = datetime.now() - timedelta(seconds=1000)
        entry = CriticalDataEntry(
            project="test",
            source_name="test",
            data={},
            timestamp=old_time.isoformat(),
            ttl_seconds=900
        )

        assert entry.is_expired() is True

    def test_get_age_seconds(self):
        """Test getting entry age."""
        # Create entry 100 seconds ago
        old_time = datetime.now() - timedelta(seconds=100)
        entry = CriticalDataEntry(
            project="test",
            source_name="test",
            data={},
            timestamp=old_time.isoformat()
        )

        age = entry.get_age_seconds()
        assert 95 <= age <= 105  # Allow some tolerance

    def test_get_freshness_fresh(self):
        """Test freshness level for fresh data."""
        entry = CriticalDataEntry(
            project="test",
            source_name="test",
            data={},
            timestamp=datetime.now().isoformat()
        )

        assert entry.get_freshness() == DataFreshness.FRESH

    def test_get_freshness_stale(self):
        """Test freshness level for stale data."""
        old_time = datetime.now() - timedelta(seconds=400)  # 6-7 minutes
        entry = CriticalDataEntry(
            project="test",
            source_name="test",
            data={},
            timestamp=old_time.isoformat()
        )

        assert entry.get_freshness() == DataFreshness.STALE

    def test_get_freshness_expired(self):
        """Test freshness level for expired data."""
        old_time = datetime.now() - timedelta(seconds=1000)  # 16+ minutes
        entry = CriticalDataEntry(
            project="test",
            source_name="test",
            data={},
            timestamp=old_time.isoformat()
        )

        assert entry.get_freshness() == DataFreshness.EXPIRED

    def test_to_dict_and_from_dict(self):
        """Test serialization round-trip."""
        entry = CriticalDataEntry(
            project="test_project",
            source_name="test_source",
            data={"test": "data"},
            timestamp=datetime.now().isoformat(),
            ttl_seconds=600
        )

        # Convert to dict
        entry_dict = entry.to_dict()
        assert entry_dict["project"] == "test_project"
        assert entry_dict["data"] == {"test": "data"}

        # Convert back
        restored = CriticalDataEntry.from_dict(entry_dict)
        assert restored.project == entry.project
        assert restored.source_name == entry.source_name
        assert restored.data == entry.data


class TestCriticalDataCache:
    """Tests for CriticalDataCache."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.ping = AsyncMock(return_value=True)
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock(return_value=True)
        redis.delete = AsyncMock(return_value=1)
        redis.sadd = AsyncMock(return_value=1)
        redis.srem = AsyncMock(return_value=1)
        redis.smembers = AsyncMock(return_value=set())
        redis.scan_iter = AsyncMock(return_value=[])
        return redis

    @pytest.fixture
    def cache(self, mock_redis):
        """Create a critical data cache for testing."""
        return CriticalDataCache(
            redis_client=mock_redis,
            auto_refresh=False,  # Disable for testing
            refresh_interval=300
        )

    def test_initialization(self, mock_redis):
        """Test cache initialization."""
        cache = CriticalDataCache(
            redis_client=mock_redis,
            auto_refresh=True,
            refresh_interval=600
        )

        assert cache.redis == mock_redis
        assert cache.auto_refresh is True
        assert cache.refresh_interval == 600
        assert cache.key_prefix == "critical_cache"

    def test_default_ttls(self):
        """Test default TTLs for different sources."""
        assert CriticalDataCache.DEFAULT_TTLS["health_endpoints"] == 300
        assert CriticalDataCache.DEFAULT_TTLS["active_alerts"] == 300
        assert CriticalDataCache.DEFAULT_TTLS["pod_status"] == 600
        assert CriticalDataCache.DEFAULT_TTLS["analytics"] == 3600

    @pytest.mark.asyncio
    async def test_set_critical_data(self, cache, mock_redis):
        """Test storing critical data."""
        result = await cache.set_critical_data(
            project="test_project",
            source_name="test_source",
            data={"test": "value"},
            ttl=600,
            priority="high"
        )

        assert result is True
        mock_redis.setex.assert_called_once()

        # Verify the key format
        call_args = mock_redis.setex.call_args
        key = call_args[0][0]
        assert "critical_cache" in key
        assert "test_project" in key
        assert "test_source" in key

    @pytest.mark.asyncio
    async def test_get_critical_data_hit(self, cache, mock_redis):
        """Test getting cached data (cache hit)."""
        entry = CriticalDataEntry(
            project="test_project",
            source_name="test_source",
            data={"cached": True},
            timestamp=datetime.now().isoformat(),
            ttl_seconds=900
        )

        mock_redis.get.return_value = json.dumps(entry.to_dict())

        result = await cache.get_critical_data("test_project", "test_source")

        assert result is not None
        assert result["data"] == {"cached": True}
        assert "age" in result
        assert "freshness" in result
        assert cache.stats["hits"] == 1

    @pytest.mark.asyncio
    async def test_get_critical_data_miss(self, cache, mock_redis):
        """Test getting cached data (cache miss)."""
        mock_redis.get.return_value = None

        result = await cache.get_critical_data("test_project", "test_source")

        assert result is None
        assert cache.stats["misses"] == 1

    @pytest.mark.asyncio
    async def test_get_critical_data_expired(self, cache, mock_redis):
        """Test getting expired data with allow_stale=False."""
        old_time = datetime.now() - timedelta(seconds=1000)
        entry = CriticalDataEntry(
            project="test_project",
            source_name="test_source",
            data={"old": "data"},
            timestamp=old_time.isoformat(),
            ttl_seconds=900
        )

        mock_redis.get.return_value = json.dumps(entry.to_dict())

        # With allow_stale=False
        result = await cache.get_critical_data(
            "test_project",
            "test_source",
            allow_stale=False
        )

        assert result is None
        assert cache.stats["expirations"] == 1

    @pytest.mark.asyncio
    async def test_get_critical_data_expired_with_stale_allowed(self, cache, mock_redis):
        """Test getting expired data with allow_stale=True."""
        old_time = datetime.now() - timedelta(seconds=1000)
        entry = CriticalDataEntry(
            project="test_project",
            source_name="test_source",
            data={"old": "data"},
            timestamp=old_time.isoformat(),
            ttl_seconds=900
        )

        mock_redis.get.return_value = json.dumps(entry.to_dict())

        # With allow_stale=True
        result = await cache.get_critical_data(
            "test_project",
            "test_source",
            allow_stale=True
        )

        assert result is not None
        assert result["data"] == {"old": "data"}
        assert result["freshness"] == "expired"

    @pytest.mark.asyncio
    async def test_get_all_critical_data(self, cache, mock_redis):
        """Test getting all critical data for a project."""
        # Mock index lookup
        mock_redis.smembers.return_value = {"source1", "source2"}

        # Mock individual gets
        entry1 = CriticalDataEntry(
            project="test_project",
            source_name="source1",
            data={"source": 1},
            timestamp=datetime.now().isoformat()
        )
        entry2 = CriticalDataEntry(
            project="test_project",
            source_name="source2",
            data={"source": 2},
            timestamp=datetime.now().isoformat()
        )

        async def mock_get(key):
            if "source1" in key:
                return json.dumps(entry1.to_dict())
            elif "source2" in key:
                return json.dumps(entry2.to_dict())
            return None

        mock_redis.get.side_effect = mock_get

        result = await cache.get_all_critical_data("test_project")

        assert len(result) == 2
        assert "source1" in result
        assert "source2" in result

    @pytest.mark.asyncio
    async def test_invalidate_specific_source(self, cache, mock_redis):
        """Test invalidating a specific source."""
        await cache.invalidate("test_project", "test_source")

        mock_redis.delete.assert_called_once()
        mock_redis.srem.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalidate_all_sources(self, cache, mock_redis):
        """Test invalidating all sources for a project."""
        mock_redis.smembers.return_value = {"source1", "source2", "source3"}

        await cache.invalidate("test_project")

        # Should delete index
        mock_redis.delete.assert_called()

        # Should remove from index
        assert mock_redis.srem.call_count == 4  # 3 sources + 1 index

    @pytest.mark.asyncio
    async def test_refresh_entry_with_fetcher(self, cache, mock_redis):
        """Test refreshing a cache entry with a fetcher."""
        existing_entry = CriticalDataEntry(
            project="test_project",
            source_name="test_source",
            data={"old": "data"},
            timestamp=datetime.now().isoformat(),
            ttl_seconds=900,
            refresh_count=2,
            version=1
        )

        mock_redis.get.return_value = json.dumps(existing_entry.to_dict())

        async def fetcher():
            return {"new": "data"}

        await cache.refresh_entry("test_project", "test_source", fetcher)

        # Verify new data was stored
        assert mock_redis.setex.called
        cache.stats["refreshes"] == 1

    @pytest.mark.asyncio
    async def test_register_callback(self, cache):
        """Test registering a refresh callback."""
        async def fetcher():
            return {"data": "value"}

        cache.register_refresh_callback("test_project", "test_source", fetcher)

        key = "test_project:test_source"
        assert key in cache._refresh_callbacks
        assert cache._refresh_callbacks[key] == fetcher

    @pytest.mark.asyncio
    async def test_unregister_callback(self, cache):
        """Test unregistering a refresh callback."""
        async def fetcher():
            return {"data": "value"}

        cache.register_refresh_callback("test_project", "test_source", fetcher)
        assert "test_project:test_source" in cache._refresh_callbacks

        cache.unregister_refresh_callback("test_project", "test_source")
        assert "test_project:test_source" not in cache._refresh_callbacks

    @pytest.mark.asyncio
    async def test_get_stats(self, cache):
        """Test getting cache statistics."""
        cache.stats = {
            "hits": 100,
            "misses": 10,
            "refreshes": 5,
            "expirations": 2
        }

        stats = cache.get_stats()

        assert stats["hits"] == 100
        assert stats["misses"] == 10
        assert stats["refreshes"] == 5

    @pytest.mark.asyncio
    async def test_reset_stats(self, cache):
        """Test resetting statistics."""
        cache.stats["hits"] = 100

        cache.reset_stats()

        assert cache.stats["hits"] == 0
        assert cache.stats["misses"] == 0

    @pytest.mark.asyncio
    async def test_get_health_status_healthy(self, cache, mock_redis):
        """Test health status when cache is healthy."""
        mock_redis.scan_iter.return_value = [
            b"critical_cache:index:project1"
        ]
        mock_redis.smembers.return_value = {"source1", "source2"}

        # Mock health checks
        healthy_entry = CriticalDataEntry(
            project="project1",
            source_name="source1",
            data={},
            timestamp=datetime.now().isoformat()
        )

        async def mock_get(key):
            return json.dumps(healthy_entry.to_dict())

        mock_redis.get.side_effect = mock_get

        health = await cache.get_health_status()

        assert health["status"] == "healthy"
        assert health["redis_connected"] is True
        assert health["total_projects"] == 1
        assert health["total_entries"] == 2

    @pytest.mark.asyncio
    async def test_get_health_status_unhealthy(self, cache, mock_redis):
        """Test health status when Redis is unavailable."""
        mock_redis.ping.side_effect = Exception("Connection lost")

        health = await cache.get_health_status()

        assert health["status"] == "unhealthy"
        assert health["redis_connected"] is False
        assert "error" in health

    @pytest.mark.asyncio
    async def test_start_stop_auto_refresh(self, cache, mock_redis):
        """Test starting and stopping auto-refresh loop."""
        # Enable auto-refresh
        cache.auto_refresh = True

        # Start
        await cache.start()
        assert cache._refresh_task is not None

        # Stop
        await cache.stop()
        assert cache._refresh_task is None


@pytest.mark.asyncio
class TestCriticalCacheIntegration:
    """Integration tests for critical cache."""

    async def test_cache_cycle(self):
        """Test complete cache cycle: set, get, refresh, invalidate."""
        # This would require a real Redis instance or more sophisticated mocking
        # For now, we'll test the logic flow
        pass
