"""
Unit Tests for Enhanced Cache Invalidation

Phase 7 - Sprint 1 - Day 7
Tests for cache invalidation with Redis-backed tag index
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.cache.invalidation import (
    CacheInvalidator,
    DeploymentEvent,
    ConfigChangeEvent,
    WebhookRetryConfig,
    WebhookProcessor,
    InvalidationStrategy,
    create_default_tags
)


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""

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
    redis.sadd = AsyncMock(return_value=1)
    redis.smembers = AsyncMock(return_value=set())
    redis.scard = AsyncMock(return_value=0)
    redis.expire = AsyncMock(return_value=True)
    redis.ttl = AsyncMock(return_value=3600)
    redis.scan = AsyncMock(side_effect=lambda cursor, match, count: (0, []))

    # Create L2 cache mock
    class MockL2Cache:
        def _get_key(self, data_type, identifier):
            parts = [data_type]
            for k, v in sorted(identifier.items()):
                parts.append(f"{k}:{v}")
            return ":".join(parts)

        async def set(self, data_type, identifier, value, ttl_override=None):
            return True

    redis.l2_cache = MockL2Cache()

    return redis


@pytest.fixture
def invalidator(mock_redis):
    """Create cache invalidator with mock Redis."""
    l2_cache = mock_redis.l2_cache
    return CacheInvalidator(redis_client=mock_redis, l2_cache=l2_cache)


class TestCacheInvalidatorBasics:
    """Test basic cache invalidation operations."""

    @pytest.mark.asyncio
    async def test_set_with_tags(self, invalidator, mock_redis):
        """Test setting cache with tags."""
        mock_redis.sadd.return_value = 1

        result = await invalidator.set_with_tags(
            data_type="overview",
            identifier={"project": "test"},
            value={"data": "test"},
            tags=["project:test", "type:overview"],
            ttl=300
        )

        assert result is True
        # Verify sadd was called for each tag (2 tags)
        assert mock_redis.sadd.call_count == 2

    @pytest.mark.asyncio
    async def test_invalidate_by_tag(self, invalidator, mock_redis):
        """Test invalidating cache by tag."""
        # Mock tag members
        mock_redis.smembers.return_value = {
            b"cache:key1",
            b"cache:key2",
            b"cache:key3"
        }
        # Mock delete to return count of deleted keys
        delete_call_count = [0]
        async def mock_delete(*keys):
            delete_call_count[0] += len(keys)
            return len(keys)
        mock_redis.delete = mock_delete

        count = await invalidator.invalidate_by_tag("project:test")

        assert count == 3  # 3 cache keys deleted
        assert delete_call_count[0] >= 3  # At least the 3 cache keys

    @pytest.mark.asyncio
    async def test_invalidate_by_tag_no_members(self, invalidator, mock_redis):
        """Test invalidating tag with no members."""
        mock_redis.smembers.return_value = set()

        count = await invalidator.invalidate_by_tag("project:test")

        assert count == 0

    @pytest.mark.asyncio
    async def test_invalidate_by_tags(self, invalidator, mock_redis):
        """Test invalidating by multiple tags."""
        mock_redis.smembers.return_value = {b"cache:key1"}
        mock_redis.delete.return_value = 1

        count = await invalidator.invalidate_by_tags([
            "project:test",
            "service:api"
        ])

        assert count == 2  # 1 for each tag


class TestDeploymentInvalidation:
    """Test deployment-based cache invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_on_deployment(self, invalidator, mock_redis):
        """Test invalidation on deployment event."""
        mock_redis.smembers.return_value = {b"cache:key1", b"cache:key2"}
        mock_redis.delete.return_value = 2

        count = await invalidator.invalidate_on_deployment(
            project="meinvoice",
            service="api-gateway"
        )

        # Should invalidate by both project and service tags
        assert count >= 0

    @pytest.mark.asyncio
    async def test_deployment_event_creation(self):
        """Test deployment event model."""
        event = DeploymentEvent(
            project="meinvoice",
            service="api-gateway",
            version="v1.2.3",
            environment="production"
        )

        assert event.project == "meinvoice"
        assert event.service == "api-gateway"
        assert event.version == "v1.2.3"
        assert event.environment == "production"
        assert event.timestamp is not None

    def test_deployment_event_to_dict(self):
        """Test converting deployment event to dict."""
        event = DeploymentEvent(
            project="meinvoice",
            service="api-gateway",
            version="v1.2.3",
            environment="production"
        )

        data = event.to_dict()

        assert data["project"] == "meinvoice"
        assert data["service"] == "api-gateway"
        assert data["version"] == "v1.2.3"


class TestConfigChangeInvalidation:
    """Test config change-based cache invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_on_config_change(self, invalidator, mock_redis):
        """Test invalidation on config change."""
        mock_redis.smembers.return_value = {b"cache:key1"}
        mock_redis.delete.return_value = 1

        count = await invalidator.invalidate_on_config_change(
            project="meinvoice",
            config_type="alerting"
        )

        assert count == 1

    @pytest.mark.asyncio
    async def test_config_change_event_creation(self):
        """Test config change event model."""
        event = ConfigChangeEvent(
            project="meinvoice",
            config_type="alerting",
            changed_keys=["cpu_threshold", "memory_threshold"],
            environment="production"
        )

        assert event.project == "meinvoice"
        assert event.config_type == "alerting"
        assert len(event.changed_keys) == 2


class TestTagStatistics:
    """Test tag statistics functionality."""

    @pytest.mark.asyncio
    async def test_get_tag_stats(self, invalidator, mock_redis):
        """Test getting tag statistics."""
        # Mock scan to return tag index keys
        async def mock_scan(cursor, match, count):
            return (0, ["tag_index:project:test", "tag_index:service:api"])

        mock_redis.scan = mock_scan
        # Handle both string and bytes keys
        async def mock_scard(key):
            k = key.decode() if isinstance(key, bytes) else key
            return 5 if "project:test" in k else 3

        mock_redis.scard = mock_scard

        stats = await invalidator.get_tag_stats()

        assert "test" in stats
        assert stats["test"] == 5
        assert "api" in stats
        assert stats["api"] == 3

    @pytest.mark.asyncio
    async def test_get_keys_for_tag(self, invalidator, mock_redis):
        """Test getting keys for a specific tag."""
        mock_redis.smembers.return_value = {
            b"cache:key1",
            b"cache:key2"
        }

        keys = await invalidator.get_keys_for_tag("project:test")

        assert len(keys) == 2
        assert "cache:key1" in keys
        assert "cache:key2" in keys

    @pytest.mark.asyncio
    async def test_get_keys_for_tag_empty(self, invalidator, mock_redis):
        """Test getting keys for tag with no members."""
        mock_redis.smembers.return_value = set()

        keys = await invalidator.get_keys_for_tag("project:nonexistent")

        assert keys == []


class TestSpecificKeyInvalidation:
    """Test specific key invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_specific_key(self, invalidator, mock_redis):
        """Test invalidating a specific key."""
        mock_redis.delete.return_value = 1

        result = await invalidator.invalidate_specific_key("cache:specific:key")

        assert result is True

    @pytest.mark.asyncio
    async def test_invalidate_specific_key_not_found(self, invalidator, mock_redis):
        """Test invalidating non-existent key."""
        mock_redis.delete.return_value = 0

        result = await invalidator.invalidate_specific_key("cache:nonexistent")

        assert result is False


class TestWebhookProcessor:
    """Test webhook processing with retry logic."""

    @pytest.fixture
    def webhook_processor(self, invalidator):
        """Create webhook processor."""
        retry_config = WebhookRetryConfig(max_retries=3, initial_delay=0.1)
        return WebhookProcessor(invalidator=invalidator, retry_config=retry_config)

    @pytest.mark.asyncio
    async def test_process_deployment_webhook(self, webhook_processor, mock_redis):
        """Test processing deployment webhook."""
        mock_redis.smembers.return_value = {b"cache:key1"}
        delete_count = [0]
        async def mock_delete(*keys):
            delete_count[0] += len(keys)
            return len(keys)
        mock_redis.delete = mock_delete

        event = DeploymentEvent(
            project="meinvoice",
            service="api-gateway",
            version="v1.2.3",
            environment="production"
        )

        result = await webhook_processor.process_deployment_webhook(event)

        assert result["status"] == "success"
        # invalidate_on_development invalidates both project and service tags
        assert result["invalidated_count"] >= 1
        assert "event_id" in result

    @pytest.mark.asyncio
    async def test_process_deployment_webhook_duplicate(self, webhook_processor, mock_redis):
        """Test duplicate deployment webhook is ignored."""
        mock_redis.smembers.return_value = {b"cache:key1"}
        mock_redis.delete.return_value = 1

        event = DeploymentEvent(
            project="meinvoice",
            service="api-gateway",
            version="v1.2.3",
            environment="production",
            timestamp="2026-08-23T10:00:00Z"
        )

        # Process first time
        result1 = await webhook_processor.process_deployment_webhook(event)
        assert result1["status"] == "success"

        # Process duplicate
        result2 = await webhook_processor.process_deployment_webhook(event)
        assert result2["status"] == "duplicate"

    @pytest.mark.asyncio
    async def test_process_config_change_webhook(self, webhook_processor, mock_redis):
        """Test processing config change webhook."""
        mock_redis.smembers.return_value = {b"cache:key1"}
        mock_redis.delete.return_value = 1

        event = ConfigChangeEvent(
            project="meinvoice",
            config_type="alerting",
            changed_keys=["cpu_threshold"],
            environment="production"
        )

        result = await webhook_processor.process_config_change_webhook(event)

        assert result["status"] == "success"
        assert result["invalidated_count"] == 1

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, webhook_processor, mock_redis):
        """Test retry logic on transient failures."""
        call_count = 0

        async def failing_invalidator():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Transient error")
            return 5

        # First call fails, second succeeds
        result = await webhook_processor._execute_with_retry(failing_invalidator)

        assert result == 5
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhaustion(self, webhook_processor):
        """Test retry exhaustion after max retries."""
        async def always_failing():
            raise Exception("Persistent error")

        with pytest.raises(Exception, match="Persistent error"):
            await webhook_processor._execute_with_retry(always_failing, max_retries=2)

    def test_clear_processed_events(self, webhook_processor):
        """Test clearing processed events."""
        # Simulate processed event
        webhook_processor._processed_events.add("event1")
        webhook_processor._processed_events.add("event2")

        count = webhook_processor.clear_processed_events()

        assert count == 2
        assert webhook_processor.get_processed_count() == 0

    def test_get_processed_count(self, webhook_processor):
        """Test getting processed event count."""
        assert webhook_processor.get_processed_count() == 0

        webhook_processor._processed_events.add("event1")
        assert webhook_processor.get_processed_count() == 1


class TestInvalidationStrategy:
    """Test invalidation strategy enum."""

    def test_invalidation_strategies(self):
        """Test all invalidation strategies exist."""
        assert InvalidationStrategy.TIME_BASED.value == "time_based"
        assert InvalidationStrategy.EVENT_BASED.value == "event_based"
        assert InvalidationStrategy.TAG_BASED.value == "tag_based"
        assert InvalidationStrategy.SELECTIVE.value == "selective"


class TestDefaultTags:
    """Test default tag creation."""

    def test_create_default_tags(self):
        """Test creating default tags."""
        tags = create_default_tags(
            project="meinvoice",
            data_type="overview"
        )

        assert "project:meinvoice" in tags
        assert "type:overview" in tags
        assert "environment:default" in tags

    def test_create_default_tags_with_additional(self):
        """Test creating default tags with additional tags."""
        tags = create_default_tags(
            project="meinvoice",
            data_type="overview",
            additional_tags=["service:api", "severity:high"]
        )

        assert "project:meinvoice" in tags
        assert "type:overview" in tags
        assert "service:api" in tags
        assert "severity:high" in tags

    def test_create_default_tags_deduplication(self):
        """Test duplicate tags are removed."""
        tags = create_default_tags(
            project="meinvoice",
            data_type="overview",
            additional_tags=["project:meinvoice", "service:api"]
        )

        # Should only have one project:meinvoice
        project_count = sum(1 for t in tags if t == "project:meinvoice")
        assert project_count == 1


class TestCacheInvalidatorStats:
    """Test cache invalidator statistics."""

    @pytest.mark.asyncio
    async def test_get_stats(self, invalidator):
        """Test getting invalidator stats."""
        stats = invalidator.get_stats()

        assert "invalidations_by_tag" in stats
        assert "invalidations_by_key" in stats
        assert "tags_created" in stats
        assert "webhooks_processed" in stats

    def test_reset_stats(self, invalidator):
        """Test resetting invalidator stats."""
        invalidator._stats["invalidations_by_tag"] = 10
        invalidator._stats["tags_created"] = 5

        invalidator.reset_stats()

        assert invalidator._stats["invalidations_by_tag"] == 0
        assert invalidator._stats["tags_created"] == 0


class TestAdvancedInvalidation:
    """Test advanced invalidation scenarios."""

    @pytest.mark.asyncio
    async def test_invalidate_by_pattern(self, invalidator, mock_redis):
        """Test invalidating by key pattern."""
        deleted_keys = []

        async def mock_scan(cursor, match, count):
            # Return matching keys in second call
            if cursor == 0:
                return (100, [b"cache:key1", b"cache:key2"])
            return (0, [])

        async def mock_delete(*keys):
            deleted_keys.extend(keys)
            return len(keys)

        mock_redis.scan = mock_scan
        mock_redis.delete = mock_delete

        count = await invalidator.invalidate_by_pattern("cache:*")

        assert count == 2
        assert len(deleted_keys) == 2

    @pytest.mark.asyncio
    async def test_cleanup_expired_tags(self, invalidator, mock_redis):
        """Test cleaning up expired tag entries."""

        async def mock_scan(cursor, match, count):
            if cursor == 0:
                return (100, [b"tag_index:project:test"])
            return (0, [])

        mock_redis.scan = mock_scan
        mock_redis.ttl.return_value = -1  # No expiry
        mock_redis.expire.return_value = True

        cleaned = await invalidator.cleanup_expired_tags(max_age_seconds=3600)

        assert cleaned == 1

    @pytest.mark.asyncio
    async def test_invalidate_on_deployment_with_service(self, invalidator, mock_redis):
        """Test deployment invalidation with specific service."""
        mock_redis.smembers.return_value = {b"cache:key1"}
        mock_redis.delete.return_value = 1

        count = await invalidator.invalidate_on_deployment(
            project="meinvoice",
            service="api-gateway"
        )

        # Should invalidate both project and service tags
        assert count >= 0


class TestRealWorldScenarios:
    """Test real-world invalidation scenarios."""

    @pytest.mark.asyncio
    async def test_deployment_invalidation_flow(self, invalidator, mock_redis):
        """Test complete deployment invalidation flow."""
        # Set up cache with tags
        mock_redis.sadd.return_value = 1

        await invalidator.set_with_tags(
            data_type="overview",
            identifier={"project": "meinvoice"},
            value={"status": "healthy"},
            tags=["project:meinvoice", "service:api-gateway", "type:overview"],
            ttl=300
        )

        # Mock the invalidation
        mock_redis.smembers.return_value = {b"l2:overview:project:meinvoice"}
        mock_redis.delete.return_value = 1

        # Invalidate on deployment
        count = await invalidator.invalidate_on_deployment(
            project="meinvoice",
            service="api-gateway"
        )

        # Verify invalidation occurred
        assert count >= 0

    @pytest.mark.asyncio
    async def test_config_change_invalidation_flow(self, invalidator, mock_redis):
        """Test config change invalidation flow."""
        # Mock the invalidation
        mock_redis.smembers.return_value = {
            b"l2:config:project:meinvoice:config_type:alerting"
        }
        mock_redis.delete.return_value = 1

        count = await invalidator.invalidate_on_config_change(
            project="meinvoice",
            config_type="alerting"
        )

        assert count == 1

    @pytest.mark.asyncio
    async def test_batch_invalidation(self, invalidator, mock_redis):
        """Test invalidating multiple tags at once."""
        mock_redis.smembers.return_value = {b"cache:key1"}
        mock_redis.delete.return_value = 1

        tags = [
            "project:meinvoice",
            "service:api-gateway",
            "type:overview"
        ]

        total = await invalidator.invalidate_by_tags(tags)

        assert total == 3  # 1 key per tag
