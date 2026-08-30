"""Redis leader election for in-process background tasks (Phase 12 H1).

The AlertEngine and SloReporter run as asyncio tasks inside FastAPI. With
more than one backend replica, every pod would run its own engine: duplicate
alert evaluations, duplicate notifications, N daily SLO reports.

The lazy fix (no separate alert-worker deployment): every pod starts the
same run_as_leader() wrapper; one pod wins a renewable Redis lock per task
and runs the engine, the others poll. If the leader dies, the lock expires
after the TTL and another pod takes over (detection bounded by the renewal
interval, not the TTL, on a live leader).

Fail-safe direction: if Redis is unreachable, nobody runs the engine
(missed evaluations for the window) rather than everybody running it
(duplicate alerts). Single-replica deployments keep today's behavior by
leaving ALERT_ENGINE_LEADER_LOCK off.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

logger = logging.getLogger(__name__)

LEADER_TTL_SECONDS = 30
RENEW_INTERVAL_SECONDS = 10
ACQUIRE_RETRY_SECONDS = 5
# Transient Redis errors: tolerate this many consecutive renew failures before
# dropping leadership — one timeout must not cancel a healthy engine. Three
# misses (~30s) still expires inside the lock TTL.
MAX_MISSED_RENEWS = 3

# Compare-and-expire: no gap between ownership check and expiry extension,
# so a lock that expired and was re-acquired by another pod can never be
# renewed by the old owner.
_RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('pexpire', KEYS[1], ARGV[2])
end
return 0
"""

# Compare-and-delete: the old owner can never delete a lock it no longer
# owns (e.g. after a long pause let someone else take over).
_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


class RedisLeaderLock:
    """Renewable Redis lock (SET NX PX, Lua compare-and-renew/release)."""

    def __init__(
        self,
        name: str,
        ttl: int = LEADER_TTL_SECONDS,
        renew_interval: int = RENEW_INTERVAL_SECONDS,
        client=None,
    ) -> None:
        self.key = f"leader:{name}"
        self.ttl = ttl
        self.renew_interval = renew_interval
        self._identity = str(uuid.uuid4())
        self._client = client

    def _get_client(self):
        if self._client is None:
            from app.redis_client import get_redis

            self._client = get_redis()
        return self._client

    async def try_acquire(self) -> bool:
        """One acquisition attempt. False also covers Redis errors (fail-safe)."""
        try:
            return bool(
                await self._get_client().set(self.key, self._identity, nx=True, px=self.ttl * 1000)
            )
        except Exception as e:
            logger.warning("Leader lock acquire failed (%s): %s", self.key, e)
            return False

    async def renew(self) -> bool:
        """Extend the lock if and only if we still own it.

        False = ownership genuinely lost (Lua returned 0). Redis errors raise
        so the caller can apply its own grace policy instead of treating a
        transient timeout as leadership loss.
        """
        return bool(
            await self._get_client().eval(
                _RENEW_SCRIPT, 1, self.key, self._identity, self.ttl * 1000
            )
        )

    async def release(self) -> None:
        """Release the lock if and only if we still own it."""
        try:
            await self._get_client().eval(_RELEASE_SCRIPT, 1, self.key, self._identity)
        except Exception as e:
            logger.warning("Leader lock release failed (%s): %s", self.key, e)


async def run_as_leader(
    name: str,
    task_factory,
    lock: RedisLeaderLock,
) -> None:
    """Run task_factory() only while this pod holds the leader lock.

    task_factory is a zero-arg callable returning an awaitable (e.g.
    ``lambda: alert_engine.start(app.state)``) so every (re)acquisition
    starts a fresh engine task; it is cancelled the moment leadership is
    lost. After losing the lock the wrapper releases it (owned-delete) and
    polls to re-acquire.
    """
    while True:
        if not await lock.try_acquire():
            await asyncio.sleep(ACQUIRE_RETRY_SECONDS)
            continue

        logger.info("Leader lock %s acquired by %s", lock.key, name)
        inner = asyncio.create_task(task_factory())
        try:
            missed = 0
            while True:
                try:
                    if not await lock.renew():
                        break  # ownership genuinely lost
                    missed = 0
                except Exception as e:
                    missed += 1
                    logger.warning(
                        "Leader lock renew error (%s), miss %d/%d: %s",
                        lock.key, missed, MAX_MISSED_RENEWS, e,
                    )
                    if missed >= MAX_MISSED_RENEWS:
                        break
                await asyncio.sleep(lock.renew_interval)
        finally:
            inner.cancel()
            try:
                await inner
            except asyncio.CancelledError:
                pass
            await lock.release()

        logger.warning("Leader lock %s lost by %s; retrying", lock.key, name)
        # backoff before re-acquiring: no hot acquire loop after a drop
        await asyncio.sleep(ACQUIRE_RETRY_SECONDS)
