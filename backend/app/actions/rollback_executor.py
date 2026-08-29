"""Rollback executor for automatic rollback on failure."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RollbackStatus(str, Enum):
    """Status of rollback operations."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    APPROVAL_REQUIRED = "approval_required"


@dataclass
class RollbackCondition:
    """Condition for triggering automatic rollback."""
    name: str
    description: str
    check_fn: Callable[[dict[str, Any]], bool]  # Returns True if rollback needed


@dataclass
class RollbackPlan:
    """Plan for rolling back an action."""
    action_id: str
    original_command: str
    rollback_command: str  # Command to execute for rollback
    reason: str  # Why this rollback plan was created
    requires_approval: bool = True  # Whether rollback needs approval
    estimated_duration_seconds: float = 30.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RollbackResult:
    """Result of a rollback operation."""
    action_id: str
    rollback_action_id: str
    status: RollbackStatus
    rollback_command: str
    output: str = ""
    error: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_seconds: float = 0.0


class RollbackExecutor:
    """Executor for automatic rollback of failed actions.

    This class provides:
    - Automatic rollback plan generation for common operations
    - Rollback condition checking
    - Rollback execution with approval workflow
    """

    def __init__(self):
        """Initialize the rollback executor."""
        self._rollback_plans: dict[str, RollbackPlan] = {}  # action_id -> plan
        self._rollback_history: list[RollbackResult] = []

        # Default rollback conditions
        self._conditions = self._get_default_conditions()

    def _get_default_conditions(self) -> list[RollbackCondition]:
        """Get default rollback conditions."""
        return [
            RollbackCondition(
                name="action_failed",
                description="Action execution failed",
                check_fn=lambda ctx: ctx.get("execution_success") is False,
            ),
            RollbackCondition(
                name="high_error_rate",
                description="Error rate exceeded threshold",
                check_fn=lambda ctx: ctx.get("error_rate", 0) > 0.5,
            ),
            RollbackCondition(
                name="health_check_failed",
                description="Health check failed after action",
                check_fn=lambda ctx: ctx.get("health_check_passed") is False,
            ),
            RollbackCondition(
                name="latency_spike",
                description="Latency increased significantly",
                check_fn=lambda ctx: ctx.get("latency_increase_ratio", 0) > 2.0,
            ),
        ]

    def create_rollback_plan(
        self,
        action_id: str,
        command: str,
        context: dict[str, Any] | None = None,
    ) -> RollbackPlan | None:
        """Create a rollback plan for an action.

        Args:
            action_id: ID of the action
            command: Original command that was executed
            context: Additional context for creating the plan

        Returns:
            RollbackPlan if rollback is possible, None otherwise
        """
        rollback_cmd = self._generate_rollback_command(command)

        if rollback_cmd is None:
            logger.warning(f"No rollback plan available for action {action_id}: {command}")
            return None

        plan = RollbackPlan(
            action_id=action_id,
            original_command=command,
            rollback_command=rollback_cmd,
            reason="Generated rollback plan",
            requires_approval=True,
            metadata={"context": context or {}},
        )

        self._rollback_plans[action_id] = plan
        logger.info(f"Created rollback plan for action {action_id}: {rollback_cmd}")

        return plan

    def _generate_rollback_command(self, command: str) -> str | None:
        """Generate a rollback command for a given action.

        Args:
            command: Original command

        Returns:
            Rollback command or None if not possible
        """
        parts = command.strip().split()
        if not parts:
            return None

        tool = parts[0]
        operation = parts[1] if len(parts) > 1 else None

        # Reconstruct flags and args
        flags = {}
        args = []
        i = 2
        while i < len(parts):
            part = parts[i]
            if part.startswith("-"):
                flag_name = part.lstrip("-")
                if i + 1 < len(parts) and not parts[i + 1].startswith("-"):
                    flags[flag_name] = parts[i + 1]
                    i += 2
                else:
                    flags[flag_name] = True
                    i += 1
            else:
                args.append(part)
                i += 1

        # Generate rollback based on tool and operation
        if tool == "kubectl":
            return self._generate_kubectl_rollback(operation, flags, args)
        elif tool == "helm":
            return self._generate_helm_rollback(operation, flags, args)
        elif tool == "argocd":
            return self._generate_argocd_rollback(operation, flags, args)

        return None

    def _generate_kubectl_rollback(
        self,
        operation: str | None,
        flags: dict[str, str],
        args: list[str],
    ) -> str | None:
        """Generate kubectl rollback command."""
        namespace_flag = ""
        if "n" in flags:
            namespace_flag = f"-n {flags['n']}"
        elif "namespace" in flags:
            namespace_flag = f"--namespace {flags['namespace']}"

        if operation == "apply":
            # Rollback apply by deleting resources (simplified - would use backup in production)
            # Check for -f flag which is stored in flags dict
            if "f" in flags:
                # kubectl apply -f <file> -> kubectl delete -f <file>
                return f"kubectl delete -f {flags['f']} {namespace_flag}".strip()
            elif len(args) > 0:
                # Other forms of apply
                return f"kubectl delete {args[0]} {namespace_flag}".strip()

        elif operation == "scale":
            # Rollback scale by scaling back (need original replicas)
            # This would require context about original scale
            return None  # Cannot generate without more context

        elif operation == "rollout" and "restart" in args:
            # Rollback restart by rolling back to previous revision
            if len(args) >= 3:
                deployment = args[2]  # kubectl rollout restart deployment <name>
                return f"kubectl rollout undo deployment {deployment} {namespace_flag}".strip()

        return None

    def _generate_helm_rollback(
        self,
        operation: str | None,
        flags: dict[str, str],
        args: list[str],
    ) -> str | None:
        """Generate helm rollback command."""
        namespace_flag = ""
        if "n" in flags:
            namespace_flag = f"-n {flags['n']}"
        elif "namespace" in flags:
            namespace_flag = f"--namespace {flags['namespace']}"

        if operation == "upgrade" and args:
            release = args[0]
            return f"helm rollback {release} {namespace_flag}"

        elif operation == "install" and args:
            release = args[0]
            return f"helm uninstall {release} {namespace_flag}"

        return None

    def _generate_argocd_rollback(
        self,
        operation: str | None,
        flags: dict[str, str],
        args: list[str],
    ) -> str | None:
        """Generate argocd rollback command."""
        if operation == "app" and "sync" in args:
            # Rollback sync by deploying previous revision
            # This would require app name and revision info
            if "app" in args:
                app_idx = args.index("app")
                if app_idx + 1 < len(args):
                    app_name = args[app_idx + 1]
                    return f"argocd app rollback {app_name}"

        return None

    def should_rollback(
        self,
        action_id: str,
        execution_context: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """Check if an action should be rolled back based on conditions.

        Args:
            action_id: ID of the action to check
            execution_context: Context from action execution

        Returns:
            Tuple of (should_rollback, triggered_conditions)
        """
        triggered = []

        for condition in self._conditions:
            try:
                if condition.check_fn(execution_context):
                    triggered.append(condition.name)
            except Exception as e:
                logger.error(f"Error checking rollback condition {condition.name}: {e}")

        return len(triggered) > 0, triggered

    async def execute_rollback(
        self,
        action_id: str,
        executor: Any,  # CommandExecutor instance
        dry_run: bool = False,
    ) -> RollbackResult:
        """Execute a rollback for an action.

        Args:
            action_id: ID of the action to rollback
            executor: CommandExecutor to run the rollback command
            dry_run: If True, don't actually execute

        Returns:
            RollbackResult with execution details
        """
        plan = self._rollback_plans.get(action_id)
        if plan is None:
            return RollbackResult(
                action_id=action_id,
                rollback_action_id="",
                status=RollbackStatus.FAILED,
                rollback_command="",
                error=f"No rollback plan found for action {action_id}",
            )

        rollback_action_id = f"rollback-{action_id}"
        start_time = datetime.now(timezone.utc)

        try:
            if dry_run:
                result = RollbackResult(
                    action_id=action_id,
                    rollback_action_id=rollback_action_id,
                    status=RollbackStatus.SKIPPED,
                    rollback_command=plan.rollback_command,
                    output=f"[DRY RUN] Would execute: {plan.rollback_command}",
                )
            else:
                # Execute rollback command
                exec_result = await executor.execute(
                    plan.rollback_command,
                    dry_run=False,
                )

                duration = (datetime.now(timezone.utc) - start_time).total_seconds()

                if exec_result.success:
                    result = RollbackResult(
                        action_id=action_id,
                        rollback_action_id=rollback_action_id,
                        status=RollbackStatus.SUCCESS,
                        rollback_command=plan.rollback_command,
                        output=exec_result.stdout,
                        duration_seconds=duration,
                    )
                    logger.info(f"Rollback successful for action {action_id}")
                else:
                    result = RollbackResult(
                        action_id=action_id,
                        rollback_action_id=rollback_action_id,
                        status=RollbackStatus.FAILED,
                        rollback_command=plan.rollback_command,
                        error=exec_result.stderr or exec_result.error_message or "Execution failed",
                        duration_seconds=duration,
                    )
                    logger.error(f"Rollback failed for action {action_id}: {result.error}")

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            result = RollbackResult(
                action_id=action_id,
                rollback_action_id=rollback_action_id,
                status=RollbackStatus.FAILED,
                rollback_command=plan.rollback_command,
                error=str(e),
                duration_seconds=duration,
            )
            logger.error(f"Rollback error for action {action_id}: {e}")

        # Record in history
        self._rollback_history.append(result)

        return result

    def get_rollback_plan(self, action_id: str) -> RollbackPlan | None:
        """Get the rollback plan for an action.

        Args:
            action_id: ID of the action

        Returns:
            RollbackPlan or None
        """
        return self._rollback_plans.get(action_id)

    def get_rollback_history(
        self,
        action_id: str | None = None,
        limit: int = 100,
    ) -> list[RollbackResult]:
        """Get rollback history.

        Args:
            action_id: Optional filter by action ID
            limit: Maximum results to return

        Returns:
            List of rollback results
        """
        history = self._rollback_history

        if action_id:
            history = [r for r in history if r.action_id == action_id]

        # Sort by timestamp descending
        history.sort(key=lambda r: r.timestamp, reverse=True)

        return history[:limit]

    def add_rollback_condition(self, condition: RollbackCondition) -> None:
        """Add a custom rollback condition.

        Args:
            condition: RollbackCondition to add
        """
        self._conditions.append(condition)
        logger.info(f"Added rollback condition: {condition.name}")

    def remove_rollback_condition(self, name: str) -> bool:
        """Remove a rollback condition.

        Args:
            name: Name of condition to remove

        Returns:
            True if removed, False if not found
        """
        original_len = len(self._conditions)
        self._conditions = [c for c in self._conditions if c.name != name]
        return len(self._conditions) < original_len

    def clear_rollback_plan(self, action_id: str) -> None:
        """Clear a rollback plan.

        Args:
            action_id: ID of action to clear plan for
        """
        if action_id in self._rollback_plans:
            del self._rollback_plans[action_id]
            logger.info(f"Cleared rollback plan for action {action_id}")


# Global singleton instance
_rollback_executor: RollbackExecutor | None = None


def get_rollback_executor() -> RollbackExecutor:
    """Get or create the global RollbackExecutor instance.

    Returns:
        The RollbackExecutor singleton instance
    """
    global _rollback_executor
    if _rollback_executor is None:
        _rollback_executor = RollbackExecutor()
    return _rollback_executor
