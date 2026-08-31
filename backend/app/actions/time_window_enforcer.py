"""Time window enforcement for restricting action execution to safe hours."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class WindowType(str, Enum):
    """Types of time windows."""
    DAILY = "daily"  # Same hours each day
    WEEKDAYS = "weekdays"  # Monday-Friday only
    WEEKENDS = "weekends"  # Saturday-Sunday only
    CUSTOM = "custom"  # Custom days and times


@dataclass
class SafeHoursWindow:
    """Definition of safe hours for action execution."""
    name: str  # e.g., "business-hours", "maintenance-window"
    description: str
    window_type: WindowType = WindowType.DAILY
    start_hour: int = 9  # Start hour (24-hour format)
    end_hour: int = 17  # End hour (24-hour format)
    timezone: str = "UTC"  # Timezone for the window
    allowed_days: list[int] | None = None  # 0=Monday, 6=Sunday (for CUSTOM type)
    emergency_override: bool = False  # Allow override for emergencies
    environments: list[str] = field(default_factory=lambda: ["production"])  # Which envs apply


@dataclass
class WindowCheckResult:
    """Result of checking if an action is within safe hours."""
    is_allowed: bool
    window_name: str | None = None
    reason: str = ""
    current_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    window_start: time | None = None
    window_end: time | None = None
    next_allowed_time: datetime | None = None
    emergency_override_available: bool = False


class TimeWindowEnforcer:
    """Enforce time window restrictions for action execution.

    This class provides:
    - Time window configuration per environment
    - Safe hours checking before action execution
    - Emergency override capability
    - Timezone-aware scheduling
    """

    def __init__(self):
        """Initialize the time window enforcer."""
        self._windows: dict[str, SafeHoursWindow] = {}
        self._environment_windows: dict[str, str] = {}  # env -> window name

        # Load default windows
        self._load_default_windows()

    def _load_default_windows(self):
        """Load default time window configurations."""
        # Business hours window (9 AM - 5 PM UTC, weekdays)
        business_hours = SafeHoursWindow(
            name="business-hours",
            description="Standard business hours (9 AM - 5 PM UTC, Mon-Fri)",
            window_type=WindowType.WEEKDAYS,
            start_hour=9,
            end_hour=17,
            timezone="UTC",
            allowed_days=list(range(5)),  # Monday-Friday (0-4)
            emergency_override=True,
            environments=["production"],
        )
        self._windows["business-hours"] = business_hours

        # 24/7 window for non-production
        always_available = SafeHoursWindow(
            name="always-available",
            description="No time restrictions (24/7)",
            window_type=WindowType.DAILY,
            start_hour=0,
            end_hour=24,  # end_hour is exclusive; 24 means "through 23:59"
            timezone="UTC",
            emergency_override=False,
            environments=["development", "staging"],
        )
        self._windows["always-available"] = always_available

        # Maintenance window (2 AM - 4 AM UTC, daily)
        maintenance_window = SafeHoursWindow(
            name="maintenance-window",
            description="Maintenance window (2 AM - 4 AM UTC, daily)",
            window_type=WindowType.DAILY,
            start_hour=2,
            end_hour=4,
            timezone="UTC",
            emergency_override=True,
            environments=["production"],
        )
        self._windows["maintenance-window"] = maintenance_window

        # Set default environment mappings
        self._environment_windows["production"] = "business-hours"
        self._environment_windows["development"] = "always-available"
        self._environment_windows["staging"] = "always-available"

    def add_window(self, window: SafeHoursWindow) -> None:
        """Add a custom time window.

        Args:
            window: SafeHoursWindow to add
        """
        self._windows[window.name] = window
        logger.info(f"Added time window: {window.name}")

    def remove_window(self, name: str) -> bool:
        """Remove a time window.

        Args:
            name: Name of window to remove

        Returns:
            True if removed, False if not found
        """
        if name in self._windows:
            del self._windows[name]
            logger.info(f"Removed time window: {name}")
            return True
        return False

    def set_environment_window(self, environment: str, window_name: str) -> None:
        """Set the time window for an environment.

        Args:
            environment: Environment name (e.g., "production")
            window_name: Name of the time window to apply
        """
        if window_name not in self._windows:
            raise ValueError(f"Window '{window_name}' not found")

        self._environment_windows[environment] = window_name
        logger.info(f"Set environment '{environment}' to window '{window_name}'")

    def check_time_window(
        self,
        environment: str,
        action_time: datetime | None = None,
        allow_emergency_override: bool = False,
    ) -> WindowCheckResult:
        """Check if an action is allowed at the given time.

        Args:
            environment: Environment name
            action_time: Time to check (defaults to now)
            allow_emergency_override: Whether emergency override is allowed

        Returns:
            WindowCheckResult with check details
        """
        if action_time is None:
            action_time = datetime.now(timezone.utc)

        # Get the window for this environment
        window_name = self._environment_windows.get(environment)
        if window_name is None:
            # Phase 15 P3: fail closed. An environment without a mapping
            # (typo, new project tag) used to bypass time windows entirely.
            return WindowCheckResult(
                is_allowed=False,
                reason=(
                    f"No time window configured for environment '{environment}' "
                    f"— denying (fail closed; map it via set_environment_window)"
                ),
                current_time=action_time,
            )

        window = self._windows.get(window_name)
        if window is None:
            # Window referenced but not found
            return WindowCheckResult(
                is_allowed=False,
                reason=f"Time window '{window_name}' not found",
                current_time=action_time,
            )

        # Check if environment is in the window's applicable environments
        if environment not in window.environments:
            return WindowCheckResult(
                is_allowed=True,
                reason=f"Window '{window_name}' does not apply to environment '{environment}'",
                current_time=action_time,
            )

        # Convert action time to window timezone
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(window.timezone)
            localized_time = action_time.astimezone(tz)
        except ImportError:
            # Fallback for older Python versions
            localized_time = action_time

        current_hour = localized_time.hour
        current_day = localized_time.weekday()  # 0=Monday, 6=Sunday

        # Check if current day is allowed
        day_allowed = True
        if window.allowed_days is not None:
            day_allowed = current_day in window.allowed_days

        # Check if current hour is within the window
        if window.start_hour <= window.end_hour:
            # Normal case: e.g., 9 AM - 5 PM → [9, 17). end_hour is
            # exclusive — the old `<=` stretched a "9-17" window to 17:59.
            hour_allowed = window.start_hour <= current_hour < window.end_hour
        else:
            # Overnight case: e.g., 10 PM - 2 AM → [22, 24) ∪ [0, 2)
            hour_allowed = current_hour >= window.start_hour or current_hour < window.end_hour

        is_allowed = day_allowed and hour_allowed

        # Calculate next allowed time if not allowed
        next_allowed = None
        if not is_allowed:
            next_allowed = self._calculate_next_allowed_time(
                localized_time, window
            )

        return WindowCheckResult(
            is_allowed=is_allowed,
            window_name=window_name,
            reason=f"{'Allowed' if is_allowed else 'Not allowed'} in time window '{window_name}'",
            current_time=action_time,
            window_start=time(window.start_hour % 24, 0),
            window_end=time(window.end_hour % 24, 0),
            next_allowed_time=next_allowed,
            emergency_override_available=window.emergency_override and allow_emergency_override,
        )

    def _calculate_next_allowed_time(
        self,
        current_time: datetime,
        window: SafeHoursWindow,
    ) -> datetime:
        """Calculate the next time when actions will be allowed.

        Walks forward one calendar day at a time (in the window's timezone)
        and returns the first window start strictly after `current_time` on
        an allowed day. Day offsets are added absolutely: the previous loop
        advanced one day per *checked* day, so a run of non-allowed days
        (e.g. Friday evening before a weekend block) landed on the wrong day
        and could also return a time earlier than `current_time`.

        Args:
            current_time: Current time in window's timezone
            window: Time window configuration

        Returns:
            Next allowed datetime (UTC)
        """
        from datetime import timedelta

        for day_offset in range(8):  # a week, plus one for safety
            day = (current_time + timedelta(days=day_offset)).date()
            if window.allowed_days is not None and day.weekday() not in window.allowed_days:
                continue
            candidate = datetime.combine(
                day, time(window.start_hour % 24, 0), tzinfo=current_time.tzinfo
            )
            if candidate > current_time:
                return candidate.astimezone(timezone.utc)

        # Unreachable for sane configs (allowed_days None or non-empty always
        # admits a day within a week); defensive fallback.
        return (current_time + timedelta(days=1)).replace(
            hour=window.start_hour % 24,
            minute=0,
            second=0,
            microsecond=0,
        ).astimezone(timezone.utc)

    def get_safe_hours(
        self,
        environment: str,
    ) -> dict[str, Any] | None:
        """Get safe hours information for an environment.

        Args:
            environment: Environment name

        Returns:
            Dict with safe hours info or None
        """
        window_name = self._environment_windows.get(environment)
        if window_name is None:
            return None

        window = self._windows.get(window_name)
        if window is None:
            return None

        return {
            "window_name": window.name,
            "description": window.description,
            "window_type": window.window_type.value,
            "start_hour": window.start_hour,
            "end_hour": window.end_hour,
            "timezone": window.timezone,
            "allowed_days": window.allowed_days,
            "emergency_override": window.emergency_override,
        }

    def list_windows(self) -> list[str]:
        """List all available time window names.

        Returns:
            List of window names
        """
        return list(self._windows.keys())

    def get_window(self, name: str) -> SafeHoursWindow | None:
        """Get a time window by name.

        Args:
            name: Window name

        Returns:
            SafeHoursWindow or None
        """
        return self._windows.get(name)


# Global singleton instance
_time_window_enforcer: TimeWindowEnforcer | None = None


def get_time_window_enforcer() -> TimeWindowEnforcer:
    """Get or create the global TimeWindowEnforcer instance.

    Returns:
        The TimeWindowEnforcer singleton instance
    """
    global _time_window_enforcer
    if _time_window_enforcer is None:
        _time_window_enforcer = TimeWindowEnforcer()
    return _time_window_enforcer
