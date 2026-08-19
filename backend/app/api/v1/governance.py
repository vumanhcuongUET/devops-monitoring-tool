"""Governance API endpoints for Phase 3: RBAC and Policy Management."""

from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Optional

from app.auth import api_key_auth
from app.governance.ai_rbac import get_ai_permission_matrix, get_permission_summary
from app.governance.permission_checker import get_permission_checker
from app.governance.opa_client import get_opa_client

router = APIRouter(prefix="/governance", tags=["governance"])


@router.get("/permissions")
async def list_permissions() -> dict[str, Any]:
    """List RBAC permission matrix.

    Returns:
        Dictionary with permission matrix for all environments
    """
    try:
        environments = ["development", "staging", "production"]
        permissions = {}

        for env in environments:
            permissions[env] = get_permission_summary(env)

        return {
            "environments": permissions,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/permissions/check")
async def check_permission(request: dict[str, Any]) -> dict[str, Any]:
    """Check if an action is allowed.

    Args:
        request: Permission check request
            - action: Action to check
            - environment: Environment to check against
            - project: Optional project name

    Returns:
        Dictionary with check result
    """
    try:
        action = request.get("action")
        environment = request.get("environment", "production")
        project = request.get("project")

        checker = get_permission_checker()
        result = checker.check(
            action=action,
            environment=environment,
            project=project,
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/policies/validate")
async def validate_policy(request: dict[str, Any]) -> dict[str, Any]:
    """Validate an action against OPA policies.

    Args:
        request: Policy validation request
            - action: Action to validate
            - project: Project name
            - environment: Environment name
            - user: Optional user

    Returns:
        Dictionary with policy decision
    """
    try:
        action = request.get("action", {})
        project = request.get("project", "")
        environment = request.get("environment", "production")
        user = request.get("user")

        if not project:
            raise HTTPException(status_code=400, detail="project is required")

        client = get_opa_client()
        result = await client.evaluate_action(
            action=action,
            project=project,
            environment=environment,
            user=user,
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/policies")
async def list_policies() -> dict[str, Any]:
    """List active OPA policies.

    Returns:
        Dictionary with policy list
    """
    try:
        client = get_opa_client()

        # This would query OPA for active policies
        # For now, return the defined policies
        policies = [
            {
                "id": "actions",
                "name": "Action Validation Policy",
                "description": "Validates actions against RBAC and business rules",
                "category": "actions",
                "enabled": True,
            },
            {
                "id": "resources",
                "name": "Resource Protection Policy",
                "description": "Protects critical resources from destructive actions",
                "category": "resources",
                "enabled": True,
            },
            {
                "id": "time_windows",
                "name": "Time Window Policy",
                "description": "Enforces time-based restrictions on actions",
                "category": "time_windows",
                "enabled": True,
            },
        ]

        return {
            "policies": policies,
            "total": len(policies),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/compliance")
async def get_compliance_status(
    project: Optional[str] = None,
    environment: str = "production",
) -> dict[str, Any]:
    """Get overall compliance status.

    Args:
        project: Optional project name
        environment: Environment to check

    Returns:
        Dictionary with compliance score and violations
    """
    try:
        client = get_opa_client()
        compliance = await client.check_compliance(
            project=project or "",
            environment=environment,
        )

        return compliance

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit")
async def get_audit_log(
    skill_id: Optional[str] = None,
    project: Optional[str] = None,
    environment: Optional[str] = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Get governance audit log.

    Args:
        skill_id: Optional skill filter
        project: Optional project filter
        environment: Optional environment filter
        limit: Maximum results

    Returns:
        Dictionary with audit log entries
    """
    try:
        checker = get_permission_checker()
        audit_log = checker.get_audit_log(
            limit=limit,
            project=project,
            environment=environment,
        )

        return {
            "audit_log": audit_log,
            "total": len(audit_log),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/service-account/{project}")
async def get_service_account_config(project: str) -> dict[str, Any]:
    """Get service account configuration for a project.

    Args:
        project: Project name

    Returns:
        Dictionary with service account configuration
    """
    try:
        from app.registry import get_registry

        registry = get_registry()
        project_config = registry.get_project(project)

        if not project_config:
            raise HTTPException(status_code=404, detail=f"Project {project} not found")

        environment = project_config.tags.get("environment", "production")

        # Map environment to service account
        sa_mapping = {
            "development": {
                "service_account": "ai-agent-dev-admin",
                "namespace": "ai-agents",
                "access_level": "admin",
            },
            "staging": {
                "service_account": "ai-agent-staging-operator",
                "namespace": "ai-agents",
                "access_level": "operator",
            },
            "production": {
                "service_account": "ai-agent-prod-viewer",
                "namespace": "ai-agents",
                "access_level": "read-only",
            },
        }

        sa_config = sa_mapping.get(environment, sa_mapping["production"])
        sa_config["environment"] = environment

        return sa_config

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
