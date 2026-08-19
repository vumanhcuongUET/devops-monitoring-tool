"""Governance Package for Phase 3: RBAC and Policy Management.

This package contains:
- AI RBAC: Environment-based permissions for AI agents
- Permission checker: Validate AI actions against permissions
- Service accounts: K8s service account management
- OPA integration: Policy as Code validation
"""

from app.governance.ai_rbac import (
    AIPermission,
    ENVIRONMENT_PERMISSIONS,
    get_ai_permission_matrix,
)
from app.governance.permission_checker import (
    AIPermissionChecker,
    get_permission_checker,
)
from app.governance.opa_client import (
    PolicyDecision,
    PolicyEvaluationResult,
    PolicyViolation,
    OPAClient,
    get_opa_client,
)

__all__ = [
    "AIPermission",
    "ENVIRONMENT_PERMISSIONS",
    "get_ai_permission_matrix",
    "AIPermissionChecker",
    "get_permission_checker",
    "PolicyDecision",
    "PolicyEvaluationResult",
    "PolicyViolation",
    "OPAClient",
    "get_opa_client",
]
