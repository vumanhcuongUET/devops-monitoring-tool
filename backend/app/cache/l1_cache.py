"""
L1 In-Memory Cache Implementation

Phase 7 - Sprint 1 - Day 4
Purpose: Per-request cache to prevent duplicate queries within a single HTTP request

Features:
- Request-scoped cache using contextvars
- Cache key generation from source and parameters
- Cache statistics tracking
- Automatic cleanup after request completion
"""

import hashlib
import json
import time
from collections import defaultdict
from contextvars import ContextVar
from functools import wraps
from typing import Any

# Context variable for request-scoped cache
request_cache: ContextVar[dict[str, Any]] = ContextVar("request_cache", default=None)


class L1Cache:
    """
    In-memory cache for deduplicating queries within a single request.

    This prevents the same data from being fetched multiple times
    when different parts of the code need the same information.

    Example:
        cache = L1Cache()

        # First call fetches from source
        data1 = await cache.get_or_fetch("es_logs", params, fetch_func)

        # Second call returns cached result (no duplicate query)
        data2 = await cache.get_or_fetch("es_logs", params, fetch_func)
    """

    def __init__(self):
        self._stats = defaultdict(lambda: {"hits": 0, "misses": 0})

    @staticmethod
    def _generate_key(source: str, params: dict[str, Any]) -> str:
        """
        Generate a unique cache key from source and parameters.

        Args:
            source: Data source identifier (e.g., "elasticsearch", "prometheus")
            params: Query parameters dictionary

        Returns:
            SHA256 hash of the combined source and parameters
        """
        # Normalize parameters for consistent hashing
        key_dict = {"source": source, **params}
        key_str = json.dumps(key_dict, sort_keys=True, default=str)
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get(self, source: str, params: dict[str, Any]) -> Any | None:
        """
        Get cached result for current request.

        Args:
            source: Data source identifier
            params: Query parameters

        Returns:
            Cached value if exists, None otherwise
        """
        cache = request_cache.get({})
        key = self._generate_key(source, params)
        value = cache.get(key)

        if value is not None:
            self._stats[key]["hits"] += 1
        else:
            self._stats[key]["misses"] += 1

        return value

    def set(self, source: str, params: dict[str, Any], value: Any) -> None:
        """
        Cache result for current request.

        Args:
            source: Data source identifier
            params: Query parameters
            value: Value to cache
        """
        cache = request_cache.get({})
        key = self._generate_key(source, params)
        cache[key] = value
        request_cache.set(cache)

    def get_or_set(
        self,
        source: str,
        params: dict[str, Any],
        fetch_func,
        *func_args,
        **func_kwargs
    ) -> Any:
        """
        Get from cache or fetch and cache.

        Args:
            source: Data source identifier
            params: Query parameters
            fetch_func: Function to call if cache miss
            *func_args: Arguments for fetch_func
            **func_kwargs: Keyword arguments for fetch_func

        Returns:
            Cached or fetched value
        """
        # Check cache first
        cached = self.get(source, params)
        if cached is not None:
            return cached

        # Cache miss - fetch and cache
        value = fetch_func(*func_args, **func_kwargs)
        self.set(source, params, value)
        return value

    def clear(self) -> None:
        """Clear cache for current request."""
        request_cache.set({})
        self._stats.clear()

    def get_stats(self) -> dict[str, dict[str, int]]:
        """
        Get cache statistics for current request.

        Returns:
            Dictionary with hit/miss counts per key
        """
        return dict(self._stats)

    def get_summary(self) -> dict[str, Any]:
        """
        Get cache summary for current request.

        Returns:
            Summary with total hits, misses, size, and hit rate
        """
        total_hits = sum(s["hits"] for s in self._stats.values())
        total_misses = sum(s["misses"] for s in self._stats.values())
        total = total_hits + total_misses
        hit_rate = total_hits / total if total > 0 else 0.0

        return {
            "total_hits": total_hits,
            "total_misses": total_misses,
            "total_requests": total,
            "cache_size": len(request_cache.get({})),
            "hit_rate": round(hit_rate, 4),
            "keys_cached": len(self._stats),
        }


def cached(source: str, ttl: int = 0):
    """
    Decorator for caching function results in L1 cache.

    Args:
        source: Data source identifier for cache key
        ttl: Ignored for L1 (kept for API compatibility)

    Example:
        @cached("elasticsearch")
        async def get_logs(query):
            return await es.search(query)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache = L1Cache()

            # Generate params from function arguments
            # Skip 'self' for methods
            params = {}
            if args and hasattr(args[0], '__self__'):
                args = args[1:]

            # Convert args to positional params
            for i, arg in enumerate(args):
                params[f"arg_{i}"] = arg

            # Add kwargs
            params.update(kwargs)

            # Check cache
            cached = cache.get(source, params)
            if cached is not None:
                return cached

            # Cache miss - call function
            result = await func(*args, **kwargs)

            # Cache result
            cache.set(source, params, result)
            return result

        return wrapper
    return decorator


class RequestCacheMiddleware:
    """
    Middleware to manage L1 cache lifecycle per request.

    Ensures cache is cleared at the start of each request
    and statistics are available for monitoring.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Initialize cache for this request
        L1Cache().clear()

        # Wrap send to capture response
        start_time = time.time()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                # Add cache headers
                cache_stats = L1Cache().get_summary()
                headers = dict(message.get("headers", []))

                # Add cache statistics as headers
                headers.append((
                    b"x-l1-cache-hits",
                    str(cache_stats["total_hits"]).encode()
                ))
                headers.append((
                    b"x-l1-cache-misses",
                    str(cache_stats["total_misses"]).encode()
                ))
                headers.append((
                    b"x-l1-cache-hit-rate",
                    str(cache_stats["hit_rate"]).encode()
                ))

                message["headers"] = list(headers.items())

            await send(message)

        await self.app(scope, receive, send_wrapper)
