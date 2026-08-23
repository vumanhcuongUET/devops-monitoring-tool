"""
Enhanced Cache Invalidation with Redis-backed Tag Index

Phase 7 - Sprint 1 - Day 7
Purpose: Implement improved cache invalidation with Redis-backed tag index

Features:
- Redis-backed tag index (not in-memory)
- Tag-based group invalidation
- Webhook integration for deployment/config changes
- Tag statistics tracking
"""

import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from collections import defaultdict

logger = logging.getLogger(__name__)


class InvalidationStrategy(Enum):
    """Cache invalidation strategies."""
    TIME_BASED = "time_based"           # TTL expiration
    EVENT_BASED = "event_based"        # On specific events
    TAG_BASED = "tag_based"            # Cache tagging (Redis-backed)
    SELECTIVE = "selective"            # Selective invalidation


class CacheInvalidator:
    """
    Manage cache invalidation strategies with Redis backing.

    Uses Redis to maintain tag → keys index, allowing efficient
    group invalidation of related cache entries.
    """

    TAG_INDEX_PREFIX = "tag_index"

    def __init__(self, redis_client, l2_cache=None):
        """
        Initialize cache invalidator.

        Args:
            redis_client: Redis client for tag index
            l2_cache: Optional L2CacheManager for direct invalidation
        """
        self.redis = redis_client
        self.l2_cache = l2_cache
        self._stats = {
            "invalidations_by_tag": 0,
            "invalidations_by_key": 0,
            "tags_created": 0,
            "webhooks_processed": 0
        }

    async def set_with_tags(
        self,
        data_type: str,
        identifier: Dict,
        value: Any,
        tags: List[str],
        ttl: int
    ) -> bool:
        """
        Set cache with tags for group invalidation.

        Args:
            data_type: Type of data being cached
            identifier: Cache key identifier
            value: Value to cache
            tags: List of tags for this cache entry
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        if not self.l2_cache:
            logger.warning("L2 cache not configured, cannot set with tags")
            return False

        try:
            # Generate cache key
            key = self.l2_cache._get_key(data_type, identifier)

            # Set in L2 cache
            result = await self.l2_cache.set(
                data_type,
                identifier,
                value,
                ttl_override=ttl
            )

            if not result:
                return False

            # Index by tags in Redis (not in-memory)
            for tag in tags:
                tag_key = f"{self.TAG_INDEX_PREFIX}:{tag}"
                await self.redis.sadd(tag_key, key)
                # Set TTL on tag index (keep longer than cache)
                await self.redis.expire(tag_key, ttl + 60)

            self._stats["tags_created"] += len(tags)
            return True

        except Exception as e:
            logger.error(f"Error setting cache with tags: {e}")
            return False

    async def invalidate_by_tag(self, tag: str) -> int:
        """
        Invalidate all cache entries with a tag.

        Args:
            tag: Tag to invalidate

        Returns:
            Number of keys invalidated
        """
        try:
            tag_key = f"{self.TAG_INDEX_PREFIX}:{tag}"

            # Get all keys for this tag
            keys = await self.redis.smembers(tag_key)

            if not keys:
                return 0

            # Decode keys if needed
            if isinstance(keys, set):
                decoded_keys = [
                    k.decode() if isinstance(k, bytes) else k
                    for k in keys
                ]
            else:
                decoded_keys = list(keys)

            # Delete all cached keys
            count = 0
            for key in decoded_keys:
                deleted = await self.redis.delete(key)
                if deleted:
                    count += deleted

            # Clear tag index
            await self.redis.delete(tag_key)

            self._stats["invalidations_by_tag"] += 1
            return count

        except Exception as e:
            logger.error(f"Error invalidating by tag {tag}: {e}")
            return 0

    async def invalidate_by_tags(self, tags: List[str]) -> int:
        """
        Invalidate all cache entries with any of the given tags.

        Args:
            tags: List of tags to invalidate

        Returns:
            Number of keys invalidated
        """
        total = 0
        for tag in tags:
            total += await self.invalidate_by_tag(tag)
        return total

    async def invalidate_on_deployment(
        self,
        project: str,
        service: str
    ) -> int:
        """
        Invalidate cache when deployment occurs.

        Args:
            project: Project name
            service: Service name

        Returns:
            Number of keys invalidated
        """
        tags = [f"project:{project}", f"service:{service}"]
        total = 0
        for tag in tags:
            total += await self.invalidate_by_tag(tag)

        logger.info(
            f"Invalidated {total} cache entries for "
            f"deployment: project={project}, service={service}"
        )
        return total

    async def invalidate_on_config_change(
        self,
        project: str,
        config_type: str
    ) -> int:
        """
        Invalidate cache when config changes.

        Args:
            project: Project name
            config_type: Type of config that changed

        Returns:
            Number of keys invalidated
        """
        tag = f"config:{project}:{config_type}"
        return await self.invalidate_by_tag(tag)

    async def get_tag_stats(self) -> Dict[str, int]:
        """
        Get statistics about tag index.

        Returns:
            Dictionary mapping tag names to member count
        """
        try:
            stats = {}
            pattern = f"{self.TAG_INDEX_PREFIX}:*"

            # Scan all tag index keys
            async for key in self._scan_keys_async(pattern):
                tag_name = key.split(":")[-1]
                member_count = await self.redis.scard(key)
                stats[tag_name] = member_count

            return stats

        except Exception as e:
            logger.error(f"Error getting tag stats: {e}")
            return {}

    async def _scan_keys_async(self, pattern: str):
        """
        Async generator for scanning Redis keys.

        Args:
            pattern: Key pattern to match

        Yields:
            Matching keys
        """
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
            for key in keys:
                yield key.decode() if isinstance(key, bytes) else key
            if cursor == 0:
                break

    async def get_keys_for_tag(self, tag: str) -> List[str]:
        """
        Get all cache keys associated with a tag.

        Args:
            tag: Tag to look up

        Returns:
            List of cache keys
        """
        try:
            tag_key = f"{self.TAG_INDEX_PREFIX}:{tag}"
            members = await self.redis.smembers(tag_key)

            if not members:
                return []

            return [
                m.decode() if isinstance(m, bytes) else m
                for m in members
            ]

        except Exception as e:
            logger.error(f"Error getting keys for tag {tag}: {e}")
            return []

    async def invalidate_specific_key(self, key: str) -> bool:
        """
        Invalidate a specific cache key.

        Args:
            key: Cache key to invalidate

        Returns:
            True if key was deleted, False otherwise
        """
        try:
            result = await self.redis.delete(key)
            if result:
                self._stats["invalidations_by_key"] += 1
            return result > 0

        except Exception as e:
            logger.error(f"Error invalidating key {key}: {e}")
            return False

    async def invalidate_by_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching a pattern.

        WARNING: Use with caution - can be slow on large datasets.

        Args:
            pattern: Key pattern to match (supports wildcards)

        Returns:
            Number of keys invalidated
        """
        try:
            count = 0
            async for key in self._scan_keys_async(pattern):
                deleted = await self.redis.delete(key)
                if deleted:
                    count += deleted

            return count

        except Exception as e:
            logger.error(f"Error invalidating by pattern {pattern}: {e}")
            return 0

    async def cleanup_expired_tags(self, max_age_seconds: int = 3600) -> int:
        """
        Clean up expired tag index entries.

        Args:
            max_age_seconds: Maximum age for tag entries

        Returns:
            Number of entries cleaned up
        """
        try:
            cleaned = 0
            pattern = f"{self.TAG_INDEX_PREFIX}:*"

            async for key in self._scan_keys_async(pattern):
                # Check if tag index has TTL
                ttl = await self.redis.ttl(key)
                if ttl == -1:  # No expiry set
                    await self.redis.expire(key, max_age_seconds)
                    cleaned += 1

            return cleaned

        except Exception as e:
            logger.error(f"Error cleaning up expired tags: {e}")
            return 0

    def get_stats(self) -> Dict[str, int]:
        """
        Get invalidation statistics.

        Returns:
            Statistics dictionary
        """
        return self._stats.copy()

    def reset_stats(self) -> None:
        """Reset invalidation statistics."""
        self._stats = {
            "invalidations_by_tag": 0,
            "invalidations_by_key": 0,
            "tags_created": 0,
            "webhooks_processed": 0
        }


class DeploymentEvent:
    """Deployment event model."""

    def __init__(
        self,
        project: str,
        service: str,
        version: str,
        environment: str,
        timestamp: Optional[str] = None
    ):
        self.project = project
        self.service = service
        self.version = version
        self.environment = environment
        self.timestamp = timestamp or datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "project": self.project,
            "service": self.service,
            "version": self.version,
            "environment": self.environment,
            "timestamp": self.timestamp
        }


class ConfigChangeEvent:
    """Config change event model."""

    def __init__(
        self,
        project: str,
        config_type: str,
        changed_keys: List[str],
        environment: str,
        timestamp: Optional[str] = None
    ):
        self.project = project
        self.config_type = config_type
        self.changed_keys = changed_keys
        self.environment = environment
        self.timestamp = timestamp or datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "project": self.project,
            "config_type": self.config_type,
            "changed_keys": self.changed_keys,
            "environment": self.environment,
            "timestamp": self.timestamp
        }


class WebhookRetryConfig:
    """Configuration for webhook retry logic."""

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 0.5,
        max_delay: float = 30.0,
        exponential_base: float = 2.0
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base


class WebhookProcessor:
    """
    Process webhook events with retry logic.

    Handles incoming webhooks for deployment and config change events,
    triggering appropriate cache invalidation with retry on failure.
    """

    def __init__(
        self,
        invalidator: CacheInvalidator,
        retry_config: Optional[WebhookRetryConfig] = None
    ):
        """
        Initialize webhook processor.

        Args:
            invalidator: Cache invalidator instance
            retry_config: Optional retry configuration
        """
        self.invalidator = invalidator
        self.retry_config = retry_config or WebhookRetryConfig()
        self._processed_events = set()
        self._event_lock = None

    async def process_deployment_webhook(
        self,
        event: DeploymentEvent
    ) -> Dict[str, Any]:
        """
        Process deployment webhook with retry.

        Args:
            event: Deployment event

        Returns:
            Processing result
        """
        # Check for duplicate events
        event_id = f"deploy:{event.project}:{event.service}:{event.timestamp}"
        if event_id in self._processed_events:
            return {
                "status": "duplicate",
                "message": "Event already processed",
                "event_id": event_id
            }

        try:
            # Invalidate with retry
            invalidated = await self._execute_with_retry(
                lambda: self.invalidator.invalidate_on_deployment(
                    event.project,
                    event.service
                )
            )

            self._processed_events.add(event_id)
            self.invalidator._stats["webhooks_processed"] += 1

            return {
                "status": "success",
                "invalidated_count": invalidated,
                "event_id": event_id,
                "project": event.project,
                "service": event.service,
                "version": event.version
            }

        except Exception as e:
            logger.error(f"Error processing deployment webhook: {e}")
            return {
                "status": "error",
                "error": str(e),
                "event_id": event_id
            }

    async def process_config_change_webhook(
        self,
        event: ConfigChangeEvent
    ) -> Dict[str, Any]:
        """
        Process config change webhook with retry.

        Args:
            event: Config change event

        Returns:
            Processing result
        """
        # Check for duplicate events
        event_id = f"config:{event.project}:{event.config_type}:{event.timestamp}"
        if event_id in self._processed_events:
            return {
                "status": "duplicate",
                "message": "Event already processed",
                "event_id": event_id
            }

        try:
            # Invalidate with retry
            invalidated = await self._execute_with_retry(
                lambda: self.invalidator.invalidate_on_config_change(
                    event.project,
                    event.config_type
                )
            )

            self._processed_events.add(event_id)
            self.invalidator._stats["webhooks_processed"] += 1

            return {
                "status": "success",
                "invalidated_count": invalidated,
                "event_id": event_id,
                "project": event.project,
                "config_type": event.config_type,
                "changed_keys": event.changed_keys
            }

        except Exception as e:
            logger.error(f"Error processing config change webhook: {e}")
            return {
                "status": "error",
                "error": str(e),
                "event_id": event_id
            }

    async def _execute_with_retry(
        self,
        func,
        max_retries: Optional[int] = None
    ) -> Any:
        """
        Execute function with exponential backoff retry.

        Args:
            func: Async function to execute
            max_retries: Override max retries

        Returns:
            Function result

        Raises:
            Exception: If all retries exhausted
        """
        import asyncio

        max_tries = max_retries or self.retry_config.max_retries
        delay = self.retry_config.initial_delay
        last_error = None

        for attempt in range(max_tries):
            try:
                return await func()
            except Exception as e:
                last_error = e
                if attempt < max_tries - 1:
                    # Wait before retry with exponential backoff
                    await asyncio.sleep(delay)
                    delay = min(
                        delay * self.retry_config.exponential_base,
                        self.retry_config.max_delay
                    )

        raise last_error

    def clear_processed_events(self) -> int:
        """
        Clear processed events tracking.

        Returns:
            Number of events cleared
        """
        count = len(self._processed_events)
        self._processed_events.clear()
        return count

    def get_processed_count(self) -> int:
        """Get count of processed events."""
        return len(self._processed_events)


def create_default_tags(
    project: str,
    data_type: str,
    additional_tags: Optional[List[str]] = None
) -> List[str]:
    """
    Create default tags for cache entries.

    Args:
        project: Project name
        data_type: Type of data
        additional_tags: Optional additional tags

    Returns:
        List of tags
    """
    tags = [
        f"project:{project}",
        f"type:{data_type}",
        f"environment:default"
    ]

    if additional_tags:
        tags.extend(additional_tags)

    return list(set(tags))  # Deduplicate
