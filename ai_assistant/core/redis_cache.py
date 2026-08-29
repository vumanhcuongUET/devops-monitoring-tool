"""
Redis-based distributed caching for AI Assistant.

Provides distributed caching with TTL using Redis backend.
Falls back to SimpleCache if Redis is unavailable.
"""

import hashlib
import json
import time
from typing import Any, Callable, Dict, Optional, TypeVar

T = TypeVar("T")

# Lazy imports to avoid circular dependency
def _get_logger():
    from core.logging_config import get_logger
    return get_logger(__name__)


def _get_metrics():
    from core.logging_config import get_metrics
    return get_metrics()


class RedisCache:
    """
    Redis-based distributed cache with TTL.

    Provides distributed caching across multiple processes/instances.
    Falls back to no-op if Redis is unavailable.
    """

    def __init__(
        self,
        ttl: int = 60,
        redis_url: str = "redis://localhost:6379/0",
        key_prefix: str = "ai_assistant:",
        fallback_enabled: bool = True
    ):
        """
        Initialize Redis cache.

        Args:
            ttl: Time-to-live in seconds
            redis_url: Redis connection URL
            key_prefix: Prefix for all cache keys
            fallback_enabled: If True, cache operations become no-ops when Redis unavailable
        """
        self._ttl = ttl
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._fallback_enabled = fallback_enabled
        self._redis = None
        self._available = False

        self._connect()

    def _connect(self):
        """Attempt to connect to Redis."""
        try:
            import redis
            self._redis = redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2
            )
            # Test connection
            self._redis.ping()
            self._available = True
            _get_logger().info("Redis cache connected", url=self._redis_url)
            _get_metrics().increment("redis_cache_connected")
        except Exception as e:
            self._available = False
            if self._fallback_enabled:
                _get_logger().warning(f"Redis cache unavailable, operations will be no-ops: {e}")
                _get_metrics().increment("redis_cache_unavailable")
            else:
                raise RuntimeError(f"Redis cache required but unavailable: {e}") from e

    @property
    def available(self) -> bool:
        """Check if Redis is available."""
        return self._available

    def _make_key(self, key: str) -> str:
        """Add prefix to cache key."""
        return f"{self._key_prefix}{key}"

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from Redis cache.

        Args:
            key: Cache key (without prefix)

        Returns:
            Cached value or None if not found/expired
        """
        if not self._available:
            return None

        try:
            redis_key = self._make_key(key)
            value = self._redis.get(redis_key)

            if value is None:
                _get_metrics().increment("redis_cache_miss", labels={"reason": "not_found"})
                _get_logger().debug("Redis cache miss", key=key[:32])
                return None

            # Deserialize JSON
            try:
                deserialized = json.loads(value)
                _get_metrics().increment("redis_cache_hit")
                _get_logger().debug("Redis cache hit", key=key[:32])
                return deserialized
            except json.JSONDecodeError:
                # If not JSON, return as-is
                _get_metrics().increment("redis_cache_hit")
                return value

        except Exception as e:
            _get_logger().warning("Redis cache get failed", key=key[:32], error=str(e))
            _get_metrics().increment("redis_cache_error", labels={"operation": "get"})
            return None

    def set(self, key: str, value: Any):
        """
        Set value in Redis cache.

        Args:
            key: Cache key (without prefix)
            value: Value to cache (must be JSON-serializable)
        """
        if not self._available:
            return

        try:
            redis_key = self._make_key(key)

            # Serialize to JSON
            if isinstance(value, (str, int, float, bool, type(None))):
                serialized = json.dumps(value)
            else:
                serialized = json.dumps(value, default=str)

            # Set with TTL
            self._redis.setex(redis_key, self._ttl, serialized)
            _get_metrics().increment("redis_cache_set")
            _get_logger().debug("Redis cache set", key=key[:32])

        except Exception as e:
            _get_logger().warning("Redis cache set failed", key=key[:32], error=str(e))
            _get_metrics().increment("redis_cache_error", labels={"operation": "set"})

    def delete(self, key: str):
        """
        Delete value from Redis cache.

        Args:
            key: Cache key (without prefix)
        """
        if not self._available:
            return

        try:
            redis_key = self._make_key(key)
            self._redis.delete(redis_key)
            _get_logger().debug("Redis cache deleted", key=key[:32])

        except Exception as e:
            _get_logger().warning("Redis cache delete failed", key=key[:32], error=str(e))

    def clear(self):
        """Clear all cache entries with our prefix."""
        if not self._available:
            return

        try:
            pattern = f"{self._key_prefix}*"
            keys = self._redis.keys(pattern)

            if keys:
                self._redis.delete(*keys)
                _get_logger().info("Redis cache cleared", count=len(keys))

        except Exception as e:
            _get_logger().warning("Redis cache clear failed", error=str(e))

    def stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        if not self._available:
            return {
                "type": "redis",
                "available": False,
                "url": self._redis_url
            }

        try:
            info = self._redis.info()
            pattern = f"{self._key_prefix}*"
            keys = self._redis.keys(pattern)

            return {
                "type": "redis",
                "available": True,
                "url": self._redis_url,
                "key_count": len(keys),
                "ttl": self._ttl,
                "memory_used": info.get("used_memory_human", "unknown"),
                "connected_clients": info.get("connected_clients", 0)
            }

        except Exception as e:
            return {
                "type": "redis",
                "available": False,
                "error": str(e)
            }


# Global Redis cache instance
_global_redis_cache: Optional[RedisCache] = None


def get_global_redis_cache() -> Optional[RedisCache]:
    """Get or create global Redis cache instance."""
    global _global_redis_cache

    if _global_redis_cache is None:
        from core.config_loader import get_feature_flags

        flags = get_feature_flags()
        redis_config = flags.get("optimization", {}).get("redis_cache", {})

        if not redis_config.get("enabled", False):
            return None

        _global_redis_cache = RedisCache(
            ttl=redis_config.get("ttl_seconds", 60),
            redis_url=redis_config.get("url", "redis://localhost:6379/0"),
            key_prefix=redis_config.get("key_prefix", "ai_assistant:"),
            fallback_enabled=redis_config.get("fallback_enabled", True)
        )

    return _global_redis_cache
