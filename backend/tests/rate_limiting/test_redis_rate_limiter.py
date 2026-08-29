"""
Redis Rate Limiter Tests

Phase 9 - Sprint 1 - Day 3
Tests for Redis-based distributed rate limiting
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture
async def mock_redis():
    """Create a mock Redis client for testing."""
    redis = MagicMock()
    redis.pipeline = MagicMock()
    redis.zremrangebyscore = AsyncMock(return_value=0)
    redis.zcard = AsyncMock(return_value=0)
    redis.zadd = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.zrange = AsyncMock(return_value=[])
    redis.delete = AsyncMock(return_value=1)
    redis.scan_iter = AsyncMock(return_value=[])
    redis.close = AsyncMock(return_value=None)
    return redis


@pytest.fixture
def mock_pipe(mock_redis):
    """Create a mock Redis pipeline."""
    pipe = MagicMock()
    pipe.zremrangebyscore = AsyncMock(return_value=None)
    pipe.zcard = AsyncMock(return_value=0)
    pipe.zadd = AsyncMock(return_value=1)
    pipe.expire = AsyncMock(return_value=None)
    pipe.execute = AsyncMock(return_value=[0, 0, 1, True])  # [rem_result, count, add_result, expire_result]
    return pipe


@pytest.fixture
def redis_limiter(mock_redis):
    """Create a RedisRateLimiter with mock Redis client."""
    from app.rate_limiting.redis_rate_limiter import RedisRateLimiter

    with patch("redis.asyncio.Redis", return_value=mock_redis):
        limiter = RedisRateLimiter(
            redis_host="localhost",
            redis_port=6379,
            redis_password=None,
            redis_db=2,
        )
        limiter.redis = mock_redis
        return limiter


class TestRedisRateLimiter:
    """Test RedisRateLimiter functionality."""

    @pytest.mark.asyncio
    async def test_check_rate_limit_allowed(self, redis_limiter, mock_redis, mock_pipe):
        """Test rate limit check when allowed."""
        # Setup: 5 current requests, limit is 10
        mock_redis.pipeline.return_value = mock_pipe
        mock_pipe.execute = AsyncMock(return_value=[0, 5, 1, True])

        allowed, info = await redis_limiter.check_rate_limit(
            key="user:123",
            max_requests=10,
            window_seconds=60,
        )

        assert allowed is True
        assert info["limit"] == 10
        assert info["remaining"] == 4  # 10 - 5 - 1 (current)
        assert "reset" in info

    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self, redis_limiter, mock_redis, mock_pipe):
        """Test rate limit check when exceeded."""
        # Setup: 10 current requests, limit is 10
        mock_redis.pipeline.return_value = mock_pipe
        mock_pipe.execute = AsyncMock(return_value=[0, 10, 1, True])

        allowed, info = await redis_limiter.check_rate_limit(
            key="user:123",
            max_requests=10,
            window_seconds=60,
        )

        assert allowed is False
        assert info["limit"] == 10
        assert info["remaining"] == 0
        assert info["retry_after"] > 0

    @pytest.mark.asyncio
    async def test_check_rate_limit_with_burst_requests(self, redis_limiter, mock_redis, mock_pipe):
        """Test rate limit handles burst requests correctly."""
        # Simulate multiple concurrent requests
        mock_redis.pipeline.return_value = mock_pipe

        results = []
        for i in range(5):
            # First request: 0 current, second: 1 current, etc.
            mock_pipe.execute = AsyncMock(return_value=[0, i, 1, True])
            allowed, info = await redis_limiter.check_rate_limit(
                key="user:burst",
                max_requests=10,
                window_seconds=60,
            )
            results.append((allowed, info))

        # First 5 should all be allowed
        assert all(allowed for allowed, _ in results)

    @pytest.mark.asyncio
    async def test_reset_rate_limit(self, redis_limiter, mock_redis):
        """Test resetting rate limit for a key."""
        mock_redis.delete.return_value = 1

        result = await redis_limiter.reset("user:123")

        assert result is True
        mock_redis.delete.assert_called_once_with("ratelimit:user:123")

    @pytest.mark.asyncio
    async def test_get_current_count(self, redis_limiter, mock_redis):
        """Test getting current request count."""
        mock_redis.zremrangebyscore = AsyncMock(return_value=2)  # Removed 2 old entries
        mock_redis.zcard = AsyncMock(return_value=5)  # 5 current requests

        count = await redis_limiter.get_current_count("user:123", window_seconds=60)

        assert count == 5

    @pytest.mark.asyncio
    async def test_get_all_keys(self, redis_limiter, mock_redis):
        """Test getting all rate limit keys."""
        async def mock_scan_iter(match):
            yield b"ratelimit:user:123"
            yield b"ratelimit:ip:1.2.3.4"

        mock_redis.scan_iter = mock_scan_iter

        keys = await redis_limiter.get_all_keys()

        assert len(keys) == 2
        assert "user:123" in keys
        assert "ip:1.2.3.4" in keys

    @pytest.mark.asyncio
    async def test_redis_failure_fails_open(self, redis_limiter, mock_redis):
        """Test that rate limiter fails open on Redis error."""
        # Make pipeline execute raise an exception
        mock_redis.pipeline = MagicMock(side_effect=Exception("Redis connection failed"))

        allowed, info = await redis_limiter.check_rate_limit(
            key="user:123",
            max_requests=10,
            window_seconds=60,
        )

        # Should allow request when Redis is down (fail open)
        assert allowed is True
        assert info["remaining"] == 10  # Full allowance


class TestRateLimitMiddleware:
    """Test RateLimitMiddleware with Redis backend."""

    @pytest.mark.asyncio
    async def test_middleware_with_redis(self, mock_redis, mock_pipe):
        """Test middleware uses Redis when configured."""
        from starlette.applications import Starlette

        from app.rate_limit import RateLimitMiddleware

        # Create app and middleware
        app = Starlette()

        # Setup Redis limiter
        mock_redis.pipeline.return_value = mock_pipe
        mock_pipe.execute = AsyncMock(return_value=[0, 5, 1, True])

        with patch("redis.asyncio.Redis", return_value=mock_redis):
            middleware = RateLimitMiddleware(
                app,
                requests_per_minute=10,
                burst=5,
                use_redis=True,
            )

        # Verify Redis limiter is initialized
        assert middleware._redis_limiter is not None
        assert middleware.use_redis is True

    @pytest.mark.asyncio
    async def test_middleware_falls_back_to_memory_on_redis_error(self, mock_redis):
        """Test middleware falls back to in-memory when Redis unavailable."""
        from starlette.applications import Starlette

        from app.rate_limit import RateLimitMiddleware

        app = Starlette()

        # Mock ImportError when trying to import Redis
        with patch("app.rate_limit.REDIS_RATE_LIMITER_AVAILABLE", False):
            middleware = RateLimitMiddleware(
                app,
                requests_per_minute=10,
                burst=5,
                use_redis=True,
            )

        # Should fall back to in-memory
        assert middleware.use_redis is False
        assert middleware._windows is not None


class TestSlidingWindowAlgorithm:
    """Test sliding window rate limiting algorithm correctness."""

    @pytest.mark.asyncio
    async def test_sliding_window_removes_old_entries(self, redis_limiter, mock_redis, mock_pipe):
        """Test that sliding window removes entries outside time window."""
        mock_redis.pipeline.return_value = mock_pipe

        # Simulate: zremrangebyscore removes 3 old entries
        # zcard returns count of remaining entries
        mock_pipe.execute = AsyncMock(return_value=[3, 7, 1, True])

        allowed, info = await redis_limiter.check_rate_limit(
            key="user:sliding",
            max_requests=10,
            window_seconds=60,
        )

        assert allowed is True
        assert info["remaining"] == 2  # 10 - 7 - 1

    @pytest.mark.asyncio
    async def test_sliding_window_across_pods(self, redis_limiter, mock_redis, mock_pipe):
        """Test that rate limiting works across multiple pods (shared Redis)."""
        mock_redis.pipeline.return_value = mock_pipe

        # Simulate requests from pod 1
        mock_pipe.execute = AsyncMock(return_value=[0, 5, 1, True])
        allowed1, info1 = await redis_limiter.check_rate_limit(
            key="user:multi-pod",
            max_requests=10,
            window_seconds=60,
        )

        # Simulate requests from pod 2 (same Redis, count accumulates)
        mock_pipe.execute = AsyncMock(return_value=[0, 8, 1, True])
        allowed2, info2 = await redis_limiter.check_rate_limit(
            key="user:multi-pod",
            max_requests=10,
            window_seconds=60,
        )

        # Both should see consistent state
        assert allowed1 is True
        assert allowed2 is True
        assert info2["remaining"] < info1["remaining"]  # More requests made


@pytest.mark.asyncio
async def test_create_redis_rate_limiter_from_env():
    """Test creating rate limiter from environment settings."""
    from unittest.mock import patch

    from app.config import settings
    from app.rate_limiting.redis_rate_limiter import create_redis_rate_limiter

    with patch("redis.asyncio.Redis") as mock_redis_cls:
        mock_redis = MagicMock()
        mock_redis_cls.return_value = mock_redis

        limiter = create_redis_rate_limiter()

        # Verify it uses settings from config
        mock_redis_cls.assert_called_once()

        call_kwargs = mock_redis_cls.call_args[1]
        assert call_kwargs["host"] == settings.REDIS_HOST
        assert call_kwargs["port"] == settings.REDIS_PORT
        assert call_kwargs["db"] == settings.REDIS_DB_RATE_LIMIT
