"""
Redis Alert Store Tests

Phase 9 - Sprint 1 - Day 1
Tests for Redis-backed alert state management
"""

import asyncio
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture
async def mock_redis():
    """Create a mock Redis client for testing."""
    redis = MagicMock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.scan_iter = AsyncMock(return_value=[])
    redis.mget = AsyncMock(return_value=[])
    redis.lpush = AsyncMock(return_value=1)
    redis.ltrim = AsyncMock(return_value=True)
    redis.lrange = AsyncMock(return_value=[])
    redis.expire = AsyncMock(return_value=True)
    redis.close = AsyncMock(return_value=None)
    return redis


@pytest.fixture
def redis_store(mock_redis):
    """Create a RedisAlertStore with mock Redis client."""
    from app.alerting.redis_store import RedisAlertStore

    # Patch the redis.asyncio.Redis to return our mock
    with patch("redis.asyncio.Redis", return_value=mock_redis):
        store = RedisAlertStore(
            redis_host="localhost",
            redis_port=6379,
            redis_password=None,
            redis_db=0,
        )
        store.redis = mock_redis
        return store


@pytest.fixture
def redis_history(mock_redis):
    """Create a RedisAlertHistory with mock Redis client."""
    from app.alerting.redis_store import RedisAlertHistory

    with patch("redis.asyncio.Redis", return_value=mock_redis):
        history = RedisAlertHistory(
            redis_host="localhost",
            redis_port=6379,
            redis_password=None,
            redis_db=0,
        )
        history.redis = mock_redis
        return history


class TestRedisAlertStore:
    """Test RedisAlertStore functionality."""

    @pytest.mark.asyncio
    async def test_get_alert_state_not_found(self, redis_store, mock_redis):
        """Test getting alert state that doesn't exist."""
        mock_redis.get.return_value = None

        result = await redis_store.get("nonexistent-rule")

        assert result is None
        mock_redis.get.assert_called_once_with("alert:state:nonexistent-rule")

    @pytest.mark.asyncio
    async def test_get_alert_state_found(self, redis_store, mock_redis):
        """Test getting existing alert state."""
        state_data = {
            "rule_id": "test-rule",
            "status": "firing",
            "first_breached_at": "2026-08-25T10:00:00Z",
            "fired_at": "2026-08-25T10:05:00Z",
            "resolved_at": None,
        }
        mock_redis.get.return_value = json.dumps(state_data)

        result = await redis_store.get("test-rule")

        assert result == state_data
        mock_redis.get.assert_called_once_with("alert:state:test-rule")

    @pytest.mark.asyncio
    async def test_set_breached_new_state(self, redis_store, mock_redis):
        """Test setting breached status for new rule."""
        mock_redis.get.return_value = None  # No existing state
        mock_redis.set.return_value = True  # Lock acquired

        result = await redis_store.set_breached("new-rule")

        assert result["rule_id"] == "new-rule"
        assert result["status"] == "pending"
        assert "first_breached_at" in result
        assert "last_breached_at" in result
        # Just check both timestamps exist, they'll be very close but may differ slightly

    @pytest.mark.asyncio
    async def test_set_firing(self, redis_store, mock_redis):
        """Test setting firing status."""
        existing_state = {
            "rule_id": "test-rule",
            "status": "pending",
            "first_breached_at": "2026-08-25T10:00:00Z",
            "fired_at": None,
            "resolved_at": None,
        }
        mock_redis.get.return_value = json.dumps(existing_state)
        mock_redis.set.return_value = True

        result = await redis_store.set_firing("test-rule")

        assert result["status"] == "firing"
        assert "fired_at" in result

    @pytest.mark.asyncio
    async def test_set_resolved(self, redis_store, mock_redis):
        """Test setting resolved status."""
        existing_state = {
            "rule_id": "test-rule",
            "status": "firing",
            "first_breached_at": "2026-08-25T10:00:00Z",
            "fired_at": "2026-08-25T10:05:00Z",
            "resolved_at": None,
        }
        mock_redis.get.return_value = json.dumps(existing_state)
        mock_redis.set.return_value = True

        result = await redis_store.set_resolved("test-rule")

        assert result["status"] == "resolved"
        assert "resolved_at" in result

    @pytest.mark.asyncio
    async def test_delete_alert_state(self, redis_store, mock_redis):
        """Test deleting alert state."""
        mock_redis.delete.return_value = 2  # Both state and lock deleted

        result = await redis_store.delete("test-rule")

        assert result == 1

    @pytest.mark.asyncio
    async def test_get_all_state(self, redis_store, mock_redis):
        """Test getting all alert states."""
        states = [
            "alert:state:rule1",
            "alert:state:rule2",
        ]
        state_values = [
            json.dumps({"rule_id": "rule1", "status": "firing"}),
            json.dumps({"rule_id": "rule2", "status": "resolved"}),
        ]

        async def mock_scan_iter(match):
            for state in states:
                yield state

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.mget.return_value = state_values

        result = await redis_store.get_all_state()

        assert len(result) == 2
        assert "rule1" in result
        assert "rule2" in result

    @pytest.mark.asyncio
    async def test_get_firing_count(self, redis_store, mock_redis):
        """Test getting count of firing alerts."""
        states = ["alert:state:rule1", "alert:state:rule2", "alert:state:rule3"]
        state_values = [
            json.dumps({"rule_id": "rule1", "status": "firing"}),
            json.dumps({"rule_id": "rule2", "status": "firing"}),
            json.dumps({"rule_id": "rule3", "status": "resolved"}),
        ]

        async def mock_scan_iter(match):
            for state in states:
                yield state

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.mget.return_value = state_values

        count = await redis_store.get_firing_count()

        assert count == 2

    @pytest.mark.asyncio
    async def test_acquire_lock_success(self, redis_store, mock_redis):
        """Test acquiring distributed lock successfully."""
        mock_redis.set.return_value = True

        result = await redis_store.acquire_lock("test-alert")

        assert result is True

    @pytest.mark.asyncio
    async def test_acquire_lock_failure(self, redis_store, mock_redis):
        """Test failing to acquire lock (already held)."""
        mock_redis.set.return_value = False

        result = await redis_store.acquire_lock("test-alert")

        assert result is False

    @pytest.mark.asyncio
    async def test_release_lock(self, redis_store, mock_redis):
        """Test releasing distributed lock."""
        mock_redis.delete.return_value = 1

        result = await redis_store.release_lock("test-alert")

        assert result is True

    @pytest.mark.asyncio
    async def test_concurrent_modifications(self, redis_store, mock_redis):
        """Test handling of concurrent modifications."""
        existing_state = {
            "rule_id": "test-rule",
            "status": "pending",
            "first_breached_at": "2026-08-25T10:00:00Z",
            "fired_at": None,
            "resolved_at": None,
        }
        mock_redis.get.return_value = json.dumps(existing_state)
        mock_redis.set.return_value = True  # Lock acquired

        # Simulate concurrent modifications
        tasks = [
            redis_store.set_breached("test-rule"),
            redis_store.set_firing("test-rule"),
        ]

        results = await asyncio.gather(*tasks)

        # Both should succeed with locking
        assert all(r is not None for r in results)


class TestRedisAlertHistory:
    """Test RedisAlertHistory functionality."""

    @pytest.mark.asyncio
    async def test_add_event(self, redis_history, mock_redis):
        """Test adding event to history."""
        event = {
            "id": "event-1",
            "rule_id": "rule-1",
            "status": "firing",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        mock_redis.lpush.return_value = 1

        result = await redis_history.add(event)

        assert result is True
        mock_redis.lpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_entries(self, redis_history, mock_redis):
        """Test getting history entries."""
        events = [
            json.dumps({"id": "event-1", "status": "firing"}),
            json.dumps({"id": "event-2", "status": "resolved"}),
        ]
        mock_redis.lrange.return_value = events

        result = await redis_history.get_entries()

        assert len(result) == 2
        assert result[0]["id"] == "event-1"
        assert result[1]["id"] == "event-2"

    @pytest.mark.asyncio
    async def test_get_entries_with_limit(self, redis_history, mock_redis):
        """Test getting limited history entries."""
        events = [
            json.dumps({"id": "event-1"}),
        ]
        mock_redis.lrange.return_value = events

        result = await redis_history.get_entries(limit=1)

        assert len(result) == 1
        # Verify lrange was called with correct range (0 to 0 for limit=1)
        call_args = mock_redis.lrange.call_args
        assert call_args[0][1] == 0
        assert call_args[0][2] == 0

    @pytest.mark.asyncio
    async def test_clear_history(self, redis_history, mock_redis):
        """Test clearing all history."""
        mock_redis.delete.return_value = 1

        result = await redis_history.clear()

        assert result is True
        mock_redis.delete.assert_called_once_with("alert:history:events")


class TestRedisAlertStoreIntegration:
    """Integration tests for Redis alert store (require actual Redis)."""

    @pytest.mark.skip(reason="Requires actual Redis instance")
    @pytest.mark.asyncio
    async def test_real_redis_connection(self):
        """Test with real Redis connection (skip in CI)."""
        pass

    @pytest.mark.skip(reason="Requires actual Redis instance")
    @pytest.mark.asyncio
    async def test_ttl_cleanup(self):
        """Test TTL-based cleanup (requires real Redis)."""
        pass


@pytest.mark.asyncio
async def test_redis_store_backward_compatibility():
    """Test that file-based and Redis-based stores have compatible interfaces."""
    from app.alerting.redis_store import RedisAlertStore, RedisAlertHistory
    from app.alerting.state import AlertStateTracker, AlertHistory

    # Both stores should have similar methods
    redis_store_attrs = set(dir(RedisAlertStore("localhost", 6379, None, 0)))
    file_store_attrs = set(dir(AlertStateTracker()))

    # Common methods that should exist in both
    # Note: file-based store uses sync methods, Redis uses async
    common_methods = {"get"}
    assert common_methods.issubset(redis_store_attrs)
    assert common_methods.issubset(file_store_attrs)

    # Check for set_* methods
    assert any("set_" in attr for attr in redis_store_attrs)
    assert any("set_" in attr for attr in file_store_attrs)

    # History stores
    redis_history_attrs = set(dir(RedisAlertHistory("localhost", 6379, None, 0)))
    file_history_attrs = set(dir(AlertHistory()))

    common_history_methods = {"add"}
    assert common_history_methods.issubset(redis_history_attrs)
    assert common_history_methods.issubset(file_history_attrs)
