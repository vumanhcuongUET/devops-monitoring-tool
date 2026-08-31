"""
Unit tests for the shared Redis store base (app.redis_store_base).

These run without a live Redis server: the client is replaced by a small
in-memory fake, so key building, locking, serialization, and the locked
read-modify-write cycle are exercised directly.
"""

import json
from unittest.mock import patch

import pytest

from app.alerting.redis_store import RedisAlertHistory, RedisAlertStore
from app.approvals.redis_store import RedisApprovalHistory, RedisApprovalStore
from app.redis_store_base import LOCK_ATTEMPTS, LOCK_BACKOFF_BASE, LOCK_VALUE


class FakeRedis:
    """Minimal in-memory async Redis client (strings + lists + scan/mget)."""

    def __init__(self):
        self.data: dict = {}
        self.ttls: dict = {}
        self.list_trims: list = []
        self.closed = False

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return False
        self.data[key] = value
        self.ttls[key] = ex
        return True

    async def setex(self, key, seconds, value):
        self.data[key] = value
        self.ttls[key] = seconds
        return True

    async def delete(self, *keys):
        deleted = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                self.ttls.pop(key, None)
                deleted += 1
        return deleted

    async def expire(self, key, seconds):
        self.ttls[key] = seconds
        return True

    async def lpush(self, key, value):
        self.data.setdefault(key, []).insert(0, value)
        return len(self.data[key])

    async def ltrim(self, key, start, stop):
        entries = self.data.get(key, [])
        end = len(entries) if stop == -1 else stop + 1
        self.data[key] = entries[start:end]
        self.list_trims.append((key, start, stop))
        return True

    async def lrange(self, key, start, stop):
        entries = self.data.get(key, [])
        end = len(entries) if stop == -1 else stop + 1
        return entries[start:end]

    async def mget(self, keys):
        return [self.data.get(key) for key in keys]

    async def scan_iter(self, match=None):
        import fnmatch
        for key in list(self.data):
            if match is None or fnmatch.fnmatch(key, match):
                yield key

    async def close(self):
        self.closed = True


def make_store(cls, **kwargs):
    """Instantiate a store wired to a FakeRedis client (no server needed)."""
    fake = FakeRedis()
    with patch("redis.asyncio.Redis", return_value=fake):
        store = cls(**kwargs)
    store.redis = fake
    return store, fake


@pytest.fixture
def approval_store():
    return make_store(RedisApprovalStore, redis_db=1)


@pytest.fixture
def alert_store():
    return make_store(RedisAlertStore, redis_db=0)


# ---------------------------------------------------------------------------
# Construction / client wiring
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_default_ctor_params_differ_per_domain(self):
        with patch("redis.asyncio.Redis") as mock_redis_cls:
            RedisApprovalStore()
            approval_kwargs = mock_redis_cls.call_args.kwargs
            mock_redis_cls.reset_mock()
            RedisAlertStore()
            alert_kwargs = mock_redis_cls.call_args.kwargs

        # Separate DB per domain, shared client options
        assert approval_kwargs["db"] == 1
        assert alert_kwargs["db"] == 0
        for kwargs in (approval_kwargs, alert_kwargs):
            assert kwargs["decode_responses"] is True
            assert kwargs["socket_connect_timeout"] == 5
            assert kwargs["socket_timeout"] == 5

    def test_history_client_has_socket_timeouts(self):
        """Phase 15: history writes run inside request/execution paths — a
        stuck socket must raise, not hang the loop (was: no timeouts)."""
        with patch("redis.asyncio.Redis") as mock_redis_cls:
            RedisAlertHistory()
        kwargs = mock_redis_cls.call_args.kwargs
        assert kwargs["decode_responses"] is True
        assert kwargs["socket_connect_timeout"] == 5
        assert kwargs["socket_timeout"] == 5

    def test_ttl_defaults_are_domain_specific(self):
        approvals, _ = make_store(RedisApprovalStore)
        alerts, _ = make_store(RedisAlertStore)
        assert approvals.ttl_seconds == 604800  # 7 days
        assert alerts.ttl_seconds == 86400  # 24 hours
        assert approvals.lock_ttl == alerts.lock_ttl == 30

    def test_history_retention_converted_to_seconds(self):
        history, _ = make_store(RedisApprovalHistory, max_entries=50, retention_days=3)
        assert history.max_entries == 50
        assert history.retention_seconds == 3 * 86400

    def test_import_error_when_redis_package_missing(self, monkeypatch):
        import app.redis_store_base as base

        monkeypatch.setattr(base, "REDIS_AVAILABLE", False)
        with pytest.raises(ImportError, match="RedisApprovalStore"):
            RedisApprovalStore()
        with pytest.raises(ImportError, match="RedisAlertHistory"):
            RedisAlertHistory()


# ---------------------------------------------------------------------------
# Key building
# ---------------------------------------------------------------------------


class TestKeyBuilding:
    def test_state_and_lock_keys_use_domain_namespace(self, approval_store, alert_store):
        approvals, _ = approval_store
        alerts, _ = alert_store
        assert approvals._state_key("a1") == "approval:state:a1"
        assert approvals._lock_key("a1") == "approval:lock:a1"
        assert alerts._state_key("r1") == "alert:state:r1"
        assert alerts._lock_key("r1") == "alert:lock:r1"

    def test_history_keys_keep_domain_names(self):
        approval_history, _ = make_store(RedisApprovalHistory)
        alert_history, _ = make_store(RedisAlertHistory)
        assert approval_history.global_history_key == "approval:history:events"
        assert alert_history.history_key == "alert:history:events"


# ---------------------------------------------------------------------------
# Locking (SET NX EX + DEL — no Lua in either implementation)
# ---------------------------------------------------------------------------


class TestLocking:
    async def test_acquire_lock_issues_set_nx_ex(self, approval_store):
        store, fake = approval_store
        assert await store.acquire_lock("a1") is True
        assert fake.data["approval:lock:a1"] == LOCK_VALUE
        assert fake.ttls["approval:lock:a1"] == 30

    async def test_acquire_lock_honors_custom_ttl(self, alert_store):
        store, fake = alert_store
        assert await store.acquire_lock("r1", ttl=5) is True
        assert fake.ttls["alert:lock:r1"] == 5

    async def test_acquire_lock_fails_when_held(self, approval_store):
        store, fake = approval_store
        assert await store.acquire_lock("a1") is True
        assert await store.acquire_lock("a1") is False

    async def test_release_lock_deletes_key(self, approval_store):
        store, fake = approval_store
        await store.acquire_lock("a1")
        assert await store.release_lock("a1") is True
        assert "approval:lock:a1" not in fake.data

    async def test_lock_acquisition_error_returns_false(self, approval_store):
        store, fake = approval_store

        async def boom(*args, **kwargs):
            raise ConnectionError("down")

        fake.set = boom
        assert await store.acquire_lock("a1") is False

    async def test_update_retries_with_backoff_then_raises(self, alert_store, monkeypatch):
        store, fake = alert_store
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr("app.redis_store_base.asyncio.sleep", fake_sleep)
        # Pre-hold the lock so every SET NX fails
        fake.data["alert:lock:r1"] = LOCK_VALUE

        with pytest.raises(RuntimeError) as exc:
            await store.set_firing("r1")

        # One exponential backoff sleep after every failed attempt (original behaviour)
        assert len(sleeps) == LOCK_ATTEMPTS
        assert sleeps == [LOCK_BACKOFF_BASE * (2 ** i) for i in range(LOCK_ATTEMPTS)]
        message = str(exc.value)
        assert "alert r1" in message
        assert "being modified by another process" in message
        # The state key must be untouched when the lock is never acquired
        assert "alert:state:r1" not in fake.data


# ---------------------------------------------------------------------------
# Locked read-modify-write
# ---------------------------------------------------------------------------


class TestLockedUpdate:
    async def test_new_state_uses_domain_initial_schema(self, alert_store):
        store, fake = alert_store
        state = await store.set_breached("r1")

        assert state["rule_id"] == "r1"
        assert state["status"] == "pending"
        assert state["first_breached_at"] is not None
        assert state["fired_at"] is None
        assert state["resolved_at"] is None
        assert state["last_breached_at"] is not None

    async def test_existing_state_is_merged_not_replaced(self, alert_store):
        store, fake = alert_store
        await store.set_breached("r1")
        state = await store.set_firing("r1")

        assert state["status"] == "firing"
        assert state["fired_at"] is not None
        # Initial fields survive subsequent updates
        assert state["first_breached_at"] is not None
        assert state["rule_id"] == "r1"

    async def test_state_persisted_with_domain_ttl_and_released(self, alert_store):
        store, fake = alert_store
        await store.set_firing("r1")

        assert json.loads(fake.data["alert:state:r1"])["status"] == "firing"
        assert fake.ttls["alert:state:r1"] == 86400
        # Lock always released after the update
        assert "alert:lock:r1" not in fake.data

    async def test_lock_released_even_when_apply_fails(self, approval_store):
        store, fake = approval_store

        def explode(state):
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await store._locked_update("a1", dict, explode)

        assert "approval:lock:a1" not in fake.data
        assert "approval:state:a1" not in fake.data

    async def test_approval_serialization_uses_default_str(self, approval_store):
        from datetime import datetime, timezone

        store, fake = approval_store
        await store.set_status(action_id="a1", status="approved", user="admin")
        # default=str keeps the ActionStatus enum serializable
        assert json.loads(fake.data["approval:state:a1"])["status"] == "approved"
        # broadcast-style datetime payload also survives approval serialization
        assert store._serialize_state({"ts": datetime.now(timezone.utc)})  # no raise


# ---------------------------------------------------------------------------
# Scan-all (robust bulk read)
# ---------------------------------------------------------------------------


class TestScanAllStates:
    async def test_states_keyed_by_entity_id(self, approval_store):
        store, fake = approval_store
        await store.set_status(action_id="a1", status="pending", user="u")
        await store.set_status(action_id="a2", status="approved", user="u")

        result = await store.get_all()

        assert set(result) == {"a1", "a2"}
        assert result["a1"]["action_id"] == "a1"

    async def test_malformed_entries_are_skipped_not_fatal(self, alert_store):
        store, fake = alert_store
        fake.data["alert:state:good"] = json.dumps({"rule_id": "good", "status": "firing"})
        fake.data["alert:state:bad"] = "{not json"

        result = await store.get_all_state()

        assert set(result) == {"good"}

    async def test_empty_db_returns_empty_dict(self, alert_store):
        store, _ = alert_store
        assert await store.get_all_state() == {}


# ---------------------------------------------------------------------------
# History lists
# ---------------------------------------------------------------------------


class TestHistory:
    async def test_append_pushes_trims_and_sets_ttl(self, alert_store):
        history, fake = make_store(RedisAlertHistory, max_entries=10, retention_days=2)
        event = {"id": "e1", "status": "firing"}

        assert await history.add(event) is True

        assert fake.data["alert:history:events"] == [json.dumps(event)]
        assert fake.list_trims == [("alert:history:events", 0, 9)]
        assert fake.ttls["alert:history:events"] == 2 * 86400

    async def test_approval_history_also_writes_per_action_list(self):
        history, fake = make_store(RedisApprovalHistory, max_entries=10, retention_days=2)
        event = {"action_id": "a1", "status": "approved"}

        assert await history.add(event) is True

        assert "approval:history:events" in fake.data
        assert "approval:history:action:a1" in fake.data
        # Events without an action_id only go to the global list
        assert await history.add({"status": "pending"}) is True
        assert len(fake.data["approval:history:events"]) == 2

    async def test_read_entries_newest_first_and_skips_malformed(self):
        history, fake = make_store(RedisApprovalHistory)
        await history.add({"action_id": "a1", "n": 1})
        await history.add({"action_id": "a1", "n": 2})
        fake.data["approval:history:action:a1"].append("{broken")

        entries = await history.get_for_action("a1")

        assert [e["n"] for e in entries] == [2, 1]

    async def test_get_entries_limit_maps_to_lrange_end(self):
        history, fake = make_store(RedisAlertHistory)
        await history.add({"n": 1})
        await history.add({"n": 2})

        limited = await history.get_entries(limit=1)
        all_entries = await history.get_entries()

        assert [e["n"] for e in limited] == [2]
        assert [e["n"] for e in all_entries] == [2, 1]

    async def test_redis_error_returns_empty_list_not_raise(self):
        history, fake = make_store(RedisAlertHistory)

        async def boom(*args, **kwargs):
            raise ConnectionError("down")

        fake.lrange = boom
        assert await history.get_entries() == []


# ---------------------------------------------------------------------------
# Close
# ---------------------------------------------------------------------------


class TestClose:
    async def test_close_closes_client(self, alert_store):
        store, fake = alert_store
        await store.close()
        assert fake.closed is True

    async def test_close_swallows_errors(self, alert_store):
        store, fake = alert_store

        async def boom():
            raise ConnectionError("down")

        fake.close = boom
        await store.close()  # must not raise
