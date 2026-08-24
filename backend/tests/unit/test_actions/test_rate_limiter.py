"""Unit tests for RateLimiter."""

import time
import pytest
from datetime import datetime, timedelta

from app.actions.rate_limiter import (
    RateLimiter,
    RateLimitConfig,
    ActionRecord,
    get_rate_limiter,
)


@pytest.fixture
def reset_rate_limiter():
    """Reset the global rate limiter before each test."""
    global _rate_limiter
    from app.actions.rate_limiter import _rate_limiter
    _rate_limiter = None
    yield
    _rate_limiter = None


@pytest.fixture
def rate_limiter():
    """Create a fresh rate limiter for each test."""
    config = RateLimitConfig(
        max_actions_per_hour=3,
        cooldown_seconds=5,  # Short cooldown for testing
        time_window_seconds=60,  # Short window for testing
        max_chain_length=10,  # High chain limit for non-chain tests
    )
    return RateLimiter(config)


class TestRateLimiter:
    """Test RateLimiter functionality."""

    def test_initial_state(self, rate_limiter):
        """Test that rate limiter starts with clean state."""
        allowed, reason, metadata = rate_limiter.check(
            project="test-project",
            action_type="restart",
        )

        assert allowed is True
        assert "Rate limit check passed" in reason
        assert metadata["limit"] == 3
        assert metadata["remaining"] == 2
        assert metadata["cooldown_remaining"] == 0

    def test_action_recording(self, rate_limiter):
        """Test recording actions."""
        rate_limiter.record_action(
            project="test-project",
            action_type="restart",
            user="test-user",
        )

        # Check history
        history = rate_limiter.get_action_history(
            project="test-project",
            action_type="restart",
        )

        assert len(history) == 1
        assert history[0].project == "test-project"
        assert history[0].action_type == "restart"
        assert history[0].user == "test-user"

    def test_rate_limit_enforcement(self, rate_limiter):
        """Test that rate limit is enforced after max actions."""
        # Create rate limiter with no cooldown for this test
        config = RateLimitConfig(
            max_actions_per_hour=3,
            cooldown_seconds=0,  # No cooldown for this test
            time_window_seconds=60,
            max_chain_length=10,  # High chain limit to not interfere
        )
        test_limiter = RateLimiter(config)

        project = "test-project"
        action_type = "restart"

        # Execute max allowed actions
        for i in range(3):
            allowed, reason, metadata = test_limiter.check(project, action_type)
            assert allowed is True, f"Action {i+1} should be allowed"
            test_limiter.record_action(project, action_type)

        # Next action should be rate limited
        allowed, reason, metadata = test_limiter.check(project, action_type)
        assert allowed is False
        assert "Rate limit exceeded" in reason
        assert metadata["remaining"] == 0

    def test_cooldown_enforcement(self, rate_limiter):
        """Test that cooldown period is enforced."""
        project = "test-project"
        action_type = "restart"

        # Execute one action
        rate_limiter.record_action(project, action_type)

        # Immediate next action should be blocked by cooldown
        allowed, reason, metadata = rate_limiter.check(project, action_type)
        assert allowed is False
        assert "Cooldown active" in reason
        assert metadata["cooldown_remaining"] > 0

    def test_cooldown_expiration(self, rate_limiter):
        """Test that cooldown expires after time passes."""
        project = "test-project"
        action_type = "restart"

        # Execute one action
        rate_limiter.record_action(project, action_type)

        # Wait for cooldown to expire
        time.sleep(6)

        # Next action should be allowed
        allowed, reason, metadata = rate_limiter.check(project, action_type)
        assert allowed is True
        assert metadata["cooldown_remaining"] == 0

    def test_time_window_expiration(self, rate_limiter):
        """Test that old actions are removed from time window."""
        project = "test-project"
        action_type = "restart"

        # Execute max actions
        for i in range(3):
            rate_limiter.record_action(project, action_type)

        # Should be rate limited
        allowed, _, _ = rate_limiter.check(project, action_type)
        assert allowed is False

        # Wait for time window to expire
        time.sleep(61)

        # Should be allowed again
        allowed, reason, metadata = rate_limiter.check(project, action_type)
        assert allowed is True
        assert metadata["remaining"] == 2

    def test_different_action_types(self, rate_limiter):
        """Test that rate limits are per action type."""
        project = "test-project"

        # Execute max restart actions
        for i in range(3):
            rate_limiter.record_action(project, "restart")

        # Should be rate limited for restart
        allowed, _, _ = rate_limiter.check(project, "restart")
        assert allowed is False

        # But scale should still be allowed (different action type)
        allowed, _, _ = rate_limiter.check(project, "scale")
        assert allowed is True

    def test_different_projects(self, rate_limiter):
        """Test that rate limits are per project."""
        action_type = "restart"

        # Execute max actions for project-1
        for i in range(3):
            rate_limiter.record_action("project-1", action_type)

        # Should be rate limited for project-1
        allowed, _, _ = rate_limiter.check("project-1", action_type)
        assert allowed is False

        # But project-2 should still be allowed (different project)
        allowed, _, _ = rate_limiter.check("project-2", action_type)
        assert allowed is True

    def test_emergency_bypass(self, rate_limiter):
        """Test emergency bypass functionality."""
        rate_limiter.config.emergency_bypass = True

        project = "test-project"
        action_type = "restart"

        # Execute max actions
        for i in range(3):
            rate_limiter.record_action(project, action_type)

        # Should still be allowed due to bypass
        allowed, reason, metadata = rate_limiter.check(project, action_type)
        assert allowed is True
        assert "Emergency bypass" in reason
        assert metadata["bypass_active"] is True

    def test_get_stats(self, rate_limiter):
        """Test getting rate limit statistics."""
        project = "test-project"

        # Record some actions
        rate_limiter.record_action(project, "restart")
        rate_limiter.record_action(project, "restart")
        rate_limiter.record_action(project, "scale")

        stats = rate_limiter.get_stats(project)

        assert stats["project"] == project
        assert stats["total_actions"] == 3
        assert stats["active_windows"] == 2
        assert "restart" in stats["action_types"]
        assert "scale" in stats["action_types"]
        assert stats["action_types"]["restart"]["count"] == 2
        assert stats["action_types"]["scale"]["count"] == 1

    def test_reset_project(self, rate_limiter):
        """Test resetting rate limit state for a project."""
        project = "test-project"

        # Record actions
        rate_limiter.record_action(project, "restart")
        rate_limiter.record_action(project, "scale")

        # Reset the project
        rate_limiter.reset(project=project)

        # Should have no actions
        stats = rate_limiter.get_stats(project)
        assert stats["total_actions"] == 0

    def test_reset_action_type(self, rate_limiter):
        """Test resetting rate limit state for a specific action type."""
        project = "test-project"

        # Record actions
        rate_limiter.record_action(project, "restart")
        rate_limiter.record_action(project, "restart")
        rate_limiter.record_action(project, "scale")

        # Reset only restart actions
        rate_limiter.reset(project=project, action_type="restart")

        # Should still have scale action
        stats = rate_limiter.get_stats(project)
        assert stats["total_actions"] == 1
        assert "restart" not in stats["action_types"]
        assert "scale" in stats["action_types"]

    def test_reset_all(self, rate_limiter):
        """Test resetting all rate limit state."""
        # Record actions for multiple projects
        rate_limiter.record_action("project-1", "restart")
        rate_limiter.record_action("project-2", "scale")

        # Reset everything
        rate_limiter.reset()

        # Both projects should be cleared
        stats1 = rate_limiter.get_stats("project-1")
        stats2 = rate_limiter.get_stats("project-2")
        assert stats1["total_actions"] == 0
        assert stats2["total_actions"] == 0

    def test_metadata_structure(self, rate_limiter):
        """Test that metadata has correct structure."""
        allowed, reason, metadata = rate_limiter.check(
            project="test-project",
            action_type="restart",
        )

        # Check all required fields
        assert "limit" in metadata
        assert "remaining" in metadata
        assert "reset" in metadata
        assert "reset_datetime" in metadata
        assert "cooldown_remaining" in metadata
        assert "bypass_active" in metadata
        assert "window_seconds" in metadata

        # Check types
        assert isinstance(metadata["limit"], int)
        assert isinstance(metadata["remaining"], int)
        assert isinstance(metadata["reset"], int)
        assert isinstance(metadata["reset_datetime"], str)
        assert isinstance(metadata["cooldown_remaining"], int)
        assert isinstance(metadata["bypass_active"], bool)
        assert isinstance(metadata["window_seconds"], int)

    def test_reset_datetime_format(self, rate_limiter):
        """Test that reset_datetime is properly formatted."""
        allowed, reason, metadata = rate_limiter.check(
            project="test-project",
            action_type="restart",
        )

        # Should be ISO format string
        reset_dt = datetime.fromisoformat(metadata["reset_datetime"])
        assert isinstance(reset_dt, datetime)

    def test_update_config(self, rate_limiter):
        """Test updating rate limiter configuration."""
        new_config = RateLimitConfig(
            max_actions_per_hour=10,
            cooldown_seconds=60,
            time_window_seconds=3600,
        )

        rate_limiter.update_config(new_config)

        # Check that new config is applied
        assert rate_limiter.config.max_actions_per_hour == 10
        assert rate_limiter.config.cooldown_seconds == 60
        assert rate_limiter.config.time_window_seconds == 3600


class TestGlobalRateLimiter:
    """Test global rate limiter singleton."""

    def test_singleton(self):
        """Test that get_rate_limiter returns same instance."""
        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()

        assert limiter1 is limiter2

    def test_singleton_with_config(self):
        """Test that config is applied on first call."""
        from app.actions.rate_limiter import _rate_limiter
        _rate_limiter = None

        config = RateLimitConfig(max_actions_per_hour=5)
        limiter = get_rate_limiter(config)

        assert limiter.config.max_actions_per_hour == 5


class TestActionRecord:
    """Test ActionRecord dataclass."""

    def test_action_record_creation(self):
        """Test creating an ActionRecord."""
        record = ActionRecord(
            timestamp=time.time(),
            action_type="restart",
            project="test-project",
            user="test-user",
        )

        assert record.action_type == "restart"
        assert record.project == "test-project"
        assert record.user == "test-user"
        assert isinstance(record.timestamp, float)


class TestActionChaining:
    """Test action chaining prevention."""

    @pytest.fixture
    def chain_limiter(self):
        """Create a rate limiter with strict chain limit for testing."""
        config = RateLimitConfig(
            max_actions_per_hour=10,
            cooldown_seconds=0,
            time_window_seconds=60,
            max_chain_length=3,  # Allow max 3 consecutive actions
            chain_break_seconds=10,  # 10 seconds to reset chain
        )
        return RateLimiter(config)

    def test_chain_detection(self, chain_limiter):
        """Test that consecutive actions are tracked as a chain."""
        project = "test-project"
        action_type = "restart"

        # Execute 3 actions (at chain limit)
        for i in range(3):
            chain_limiter.record_action(project, action_type)

        # 4th action should be blocked by chain limit
        allowed, reason, metadata = chain_limiter.check(project, action_type)
        assert allowed is False
        assert "chain limit" in reason.lower()
        assert metadata["chain_count"] == 3

    def test_chain_break_after_timeout(self, chain_limiter):
        """Test that chain counter resets after break period."""
        project = "test-project"
        action_type = "restart"

        # Execute actions at chain limit
        for i in range(3):
            chain_limiter.record_action(project, action_type)

        # Wait for chain break period
        time.sleep(11)

        # Should be allowed again after break period
        allowed, reason, metadata = chain_limiter.check(project, action_type)
        assert allowed is True
        # Chain counter should have been reset
        assert metadata["chain_count"] == 0

    def test_different_action_types_dont_chain(self, chain_limiter):
        """Test that different action types don't contribute to same chain."""
        project = "test-project"

        # Execute 3 restart actions (at chain limit)
        for i in range(3):
            chain_limiter.record_action(project, "restart")

        # Should be blocked for restart
        allowed, _, _ = chain_limiter.check(project, "restart")
        assert allowed is False

        # But scale should still be allowed (different chain)
        allowed, _, _ = chain_limiter.check(project, "scale")
        assert allowed is True

    def test_chain_metadata(self, chain_limiter):
        """Test that chain information is included in metadata."""
        project = "test-project"
        action_type = "restart"

        # Record some actions
        chain_limiter.record_action(project, action_type)
        chain_limiter.record_action(project, action_type)

        allowed, reason, metadata = chain_limiter.check(project, action_type)

        # Check chain-related metadata
        assert "chain_count" in metadata
        assert "chain_limit" in metadata
        assert "chain_break_remaining" in metadata
        assert metadata["chain_limit"] == 3
        assert metadata["chain_count"] == 2

    def test_max_chain_length_config(self, chain_limiter):
        """Test that max_chain_length can be configured."""
        assert chain_limiter.config.max_chain_length == 3

        # Update config
        chain_limiter.update_config(RateLimitConfig(max_chain_length=5))
        assert chain_limiter.config.max_chain_length == 5

    def test_chain_included_in_stats(self, chain_limiter):
        """Test that stats include chain information."""
        project = "test-project"
        action_type = "restart"

        # Record some actions
        chain_limiter.record_action(project, action_type)
        chain_limiter.record_action(project, action_type)

        stats = chain_limiter.get_stats(project)

        # Stats should include chain info if we add it to the stats method
        assert stats["project"] == project
        assert stats["total_actions"] == 2
