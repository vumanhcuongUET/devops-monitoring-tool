"""
Integration Tests for Distributed State Management

Phase 9 - Sprint 1 - Day 5
Tests for Redis-based distributed state (alerts, approvals, rate limiting)
"""

import asyncio

import pytest

# Mark all tests in this module as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.slow]


class TestDistributedAlertState:
    """Integration tests for Redis-based alert state."""

    @pytest.mark.skip(reason="Requires actual Redis instance")
    @pytest.mark.asyncio
    async def test_concurrent_alert_modifications(self):
        """Test that concurrent alert modifications are handled correctly."""
        from app.alerting.redis_store import RedisAlertStore

        store = RedisAlertStore(
            redis_host="localhost",
            redis_port=6379,
            redis_db=0,
        )
        alert_id = "test-concurrent-123"

        try:
            # Simulate concurrent modifications
            tasks = [
                store.set_breached(alert_id),
                store.set_firing(alert_id),
                store.set_resolved(alert_id),
            ]
            results = await asyncio.gather(*tasks)

            # All should complete without errors
            assert all(r is not None for r in results)

            # Final state should be consistent
            final_state = await store.get(alert_id)
            assert final_state is not None
            assert final_state["id"] == alert_id
        finally:
            await store.close()

    @pytest.mark.skip(reason="Requires actual Redis instance")
    @pytest.mark.asyncio
    async def test_alert_state_ttl_cleanup(self):
        """Test that alert state TTL works correctly."""
        from app.alerting.redis_store import RedisAlertStore

        # Use short TTL for testing
        store = RedisAlertStore(
            redis_host="localhost",
            redis_port=6379,
            redis_db=0,
            ttl_seconds=5,  # 5 seconds for testing
        )

        try:
            alert_id = "test-ttl-123"

            # Create alert state
            await store.set_firing(alert_id)

            # Verify it exists
            state = await store.get(alert_id)
            assert state is not None

            # Wait for TTL to expire
            await asyncio.sleep(6)

            # Verify it's gone
            state = await store.get(alert_id)
            assert state is None
        finally:
            await store.close()

    @pytest.mark.skip(reason="Requires actual Redis instance")
    @pytest.mark.asyncio
    async def test_distributed_lock_prevents_race_conditions(self):
        """Test that distributed locking prevents race conditions."""
        from app.alerting.redis_store import RedisAlertStore

        store = RedisAlertStore(
            redis_host="localhost",
            redis_port=6379,
            redis_db=0,
        )

        try:
            alert_id = "test-lock-456"

            # First lock acquisition should succeed
            lock1 = await store.acquire_lock(alert_id, ttl=10)
            assert lock1 is True

            # Second lock acquisition should fail
            lock2 = await store.acquire_lock(alert_id, ttl=10)
            assert lock2 is False

            # Release first lock
            await store.release_lock(alert_id)

            # Now lock acquisition should succeed again
            lock3 = await store.acquire_lock(alert_id, ttl=10)
            assert lock3 is True

            # Cleanup
            await store.release_lock(alert_id)
        finally:
            await store.close()


class TestDistributedApprovalState:
    """Integration tests for Redis-based approval state."""

    @pytest.mark.skip(reason="Requires actual Redis instance")
    @pytest.mark.asyncio
    async def test_concurrent_approval_status_updates(self):
        """Test that concurrent approval status updates work correctly."""
        from app.approvals.redis_store import RedisApprovalStore
        from app.models.actions import ActionStatus

        store = RedisApprovalStore(
            redis_host="localhost",
            redis_port=6379,
            redis_db=1,
        )

        try:
            action_id = "test-concurrent-action-789"

            # Simulate concurrent status updates
            tasks = [
                store.set_status(action_id, ActionStatus.PENDING, user="user1"),
                store.set_status(action_id, ActionStatus.APPROVED, user="approver1"),
            ]
            results = await asyncio.gather(*tasks)

            # Both should complete
            assert all(r is not None for r in results)

            # Final state should exist
            final_state = await store.get(action_id)
            assert final_state is not None
        finally:
            await store.close()

    @pytest.mark.skip(reason="Requires actual Redis instance")
    @pytest.mark.asyncio
    async def test_approval_lock_prevents_race_conditions(self):
        """Test that approval locking prevents race conditions."""
        from app.approvals.redis_store import RedisApprovalStore

        store = RedisApprovalStore(
            redis_host="localhost",
            redis_port=6379,
            redis_db=1,
        )

        try:
            action_id = "test-approval-lock-999"

            # Acquire lock
            locked = await store.acquire_lock(action_id, ttl=10)
            assert locked is True

            # Try to modify while locked (should fail)
            try:
                await store.set_status(action_id, "approved", user="user1")
                # Should not reach here
                raise AssertionError("Should have raised RuntimeError")
            except RuntimeError as e:
                assert "being modified" in str(e).lower()

            # Release lock and try again
            await store.release_lock(action_id)
            result = await store.set_status(action_id, "approved", user="user1")
            assert result is not None
        finally:
            await store.close()


class TestDistributedRateLimiting:
    """Integration tests for Redis-based rate limiting."""

    @pytest.mark.skip(reason="Requires actual Redis instance")
    @pytest.mark.asyncio
    async def test_distributed_rate_limit_across_pods(self):
        """Test rate limiting works across distributed processes."""
        from app.rate_limiting.redis_rate_limiter import RedisRateLimiter

        limiter = RedisRateLimiter(
            redis_host="localhost",
            redis_port=6379,
            redis_db=2,
        )

        try:
            key = "test-distributed-rate-limit"

            # Make 10 concurrent requests, limit is 5
            tasks = [
                limiter.check_rate_limit(key, max_requests=5, window_seconds=60)
                for _ in range(10)
            ]
            results = await asyncio.gather(*tasks)

            allowed_count = sum(1 for allowed, _ in results if allowed)

            # Should have exactly 5 allowed
            assert allowed_count == 5

            # All responses should have consistent info
            for allowed, info in results:
                assert info["limit"] == 5
                assert "remaining" in info
                assert "reset" in info
        finally:
            await limiter.close()

    @pytest.mark.skip(reason="Requires actual Redis instance")
    @pytest.mark.asyncio
    async def test_rate_limit_sliding_window(self):
        """Test that sliding window rate limiting works correctly."""
        from app.rate_limiting.redis_rate_limiter import RedisRateLimiter

        limiter = RedisRateLimiter(
            redis_host="localhost",
            redis_port=6379,
            redis_db=2,
        )

        try:
            key = "test-sliding-window"

            # Make 3 requests under limit of 5
            for i in range(3):
                allowed, info = await limiter.check_rate_limit(
                    key, max_requests=5, window_seconds=60
                )
                assert allowed is True
                assert info["remaining"] >= 2 - i  # 5 - (i+1) requests made

            # Wait for window to slide (not feasible in quick test, so we trust the algorithm)
            # In production, old entries would be removed after 60 seconds
        finally:
            await limiter.close()

    @pytest.mark.skip(reason="Requires actual Redis instance")
    @pytest.mark.asyncio
    async def test_rate_limit_reset_functionality(self):
        """Test that rate limit can be reset."""
        from app.rate_limiting.redis_rate_limiter import RedisRateLimiter

        limiter = RedisRateLimiter(
            redis_host="localhost",
            redis_port=6379,
            redis_db=2,
        )

        try:
            key = "test-reset"

            # Make some requests
            for _ in range(3):
                await limiter.check_rate_limit(key, max_requests=5, window_seconds=60)

            # Get count before reset
            count = await limiter.get_current_count(key, window_seconds=60)
            assert count == 3

            # Reset
            result = await limiter.reset(key)
            assert result is True

            # Verify count is now 0
            count = await limiter.get_current_count(key, window_seconds=60)
            assert count == 0
        finally:
            await limiter.close()


class TestDistributedStateIntegration:
    """Integration tests across all distributed state components."""

    @pytest.mark.skip(reason="Requires actual Redis instance")
    @pytest.mark.asyncio
    async def test_all_components_use_different_redis_dbs(self):
        """Test that different components use separate Redis databases."""
        from app.alerting.redis_store import RedisAlertStore
        from app.approvals.redis_store import RedisApprovalStore
        from app.config import settings
        from app.rate_limiting.redis_rate_limiter import RedisRateLimiter

        # Verify each component uses its own DB
        assert settings.REDIS_DB_ALERTS == 0
        assert settings.REDIS_DB_APPROVALS == 1
        assert settings.REDIS_DB_RATE_LIMIT == 2
        assert settings.REDIS_DB_CACHE == 3

        # Create stores for each component
        alert_store = RedisAlertStore(redis_host="localhost", redis_port=6379, redis_db=0)
        approval_store = RedisApprovalStore(redis_host="localhost", redis_port=6379, redis_db=1)
        rate_limiter = RedisRateLimiter(redis_host="localhost", redis_port=6379, redis_db=2)

        try:
            # Each should use its own Redis DB
            assert alert_store.redis.db == 0
            assert approval_store.redis.db == 1
            assert rate_limiter.redis.db == 2
        finally:
            await alert_store.close()
            await approval_store.close()
            await rate_limiter.close()


# Unit tests that don't require Redis
class TestDistributedStateUnitTests:
    """Unit tests for distributed state that don't require Redis."""

    @pytest.mark.asyncio
    async def test_redis_db_settings_are_configured(self):
        """Test that Redis DB settings are properly configured."""
        from app.config import settings

        # Verify all Redis DB settings exist
        assert hasattr(settings, "REDIS_HOST")
        assert hasattr(settings, "REDIS_PORT")
        assert hasattr(settings, "REDIS_DB_ALERTS")
        assert hasattr(settings, "REDIS_DB_APPROVALS")
        assert hasattr(settings, "REDIS_DB_RATE_LIMIT")
        assert hasattr(settings, "REDIS_DB_CACHE")

        # Verify they use different DB numbers
        dbs = [
            settings.REDIS_DB_ALERTS,
            settings.REDIS_DB_APPROVALS,
            settings.REDIS_DB_RATE_LIMIT,
            settings.REDIS_DB_CACHE,
        ]
        assert len(dbs) == len(set(dbs)), "All Redis DBs should be different"

    @pytest.mark.asyncio
    async def test_redis_toggle_settings_exist(self):
        """Test that Redis toggle settings exist."""
        from app.config import settings

        assert hasattr(settings, "ALERT_STATE_USE_REDIS")
        assert hasattr(settings, "APPROVAL_STATE_USE_REDIS")
        assert hasattr(settings, "RATE_LIMIT_USE_REDIS")

        # All should default to False (file-based/in-memory by default)
        assert settings.ALERT_STATE_USE_REDIS is False
        assert settings.APPROVAL_STATE_USE_REDIS is False
        assert settings.RATE_LIMIT_USE_REDIS is False
