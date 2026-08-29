"""
Redis Approval Store Tests

Phase 9 - Sprint 1 - Day 2
Tests for Redis-backed approval state management
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.actions import ActionStatus

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
    """Create a RedisApprovalStore with mock Redis client."""
    from app.approvals.redis_store import RedisApprovalStore

    with patch("redis.asyncio.Redis", return_value=mock_redis):
        store = RedisApprovalStore(
            redis_host="localhost",
            redis_port=6379,
            redis_password=None,
            redis_db=1,
        )
        store.redis = mock_redis
        return store


@pytest.fixture
def redis_history(mock_redis):
    """Create a RedisApprovalHistory with mock Redis client."""
    from app.approvals.redis_store import RedisApprovalHistory

    with patch("redis.asyncio.Redis", return_value=mock_redis):
        history = RedisApprovalHistory(
            redis_host="localhost",
            redis_port=6379,
            redis_password=None,
            redis_db=1,
        )
        history.redis = mock_redis
        return history


class TestRedisApprovalStore:
    """Test RedisApprovalStore functionality."""

    @pytest.mark.asyncio
    async def test_get_approval_not_found(self, redis_store, mock_redis):
        """Test getting approval state that doesn't exist."""
        mock_redis.get.return_value = None

        result = await redis_store.get("nonexistent-action")

        assert result is None
        mock_redis.get.assert_called_once_with("approval:state:nonexistent-action")

    @pytest.mark.asyncio
    async def test_get_approval_found(self, redis_store, mock_redis):
        """Test getting existing approval state."""
        state_data = {
            "action_id": "test-action",
            "status": "pending",
            "created_at": "2026-08-25T10:00:00Z",
            "command": "kubectl get pods",
        }
        mock_redis.get.return_value = json.dumps(state_data)

        result = await redis_store.get("test-action")

        assert result == state_data
        mock_redis.get.assert_called_once_with("approval:state:test-action")

    @pytest.mark.asyncio
    async def test_get_all_states(self, redis_store, mock_redis):
        """Test getting all approval states."""
        states = [
            "approval:state:action1",
            "approval:state:action2",
        ]
        state_values = [
            json.dumps({"action_id": "action1", "status": "pending"}),
            json.dumps({"action_id": "action2", "status": "approved"}),
        ]

        async def mock_scan_iter(match):
            for state in states:
                yield state

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.mget.return_value = state_values

        result = await redis_store.get_all()

        assert len(result) == 2
        assert "action1" in result
        assert "action2" in result

    @pytest.mark.asyncio
    async def test_get_by_status(self, redis_store, mock_redis):
        """Test getting actions by status."""
        states = [
            "approval:state:action1",
            "approval:state:action2",
            "approval:state:action3",
        ]
        state_values = [
            json.dumps({"action_id": "action1", "status": "pending"}),
            json.dumps({"action_id": "action2", "status": "pending"}),
            json.dumps({"action_id": "action3", "status": "approved"}),
        ]

        async def mock_scan_iter(match):
            for state in states:
                yield state

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.mget.return_value = state_values

        pending = await redis_store.get_by_status(ActionStatus.PENDING)
        approved = await redis_store.get_by_status(ActionStatus.APPROVED)

        assert len(pending) == 2
        assert len(approved) == 1
        assert "action1" in pending
        assert "action3" in approved

    @pytest.mark.asyncio
    async def test_get_pending_count(self, redis_store, mock_redis):
        """Test getting count of pending actions."""
        states = ["approval:state:action1", "approval:state:action2"]
        state_values = [
            json.dumps({"action_id": "action1", "status": "pending"}),
            json.dumps({"action_id": "action2", "status": "pending"}),
        ]

        async def mock_scan_iter(match):
            for state in states:
                yield state

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.mget.return_value = state_values

        count = await redis_store.get_pending_count()

        assert count == 2

    @pytest.mark.asyncio
    async def test_set_status_new_action(self, redis_store, mock_redis):
        """Test setting status for new action."""
        mock_redis.get.return_value = None  # No existing state
        mock_redis.set.return_value = True  # Lock acquired

        result = await redis_store.set_status(
            action_id="new-action",
            status=ActionStatus.PENDING,
            user="admin",
            command="kubectl delete pod test-pod",
        )

        assert result["action_id"] == "new-action"
        assert result["status"] == ActionStatus.PENDING
        assert result["created_by"] == "admin"
        assert result["command"] == "kubectl delete pod test-pod"

    @pytest.mark.asyncio
    async def test_set_status_approved(self, redis_store, mock_redis):
        """Test setting status to approved."""
        existing_state = {
            "action_id": "test-action",
            "status": "pending",
            "created_at": "2026-08-25T10:00:00Z",
            "created_by": "admin",
        }
        mock_redis.get.return_value = json.dumps(existing_state)
        mock_redis.set.return_value = True

        result = await redis_store.set_status(
            action_id="test-action",
            status=ActionStatus.APPROVED,
            user="approver",
        )

        assert result["status"] == ActionStatus.APPROVED
        assert "approved_at" in result
        assert result["approved_by"] == "approver"

    @pytest.mark.asyncio
    async def test_set_status_rejected(self, redis_store, mock_redis):
        """Test setting status to rejected with reason."""
        existing_state = {
            "action_id": "test-action",
            "status": "pending",
            "created_at": "2026-08-25T10:00:00Z",
        }
        mock_redis.get.return_value = json.dumps(existing_state)
        mock_redis.set.return_value = True

        result = await redis_store.set_status(
            action_id="test-action",
            status=ActionStatus.REJECTED,
            user="approver",
            reason="Risk too high",
        )

        assert result["status"] == ActionStatus.REJECTED
        assert result["rejected_by"] == "approver"
        assert result["rejection_reason"] == "Risk too high"

    @pytest.mark.asyncio
    async def test_set_status_executed(self, redis_store, mock_redis):
        """Test setting status to executed."""
        existing_state = {
            "action_id": "test-action",
            "status": "approved",
            "created_at": "2026-08-25T10:00:00Z",
        }
        mock_redis.get.return_value = json.dumps(existing_state)
        mock_redis.set.return_value = True

        result = await redis_store.set_status(
            action_id="test-action",
            status=ActionStatus.EXECUTED,
            user="executor",
        )

        assert result["status"] == ActionStatus.EXECUTED
        assert "executed_at" in result
        assert result["executed_by"] == "executor"

    @pytest.mark.asyncio
    async def test_set_status_failed(self, redis_store, mock_redis):
        """Test setting status to failed."""
        existing_state = {
            "action_id": "test-action",
            "status": "executed",
            "created_at": "2026-08-25T10:00:00Z",
        }
        mock_redis.get.return_value = json.dumps(existing_state)
        mock_redis.set.return_value = True

        result = await redis_store.set_status(
            action_id="test-action",
            status=ActionStatus.FAILED,
            user="executor",
        )

        assert result["status"] == ActionStatus.FAILED
        assert "failed_at" in result
        assert result["failed_by"] == "executor"

    @pytest.mark.asyncio
    async def test_delete_approval(self, redis_store, mock_redis):
        """Test deleting approval state."""
        mock_redis.delete.return_value = 2  # Both state and lock deleted

        result = await redis_store.delete("test-action")

        assert result is True

    @pytest.mark.asyncio
    async def test_acquire_lock_success(self, redis_store, mock_redis):
        """Test acquiring distributed lock successfully."""
        mock_redis.set.return_value = True

        result = await redis_store.acquire_lock("test-action")

        assert result is True

    @pytest.mark.asyncio
    async def test_acquire_lock_failure(self, redis_store, mock_redis):
        """Test failing to acquire lock (already held)."""
        mock_redis.set.return_value = False

        result = await redis_store.acquire_lock("test-action")

        assert result is False

    @pytest.mark.asyncio
    async def test_release_lock(self, redis_store, mock_redis):
        """Test releasing distributed lock."""
        mock_redis.delete.return_value = 1

        result = await redis_store.release_lock("test-action")

        assert result is True

    @pytest.mark.asyncio
    async def test_set_status_with_lock_contention(self, redis_store, mock_redis):
        """Test handling lock contention during set_status."""
        mock_redis.get.return_value = None
        mock_redis.set.return_value = False  # Lock acquisition fails

        with pytest.raises(RuntimeError, match="being modified by another process"):
            await redis_store.set_status(
                action_id="test-action",
                status=ActionStatus.PENDING,
                user="admin",
            )


class TestRedisApprovalHistory:
    """Test RedisApprovalHistory functionality."""

    @pytest.mark.asyncio
    async def test_add_event(self, redis_history, mock_redis):
        """Test adding event to history."""
        event = {
            "action_id": "action-1",
            "status": "approved",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        mock_redis.lpush.return_value = 1

        result = await redis_history.add(event)

        assert result is True
        mock_redis.lpush.assert_called()

    @pytest.mark.asyncio
    async def test_get_for_action(self, redis_history, mock_redis):
        """Test getting history for specific action."""
        # Note: lpush adds to front, so order is reversed
        # We return approved first because it was "lpush"ed last
        events = [
            json.dumps({"action_id": "action-1", "status": "approved"}),
            json.dumps({"action_id": "action-1", "status": "pending"}),
        ]
        mock_redis.lrange.return_value = events

        result = await redis_history.get_for_action("action-1")

        assert len(result) == 2
        assert result[0]["status"] == "approved"  # Newest first
        assert result[1]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_get_recent(self, redis_history, mock_redis):
        """Test getting recent events."""
        events = [
            json.dumps({"id": "event-1"}),
            json.dumps({"id": "event-2"}),
        ]
        mock_redis.lrange.return_value = events

        result = await redis_history.get_recent(limit=10)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_entries_property(self, redis_history, mock_redis):
        """Test entries property (async)."""
        events = [
            json.dumps({"id": "event-1"}),
        ]
        mock_redis.lrange.return_value = events

        result = await redis_history.entries

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_clear_history(self, redis_history, mock_redis):
        """Test clearing all history."""
        async def mock_scan_iter(match):
            yield "approval:history:events"
            yield "approval:history:action:action1"

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.delete.return_value = 2

        result = await redis_history.clear()

        assert result is True


class TestRedisApprovalStoreIntegration:
    """Integration tests for Redis approval store (require actual Redis)."""

    @pytest.mark.skip(reason="Requires actual Redis instance")
    @pytest.mark.asyncio
    async def test_real_redis_connection(self):
        """Test with real Redis connection (skip in CI)."""


@pytest.mark.asyncio
async def test_redis_store_backward_compatibility():
    """Test that file-based and Redis-based stores have compatible interfaces."""
    from app.approvals.redis_store import RedisApprovalHistory, RedisApprovalStore
    from app.approvals.store import ApprovalHistory, ApprovalStateTracker

    # Both stores should have similar methods
    redis_store_attrs = set(dir(RedisApprovalStore("localhost", 6379, None, 1)))
    file_store_attrs = set(dir(ApprovalStateTracker(use_redis=False)))

    # Common methods that should exist in both
    common_methods = {"get", "delete", "get_all", "get_by_status"}
    assert common_methods.issubset(redis_store_attrs)
    assert common_methods.issubset(file_store_attrs)

    # History stores
    redis_history_attrs = set(dir(RedisApprovalHistory("localhost", 6379, None, 1)))
    file_history_attrs = set(dir(ApprovalHistory()))

    common_history_methods = {"add", "get_for_action", "get_recent"}
    assert common_history_methods.issubset(redis_history_attrs)
    assert common_history_methods.issubset(file_history_attrs)
