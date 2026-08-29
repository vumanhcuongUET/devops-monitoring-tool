"""AI RBAC - Environment-based permissions for AI agents.

This module implements a permission matrix that controls what AI agents
can do in different environments (dev, staging, production).

Principles:
1. Principle of Least Privilege - AI agents have minimum required permissions
2. Environment Segregation - Different permissions per environment
3. Human Oversight - High-risk actions require approval
4. Audit Trail - All permission checks are logged
"""

from enum import Enum


class AIPermission(str, Enum):
    """Permissions that AI agents can request.

    Each permission represents a category of actions:
    - view: Read-only access (get, describe, list)
    - modify: Modify existing resources (update, patch)
    - create: Create new resources
    - delete: Delete resources
    - execute: Run commands or scripts
    - scale: Change resource counts (HPA, replicas)
    - rollback: Rollback deployments
    - approve: Approve actions (limited to staging/dev)
    """

    VIEW = "view"
    MODIFY = "modify"
    CREATE = "create"
    DELETE = "delete"
    EXECUTE = "execute"
    SCALE = "scale"
    ROLLBACK = "rollback"
    APPROVE = "approve"


# Environment-based permission matrix
# Each environment has a set of allowed permissions
ENVIRONMENT_PERMISSIONS: dict[str, list[AIPermission]] = {
    "development": [
        AIPermission.VIEW,
        AIPermission.MODIFY,
        AIPermission.CREATE,
        AIPermission.DELETE,
        AIPermission.EXECUTE,
        AIPermission.SCALE,
        AIPermission.ROLLBACK,
        AIPermission.APPROVE,  # Can self-approve in dev
    ],
    "staging": [
        AIPermission.VIEW,
        AIPermission.MODIFY,
        AIPermission.CREATE,
        AIPermission.EXECUTE,
        AIPermission.SCALE,
        AIPermission.ROLLBACK,
        # DELETE and APPROVE require human approval in staging
    ],
    "production": [
        AIPermission.VIEW,
        AIPermission.SCALE,
        # All other actions require human approval in production
    ],
    "production-read-only": [
        AIPermission.VIEW,  # Read-only access to production
    ],
}


# Action type to permission mapping
ACTION_PERMISSION_MAP: dict[str, AIPermission] = {
    # Kubernetes actions
    "get": AIPermission.VIEW,
    "describe": AIPermission.VIEW,
    "list": AIPermission.VIEW,
    "logs": AIPermission.VIEW,
    "top": AIPermission.VIEW,

    "apply": AIPermission.CREATE,
    "create": AIPermission.CREATE,
    "run": AIPermission.CREATE,

    "update": AIPermission.MODIFY,
    "patch": AIPermission.MODIFY,
    "edit": AIPermission.MODIFY,

    "delete": AIPermission.DELETE,
    "remove": AIPermission.DELETE,

    "scale": AIPermission.SCALE,
    "autoscale": AIPermission.SCALE,

    "rollout": AIPermission.ROLLBACK,
    "rollback": AIPermission.ROLLBACK,
    "undo": AIPermission.ROLLBACK,

    "exec": AIPermission.EXECUTE,
    "attach": AIPermission.EXECUTE,
    "cp": AIPermission.EXECUTE,

    # Helm/ArgoCD actions
    "install": AIPermission.CREATE,
    "upgrade": AIPermission.MODIFY,
    "uninstall": AIPermission.DELETE,

    # ArgoCD actions
    "sync": AIPermission.MODIFY,
}


# Risk levels for action types
ACTION_RISK_LEVELS: dict[str, str] = {
    AIPermission.VIEW: "safe",
    AIPermission.SCALE: "low",
    AIPermission.MODIFY: "medium",
    AIPermission.CREATE: "medium",
    AIPermission.ROLLBACK: "high",
    AIPermission.EXECUTE: "high",
    AIPermission.DELETE: "critical",
    AIPermission.APPROVE: "medium",
}


def get_ai_permission_matrix(
    environment: str = "production",
) -> list[AIPermission]:
    """Get allowed permissions for an environment.

    Args:
        environment: Environment name (dev, staging, production)

    Returns:
        List of allowed permissions

    Raises:
        ValueError: If environment is not recognized
    """
    # Normalize environment name
    env_map = {
        "dev": "development",
        "development": "development",
        "staging": "staging",
        "stage": "staging",
        "prod": "production",
        "production": "production",
        "prod-read-only": "production-read-only",
        "production-read-only": "production-read-only",
    }

    normalized = env_map.get(environment.lower(), environment)

    if normalized not in ENVIRONMENT_PERMISSIONS:
        raise ValueError(
            f"Unknown environment: {environment}. "
            f"Valid environments: {list(ENVIRONMENT_PERMISSIONS.keys())}"
        )

    return ENVIRONMENT_PERMISSIONS[normalized]


def get_required_permission(action: str) -> AIPermission:
    """Get the permission required for an action.

    Args:
        action: Action name (e.g., "get", "delete", "scale")

    Returns:
        Required permission
    """
    # Normalize action
    action_lower = action.lower()

    # Check direct mapping
    if action_lower in ACTION_PERMISSION_MAP:
        return ACTION_PERMISSION_MAP[action_lower]

    # Check if action starts with a known prefix
    for known_action, permission in ACTION_PERMISSION_MAP.items():
        if action_lower.startswith(known_action):
            return permission

    # Default to EXECUTE for unknown actions
    return AIPermission.EXECUTE


def get_action_risk_level(permission: AIPermission) -> str:
    """Get risk level for a permission.

    Args:
        permission: AI permission

    Returns:
        Risk level: safe, low, medium, high, critical
    """
    return ACTION_RISK_LEVELS.get(permission, "medium")


def check_permission(
    action: str,
    environment: str = "production",
) -> tuple[bool, AIPermission, str]:
    """Check if an action is allowed in an environment.

    Args:
        action: Action to check
        environment: Environment to check against

    Returns:
        Tuple of (allowed, required_permission, reason)
    """
    try:
        # Get required permission
        required = get_required_permission(action)

        # Get allowed permissions for environment
        allowed_permissions = get_ai_permission_matrix(environment)

        # Check if permission is allowed
        if required in allowed_permissions:
            risk = get_action_risk_level(required)
            reason = f"Allowed ({risk} risk)"
            return True, required, reason
        else:
            return (
                False,
                required,
                f"Permission '{required}' not allowed in {environment}. "
                f"Requires human approval."
            )

    except ValueError as e:
        return False, AIPermission.VIEW, str(e)


def can_auto_approve(
    action: str,
    environment: str = "production",
) -> bool:
    """Check if an action can be auto-approved in an environment.

    Args:
        action: Action to check
        environment: Environment to check against

    Returns:
        True if action can be auto-approved
    """
    allowed, _, _ = check_permission(action, environment)
    return allowed


def get_permission_summary(environment: str = "production") -> dict:
    """Get a summary of permissions for an environment.

    Args:
        environment: Environment name

    Returns:
        Dictionary with permission summary
    """
    permissions = get_ai_permission_matrix(environment)

    # Count by risk level
    risk_counts = {"safe": 0, "low": 0, "medium": 0, "high": 0, "critical": 0}

    for perm in permissions:
        risk = get_action_risk_level(perm)
        risk_counts[risk] += 1

    return {
        "environment": environment,
        "total_permissions": len(permissions),
        "permissions": [p.value for p in permissions],
        "risk_breakdown": risk_counts,
    }
