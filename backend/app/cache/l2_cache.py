"""
L2 Redis Cache Implementation

Phase 7 - Sprint 1 - Day 5
Purpose: Distributed caching layer with Redis for cross-request data sharing

Features:
- Intelligent TTL configuration per data type
- Redis integration with connection pooling
- Tag-based cache invalidation
- Cache statistics and monitoring
- Serialization support (JSON, MsgPack)
"""

import json
import time
from typing import Any, Dict, List, Optional, Union
from datetime import timedelta
import hashlib
import logging

try:
    import redis.asyncio as redis
    from redis.asyncio import Redis, ConnectionPool
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

logger = logging.getLogger(__name__)


class SerializationFormat:
    """Supported serialization formats."""
    JSON = "json"
    MSGPACK = "msgpack"


class L2CacheManager:
    """
    Redis-based distributed cache manager with intelligent TTL.

    This is the L2 cache layer that persists data across requests
    with appropriate TTL values for different data types.

    Example:
        cache = L2CacheManager(redis_client)

        # Cache with type-specific TTL
        await cache.set("health", {"project": "test"}, data, ttl=60)

        # Get with automatic deserialization
        data = await cache.get("health", {"project": "test"})
    """

    # Type-specific TTL configurations (in seconds)
    TTL_CONFIG = {
        "health": 60,                # 1 minute for health checks
        "metrics": 300,              # 5 minutes for metrics
        "pod_status": 180,           # 3 minutes for pod status
        "alerts": 120,               # 2 minutes for alerts
        "overview": 300,             # 5 minutes for overview
        "triage_card": 600,          # 10 minutes for triage cards
        "semantic": 86400,           # 24 hours for semantic cache
        "logs": 60,                  # 1 minute for logs
        "slo": 300,                  # 5 minutes for SLO data
        "default": 300               # 5 minutes default
    }

    def __init__(
        self,
        redis_client: Optional[Redis] = None,
        redis_url: Optional[str] = None,
        default_ttl: int = 300,
        serialization: str = SerializationFormat.JSON,
        key_prefix: str = "l2"
    ):
        """
        Initialize L2 cache manager.

        Args:
            redis_client: Existing Redis client (optional)
            redis_url: Redis connection URL (if no client provided)
            default_ttl: Default TTL in seconds
            serialization: Serialization format (json or msgpack)
            key_prefix: Prefix for all cache keys
        """
        if not REDIS_AVAILABLE:
            raise ImportError("redis package is required for L2 cache")

        if redis_client:
            self.redis = redis_client
        elif redis_url:
            self.redis_pool = ConnectionPool.from_url(
                redis_url,
                decode_responses=False,
                max_connections=20
            )
            self.redis = Redis(connection_pool=self.redis_pool)
        else:
            raise ValueError("Either redis_client or redis_url must be provided")

        self.default_ttl = default_ttl
        self.serialization = serialization
        self.key_prefix = key_prefix
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0
        }

    def _get_key(self, data_type: str, identifier: Dict[str, Any]) -> str:
        """
        Generate Redis key with prefix and identifier.

        Args:
            data_type: Type of data (e.g., "health", "metrics")
            identifier: Dictionary identifying the specific data

        Returns:
            Redis key string
        """
        # Sort identifier for consistent keys
        parts = [self.key_prefix, data_type]

        # Add identifier parts in sorted order
        for k, v in sorted(identifier.items()):
            # Hash long values to keep key length reasonable
            if isinstance(v, (dict, list)) or len(str(v)) > 50:
                v_hash = hashlib.sha256(str(v).encode()).hexdigest()[:8]
                parts.append(f"{k}:{v_hash}")
            else:
                parts.append(f"{k}:{v}")

        return ":".join(parts)

    async def get(
        self,
        data_type: str,
        identifier: Dict[str, Any]
    ) -> Optional[Any]:
        """
        Get cached data by type and identifier.

        Args:
            data_type: Type of data
            identifier: Dictionary identifying the data

        Returns:
            Cached value if exists, None otherwise
        """
        key = self._get_key(data_type, identifier)

        try:
            value = await self.redis.get(key)

            if value is not None:
                self._stats["hits"] += 1
                # Deserialize based on format
                return self._deserialize(value)
            else:
                self._stats["misses"] += 1
                return None

        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"L2Cache: Error getting {key}: {e}")
            return None

    async def set(
        self,
        data_type: str,
        identifier: Dict[str, Any],
        value: Any,
        ttl: Optional[int] = None,
        tags: Optional[List[str]] = None
    ) -> bool:
        """
        Cache data with type-specific TTL.

        Args:
            data_type: Type of data
            identifier: Dictionary identifying the data
            value: Value to cache
            ttl: Override TTL (optional, uses type-specific TTL if not provided)
            tags: List of tags for invalidation (optional)

        Returns:
            True if successful, False otherwise
        """
        key = self._get_key(data_type, identifier)
        ttl = ttl or self.TTL_CONFIG.get(data_type, self.default_ttl)

        try:
            # Serialize value
            serialized = self._serialize(value)

            # Set in Redis with TTL
            await self.redis.setex(key, ttl, serialized)

            self._stats["sets"] += 1

            # Add to tag indexes if tags provided
            if tags:
                await self._add_to_tag_index(key, tags, ttl)

            return True

        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"L2Cache: Error setting {key}: {e}")
            return False

    async def delete(self, data_type: str, identifier: Dict[str, Any]) -> int:
        """
        Delete cached data.

        Args:
            data_type: Type of data
            identifier: Dictionary identifying the data

        Returns:
            Number of keys deleted (0 or 1)
        """
        key = self._get_key(data_type, identifier)

        try:
            result = await self.redis.delete(key)
            self._stats["deletes"] += 1
            return result
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"L2Cache: Error deleting {key}: {e}")
            return 0

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching a pattern.

        Args:
            pattern: Redis key pattern (e.g., "l2:health:*")

        Returns:
            Number of keys deleted
        """
        try:
            # Find matching keys
            keys = []
            async for key in self.redis.scan_iter(match=f"{pattern}*"):
                keys.append(key)

            if keys:
                return await self.redis.delete(*keys)
            return 0

        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"L2Cache: Error invalidating pattern {pattern}: {e}")
            return 0

    async def get_hit_rate(self) -> float:
        """
        Calculate cache hit rate.

        Returns:
            Hit rate as percentage (0-100)
        """
        total = self._stats["hits"] + self._stats["misses"]
        if total == 0:
            return 0.0
        return (self._stats["hits"] / total) * 100

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        return {
            **self._stats,
            "hit_rate": await self.get_hit_rate(),
            "total_requests": self._stats["hits"] + self._stats["misses"]
        }

    def reset_stats(self) -> None:
        """Reset cache statistics."""
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0
        }

    def _serialize(self, value: Any) -> bytes:
        """
        Serialize value based on format.

        Args:
            value: Value to serialize

        Returns:
            Serialized bytes
        """
        if self.serialization == SerializationFormat.JSON:
            return json.dumps(value).encode()

        # MsgPack serialization (more efficient)
        try:
            import msgpack
            return msgpack.packb(value, use_bin_type=True)
        except ImportError:
            logger.warning("MsgPack not available, falling back to JSON")
            return json.dumps(value).encode()

    def _deserialize(self, value: bytes) -> Any:
        """
        Deserialize value based on format.

        Args:
            value: Serialized bytes

        Returns:
            Deserialized value
        """
        if self.serialization == SerializationFormat.JSON:
            return json.loads(value.decode())

        # MsgPack deserialization
        try:
            import msgpack
            return msgpack.unpackb(value, raw=False)
        except ImportError:
            logger.warning("MsgPack not available, falling back to JSON")
            return json.loads(value.decode())

    async def _add_to_tag_index(self, key: str, tags: List[str], ttl: int) -> None:
        """
        Add key to tag indexes for group invalidation.

        Args:
            key: Cache key to index
            tags: List of tags
            ttl: TTL for tag index entries
        """
        for tag in tags:
            tag_key = f"{self.key_prefix}:tag:{tag}"
            # Add to sorted set with current timestamp as score
            await self.redis.zadd(tag_key, {key: time.time()})
            # Set expiry on tag index
            await self.redis.expire(tag_key, ttl + 60)  # Keep a bit longer

    async def invalidate_by_tag(self, tag: str) -> int:
        """
        Invalidate all cache entries with a specific tag.

        Args:
            tag: Tag to invalidate

        Returns:
            Number of keys deleted
        """
        tag_key = f"{self.key_prefix}:tag:{tag}"

        try:
            # Get all keys with this tag
            keys = await self.redis.zrange(tag_key, 0, -1)

            if keys:
                # Delete the keys
                count = await self.redis.delete(*keys)
                # Clear the tag index
                await self.redis.delete(tag_key)
                return count
            return 0

        except Exception as e:
            logger.error(f"L2Cache: Error invalidating tag {tag}: {e}")
            return 0

    async def get_by_tag(self, tag: str) -> List[Any]:
        """
        Get all cached values with a specific tag.

        Args:
            tag: Tag to fetch

        Returns:
            List of cached values
        """
        tag_key = f"{self.key_prefix}:tag:{tag}"

        try:
            # Get all keys with this tag
            keys = await self.redis.zrange(tag_key, 0, -1)

            if not keys:
                return []

            # Fetch all values
            values = await self.redis.mget(keys)

            # Deserialize and return
            return [
                self._deserialize(v) for v in values
                if v is not None
            ]

        except Exception as e:
            logger.error(f"L2Cache: Error getting by tag {tag}: {e}")
            return []

    async def mget(
        self,
        data_type: str,
        identifiers: List[Dict[str, Any]]
    ) -> List[Optional[Any]]:
        """
        Get multiple cached values at once.

        Args:
            data_type: Type of data
            identifiers: List of identifier dictionaries

        Returns:
            List of cached values (None for misses)
        """
        keys = [self._get_key(data_type, id) for id in identifiers]

        try:
            values = await self.redis.mget(keys)

            # Update stats and deserialize
            results = []
            for v in values:
                if v is not None:
                    self._stats["hits"] += 1
                    results.append(self._deserialize(v))
                else:
                    self._stats["misses"] += 1
                    results.append(None)

            return results

        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"L2Cache: Error in mget: {e}")
            return [None] * len(identifiers)

    async def mset(
        self,
        data_type: str,
        items: List[tuple[Dict[str, Any], Any]],
        ttl: Optional[int] = None,
        tags: Optional[List[str]] = None
    ) -> bool:
        """
        Set multiple cached values at once.

        Args:
            data_type: Type of data
            items: List of (identifier, value) tuples
            ttl: Override TTL
            tags: Tags for all items

        Returns:
            True if all successful, False otherwise
        """
        ttl = ttl or self.TTL_CONFIG.get(data_type, self.default_ttl)

        try:
            # Prepare pipeline
            pipe = self.redis.pipeline()

            for identifier, value in items:
                key = self._get_key(data_type, identifier)
                serialized = self._serialize(value)
                pipe.setex(key, ttl, serialized)

            # Execute pipeline
            await pipe.execute()

            self._stats["sets"] += len(items)

            # Add to tag indexes if tags provided
            if tags:
                for identifier, _ in items:
                    key = self._get_key(data_type, identifier)
                    await self._add_to_tag_index(key, tags, ttl)

            return True

        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"L2Cache: Error in mset: {e}")
            return False

    async def close(self) -> None:
        """Close Redis connection."""
        if hasattr(self, 'redis_pool'):
            await self.redis_pool.disconnect()
        if hasattr(self, 'redis'):
            await self.redis.close()


class RedisSentinelManager:
    """
    Manage Redis Sentinel for high availability.

    Provides automatic master discovery and failover handling
    for Redis clusters using Sentinel.
    """

    def __init__(
        self,
        sentinel_hosts: List[str],
        master_name: str = "mymaster",
        sentinel_password: Optional[str] = None,
        redis_password: Optional[str] = None
    ):
        """
        Initialize Sentinel manager.

        Args:
            sentinel_hosts: List of sentinel hosts (host:port)
            master_name: Name of the master group
            sentinel_password: Password for Sentinel (if required)
            redis_password: Password for Redis instances
        """
        if not REDIS_AVAILABLE:
            raise ImportError("redis package with Sentinel support required")

        self.sentinel_hosts = sentinel_hosts
        self.master_name = master_name
        self.sentinel_password = sentinel_password
        self.redis_password = redis_password
        self._current_master = None
        self._last_check = 0

    async def get_master(self) -> Optional[str]:
        """
        Get current master address.

        Returns:
            Master address as "host:port" or None
        """
        try:
            import redis.sentinel

            # Create Sentinel client
            sentinel = redis.sentinel.Sentinel(
                self.sentinel_hosts,
                socket_timeout=1,
                socket_connect_timeout=1,
                password=self.sentinel_password
            )

            # Get master address
            master_info = await sentinel.sentinel_master(self.master_name)

            master_addr = f"{master_info['host']}:{master_info['port']}"
            self._current_master = master_addr
            return master_addr

        except Exception as e:
            logger.error(f"SentinelManager: Error getting master: {e}")
            return self._current_master  # Return last known master

    async def get_redis_client(self) -> Redis:
        """
        Get Redis client connected to current master.

        Returns:
            Redis client instance
        """
        master_addr = await self.get_master()
        if not master_addr:
            raise RuntimeError("Cannot determine master address")

        host, port = master_addr.split(":")
        port = int(port)

        return Redis(
            host=host,
            port=port,
            password=self.redis_password,
            decode_responses=False,
            socket_connect_timeout=5
        )

    async def check_failover(self) -> bool:
        """
        Check if failover has occurred.

        Returns:
            True if master has changed, False otherwise
        """
        current_master = await self.get_master()
        changed = current_master != self._current_master
        return changed

    async def get_sentinels(self) -> List[Dict[str, Any]]:
        """
        Get list of known Sentinels.

        Returns:
            List of Sentinel information
        """
        try:
            import redis.sentinel

            sentinel = redis.sentinel.Sentinel(
                self.sentinel_hosts,
                socket_timeout=1
            )

            sentinel_info = await sentinel.sentinel_sentinels(self.master_name)
            return sentinel_info

        except Exception as e:
            logger.error(f"SentinelManager: Error getting sentinels: {e}")
            return []


def create_l2_cache_from_env() -> L2CacheManager:
    """
    Create L2 cache manager from environment variables.

    Environment Variables:
        REDIS_URL: Redis connection URL
        REDIS_HOST: Redis host (alternative to REDIS_URL)
        REDIS_PORT: Redis port (default: 6379)
        REDIS_PASSWORD: Redis password
        REDIS_DB: Redis database number (default: 0)

    Returns:
        Configured L2CacheManager instance
    """
    import os

    redis_url = os.getenv("REDIS_URL")

    if not redis_url:
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        password = os.getenv("REDIS_PASSWORD")
        db = int(os.getenv("REDIS_DB", "0"))

        if password:
            redis_url = f"redis://:{password}@{host}:{port}/{db}"
        else:
            redis_url = f"redis://{host}:{port}/{db}"

    return L2CacheManager(redis_url=redis_url)
