"""Unit tests for the H1 Redis leader lock (Phase 12)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.alerting.leader import RedisLeaderLock, run_as_leader


def _lock(client) -> RedisLeaderLock:
    return RedisLeaderLock("test", ttl=30, renew_interval=0.01, client=client)


@pytest.mark.asyncio
async def test_try_acquire_success_and_conflict():
    client = MagicMock()
    client.set = AsyncMock(side_effect=[True, None])  # first wins, second conflicts
    lock = _lock(client)

    assert await lock.try_acquire() is True
    assert await lock.try_acquire() is False
    client.set.assert_awaited_with("leader:test", lock._identity, nx=True, px=30_000)


@pytest.mark.asyncio
async def test_try_acquire_redis_down_returns_false():
    client = MagicMock()
    client.set = AsyncMock(side_effect=ConnectionError("redis down"))
    lock = _lock(client)

    assert await lock.try_acquire() is False


@pytest.mark.asyncio
async def test_renew_owned_and_not_owned():
    client = MagicMock()
    client.eval = AsyncMock(side_effect=[1, 0])
    lock = _lock(client)

    assert await lock.renew() is True   # still owner
    assert await lock.renew() is False  # lock taken/expired elsewhere
    args = client.eval.await_args_list[0].args
    assert args[0].strip().startswith("if redis.call('get'")
    assert args[1] == 1 and args[2] == "leader:test" and args[3] == lock._identity
    assert args[4] == 30_000


@pytest.mark.asyncio
async def test_renew_error_returns_false():
    client = MagicMock()
    client.eval = AsyncMock(side_effect=ConnectionError("redis down"))
    lock = _lock(client)

    assert await lock.renew() is False


@pytest.mark.asyncio
async def test_release_owned_only():
    client = MagicMock()
    client.eval = AsyncMock(return_value=1)
    lock = _lock(client)

    await lock.release()
    args = client.eval.await_args.args
    assert "del" in args[0] and args[2] == "leader:test" and args[3] == lock._identity


class FakeLock:
    """Controllable lock for run_as_leader tests. Every fake await yields to
    the event loop so cancellation can always be delivered."""

    key = "leader:test"
    renew_interval = 0.01

    def __init__(self, acquire_results, renew_results):
        self._acquire = list(acquire_results)
        self._renew = list(renew_results)
        self.released = False

    async def try_acquire(self):
        await asyncio.sleep(0)
        if self._acquire:
            return self._acquire.pop(0)
        return False

    async def renew(self):
        await asyncio.sleep(0)
        if self._renew:
            return self._renew.pop(0)
        return False

    async def release(self):
        self.released = True


async def _run_and_cancel(lock, started, monkeypatch=None):
    async def engine():
        started.append(1)
        await asyncio.sleep(3600)

    wrapper = asyncio.create_task(run_as_leader("t", engine, lock))
    await asyncio.sleep(0.05)
    wrapper.cancel()
    with pytest.raises(asyncio.CancelledError):
        await wrapper


@pytest.mark.asyncio
async def test_leads_then_stops_engine_on_lock_loss(monkeypatch):
    """Engine runs while leader; cancelled + lock released on leadership loss,
    then the wrapper parks in the (cancellable) acquire retry sleep."""
    monkeypatch.setattr("app.alerting.leader.ACQUIRE_RETRY_SECONDS", 0.01)
    lock = FakeLock(acquire_results=[True, False], renew_results=[True])
    started = []

    await _run_and_cancel(lock, started)

    assert started == [1]
    assert lock.released is True


@pytest.mark.asyncio
async def test_polls_until_acquired_then_leads(monkeypatch):
    """First acquire attempt fails; the engine only runs once leadership is
    actually won."""
    monkeypatch.setattr("app.alerting.leader.ACQUIRE_RETRY_SECONDS", 0.01)
    lock = FakeLock(acquire_results=[False, True, False], renew_results=[True])
    started = []

    await _run_and_cancel(lock, started)

    assert started == [1]
    assert lock.released is True
