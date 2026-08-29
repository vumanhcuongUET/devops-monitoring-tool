"""
Result caching for AI Assistant.

Provides simple in-memory caching with TTL for query results.
Supports both SimpleCache (in-memory) and RedisCache (distributed).
"""

import hashlib
import json
import threading
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar, Union

T = TypeVar("T")

# Import logging (lazy to avoid circular import)
def _get_logger():
    from core.logging_config import get_logger
    return get_logger(__name__)


def _get_metrics():
    from core.logging_config import get_metrics
    return get_metrics()


class SimpleCache:
    """
    Simple in-memory cache with TTL.

    Thread-safe for basic use cases. For production, consider
    using Redis or memcached.
    """

    def __init__(self, ttl: int = 60, max_size: int = 1000):
        """
        Initialize cache.

        Args:
            ttl: Time-to-live in seconds
            max_size: Maximum number of entries to store
        """
        self._ttl = ttl
        self._max_size = max_size
        self._cache: Dict[str, tuple[Any, float]] = {}
        # docstring promises thread safety; before 2026-08-29 no lock existed
        # and concurrent set() corrupted iteration (_evict_expired) — review F3.
        self._lock = threading.Lock()

    def _is_expired(self, timestamp: float) -> bool:
        """Check if cache entry is expired."""
        return time.time() - timestamp > self._ttl

    def _evict_expired(self):
        """Remove expired entries."""
        expired = [k for k, (_, ts) in self._cache.items() if self._is_expired(ts)]
        for k in expired:
            del self._cache[k]

    def _evict_oldest(self):
        """Remove oldest entries if cache is full."""
        if len(self._cache) >= self._max_size:
            # Remove oldest 10% of entries
            to_remove = int(self._max_size * 0.1) or 1
            sorted_keys = sorted(self._cache.keys(), key=lambda k: self._cache[k][1])
            for k in sorted_keys[:to_remove]:
                del self._cache[k]

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if self._is_expired(timestamp):
                    del self._cache[key]
                    _get_metrics().increment("cache_miss_total", labels={"reason": "expired"})
                    _get_logger().debug("Cache miss (expired)", key=key[:32])
                    return None
                _get_metrics().increment("cache_hit_total")
                _get_logger().debug("Cache hit", key=key[:32])
                return value
        _get_metrics().increment("cache_miss_total", labels={"reason": "not_found"})
        _get_logger().debug("Cache miss (not found)", key=key[:32])
        return None

    def set(self, key: str, value: Any):
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
        """
        with self._lock:
            self._evict_expired()
            self._evict_oldest()
            self._cache[key] = (value, time.time())
        _get_metrics().increment("cache_set_total")
        _get_logger().debug("Cache set", key=key[:32])

    def clear(self):
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()

    def stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        expired_count = 0
        with self._lock:
            entries = list(self._cache.values())
        for (_value, timestamp) in entries:
            if self._is_expired(timestamp):
                expired_count += 1

        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "ttl": self._ttl,
            "expired_count": expired_count
        }


# Global cache instance
_global_cache: Optional[Union[SimpleCache, "RedisCache"]] = None


def get_global_cache() -> Union[SimpleCache, "RedisCache"]:
    """
    Get or create global cache instance.

    Returns SimpleCache or RedisCache based on feature flags.
    RedisCache is used when optimization.redis_cache.enabled = true.
    Falls back to SimpleCache if Redis is unavailable.
    """
    global _global_cache

    if _global_cache is None:
        from core.config_loader import get_feature_flags

        flags = get_feature_flags()
        opt_config = flags.get("optimization", {})

        # Check if Redis cache is enabled
        redis_config = opt_config.get("redis_cache", {})
        if redis_config.get("enabled", False):
            try:
                from core.redis_cache import RedisCache
                _global_cache = RedisCache(
                    ttl=redis_config.get("ttl_seconds", opt_config.get("cache_ttl_seconds", 60)),
                    redis_url=redis_config.get("url", "redis://localhost:6379/0"),
                    key_prefix=redis_config.get("key_prefix", "ai_assistant:"),
                    fallback_enabled=redis_config.get("fallback_enabled", True)
                )
                _get_logger().info("Using Redis cache")
                return _global_cache
            except Exception as e:
                _get_logger().warning(f"Redis cache initialization failed, falling back to SimpleCache: {e}")

        # Default to SimpleCache
        ttl = opt_config.get("cache_ttl_seconds", 60)
        _global_cache = SimpleCache(ttl=ttl)
        _get_logger().info("Using SimpleCache (in-memory)")

    return _global_cache


def cache_key_from_args(*args, **kwargs) -> str:
    """
    Generate cache key from function arguments.

    Args:
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        MD5 hash cache key
    """
    # Convert args to a hashable representation
    key_parts = []
    for arg in args:
        if isinstance(arg, (dict, list)):
            key_parts.append(json.dumps(arg, sort_keys=True))
        else:
            key_parts.append(str(arg))
    for k, v in sorted(kwargs.items()):
        if isinstance(v, (dict, list)):
            key_parts.append(f"{k}={json.dumps(v, sort_keys=True)}")
        else:
            key_parts.append(f"{k}={v}")

    key_string = "|".join(key_parts)
    return hashlib.md5(key_string.encode()).hexdigest()


def cached(ttl: Optional[int] = None):
    """
    Decorator for caching function results.

    Args:
        ttl: Custom TTL in seconds (overrides global)

    Example:
        @cached(ttl=30)
        def my_function(arg1, arg2):
            return expensive_computation(arg1, arg2)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            from core.config_loader import is_feature_enabled

            # Check if caching is enabled
            if not is_feature_enabled("optimization.cache_enabled"):
                return func(*args, **kwargs)

            cache = get_global_cache()
            key = f"{func.__name__}:{cache_key_from_args(*args, **kwargs)}"

            # Try to get from cache
            cached_value = cache.get(key)
            if cached_value is not None:
                return cached_value

            # Compute and cache
            result = func(*args, **kwargs)
            cache.set(key, result)
            return result

        return wrapper
    return decorator


def clear_cache():
    """Clear the global cache."""
    global _global_cache
    if _global_cache:
        _global_cache.clear()


def get_cache_stats() -> Dict[str, Any]:
    """
    Get global cache statistics.

    Returns:
        Cache statistics dictionary
    """
    cache = get_global_cache()
    return cache.stats()
