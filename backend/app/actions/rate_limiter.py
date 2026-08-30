"""Rate limiter for action execution with time-window tracking."""

import json
import logging
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.actions.chain_monitor import get_chain_monitor
from app.config import settings

logger = logging.getLogger(__name__)

# Persisted state file for the autonomous rate limiter (under settings.DATA_DIR)
AUTONOMOUS_RATE_LIMIT_FILE = "autonomous_rate_limit.json"


@dataclass
class ActionRecord:
    """Record of an action execution."""
    timestamp: float
    action_type: str
    project: str
    user: str | None = None


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    max_actions_per_hour: int = 3  # Max actions per hour per type
    cooldown_seconds: int = 300  # 5 minutes cooldown between same action type
    time_window_seconds: int = 3600  # 1 hour rolling window
    emergency_bypass: bool = False  # Allow bypassing for emergencies
    max_chain_length: int = 3  # Maximum consecutive actions of same type (action chaining prevention)
    chain_break_seconds: int = 600  # 10 minutes - time before chain counter resets


class RateLimiter:
    """Rate limiter with time-window tracking for autonomous actions."""

    def __init__(self, config: RateLimitConfig | None = None):
        """Initialize the rate limiter.

        Args:
            config: Rate limit configuration. Defaults to sensible defaults.
        """
        self.config = config or RateLimitConfig()

        # Store action history: key = (project, action_type)
        # value = list of ActionRecord
        self._action_history: dict[tuple, list[ActionRecord]] = defaultdict(list)

        # Track last action timestamp per (project, action_type) for cooldown
        self._last_action: dict[tuple, float] = {}

        # Track consecutive actions for chain detection
        # key = (project, action_type)
        # value = count of consecutive actions
        self._consecutive_actions: dict[tuple, int] = {}

        # Track last chain break time
        self._last_chain_break: dict[tuple, float] = {}

        # Chain monitor for alerts (Phase 8 Day 6)
        self._chain_monitor = get_chain_monitor()

    def check(
        self,
        project: str,
        action_type: str,
        user: str | None = None,
    ) -> tuple[bool, str, dict]:
        """Check if action is allowed under rate limits.

        Args:
            project: Project name
            action_type: Type of action (e.g., "restart", "scale", "delete")
            user: Optional user identifier

        Returns:
            Tuple of (allowed, reason, metadata)
            - allowed: bool indicating if action is permitted
            - reason: str explaining why
            - metadata: dict with rate limit status (remaining, reset_time, etc.)
        """
        # Emergency bypass
        if self.config.emergency_bypass:
            return True, "Emergency bypass active", self._get_metadata(
                project, action_type, bypass=True
            )

        key = (project, action_type)
        now = time.time()

        # Clean old records outside the time window
        self._cleanup_old_records(key, now)

        # Get current action count in window
        action_count = len(self._action_history[key])

        # Check cooldown period
        last_action_time = self._last_action.get(key, 0)
        if last_action_time > 0:
            elapsed = now - last_action_time
            if elapsed < self.config.cooldown_seconds:
                remaining = self.config.cooldown_seconds - elapsed
                return False, f"Cooldown active. Wait {int(remaining)}s before next action", self._get_metadata(
                    project, action_type, remaining=0, reset_time=int(now + remaining)
                )

        # Check action chaining (consecutive actions of same type)
        chain_count = self._consecutive_actions.get(key, 0)
        last_chain_break = self._last_chain_break.get(key, 0)

        # Reset chain counter if enough time has passed since last action
        if last_chain_break > 0 and (now - last_chain_break) >= self.config.chain_break_seconds:
            self._consecutive_actions[key] = 0
            chain_count = 0  # Reset local counter as well

        # Trigger chain monitor for alerting (Phase 8 Day 6)
        # Check chain status and trigger alerts if approaching or at limit
        _chain_event = self._chain_monitor.check_chain(
            project=project,
            action_type=action_type,
            chain_count=chain_count,
            chain_limit=self.config.max_chain_length,
            user=user,
        )

        # Check if chain limit would be exceeded
        if chain_count >= self.config.max_chain_length:
            # Calculate time until chain break
            time_since_last = now - last_chain_break if last_chain_break else 0
            remaining_break = max(0, self.config.chain_break_seconds - time_since_last)
            return False, f"Action chain limit reached. Wait {int(remaining_break)}s before next action", self._get_metadata(
                project, action_type, remaining=0, reset_time=int(now + remaining_break)
            )

        # Check rate limit
        if action_count >= self.config.max_actions_per_hour:
            # Calculate reset time (oldest action + window)
            oldest = self._action_history[key][0].timestamp
            reset_time = oldest + self.config.time_window_seconds
            remaining = int(reset_time - now)

            return False, f"Rate limit exceeded. Maximum {self.config.max_actions_per_hour} actions per hour", self._get_metadata(
                project, action_type, remaining=0, reset_time=reset_time
            )

        # Action is allowed
        remaining = self.config.max_actions_per_hour - action_count - 1
        return True, "Rate limit check passed", self._get_metadata(
            project, action_type, remaining=max(0, remaining)
        )

    def record_action(
        self,
        project: str,
        action_type: str,
        user: str | None = None,
    ) -> None:
        """Record that an action was executed.

        Args:
            project: Project name
            action_type: Type of action
            user: Optional user identifier
        """
        key = (project, action_type)
        now = time.time()

        # Record the action
        record = ActionRecord(
            timestamp=now,
            action_type=action_type,
            project=project,
            user=user,
        )
        self._action_history[key].append(record)

        # Update last action time
        self._last_action[key] = now

        # Update consecutive action counter for chain detection
        current_chain = self._consecutive_actions.get(key, 0)
        self._consecutive_actions[key] = current_chain + 1

        # Update last chain break time
        self._last_chain_break[key] = now

    def _cleanup_old_records(self, key: tuple, now: float) -> None:
        """Remove records outside the time window."""
        if key not in self._action_history:
            return

        cutoff = now - self.config.time_window_seconds
        self._action_history[key] = [
            r for r in self._action_history[key]
            if r.timestamp > cutoff
        ]

    def _get_metadata(
        self,
        project: str,
        action_type: str,
        remaining: int | None = None,
        reset_time: float | None = None,
        bypass: bool = False,
    ) -> dict:
        """Get rate limit metadata for API responses."""
        key = (project, action_type)
        now = time.time()

        if remaining is None:
            # Calculate remaining from current state
            count = len(self._action_history.get(key, []))
            remaining = max(0, self.config.max_actions_per_hour - count - 1)

        if reset_time is None and not bypass:
            # Calculate reset time from oldest record
            if self._action_history.get(key):
                oldest = self._action_history[key][0].timestamp
                reset_time = oldest + self.config.time_window_seconds
            else:
                reset_time = now + self.config.time_window_seconds

        last_action = self._last_action.get(key, 0)
        cooldown_remaining = max(0, self.config.cooldown_seconds - (now - last_action)) if last_action > 0 else 0

        # Chain information
        chain_count = self._consecutive_actions.get(key, 0)
        last_chain_break = self._last_chain_break.get(key, 0)
        time_since_chain_break = now - last_chain_break if last_chain_break else 0
        chain_break_remaining = max(0, self.config.chain_break_seconds - time_since_chain_break)

        return {
            "limit": self.config.max_actions_per_hour,
            "remaining": remaining,
            "reset": int(reset_time) if reset_time else int(now + self.config.time_window_seconds),
            "reset_datetime": datetime.fromtimestamp(reset_time or now + self.config.time_window_seconds).isoformat(),
            "cooldown_remaining": int(cooldown_remaining),
            "bypass_active": bypass,
            "window_seconds": self.config.time_window_seconds,
            "chain_count": chain_count,
            "chain_limit": self.config.max_chain_length,
            "chain_break_remaining": int(chain_break_remaining),
        }

    def get_action_history(
        self,
        project: str,
        action_type: str | None = None,
        limit: int = 100,
    ) -> list[ActionRecord]:
        """Get historical action records.

        Args:
            project: Project name
            action_type: Optional filter by action type
            limit: Maximum records to return

        Returns:
            List of action records, most recent first
        """
        records = []

        for key, action_records in self._action_history.items():
            key_project, key_action = key

            if key_project != project:
                continue

            if action_type and key_action != action_type:
                continue

            records.extend(action_records)

        # Sort by timestamp descending
        records.sort(key=lambda r: r.timestamp, reverse=True)

        return records[:limit]

    def get_stats(self, project: str) -> dict:
        """Get rate limiting statistics for a project.

        Args:
            project: Project name

        Returns:
            Statistics dictionary
        """
        now = time.time()
        stats = {
            "project": project,
            "action_types": {},
            "total_actions": 0,
            "active_windows": 0,
        }

        for key, records in self._action_history.items():
            key_project, key_action = key

            if key_project != project:
                continue

            # Clean up first
            self._cleanup_old_records(key, now)

            if not records:
                continue

            stats["active_windows"] += 1
            stats["total_actions"] += len(records)
            stats["action_types"][key_action] = {
                "count": len(records),
                "last_action": datetime.fromtimestamp(self._last_action.get(key, 0)).isoformat(),
                "remaining": max(0, self.config.max_actions_per_hour - len(records)),
            }

        return stats

    def reset(self, project: str | None = None, action_type: str | None = None) -> None:
        """Reset rate limiting state.

        Args:
            project: Optional project filter. If None, resets all projects.
            action_type: Optional action type filter. If None, resets all types.
        """
        keys_to_remove = []

        for key in self._action_history.keys():
            key_project, key_action = key

            if project and key_project != project:
                continue

            if action_type and key_action != action_type:
                continue

            keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._action_history[key]
            if key in self._last_action:
                del self._last_action[key]
            if key in self._consecutive_actions:
                del self._consecutive_actions[key]
            if key in self._last_chain_break:
                del self._last_chain_break[key]

    def update_config(self, config: RateLimitConfig) -> None:
        """Update rate limiting configuration.

        Args:
            config: New configuration to apply
        """
        self.config = config


# Global singleton instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter(config: RateLimitConfig | None = None) -> RateLimiter:
    """Get or create the global RateLimiter instance.

    Args:
        config: Optional configuration to use on first creation

    Returns:
        The RateLimiter singleton instance
    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(config)
    elif config:
        _rate_limiter.update_config(config)
    return _rate_limiter


class _AutonomousRateStateStore:
    """File-backed persistence for :class:`AutonomousRateLimiter`.

    Phase 14 residual 3: autonomous rate-limit windows used to be in-memory
    only, so a restart reset the quota mid-incident. State lives in a single
    JSON file under ``settings.DATA_DIR``; it is loaded lazily, pruned to the
    1h window, and written atomically (tmp file + :func:`os.replace`).

    All callers run on the event-loop thread where sync sections cannot
    interleave; one plain lock keeps the read-modify-write atomic if a
    thread runner is ever used. I/O failures degrade to in-memory limiting
    (logged warning) — they must never block remediation paths.
    """

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()

    def load(self) -> tuple[dict[str, list[datetime]], dict[str, datetime]]:
        """Return ``(execution_times, last_executions)`` from disk.

        Entries older than the 1h window are pruned on load. A missing,
        corrupt, or unreadable file yields empty state (warning logged) so a
        bad state file can only loosen history, never crash the executor.
        """
        with self._lock:
            try:
                raw = json.loads(self._path.read_text())
            except FileNotFoundError:
                return defaultdict(list), {}
            except (OSError, ValueError) as e:
                logger.warning("Autonomous rate-limit state unreadable (%s); starting empty", e)
                return defaultdict(list), {}

        if not isinstance(raw, dict):
            logger.warning("Autonomous rate-limit state has unexpected shape; starting empty")
            return defaultdict(list), {}

        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        execution_times: dict[str, list[datetime]] = defaultdict(list)
        for action_type, stamps in (raw.get("execution_times") or {}).items():
            if not isinstance(stamps, list):
                continue
            times = sorted(t for ts in stamps if (t := self._parse(ts)) and t > cutoff)
            if times:
                execution_times[action_type] = times

        last_executions: dict[str, datetime] = {}
        for action_type, ts in (raw.get("last_executions") or {}).items():
            if (t := self._parse(ts)) and t > cutoff:
                last_executions[action_type] = t

        return execution_times, last_executions

    def save(
        self,
        execution_times: dict[str, list[datetime]],
        last_executions: dict[str, datetime],
    ) -> None:
        """Persist both maps atomically (tmp file + os.replace)."""
        payload = {
            "execution_times": {
                action_type: [t.isoformat() for t in sorted(times)]
                for action_type, times in execution_times.items()
                if times
            },
            "last_executions": {
                action_type: t.isoformat() for action_type, t in last_executions.items()
            },
        }
        with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self._path.with_name(self._path.name + ".tmp")
                tmp.write_text(json.dumps(payload))
                os.replace(tmp, self._path)
            except OSError as e:
                logger.warning(
                    "Failed to persist autonomous rate-limit state (%s); "
                    "in-memory limits remain active", e,
                )

    @staticmethod
    def _parse(ts: object) -> datetime | None:
        if not isinstance(ts, str):
            return None
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class AutonomousRateLimiter:
    """Rate limiter for autonomous actions.

    Prevents runaway autonomous execution by limiting actions per time window.
    Execution timestamps and the per-type cooldown map survive restarts via
    the file-backed store (Phase 14 residual 3); the public interface is
    unchanged. A Redis-backed store (``settings.RATE_LIMIT_USE_REDIS``) is
    deliberately not wired here: this interface is synchronous and the shared
    Redis client (``app.redis_client.get_redis``) is async — bridging them
    would mean blocking calls or an interface break.
    """

    def __init__(self, max_per_hour: int = 3, state_file: Path | None = None):
        """Initialize rate limiter.

        Args:
            max_per_hour: Maximum actions per hour per action type
            state_file: Override for the persisted-state path (defaults to
                ``settings.DATA_DIR/autonomous_rate_limit.json``)
        """
        self.max_per_hour = max_per_hour
        self._execution_times: dict[str, list[datetime]] = defaultdict(list)
        # Last successful execution per action type (cooldown map) — the same
        # data AutonomousExecutor._last_executions holds, persisted together.
        self._last_executions: dict[str, datetime] = {}
        self._store = _AutonomousRateStateStore(
            state_file or Path(settings.DATA_DIR) / AUTONOMOUS_RATE_LIMIT_FILE
        )
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Lazily hydrate state from disk on first use (not in __init__, so
        constructing the limiter never touches the filesystem)."""
        if self._loaded:
            return
        self._execution_times, self._last_executions = self._store.load()
        self._loaded = True

    def _prune(self, now: datetime) -> None:
        """Drop entries outside the 1h rolling window from both maps."""
        hour_ago = now - timedelta(hours=1)
        for action_type, times in self._execution_times.items():
            self._execution_times[action_type] = [t for t in times if t > hour_ago]
        self._last_executions = {
            a: t for a, t in self._last_executions.items() if t > hour_ago
        }

    def can_execute(self, action_type: str) -> tuple[bool, str | None]:
        """Check if action can be executed based on rate limit.

        Args:
            action_type: Type of remediation action

        Returns:
            Tuple of (allowed, reason_if_not_allowed)
        """
        self._ensure_loaded()
        now = datetime.now(timezone.utc)

        # Clean old entries
        self._prune(now)

        # Check limit
        if len(self._execution_times[action_type]) >= self.max_per_hour:
            return False, f"Rate limit exceeded: {len(self._execution_times[action_type])} executions in last hour"

        return True, None

    def record_execution(self, action_type: str):
        """Record an action execution for rate limiting.

        Also updates the cooldown map and persists both to disk.

        Args:
            action_type: Type of remediation action
        """
        self._ensure_loaded()
        now = datetime.now(timezone.utc)
        self._execution_times[action_type].append(now)
        self._last_executions[action_type] = now
        self._prune(now)
        self._store.save(self._execution_times, self._last_executions)

    def get_remaining_quota(self, action_type: str) -> int:
        """Get remaining execution quota for an action type.

        Args:
            action_type: Type of remediation action

        Returns:
            Number of remaining executions allowed this hour
        """
        self._ensure_loaded()
        self._prune(datetime.now(timezone.utc))
        return max(0, self.max_per_hour - len(self._execution_times[action_type]))

    def get_last_execution(self, action_type: str) -> datetime | None:
        """Get the last recorded execution time for an action type.

        Args:
            action_type: Type of remediation action

        Returns:
            Last execution datetime (UTC), or None if none in the window
        """
        self._ensure_loaded()
        return self._last_executions.get(action_type)

    @property
    def last_executions(self) -> dict[str, datetime]:
        """Copy of the persisted cooldown map (per action type)."""
        self._ensure_loaded()
        return dict(self._last_executions)
