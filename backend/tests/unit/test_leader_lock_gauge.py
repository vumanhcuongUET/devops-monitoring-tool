"""Contract tests for the leader_lock_up gauge (SA finding B).

The gauge is the only series that answers "is a replica actually running the
alert engine?". These tests pin the setter contract (1 on success, 0 on
failure/release) and the 5-minute failure-streak WARNING, by driving the
update path directly with fake outcomes — no Redis needed.
"""
import logging
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import REGISTRY

from app.alerting.leader import LEADER_STREAK_WARN_SECONDS, RedisLeaderLock


def _gauge(lock: RedisLeaderLock) -> float | None:
    return REGISTRY.get_sample_value("leader_lock_up", {"lock": lock.key})


def _lock(name: str, client=None) -> RedisLeaderLock:
    # Fresh, unique lock name per test -> its own gauge series -> no
    # cross-test pollution in the shared default REGISTRY.
    return RedisLeaderLock(name, ttl=30, renew_interval=0.01, client=client)


def test_gauge_setter_flips_on_success_and_failure():
    lock = _lock("gauge-setter", client=object())

    lock._record_lock_state(True)
    assert _gauge(lock) == 1

    lock._record_lock_state(False)
    assert _gauge(lock) == 0

    lock._record_lock_state(True)
    assert _gauge(lock) == 1


def test_gauge_setter_warns_when_streak_exceeds_five_minutes(caplog):
    lock = _lock("gauge-streak", client=object())
    lock._record_lock_state(False)  # starts the streak
    # age it past the threshold, as if Redis had been down for >5 minutes
    lock._failure_streak_started = time.monotonic() - (LEADER_STREAK_WARN_SECONDS + 60)

    with caplog.at_level(logging.WARNING, logger="app.alerting.leader"):
        lock._record_lock_state(False)

    assert _gauge(lock) == 0
    assert any(
        "acquire/renew failing" in r.getMessage() and lock.key in r.getMessage()
        for r in caplog.records
    )


def test_gauge_setter_resets_streak_on_success(caplog):
    """A recovery clears the clock: the next failure starts a fresh streak."""
    lock = _lock("gauge-recover", client=object())
    lock._record_lock_state(False)
    lock._failure_streak_started = time.monotonic() - (LEADER_STREAK_WARN_SECONDS + 1)

    with caplog.at_level(logging.WARNING, logger="app.alerting.leader"):
        lock._record_lock_state(True)  # recovered before the warning fired
        lock._record_lock_state(False)  # new streak, far below the threshold

    assert _gauge(lock) == 0
    assert not any("acquire/renew failing" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_acquire_renew_release_drive_the_gauge():
    """The lock lifecycle methods keep the gauge honest end to end."""
    client = MagicMock()
    client.set = AsyncMock(side_effect=[True, None])  # win, then conflict
    lock = _lock("gauge-wiring", client=client)

    await lock.try_acquire()
    assert _gauge(lock) == 1
    await lock.try_acquire()
    assert _gauge(lock) == 0

    client.eval = AsyncMock(return_value=1)  # still owner
    await lock.renew()
    assert _gauge(lock) == 1

    client.eval = AsyncMock(side_effect=ConnectionError("redis down"))
    with pytest.raises(ConnectionError):
        await lock.renew()  # errors still propagate for the grace policy
    assert _gauge(lock) == 0

    client.eval = AsyncMock(return_value=1)
    await lock.release()  # release is not a failure, but this pod is not leader
    assert _gauge(lock) == 0
