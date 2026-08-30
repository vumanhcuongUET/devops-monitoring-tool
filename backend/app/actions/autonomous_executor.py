"""Autonomous action executor with safety and rate limiting.

This module provides the orchestration layer for autonomous remediation,
including rate limiting, safety checks, and audit logging.
"""

import logging
from datetime import datetime, timedelta, timezone

from app.actions.rate_limiter import AutonomousRateLimiter
from app.actions.remediation_actions import (
    RemediationActionFactory,
    RemediationActionType,
)
from app.models.actions import ExecutionResult
from app.models.alerts import AlertEvent, AlertRule

from app.audit.logger import AuditLogger
from app.models.audit import AuditEventType

# Backwards-compat alias (class now lives in app.actions.rate_limiter)
RateLimiter = AutonomousRateLimiter

logger = logging.getLogger(__name__)


class SafetyChecker:
    """Safety checks for autonomous actions.

    Validates that autonomous actions meet safety criteria before execution.
    """

    # Environments where autonomous actions are allowed
    ALLOWED_ENVIRONMENTS = {"development", "staging"}

    # Risk levels that require approval even for autonomous actions
    RISK_REQUIRING_APPROVAL = {"critical", "high"}

    @classmethod
    def check_environment(cls, environment: str) -> tuple[bool, str | None]:
        """Check if environment allows autonomous actions.

        Args:
            environment: Environment name

        Returns:
            Tuple of (allowed, reason_if_not_allowed)
        """
        if environment.lower() not in cls.ALLOWED_ENVIRONMENTS:
            return False, f"Autonomous actions not allowed in '{environment}' environment"

        return True, None

    @classmethod
    def check_risk_level(cls, risk_level: str) -> tuple[bool, str | None]:
        """Check if risk level requires approval.

        Args:
            risk_level: Risk level of the action

        Returns:
            Tuple of (allowed, reason_if_not_allowed)
        """
        if risk_level.lower() in cls.RISK_REQUIRING_APPROVAL:
            return False, f"Risk level '{risk_level}' requires manual approval"

        return True, None

    @classmethod
    def check_cooldown(cls, action_type: str, last_execution: datetime | None) -> tuple[bool, str | None]:
        """Check if sufficient cooldown has passed since last execution.

        Args:
            action_type: Type of remediation action
            last_execution: Timestamp of last execution

        Returns:
            Tuple of (allowed, reason_if_not_allowed)
        """
        if not last_execution:
            return True, None

        cooldown_period = timedelta(minutes=5)  # 5 minute cooldown
        elapsed = datetime.now(timezone.utc) - last_execution

        if elapsed < cooldown_period:
            return False, f"Cooldown period not met: {elapsed.seconds / 60:.1f} minutes elapsed (5 minutes required)"

        return True, None


# Phase 14 security: server-owned risk classification per action type.
# Unknown types default to "high" — blocked for autonomous execution —
# so adding a new action type is an explicit security decision.
AUTONOMOUS_ACTION_RISK: dict[str, str] = {
    "scale_deployment": "medium",
    "restart_deployment": "medium",
    "clear_stuck_pods": "medium",
    "cleanup_failed_jobs": "medium",
    "adjust_hpa_min_replicas": "medium",
    "restart_statefulset_pod": "medium",
    "delete_crashloop_pod": "high",
    "rollback_deployment": "high",
    "flush_endpoints": "high",
    "evict_pod_from_node": "high",
    "rotate_service_account_token": "critical",
    "truncate_node_logs": "critical",
    "restart_daemonset": "high",
    "restart_ingress_controller": "high",
}


class AutonomousExecutor:
    """Orchestrates autonomous remediation actions with safety and rate limiting."""

    def __init__(self):
        """Initialize autonomous executor."""
        self.rate_limiter = AutonomousRateLimiter(max_per_hour=3)
        self.audit_logger = AuditLogger()
        self._last_executions: dict[str, datetime] = {}

    async def execute_autonomous_action(
        self,
        alert_rule: AlertRule,
        alert_event: AlertEvent,
        environment: str = "development",
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute an autonomous remediation action.

        Args:
            alert_rule: Alert rule that triggered the action
            alert_event: Alert event with context
            environment: Environment for execution
            dry_run: If True, validate without executing

        Returns:
            Execution result with status and details
        """
        # Extract autonomous action configuration
        autonomous_config = alert_rule.autonomous_action
        if not autonomous_config or not autonomous_config.get("enabled"):
            return ExecutionResult(
                success=False,
                error_message="Autonomous action not enabled for this rule",
                timestamp=datetime.now(timezone.utc),
            )

        action_type_str = autonomous_config.get("action_type")
        if not action_type_str:
            return ExecutionResult(
                success=False,
                error_message="Action type not specified in autonomous configuration",
                timestamp=datetime.now(timezone.utc),
            )

        try:
            action_type = RemediationActionType(action_type_str)
        except ValueError:
            return ExecutionResult(
                success=False,
                error_message=f"Unknown action type: {action_type_str}",
                timestamp=datetime.now(timezone.utc),
            )

        # Safety Check 1: Environment
        env_allowed, env_reason = SafetyChecker.check_environment(environment)
        if not env_allowed:
            logger.warning(f"Autonomous action blocked: {env_reason}")
            return ExecutionResult(
                success=False,
                error_message=env_reason,
                timestamp=datetime.now(timezone.utc),
            )

        # Safety Check 2: Risk level — server-owned classification; unknown
        # action types are high-risk and blocked (Phase 14).
        risk_level = AUTONOMOUS_ACTION_RISK.get(action_type_str, "high")
        risk_allowed, risk_reason = SafetyChecker.check_risk_level(risk_level)
        if not risk_allowed:
            logger.warning(f"Autonomous action blocked: {risk_reason}")
            return ExecutionResult(
                success=False,
                error_message=risk_reason,
                timestamp=datetime.now(timezone.utc),
            )

        # Safety Check 3: Rate limiting
        rate_allowed, rate_reason = self.rate_limiter.can_execute(action_type_str)
        if not rate_allowed:
            logger.warning(f"Autonomous action blocked by rate limit: {rate_reason}")
            return ExecutionResult(
                success=False,
                error_message=rate_reason,
                timestamp=datetime.now(timezone.utc),
            )

        # Safety Check 4: Cooldown
        last_exec = self._last_executions.get(action_type_str)
        cooldown_allowed, cooldown_reason = SafetyChecker.check_cooldown(action_type_str, last_exec)
        if not cooldown_allowed:
            logger.warning(f"Autonomous action blocked by cooldown: {cooldown_reason}")
            return ExecutionResult(
                success=False,
                error_message=cooldown_reason,
                timestamp=datetime.now(timezone.utc),
            )

        # Extract parameters
        parameters = autonomous_config.get("parameters", {})
        # Add alert context to parameters
        parameters["alert_event_id"] = alert_event.id
        parameters["alert_rule_id"] = alert_rule.id

        # Log audit event
        self.audit_logger.log_event(
            event_type=AuditEventType.ACTION_CREATED,
            user="autonomous_system",
            action_id=f"autonomous_{alert_event.id}",
            project=alert_rule.labels.get("project", "unknown"),
            details={
                "command": f"{action_type_str} triggered by alert {alert_rule.name}",
                "environment": environment,
                "risk_level": "low",  # Autonomous actions are low-risk
                "alert_event_id": alert_event.id,
                "alert_rule_id": alert_rule.id,
                "action_type": action_type_str,
                "dry_run": dry_run,
            },
        )

        # Create and execute action
        try:
            action = RemediationActionFactory.create(action_type)
            result = await action.execute(
                alert_event=alert_event,
                parameters=parameters,
                dry_run=dry_run,
            )
        except Exception as e:
            logger.error(f"Autonomous action execution failed: {e}")
            return ExecutionResult(
                success=False,
                error_message=f"Action execution failed: {e}",
                timestamp=datetime.now(timezone.utc),
            )

        # Record rate limit usage if successful
        if result.success and not dry_run:
            self.rate_limiter.record_execution(action_type_str)
            self._last_executions[action_type_str] = datetime.now(timezone.utc)

        # Log execution result
        if result.success:
            self.audit_logger.log_event(
                event_type=AuditEventType.ACTION_EXECUTED,
                user="autonomous_system",
                action_id=f"autonomous_{alert_event.id}",
                success=True,
                execution_duration_seconds=result.duration_seconds or 0,
                details={
                    "command": f"{action_type_str} completed successfully",
                    "exit_code": result.exit_code or 0,
                    "stdout": result.stdout or "",
                    "stderr": result.stderr or "",
                },
            )
        else:
            self.audit_logger.log_event(
                event_type=AuditEventType.ACTION_FAILED,
                user="autonomous_system",
                action_id=f"autonomous_{alert_event.id}",
                success=False,
                details={"error_message": result.error_message or "Unknown error"},
            )

        return result

    def get_action_status(self) -> dict:
        """Get status of autonomous executor.

        Returns:
            Status dict with rate limit info and last executions
        """
        return {
            "rate_limit_quota": {
                action_type: self.rate_limiter.get_remaining_quota(action_type)
                for action_type in RemediationActionFactory.get_available_actions()
            },
            "last_executions": {
                action_type: last_exec.isoformat() if last_exec else None
                for action_type, last_exec in self._last_executions.items()
            },
        }


# Singleton instance
_executor: AutonomousExecutor | None = None


def get_autonomous_executor() -> AutonomousExecutor:
    """Get or create the singleton AutonomousExecutor instance.

    Returns:
        AutonomousExecutor instance
    """
    global _executor
    if _executor is None:
        _executor = AutonomousExecutor()
    return _executor
