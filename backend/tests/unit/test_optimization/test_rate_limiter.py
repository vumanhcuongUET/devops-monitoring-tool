"""RateLimiter token-bucket regression test."""

import pytest

from app.optimization.connection_pool import RateLimiter


@pytest.mark.asyncio
async def test_burst_beyond_capacity_is_rejected():
    """20-token bucket must reject the 21st request."""
    limiter = RateLimiter(default_rate=1.0, burst=20)
    for _ in range(20):
        assert await limiter.acquire("ep") is True
    assert await limiter.acquire("ep") is False
    assert limiter.stats["rejected_requests"] == 1
    assert limiter.stats["allowed_requests"] == 20
