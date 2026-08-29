"""Command validator for RBAC and policy enforcement."""


from app.actions.parser import get_command_parser
from app.actions.rate_limiter import get_rate_limiter
from app.models.actions import CommandParams, RiskLevel
from app.registry.loader import get_registry


class ValidationResult:
    """Result of command validation."""

    def __init__(
        self,
        is_valid: bool,
        risk_level: RiskLevel = RiskLevel.MEDIUM,
        allowed: bool = True,
        requires_approval: bool = True,
        reason: str = "",
        warnings: list[str] = None,
    ):
        self.is_valid = is_valid
        self.risk_level = risk_level
        self.allowed = allowed
        self.requires_approval = requires_approval
        self.reason = reason
        self.warnings = warnings or []

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "is_valid": self.is_valid,
            "risk_level": self.risk_level,
            "allowed": self.allowed,
            "requires_approval": self.requires_approval,
            "reason": self.reason,
            "warnings": self.warnings,
        }


class CommandValidator:
    """Validate commands against project RBAC and policies."""

    def __init__(self):
        self.parser = get_command_parser()
        self.registry = get_registry()

    def validate(
        self,
        command: str,
        project: str,
        user: str | None = None,
    ) -> ValidationResult:
        """Validate a command for a specific project and user."""
        # Parse the command
        try:
            params = self.parser.parse(command)
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                allowed=False,
                reason=f"Failed to parse command: {e}",
            )

        # Get project config
        project_config = self.registry.projects and next(
            (p for p in self.registry.projects if p.name == project), None
        )
        if not project_config:
            return ValidationResult(
                is_valid=False,
                allowed=False,
                reason=f"Project '{project}' not found in registry",
            )

        # Check against global constraints first
        if self.registry.global_constraints:
            global_result = self._check_constraints(
                params, self.registry.global_constraints
            )
            if not global_result.allowed:
                return global_result

        # Check against project-specific constraints
        return self._check_constraints(params, project_config.rbac)

    def _check_constraints(self, params: CommandParams, rbac) -> ValidationResult:
        """Check command against RBAC constraints."""
        # Build action identifier
        action_id = self._build_action_id(params)

        # Check if action is forbidden
        if action_id in rbac.forbidden_actions:
            return ValidationResult(
                is_valid=True,
                allowed=False,
                requires_approval=False,
                reason=f"Action '{action_id}' is forbidden by policy",
                risk_level=RiskLevel.CRITICAL,
            )

        # Check if action is allowed without approval
        if action_id in rbac.allowed_actions:
            return ValidationResult(
                is_valid=True,
                allowed=True,
                requires_approval=False,
                reason=f"Action '{action_id}' is allowed without approval",
                risk_level=self._assess_risk(params),
            )

        # Check if action requires approval
        if action_id in rbac.requires_approval:
            # Check if comment is required
            requires_comment = action_id in rbac.requires_comment_for
            warnings = []
            if requires_comment:
                warnings.append(f"Action '{action_id}' requires a comment for approval")

            return ValidationResult(
                is_valid=True,
                allowed=True,
                requires_approval=True,
                reason=f"Action '{action_id}' requires approval",
                risk_level=self._assess_risk(params),
                warnings=warnings,
            )

        # Default: require approval for unknown actions
        return ValidationResult(
            is_valid=True,
            allowed=True,
            requires_approval=True,
            reason=f"Action '{action_id}' requires approval (default policy)",
            risk_level=self._assess_risk(params),
        )

    def _build_action_id(self, params: CommandParams) -> str:
        """Build action identifier for RBAC checking."""
        parts = [params.command_type.value]

        if params.action:
            parts.append(params.action)
        if params.resource_type:
            parts.append(params.resource_type)

        return "_".join(parts)

    def _assess_risk(self, params: CommandParams) -> RiskLevel:
        """Assess the risk level of a command."""
        # High-risk actions
        if params.action in ["delete", "remove", "uninstall"]:
            return RiskLevel.CRITICAL
        if params.action in ["scale", "restart", "rollout"]:
            return RiskLevel.HIGH

        # Medium-risk actions
        if params.action in ["apply", "upgrade", "sync"]:
            return RiskLevel.MEDIUM

        # Low-risk actions
        if params.action in ["get", "describe", "logs", "top", "list", "status"]:
            return RiskLevel.LOW

        # Safe/diagnostic actions
        if params.action in ["version", "config", "help"]:
            return RiskLevel.SAFE

        # Default to medium for unknown actions
        return RiskLevel.MEDIUM

    def check_rate_limit(
        self,
        project: str,
        action_type: str = "restart",
        user: str | None = None,
    ) -> tuple[bool, str, dict]:
        """Check if action rate limit has been exceeded.

        Args:
            project: Project name
            action_type: Type of action (restart, scale, delete, etc.)
            user: Optional user identifier

        Returns:
            Tuple of (allowed, reason, metadata)
            - allowed: bool indicating if action is permitted
            - reason: str explaining the result
            - metadata: dict with rate limit status (remaining, reset_time, etc.)
        """
        project_config = self.registry.projects and next(
            (p for p in self.registry.projects if p.name == project), None
        )
        if not project_config:
            return False, "Project not found", {}

        # Get the rate limiter instance
        rate_limiter = get_rate_limiter()

        # Check rate limits
        allowed, reason, metadata = rate_limiter.check(
            project=project,
            action_type=action_type,
            user=user,
        )

        return allowed, reason, metadata


# Singleton instance
_validator: CommandValidator | None = None


def get_command_validator() -> CommandValidator:
    """Get or create the singleton CommandValidator instance."""
    global _validator
    if _validator is None:
        _validator = CommandValidator()
    return _validator
