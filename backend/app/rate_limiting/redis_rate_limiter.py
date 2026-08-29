"""
Redis-based Distributed Rate Limiter

Phase 9 - Sprint 1 - Day 3
Purpose: Distributed rate limiting using Redis with sliding window algorithm

Features:
- Sliding window rate limiting (more accurate than fixed window)
- Works across multiple pods
- Proper HTTP 429 responses with Retry-After header
- Configurable limits and windows
"""

import logging
import time

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

logger = logging.getLogger(__name__)


class RedisRateLimiter:
    """
    Distributed rate limiter using Redis with sliding window.

    This uses Redis sorted sets to implement a sliding window rate limiter.
    Each request adds the current timestamp as a score, and old entries
    outside the window are removed.

    Example:
        limiter = RedisRateLimiter()

        allowed, info = await limiter.check_rate_limit(
            key="user:123",
            max_requests=100,
            window_seconds=60,
        )

        if not allowed:
            # Rate limit exceeded
            retry_after = info["reset"]
    """

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_password: str | None = None,
        redis_db: int = 2,  # DB for rate limiting
    ):
        """
        Initialize Redis rate limiter.

        Args:
            redis_host: Redis host
            redis_port: Redis port
            redis_password: Redis password (optional)
            redis_db: Redis database number for rate limiting
        """
        if not REDIS_AVAILABLE:
            raise ImportError("redis package is required for RedisRateLimiter")

        self.redis = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_password,
            db=redis_db,
            decode_responses=False,  # Keep binary for timestamps
            socket_connect_timeout=5,
            socket_timeout=5,
        )

    async def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, dict]:
        """
        Check rate limit using sliding window algorithm.

        Args:
            key: Unique identifier for the rate limit (e.g., "user:123", "ip:1.2.3.4")
            max_requests: Maximum number of requests allowed
            window_seconds: Time window in seconds

        Returns:
            Tuple of (allowed: bool, info: dict)
            info contains:
                - limit: max requests
                - remaining: requests remaining in window
                - reset: Unix timestamp when window resets
                - retry_after: seconds to wait before retry (if not allowed)
        """
        now = time.time()
        window_start = now - window_seconds
        redis_key = f"ratelimit:{key}"

        try:
            # Use pipeline for atomic operations
            pipe = self.redis.pipeline()

            # Remove entries outside the window (old timestamps)
            pipe.zremrangebyscore(redis_key, 0, window_start)

            # Count current requests in window
            pipe.zcard(redis_key)

            # Phase 10 Sprint 1 Day 1: Bug Fix - Handle bytes for Redis with decode_responses=False
            # When decode_responses=False (line 74), zadd expects bytes for keys, not strings
            # We encode the timestamp key to bytes
            pipe.zadd(redis_key, {str(now).encode(): now})

            # Set expiry on the key (window + 1 second for buffer)
            pipe.expire(redis_key, window_seconds + 1)

            # Execute all commands
            results = await pipe.execute()

            # results[1] is the count after cleanup
            current_count = results[1]

            allowed = current_count < max_requests

            # Calculate reset time (when oldest entry expires)
            reset_time = int(now + window_seconds)

            # Calculate retry_after if not allowed
            if not allowed:
                # Get the oldest timestamp in the window
                oldest = await self.redis.zrange(redis_key, 0, 0, withscores=True)
                if oldest:
                    oldest_timestamp = oldest[0][1]
                    retry_after = max(1, int(oldest_timestamp + window_seconds - now))
                else:
                    retry_after = window_seconds
            else:
                retry_after = 0

            info = {
                "limit": max_requests,
                "remaining": max(0, max_requests - current_count - 1),  # -1 for current request
                "reset": reset_time,
                "retry_after": retry_after,
            }

            return allowed, info

        except Exception as e:
            logger.error(f"RedisRateLimiter: Error checking rate limit for {key}: {e}")
            # Fail open - allow request if Redis is down
            return True, {
                "limit": max_requests,
                "remaining": max_requests,
                "reset": int(now + window_seconds),
                "retry_after": 0,
            }

    async def reset(self, key: str) -> bool:
        """
        Reset rate limit for a specific key.

        Useful for testing or manual intervention.

        Args:
            key: Rate limit key to reset

        Returns:
            True if successful, False otherwise
        """
        redis_key = f"ratelimit:{key}"

        try:
            result = await self.redis.delete(redis_key)
            return result > 0
        except Exception as e:
            logger.error(f"RedisRateLimiter: Error resetting {key}: {e}")
            return False

    async def get_current_count(self, key: str, window_seconds: int) -> int:
        """
        Get current request count for a key.

        Args:
            key: Rate limit key
            window_seconds: Time window in seconds

        Returns:
            Current count of requests in the window
        """
        redis_key = f"ratelimit:{key}"
        window_start = time.time() - window_seconds

        try:
            # Remove old entries first
            await self.redis.zremrangebyscore(redis_key, 0, window_start)

            # Count remaining
            count = await self.redis.zcard(redis_key)
            return count
        except Exception as e:
            logger.error(f"RedisRateLimiter: Error getting count for {key}: {e}")
            return 0

    async def get_all_keys(self) -> list[str]:
        """
        Get all rate limit keys currently in Redis.

        Useful for monitoring/debugging.

        Returns:
            List of rate limit keys (without "ratelimit:" prefix)
        """
        try:
            pattern = "ratelimit:*"
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                # Remove "ratelimit:" prefix
                key_str = key.decode() if isinstance(key, bytes) else key
                keys.append(key_str.replace("ratelimit:", ""))
            return keys
        except Exception as e:
            logger.error(f"RedisRateLimiter: Error getting keys: {e}")
            return []

    async def close(self) -> None:
        """Close Redis connection."""
        try:
            await self.redis.close()
        except Exception as e:
            logger.error(f"RedisRateLimiter: Error closing connection: {e}")


class RedisRateLimiterMiddleware:
    """
    FastAPI middleware for Redis-based rate limiting.

    Example:
        limiter = RedisRateLimiter()
        middleware = RedisRateLimiterMiddleware(limiter)

        app.add_middleware(
            RedisRateLimiterMiddleware,
            limiter=limiter,
            default_requests=100,
            default_window=60,
        )
    """

    def __init__(
        self,
        app,
        limiter: RedisRateLimiter,
        default_requests: int = 100,
        default_window: int = 60,
        key_generator: callable | None = None,
    ):
        """
        Initialize rate limit middleware.

        Args:
            app: FastAPI application
            limiter: RedisRateLimiter instance
            default_requests: Default max requests per window
            default_window: Default window size in seconds
            key_generator: Optional function to generate rate limit keys
                          Defaults to using IP address
        """
        self.app = app
        self.limiter = limiter
        self.default_requests = default_requests
        self.default_window = default_window
        self.key_generator = key_generator or self._default_key_generator

    @staticmethod
    def _default_key_generator(request) -> str:
        """Generate rate limit key from request (by IP address)."""
        # Get IP from request, handling proxies
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"
        return f"ip:{ip}"

    async def dispatch(self, request, call_next):
        """Process request with rate limiting."""
        # Skip rate limiting for health endpoints
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        # Generate rate limit key
        key = self.key_generator(request)

        # Check rate limit
        allowed, info = await self.limiter.check_rate_limit(
            key=key,
            max_requests=self.default_requests,
            window_seconds=self.default_window,
        )

        if not allowed:
            from fastapi import HTTPResponse
            return HTTPResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": info["retry_after"],
                },
                headers={
                    "Retry-After": str(info["retry_after"]),
                    "X-RateLimit-Limit": str(info["limit"]),
                    "X-RateLimit-Remaining": str(info["remaining"]),
                    "X-RateLimit-Reset": str(info["reset"]),
                },
            )

        # Add rate limit headers to successful response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(info["reset"])

        return response


def create_redis_rate_limiter() -> RedisRateLimiter:
    """
    Create RedisRateLimiter from environment settings.

    Returns:
        Configured RedisRateLimiter instance
    """
    from app.config import settings

    return RedisRateLimiter(
        redis_host=settings.REDIS_HOST,
        redis_port=settings.REDIS_PORT,
        redis_password=settings.REDIS_PASSWORD,
        redis_db=settings.REDIS_DB_RATE_LIMIT,
    )
