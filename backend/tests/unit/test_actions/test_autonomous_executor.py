"""Unit tests for Autonomous Executor (Phase 4)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

from app.actions.autonomous_executor import (
    AutonomousExecutor,
    RateLimiter,
    SafetyChecker,
    get_autonomous_executor,
)
from app.models.alerts import AlertRule, AlertSeverity, AlertEvent


class TestRateLimiter:
    """Test rate limiting for autonomous actions."""

    @pytest.fixture
    def limiter(self):
        return RateLimiter(max_per_hour=3)

    def test_initial_state(self, limiter):
        """Test initial rate limit state."""
        allowed, reason = limiter.can_execute("delete_crashloop_pod")
        assert allowed is True
        assert reason is None

    def test_record_execution(self, limiter):
        """Test recording execution."""
        limiter.record_execution("delete_crashloop_pod")
        allowed, reason = limiter.can_execute("delete_crashloop_pod")
        assert allowed is True  # Should still allow (1/3 used)

    def test_rate_limit_exceeded(self, limiter):
        """Test rate limit enforcement."""
        # Record 3 executions
        for _ in range(3):
            limiter.record_execution("delete_crashloop_pod")

        # 4th should be blocked
        allowed, reason = limiter.can_execute("delete_crashloop_pod")
        assert allowed is False
        assert "Rate limit exceeded" in reason

    def test_different_action_types(self, limiter):
        """Test rate limits are per action type."""
        limiter.record_execution("delete_crashloop_pod")
        limiter.record_execution("delete_crashloop_pod")
        limiter.record_execution("delete_crashloop_pod")

        # delete_crashloop_pod should be blocked
        allowed, _ = limiter.can_execute("delete_crashloop_pod")
        assert allowed is False

        # But scale_deployment should still be allowed
        allowed, _ = limiter.can_execute("scale_deployment")
        assert allowed is True

    def test_get_remaining_quota(self, limiter):
        """Test getting remaining quota."""
        limiter.record_execution("delete_crashloop_pod")
        quota = limiter.get_remaining_quota("delete_crashloop_pod")
        assert quota == 2  # 3 - 1 = 2 remaining

    def test_old_executions_cleaned(self, limiter):
        """Test old executions are cleaned from tracking."""
        # Record an execution over an hour ago
        old_time = datetime.now(timezone.utc) - timedelta(minutes=61)
        limiter._execution_times["delete_crashloop_pod"].append(old_time)

        # Should still be allowed (old entry cleaned)
        allowed, _ = limiter.can_execute("delete_crashloop_pod")
        assert allowed is True


class TestSafetyChecker:
    """Test safety checks for autonomous actions."""

    def test_check_environment_allowed(self):
        """Test allowed environments."""
        allowed, reason = SafetyChecker.check_environment("development")
        assert allowed is True
        assert reason is None

        allowed, reason = SafetyChecker.check_environment("staging")
        assert allowed is True

    def test_check_environment_blocked(self):
        """Test blocked environments."""
        allowed, reason = SafetyChecker.check_environment("production")
        assert allowed is False
        assert "not allowed" in reason.lower()

        allowed, reason = SafetyChecker.check_environment("production-read-only")
        assert allowed is False

    def test_check_risk_level_safe(self):
        """Test safe risk levels."""
        allowed, reason = SafetyChecker.check_risk_level("low")
        assert allowed is True

        allowed, reason = SafetyChecker.check_risk_level("medium")
        assert allowed is True

    def test_check_risk_level_requires_approval(self):
        """Test high risk requires approval."""
        allowed, reason = SafetyChecker.check_risk_level("high")
        assert allowed is False
        assert "requires manual approval" in reason.lower()

        allowed, reason = SafetyChecker.check_risk_level("critical")
        assert allowed is False

    def test_check_cooldown_passed(self):
        """Test cooldown period passed."""
        # No previous execution
        allowed, reason = SafetyChecker.check_cooldown("delete_crashloop_pod", None)
        assert allowed is True

        # Execution 10 minutes ago
        old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        allowed, reason = SafetyChecker.check_cooldown("delete_crashloop_pod", old_time)
        assert allowed is True

    def test_check_cooldown_not_passed(self):
        """Test cooldown period not passed."""
        # Execution 2 minutes ago
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=2)
        allowed, reason = SafetyChecker.check_cooldown("delete_crashloop_pod", recent_time)
        assert allowed is False
        assert "cooldown period not met" in reason.lower()


class TestAutonomousExecutor:
    """Test autonomous action orchestration."""

    @pytest.fixture
    def executor(self):
        return AutonomousExecutor()

    @pytest.fixture
    def alert_rule(self):
        return AlertRule(
            id="crashloop-rule",
            name="CrashLoopBackOff Detected",
            source="kubernetes",
            metric="pods_crashloop",
            condition="gt",
            threshold=0,
            duration_seconds=60,
            severity=AlertSeverity.WARNING,
            enabled=True,
            labels={"environment": "development", "project": "test"},
            autonomous_action={
                "enabled": True,
                "action_type": "delete_crashloop_pod",
                "auto_approve": True,
                "max_executions_per_hour": 3,
                "parameters": {"namespace": "default", "restart_threshold": 5},
            },
        )

    @pytest.fixture
    def alert_event(self):
        return AlertEvent(
            id="event-1",
            rule_id="crashloop-rule",
            rule_name="CrashLoopBackOff Detected",
            severity=AlertSeverity.WARNING,
            status="firing",
            value=1.0,
            threshold=0,
            message="Pod in crashloop",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @pytest.mark.asyncio
    async def test_execute_autonomous_action_success(self, executor, alert_rule, alert_event):
        """Test successful autonomous action execution."""
        mock_result = MagicMock(success=True, exit_code=0, stdout="Pod deleted")

        with patch("app.actions.autonomous_executor.RemediationActionFactory") as mock_factory:
            mock_action = MagicMock()
            mock_action.execute = AsyncMock(return_value=mock_result)
            mock_factory.create.return_value = mock_action

            with patch.object(executor.audit_logger, "log_action_created"):
                with patch.object(executor.audit_logger, "log_action_executed"):
                    result = await executor.execute_autonomous_action(
                        alert_rule=alert_rule,
                        alert_event=alert_event,
                        environment="development",
                        dry_run=False,
                    )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_autonomous_action_production_blocked(self, executor, alert_rule, alert_event):
        """Test autonomous action blocked in production."""
        result = await executor.execute_autonomous_action(
            alert_rule=alert_rule,
            alert_event=alert_event,
            environment="production",
            dry_run=False,
        )

        assert result.success is False
        assert "not allowed" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_execute_autonomous_action_disabled(self, executor, alert_rule, alert_event):
        """Test autonomous action not enabled."""
        alert_rule.autonomous_action["enabled"] = False

        result = await executor.execute_autonomous_action(
            alert_rule=alert_rule,
            alert_event=alert_event,
            environment="development",
            dry_run=False,
        )

        assert result.success is False
        assert "not enabled" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_execute_autonomous_action_rate_limited(self, executor, alert_rule, alert_event):
        """Test rate limiting blocks execution."""
        # Exhaust rate limit
        for _ in range(3):
            executor.rate_limiter.record_execution("delete_crashloop_pod")

        result = await executor.execute_autonomous_action(
            alert_rule=alert_rule,
            alert_event=alert_event,
            environment="development",
            dry_run=False,
        )

        assert result.success is False
        assert "rate limit" in result.error_message.lower()

    def test_get_action_status(self, executor):
        """Test getting autonomous executor status."""
        status = executor.get_action_status()

        assert "rate_limit_quota" in status
        assert "last_executions" in status
        assert isinstance(status["rate_limit_quota"], dict)


class TestAutonomousExecutorSingleton:
    """Test singleton pattern."""

    def test_get_autonomous_executor_returns_singleton(self):
        """Test that get_autonomous_executor returns same instance."""
        executor1 = get_autonomous_executor()
        executor2 = get_autonomous_executor()

        assert executor1 is executor2

    def test_get_autonomous_executor_initializes_new_instance(self):
        """Test that first call initializes the executor."""
        from app.actions.autonomous_executor import _executor
        _executor = None

        executor = get_autonomous_executor()

        assert executor is not None
        assert isinstance(executor, AutonomousExecutor)
