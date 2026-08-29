"""
Redis-based distributed single-flight deduplication.

Prevents duplicate concurrent requests across multiple processes/instances
using Redis for distributed coordination.
"""

import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional, TypeVar

T = TypeVar("T")

# Lazy imports to avoid circular dependency
def _get_logger():
    from core.logging_config import get_logger
    return get_logger(__name__)


def _get_metrics():
    from core.logging_config import get_metrics
    return get_metrics()


class RedisSingleFlight:
    """
    Distributed single-flight using Redis locks.

    Prevents duplicate concurrent requests across processes by using
    Redis for distributed coordination and result caching.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        lock_prefix: str = "sf_lock:",
        result_prefix: str = "sf_result:",
        lock_ttl: int = 30,
        result_ttl: int = 60,
        fallback_enabled: bool = True
    ):
        """
        Initialize Redis single-flight.

        Args:
            redis_url: Redis connection URL
            lock_prefix: Prefix for lock keys
            result_prefix: Prefix for result cache keys
            lock_ttl: Lock TTL in seconds (prevents deadlocks)
            result_ttl: Result TTL in seconds
            fallback_enabled: If True, falls back to direct execution when Redis unavailable
        """
        self._redis_url = redis_url
        self._lock_prefix = lock_prefix
        self._result_prefix = result_prefix
        self._lock_ttl = lock_ttl
        self._result_ttl = result_ttl
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
            _get_logger().info("Redis single-flight connected", url=self._redis_url)
            _get_metrics().increment("redis_single_flight_connected")
        except Exception as e:
            self._available = False
            if self._fallback_enabled:
                _get_logger().warning(f"Redis single-flight unavailable, falling back to direct execution: {e}")
                _get_metrics().increment("redis_single_flight_unavailable")
            else:
                raise RuntimeError(f"Redis single-flight required but unavailable: {e}") from e

    @property
    def available(self) -> bool:
        """Check if Redis is available."""
        return self._available

    def _make_lock_key(self, key: str) -> str:
        """Generate lock key."""
        return f"{self._lock_prefix}{key}"

    def _make_result_key(self, key: str) -> str:
        """Generate result cache key."""
        return f"{self._result_prefix}{key}"

    def execute(
        self,
        key: str,
        func: Callable[..., T],
        *args,
        **kwargs
    ) -> T:
        """
        Execute function with distributed single-flight deduplication.

        Args:
            key: Request identifier key
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            Exception: If function execution fails
        """
        if not self._available:
            # Fallback to direct execution
            _get_logger().debug("Redis unavailable, executing directly", key=key[:32])
            return func(*args, **kwargs)

        lock_key = self._make_lock_key(key)
        result_key = self._make_result_key(key)
        request_id = str(uuid.uuid4())

        # Try to get cached result first
        try:
            import json
            cached = self._redis.get(result_key)
            if cached:
                _get_metrics().increment("redis_single_flight_cache_hit")
                _get_logger().debug("Single-flight: reused cached result", key=key[:32])
                return json.loads(cached)
        except Exception as e:
            _get_logger().warning("Failed to get cached result", key=key[:32], error=str(e))

        # Try to acquire lock
        lock_acquired = False
        try:
            lock_acquired = self._redis.set(
                lock_key,
                request_id,
                nx=True,
                ex=self._lock_ttl
            )

            if lock_acquired:
                # We are the first, execute the function
                _get_logger().debug("Single-flight: starting new request", key=key[:32])
                _get_metrics().increment("redis_single_flight_execute_total")

                try:
                    result = func(*args, **kwargs)

                    # Cache the result
                    try:
                        import json
                        self._redis.setex(
                            result_key,
                            self._result_ttl,
                            json.dumps(result, default=str)
                        )
                    except Exception as e:
                        _get_logger().warning("Failed to cache result", key=key[:32], error=str(e))

                    _get_logger().debug("Single-flight: request completed", key=key[:32])
                    return result

                except Exception as e:
                    _get_logger().warning("Single-flight: request failed", key=key[:32], error=str(e))
                    _get_metrics().increment("redis_single_flight_error_total")
                    raise
                finally:
                    # Release lock
                    self._redis.delete(lock_key)

            else:
                # Another request is in progress, wait and poll for result
                _get_logger().debug("Single-flight: waiting for existing request", key=key[:32])
                _get_metrics().increment("redis_single_flight_wait_total")

                # Poll for result with timeout
                deadline = time.time() + self._lock_ttl
                poll_interval = 0.1  # 100ms

                while time.time() < deadline:
                    time.sleep(poll_interval)

                    try:
                        import json
                        cached = self._redis.get(result_key)
                        if cached:
                            _get_metrics().increment("redis_single_flight_dedup_total")
                            return json.loads(cached)
                    except Exception:
                        pass

                # Timeout - fall back to direct execution
                _get_logger().warning("Single-flight: timeout waiting for result, executing directly", key=key[:32])
                _get_metrics().increment("redis_single_flight_timeout_total")
                return func(*args, **kwargs)

        except Exception as e:
            _get_logger().warning("Single-flight: error during execution", key=key[:32], error=str(e))
            # On any error, fall back to direct execution
            return func(*args, **kwargs)

        finally:
            # Ensure lock is released
            if lock_acquired and self._available:
                try:
                    # Only delete if we still own the lock
                    current_owner = self._redis.get(lock_key)
                    if current_owner == request_id:
                        self._redis.delete(lock_key)
                except Exception:
                    pass

    def stats(self) -> Dict[str, Any]:
        """
        Get single-flight statistics.

        Returns:
            Dictionary with stats
        """
        if not self._available:
            return {
                "type": "redis",
                "available": False,
                "url": self._redis_url
            }

        try:
            lock_pattern = f"{self._lock_prefix}*"
            result_pattern = f"{self._result_prefix}*"

            lock_keys = self._redis.keys(lock_pattern)
            result_keys = self._redis.keys(result_pattern)

            return {
                "type": "redis",
                "available": True,
                "url": self._redis_url,
                "active_locks": len(lock_keys),
                "cached_results": len(result_keys)
            }

        except Exception as e:
            return {
                "type": "redis",
                "available": False,
                "error": str(e)
            }


# Global Redis single-flight instance
_global_redis_single_flight: Optional[RedisSingleFlight] = None


def get_global_redis_single_flight() -> Optional[RedisSingleFlight]:
    """Get or create global Redis single-flight instance."""
    global _global_redis_single_flight

    if _global_redis_single_flight is None:
        from core.config_loader import get_feature_flags

        flags = get_feature_flags()
        sf_config = flags.get("optimization", {}).get("redis_single_flight", {})

        if not sf_config.get("enabled", False):
            return None

        _global_redis_single_flight = RedisSingleFlight(
            redis_url=sf_config.get("url", "redis://localhost:6379/0"),
            lock_prefix=sf_config.get("lock_prefix", "sf_lock:"),
            result_prefix=sf_config.get("result_prefix", "sf_result:"),
            lock_ttl=sf_config.get("lock_ttl_seconds", 30),
            result_ttl=sf_config.get("result_ttl_seconds", 60),
            fallback_enabled=sf_config.get("fallback_enabled", True)
        )

    return _global_redis_single_flight
