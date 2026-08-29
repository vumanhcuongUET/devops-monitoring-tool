"""Governance Package for Phase 3: RBAC and Policy Management.

This package contains:
- AI RBAC: Environment-based permissions for AI agents
- Permission checker: Validate AI actions against permissions
- Service accounts: K8s service account management
- OPA integration: Policy as Code validation
"""

from app.governance.ai_rbac import (
    ENVIRONMENT_PERMISSIONS,
    AIPermission,
    get_ai_permission_matrix,
)
from app.governance.opa_client import (
    OPAClient,
    PolicyDecision,
    PolicyEvaluationResult,
    PolicyViolation,
    get_opa_client,
)
from app.governance.permission_checker import (
    AIPermissionChecker,
    get_permission_checker,
)

__all__ = [
    "ENVIRONMENT_PERMISSIONS",
    "AIPermission",
    "AIPermissionChecker",
    "OPAClient",
    "PolicyDecision",
    "PolicyEvaluationResult",
    "PolicyViolation",
    "get_ai_permission_matrix",
    "get_opa_client",
    "get_permission_checker",
]
