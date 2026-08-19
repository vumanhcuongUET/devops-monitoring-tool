"""AI Permission Checker - Validate AI actions against RBAC policies.

This module provides the AIPermissionChecker class which:
- Checks if AI actions are allowed based on environment
- Logs all permission checks for audit
- Integrates with the Action Engine for validation
- Supports rate limiting for safety
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.governance.ai_rbac import (
    AIPermission,
    check_permission,
    get_required_permission,
    get_action_risk_level,
    can_auto_approve,
)
from app.models.registry import ProjectConfig

logger = logging.getLogger(__name__)


class PermissionCheckResult:
    """Result of a permission check."""

    def __init__(
        self,
        allowed: bool,
        required_permission: AIPermission,
        reason: str,
        risk_level: str,
        requires_approval: bool,
        environment: str,
    ):
        """Initialize the result.

        Args:
            allowed: Whether the action is allowed
            required_permission: Permission required for the action
            reason: Human-readable reason
            risk_level: Risk level of the action
            requires_approval: Whether human approval is required
            environment: Environment where action was checked
        """
        self.allowed = allowed
        self.required_permission = required_permission
        self.reason = reason
        self.risk_level = risk_level
        self.requires_approval = requires_approval
        self.environment = environment
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "allowed": self.allowed,
            "required_permission": self.required_permission.value,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "requires_approval": self.requires_approval,
            "environment": self.environment,
            "timestamp": self.timestamp.isoformat(),
        }


class AIPermissionChecker:
    """Check AI permissions against RBAC policies.

    This checker:
    - Validates commands before execution
    - Enforces environment-based permissions
    - Maintains audit trail
    - Supports rate limiting
    """

    MAX_AUDIT_LOG_SIZE = 10000  # Maximum audit entries to keep in memory

    def __init__(
        self,
        default_environment: str = "production",
        enable_rate_limit: bool = True,
        max_checks_per_minute: int = 100,
    ):
        """Initialize the permission checker.

        Args:
            default_environment: Default environment for checks
            enable_rate_limit: Whether to enable rate limiting
            max_checks_per_minute: Maximum permission checks per minute
        """
        self.default_environment = default_environment
        self.enable_rate_limit = enable_rate_limit
        self.max_checks_per_minute = max_checks_per_minute

        # Rate limiting state
        self._check_timestamps: List[datetime] = []

        # Audit log (bounded size)
        self._audit_log: List[Dict[str, Any]] = []

    def check(
        self,
        action: str,
        environment: Optional[str] = None,
        project: Optional[str] = None,
        user: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> PermissionCheckResult:
        """Check if an action is allowed.

        Args:
            action: Action to check (e.g., "delete", "scale")
            environment: Environment to check against
            project: Optional project name
            user: Optional user requesting the action
            context: Additional context

        Returns:
            PermissionCheckResult
        """
        env = environment or self.default_environment

        # Rate limit check
        if self.enable_rate_limit:
            if not self._check_rate_limit():
                logger.warning(f"Rate limit exceeded for permission checks")
                return PermissionCheckResult(
                    allowed=False,
                    required_permission=AIPermission.VIEW,
                    reason="Rate limit exceeded - too many permission checks",
                    risk_level="medium",
                    requires_approval=True,
                    environment=env,
                )

        # Get required permission
        required = get_required_permission(action)
        risk_level = get_action_risk_level(required)

        # Check base permission
        base_allowed, _, base_reason = check_permission(action, env)

        # Determine if approval is required
        requires_approval = not base_allowed

        # Build final reason
        if base_allowed:
            reason = f"Action '{action}' allowed in {env} ({risk_level} risk)"
        else:
            reason = f"Action '{action}' requires human approval in {env}"

        # Create result
        result = PermissionCheckResult(
            allowed=base_allowed,
            required_permission=required,
            reason=reason,
            risk_level=risk_level,
            requires_approval=requires_approval,
            environment=env,
        )

        # Log to audit
        self._log_check(result, action, project, user, context)

        return result

    def check_command(
        self,
        command: str,
        environment: Optional[str] = None,
        project: Optional[str] = None,
        user: Optional[str] = None,
    ) -> PermissionCheckResult:
        """Check if a command is allowed.

        Args:
            command: Full command string (e.g., "kubectl delete pod")
            environment: Environment to check against
            project: Optional project name
            user: Optional user requesting the action

        Returns:
            PermissionCheckResult
        """
        # Extract action from command
        action = self._extract_action(command)
        if not action:
            # Unknown command - treat as execute
            action = "exec"

        return self.check(action, environment, project, user, {"command": command})

    def check_batch(
        self,
        actions: List[str],
        environment: Optional[str] = None,
        project: Optional[str] = None,
        user: Optional[str] = None,
    ) -> List[PermissionCheckResult]:
        """Check multiple actions.

        Args:
            actions: List of actions to check
            environment: Environment to check against
            project: Optional project name
            user: Optional user requesting the actions

        Returns:
            List of PermissionCheckResult
        """
        results = []
        for action in actions:
            result = self.check(action, environment, project, user)
            results.append(result)

        return results

    def get_allowed_actions(
        self,
        environment: Optional[str] = None,
    ) -> List[str]:
        """Get list of allowed action types for an environment.

        Args:
            environment: Environment to check

        Returns:
            List of allowed actions
        """
        from app.governance.ai_rbac import get_ai_permission_matrix

        env = environment or self.default_environment
        permissions = get_ai_permission_matrix(env)

        # Map permissions back to actions
        from app.governance.ai_rbac import ACTION_PERMISSION_MAP

        allowed_actions = []
        for action, perm in ACTION_PERMISSION_MAP.items():
            if perm in permissions:
                allowed_actions.append(action)

        return sorted(allowed_actions)

    def get_audit_log(
        self,
        limit: int = 100,
        project: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get audit log entries.

        Args:
            limit: Maximum entries to return
            project: Optional project filter
            environment: Optional environment filter

        Returns:
            List of audit log entries
        """
        log = self._audit_log

        # Apply filters
        if project:
            log = [e for e in log if e.get("project") == project]
        if environment:
            log = [e for e in log if e.get("environment") == environment]

        # Return most recent first
        return list(reversed(log[-limit:]))

    def _check_rate_limit(self) -> bool:
        """Check if rate limit allows another check.

        Uses a sliding window of 60 seconds from NOW, not from minute boundary.

        Returns:
            True if under rate limit
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=60)

        # Remove timestamps older than 60 seconds from NOW (sliding window)
        self._check_timestamps = [
            ts for ts in self._check_timestamps if ts > window_start
        ]

        # Check limit
        return len(self._check_timestamps) < self.max_checks_per_minute

    def _log_check(
        self,
        result: PermissionCheckResult,
        action: str,
        project: Optional[str],
        user: Optional[str],
        context: Optional[Dict[str, Any]],
    ) -> None:
        """Log a permission check to audit trail.

        Args:
            result: Check result
            action: Action that was checked
            project: Optional project name
            user: Optional user name
            context: Additional context
        """
        entry = {
            "timestamp": result.timestamp.isoformat(),
            "action": action,
            "allowed": result.allowed,
            "required_permission": result.required_permission.value,
            "risk_level": result.risk_level,
            "requires_approval": result.requires_approval,
            "environment": result.environment,
            "project": project,
            "user": user,
            "context": context or {},
        }

        self._audit_log.append(entry)

        # Trim audit log to prevent unbounded growth
        if len(self._audit_log) > self.MAX_AUDIT_LOG_SIZE:
            # Remove oldest entries (FIFO)
            excess = len(self._audit_log) - self.MAX_AUDIT_LOG_SIZE
            self._audit_log = self._audit_log[excess:]

        # Also log to standard logger
        log_level = logging.INFO if result.allowed else logging.WARNING
        logger.log(
            log_level,
            f"Permission check: action={action}, allowed={result.allowed}, "
            f"env={result.environment}, project={project}"
        )

    def _extract_action(self, command: str) -> Optional[str]:
        """Extract action from a command string.

        Args:
            command: Command string (e.g., "kubectl delete pod")

        Returns:
            Extracted action or None
        """
        parts = command.strip().split()
        if len(parts) >= 2:
            # Second word is usually the action
            return parts[1].lower()
        return None


# Singleton instance
_permission_checker: Optional[AIPermissionChecker] = None


def get_permission_checker(
    environment: str = "production",
    enable_rate_limit: bool = True,
) -> AIPermissionChecker:
    """Get or create the singleton AIPermissionChecker instance.

    Args:
        environment: Default environment
        enable_rate_limit: Whether to enable rate limiting

    Returns:
        AIPermissionChecker instance
    """
    global _permission_checker
    if _permission_checker is None:
        _permission_checker = AIPermissionChecker(
            default_environment=environment,
            enable_rate_limit=enable_rate_limit,
        )
    return _permission_checker
