"""Unit tests for TimeWindowEnforcer."""

from datetime import datetime, timezone

import pytest

from app.actions.time_window_enforcer import (
    SafeHoursWindow,
    TimeWindowEnforcer,
    WindowCheckResult,
    WindowType,
    get_time_window_enforcer,
)


class TestSafeHoursWindow:
    """Test SafeHoursWindow dataclass."""

    def test_window_creation(self):
        """Test creating a safe hours window."""
        window = SafeHoursWindow(
            name="test-window",
            description="Test window",
            start_hour=9,
            end_hour=17,
        )

        assert window.name == "test-window"
        assert window.start_hour == 9
        assert window.end_hour == 17
        assert window.window_type == WindowType.DAILY


class TestWindowCheckResult:
    """Test WindowCheckResult dataclass."""

    def test_result_creation(self):
        """Test creating a window check result."""
        result = WindowCheckResult(
            is_allowed=True,
            window_name="test-window",
            reason="Allowed",
        )

        assert result.is_allowed is True
        assert result.window_name == "test-window"
        assert isinstance(result.current_time, datetime)


class TestTimeWindowEnforcer:
    """Test TimeWindowEnforcer functionality."""

    @pytest.fixture
    def reset_enforcer(self):
        """Reset the global enforcer before each test."""
        global _time_window_enforcer
        from app.actions.time_window_enforcer import _time_window_enforcer
        _time_window_enforcer = None
        yield
        _time_window_enforcer = None

    def test_initial_state(self):
        """Test that enforcer starts with default windows."""
        enforcer = TimeWindowEnforcer()

        assert len(enforcer._windows) > 0
        assert "business-hours" in enforcer.list_windows()
        assert "always-available" in enforcer.list_windows()

    def test_default_environment_windows(self):
        """Test default environment window mappings."""
        enforcer = TimeWindowEnforcer()

        assert enforcer._environment_windows.get("production") == "business-hours"
        assert enforcer._environment_windows.get("development") == "always-available"
        assert enforcer._environment_windows.get("staging") == "always-available"

    def test_check_time_window_allowed(self, reset_enforcer):
        """Test checking time window when allowed."""
        enforcer = get_time_window_enforcer()

        # Set time to within business hours (10 AM UTC)
        test_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)  # Monday

        result = enforcer.check_time_window(
            environment="production",
            action_time=test_time,
        )

        assert result.is_allowed is True
        assert "Allowed" in result.reason

    def test_check_time_window_not_allowed_hours(self, reset_enforcer):
        """Test checking time window when outside allowed hours."""
        enforcer = get_time_window_enforcer()

        # Set time to outside business hours (8 PM UTC)
        test_time = datetime(2024, 1, 15, 20, 0, 0, tzinfo=timezone.utc)  # Monday

        result = enforcer.check_time_window(
            environment="production",
            action_time=test_time,
        )

        assert result.is_allowed is False
        assert "Not allowed" in result.reason

    def test_check_time_window_not_allowed_weekend(self, reset_enforcer):
        """Test checking time window on weekend."""
        enforcer = get_time_window_enforcer()

        # Set time to Saturday (day 5)
        test_time = datetime(2024, 1, 13, 10, 0, 0, tzinfo=timezone.utc)  # Saturday

        result = enforcer.check_time_window(
            environment="production",
            action_time=test_time,
        )

        assert result.is_allowed is False

    def test_check_time_window_development(self, reset_enforcer):
        """Test that development has no restrictions."""
        enforcer = get_time_window_enforcer()

        # Any time should be allowed for development
        test_time = datetime(2024, 1, 15, 3, 0, 0, tzinfo=timezone.utc)  # 3 AM

        result = enforcer.check_time_window(
            environment="development",
            action_time=test_time,
        )

        assert result.is_allowed is True

    def test_check_time_window_no_config(self):
        """Unknown environment → denied (Phase 15 P3 fail-closed)."""
        enforcer = TimeWindowEnforcer()

        # Remove all environment mappings
        enforcer._environment_windows = {}

        result = enforcer.check_time_window(
            environment="test-env",
        )

        assert result.is_allowed is False
        assert "No time window configured" in result.reason
        assert "fail closed" in result.reason

    def test_end_hour_exclusive(self):
        """Phase 15 P3: a '9-17' window ends at 17:00, not 17:59."""
        enforcer = TimeWindowEnforcer()

        enforcer.set_environment_window("production", "business-hours")

        before_end = datetime(2024, 1, 15, 16, 59, 0, tzinfo=timezone.utc)  # Monday
        at_end = datetime(2024, 1, 15, 17, 0, 0, tzinfo=timezone.utc)

        assert enforcer.check_time_window("production", action_time=before_end).is_allowed is True
        assert enforcer.check_time_window("production", action_time=at_end).is_allowed is False

    def test_always_available_covers_last_hour(self):
        """Phase 15 P3: the 24/7 window really is 24/7 (end_hour=24)."""
        enforcer = TimeWindowEnforcer()

        late = datetime(2024, 1, 15, 23, 30, 0, tzinfo=timezone.utc)  # Monday
        result = enforcer.check_time_window("development", action_time=late)

        assert result.is_allowed is True

    def test_next_allowed_after_weekend(self):
        """Phase 15 P3: Friday 20:00 → next allowed is Monday 09:00.

        The old loop advanced one day per *checked* day, so blocked days
        between now and the next allowed day made it land early.
        """
        enforcer = TimeWindowEnforcer()

        friday_evening = datetime(2024, 1, 12, 20, 0, 0, tzinfo=timezone.utc)  # Friday
        result = enforcer.check_time_window("production", action_time=friday_evening)

        assert result.is_allowed is False
        assert result.next_allowed_time == datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)

    def test_next_allowed_before_start_today(self):
        """Monday 06:00 → next allowed is today at 09:00."""
        enforcer = TimeWindowEnforcer()

        early = datetime(2024, 1, 15, 6, 0, 0, tzinfo=timezone.utc)  # Monday
        result = enforcer.check_time_window("production", action_time=early)

        assert result.is_allowed is False
        assert result.next_allowed_time == datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)

    def test_add_custom_window(self):
        """Test adding a custom time window."""
        enforcer = TimeWindowEnforcer()

        custom_window = SafeHoursWindow(
            name="night-shift",
            description="Night shift hours",
            window_type=WindowType.DAILY,
            start_hour=22,
            end_hour=6,
            timezone="UTC",
        )

        enforcer.add_window(custom_window)

        assert "night-shift" in enforcer.list_windows()

    def test_remove_window(self):
        """Test removing a time window."""
        enforcer = TimeWindowEnforcer()

        original_count = len(enforcer.list_windows())
        removed = enforcer.remove_window("maintenance-window")

        assert removed is True
        assert len(enforcer.list_windows()) == original_count - 1

    def test_remove_nonexistent_window(self):
        """Test removing a window that doesn't exist."""
        enforcer = TimeWindowEnforcer()

        removed = enforcer.remove_window("nonexistent")

        assert removed is False

    def test_set_environment_window(self):
        """Test setting window for an environment."""
        enforcer = TimeWindowEnforcer()

        enforcer.set_environment_window("production", "maintenance-window")

        assert enforcer._environment_windows["production"] == "maintenance-window"

    def test_set_environment_window_invalid(self):
        """Test setting invalid window raises error."""
        enforcer = TimeWindowEnforcer()

        with pytest.raises(ValueError):
            enforcer.set_environment_window("production", "invalid-window")

    def test_get_safe_hours(self, reset_enforcer):
        """Test getting safe hours for an environment."""
        enforcer = get_time_window_enforcer()

        safe_hours = enforcer.get_safe_hours("production")

        assert safe_hours is not None
        assert safe_hours["window_name"] == "business-hours"
        assert safe_hours["start_hour"] == 9
        assert safe_hours["end_hour"] == 17

    def test_get_safe_hours_no_config(self):
        """Test getting safe hours for environment with no config."""
        enforcer = TimeWindowEnforcer()

        safe_hours = enforcer.get_safe_hours("test-env")

        assert safe_hours is None

    def test_emergency_override_available(self, reset_enforcer):
        """Test emergency override availability."""
        enforcer = get_time_window_enforcer()

        # Outside business hours
        test_time = datetime(2024, 1, 15, 20, 0, 0, tzinfo=timezone.utc)

        result = enforcer.check_time_window(
            environment="production",
            action_time=test_time,
            allow_emergency_override=True,
        )

        assert result.emergency_override_available is True

    def test_emergency_override_not_allowed(self, reset_enforcer):
        """Test emergency override when not configured."""
        enforcer = get_time_window_enforcer()

        # Development environment has no emergency override configured
        test_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

        result = enforcer.check_time_window(
            environment="development",
            action_time=test_time,
            allow_emergency_override=True,
        )

        # always-available window has emergency_override=False
        assert result.emergency_override_available is False

    def test_next_allowed_time_calculated(self, reset_enforcer):
        """Test next allowed time is calculated correctly."""
        enforcer = get_time_window_enforcer()

        # 8 PM on Monday - next allowed is 9 AM next day (Tuesday)
        test_time = datetime(2024, 1, 15, 20, 0, 0, tzinfo=timezone.utc)

        result = enforcer.check_time_window(
            environment="production",
            action_time=test_time,
        )

        assert result.is_allowed is False
        assert result.next_allowed_time is not None

    def test_maintenance_window_check(self):
        """Test maintenance window (2 AM - 4 AM)."""
        enforcer = TimeWindowEnforcer()

        enforcer.set_environment_window("production", "maintenance-window")

        # Within maintenance window
        test_time = datetime(2024, 1, 15, 3, 0, 0, tzinfo=timezone.utc)

        result = enforcer.check_time_window(
            environment="production",
            action_time=test_time,
        )

        assert result.is_allowed is True

    def test_overnight_window(self):
        """Test overnight window (e.g., 10 PM - 2 AM)."""
        enforcer = TimeWindowEnforcer()

        overnight = SafeHoursWindow(
            name="overnight",
            description="Overnight window",
            window_type=WindowType.DAILY,
            start_hour=22,
            end_hour=2,
            timezone="UTC",
        )
        enforcer.add_window(overnight)
        enforcer.set_environment_window("production", "overnight")

        # At 11 PM - should be allowed
        test_time = datetime(2024, 1, 15, 23, 0, 0, tzinfo=timezone.utc)

        result = enforcer.check_time_window(
            environment="production",
            action_time=test_time,
        )

        assert result.is_allowed is True

        # At 3 AM - should not be allowed
        test_time = datetime(2024, 1, 16, 3, 0, 0, tzinfo=timezone.utc)

        result = enforcer.check_time_window(
            environment="production",
            action_time=test_time,
        )

        assert result.is_allowed is False

    def test_get_window(self):
        """Test getting a window by name."""
        enforcer = TimeWindowEnforcer()

        window = enforcer.get_window("business-hours")

        assert window is not None
        assert window.name == "business-hours"

    def test_get_window_not_found(self):
        """Test getting non-existent window."""
        enforcer = TimeWindowEnforcer()

        window = enforcer.get_window("nonexistent")

        assert window is None


class TestGlobalTimeWindowEnforcer:
    """Test global time window enforcer singleton."""

    @pytest.fixture(autouse=True)
    def reset_enforcer(self):
        """Reset the global enforcer before each test."""
        global _time_window_enforcer
        from app.actions.time_window_enforcer import _time_window_enforcer
        _time_window_enforcer = None
        yield
        _time_window_enforcer = None

    def test_singleton(self):
        """Test that get_time_window_enforcer returns same instance."""
        enforcer1 = get_time_window_enforcer()
        enforcer2 = get_time_window_enforcer()

        assert enforcer1 is enforcer2

    def test_singleton_persistence(self):
        """Test that singleton persists across calls."""
        enforcer1 = get_time_window_enforcer()
        custom_window = SafeHoursWindow(
            name="test",
            description="Test",
        )
        enforcer1.add_window(custom_window)

        enforcer2 = get_time_window_enforcer()
        assert "test" in enforcer2.list_windows()
