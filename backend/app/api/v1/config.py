"""
Configuration Management API Endpoints

Provides REST API for configuration management including:
- Configuration CRUD operations
- Version management and rollback
- Schema validation
- Audit trail
- GitOps operations
"""

import logging
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from app.config import (
    AuditAction,
    AuditLogger,
    ChangeType,
    ConfigSecurity,
    ConfigType,
    ConfigValidator,
    ConfigVersionManager,
    GitOpsManager,
)

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/api/v1/config", tags=["configuration"])

# Global instances (set via dependency injection)
_validator: ConfigValidator | None = None
_version_manager: ConfigVersionManager | None = None
_git_ops: GitOpsManager | None = None
_audit_logger: AuditLogger | None = None
_security: ConfigSecurity | None = None


def set_config_instances(
    validator: ConfigValidator,
    version_manager: ConfigVersionManager,
    git_ops: GitOpsManager | None = None,
    audit_logger: AuditLogger | None = None,
    security: ConfigSecurity | None = None
):
    """Set global instances for dependency injection."""
    global _validator, _version_manager, _git_ops, _audit_logger, _security
    _validator = validator
    _version_manager = version_manager
    _git_ops = git_ops
    _audit_logger = audit_logger
    _security = security


# Request/Response Models

class ConfigValidationRequest(BaseModel):
    """Request for configuration validation."""
    config_type: str = Field(..., description="Type of configuration to validate")
    config: dict[str, Any] = Field(..., description="Configuration data")


class ConfigValidationResponse(BaseModel):
    """Response from configuration validation."""
    is_valid: bool
    errors: list[str] = []
    warnings: list[str] = []


class VersionCreateRequest(BaseModel):
    """Request for version creation."""
    project: str = Field(..., description="Project name")
    config: dict[str, Any] = Field(..., description="Configuration data")
    author: str = Field(..., description="Author name")
    message: str = Field(..., description="Commit message")
    change_type: str = Field(default="update", description="Type of change")


class VersionRollbackRequest(BaseModel):
    """Request for version rollback."""
    project: str = Field(..., description="Project name")
    target_version: str = Field(..., description="Version to rollback to")
    author: str = Field(..., description="Author name")
    reason: str = Field(..., description="Reason for rollback")


class VersionDiffRequest(BaseModel):
    """Request for version diff."""
    project: str = Field(..., description="Project name")
    version_a: str = Field(..., description="First version")
    version_b: str = Field(..., description="Second version")


class GitBranchCreateRequest(BaseModel):
    """Request for creating Git branch."""
    project: str = Field(..., description="Project name")
    author: str = Field(..., description="Author name")
    base_branch: str = Field(default="develop", description="Base branch")


class PullRequestCreateRequest(BaseModel):
    """Request for creating pull request."""
    project: str = Field(..., description="Project name")
    branch_name: str = Field(..., description="Source branch")
    title: str = Field(..., description="PR title")
    description: str = Field(..., description="PR description")
    base_branch: str = Field(default="develop", description="Target branch")


# Endpoints

@router.post("/validate", response_model=ConfigValidationResponse)
async def validate_configuration(request: ConfigValidationRequest):
    """Validate configuration against schema.

    Args:
        request: Validation request with config type and data

    Returns:
        Validation result with errors and warnings
    """
    try:
        config_type = ConfigType(request.config_type)

        if not _validator:
            raise HTTPException(status_code=500, detail="Validator not initialized")

        result = await _validator.validate_config(
            config=request.config,
            config_type=config_type
        )

        # Log validation
        if _audit_logger:
            await _audit_logger.log(
                action=AuditAction.CONFIG_VALIDATE,
                project=request.config.get("project", {}).get("name", "unknown"),
                user="api",  # Use authenticated user in production
                details={"config_type": request.config_type, "is_valid": result.is_valid}
            )

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid config type: {e}")
    except Exception as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/versions")
async def create_version(request: VersionCreateRequest):
    """Create a new configuration version.

    Args:
        request: Version creation request

    Returns:
        Created version details
    """
    try:
        if not _version_manager:
            raise HTTPException(status_code=500, detail="Version manager not initialized")

        change_type = ChangeType(request.change_type)

        version = await _version_manager.create_version(
            project=request.project,
            config=request.config,
            author=request.author,
            message=request.message,
            change_type=change_type,
            commit_to_git=True
        )

        # Log version creation
        if _audit_logger:
            await _audit_logger.log(
                action=AuditAction.VERSION_CREATE,
                project=request.project,
                user=request.author,
                details={
                    "version": version.version,
                    "change_type": request.change_type,
                    "checksum": version.checksum
                }
            )

        return {
            "version": version.version,
            "timestamp": version.timestamp.isoformat(),
            "checksum": version.checksum,
            "author": version.author,
            "message": version.message,
            "change_type": version.change_type.value,
            "size_bytes": version.size_bytes
        }

    except Exception as e:
        logger.error(f"Version creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/versions/{project}")
async def list_versions(
    project: str = Path(..., description="Project name"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum versions to return"),
    offset: int = Query(0, ge=0, description="Pagination offset")
):
    """List versions for a project.

    Args:
        project: Project name
        limit: Maximum number of versions
        offset: Pagination offset

    Returns:
        List of version summaries
    """
    try:
        if not _version_manager:
            raise HTTPException(status_code=500, detail="Version manager not initialized")

        versions = await _version_manager.list_versions(
            project=project,
            limit=limit,
            offset=offset
        )

        return {"project": project, "versions": versions, "count": len(versions)}

    except Exception as e:
        logger.error(f"Version list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/versions/rollback")
async def rollback_version(request: VersionRollbackRequest):
    """Rollback to a specific version.

    Args:
        request: Rollback request

    Returns:
        New rollback version details
    """
    try:
        if not _version_manager:
            raise HTTPException(status_code=500, detail="Version manager not initialized")

        version = await _version_manager.rollback(
            project=request.project,
            target_version=request.target_version,
            author=request.author,
            reason=request.reason
        )

        # Log rollback
        if _audit_logger:
            await _audit_logger.log(
                action=AuditAction.VERSION_ROLLBACK,
                project=request.project,
                user=request.author,
                details={
                    "from_version": request.target_version,
                    "new_version": version.version,
                    "reason": request.reason
                }
            )

        return {
            "rollback_to": request.target_version,
            "new_version": version.version,
            "timestamp": version.timestamp.isoformat(),
            "message": version.message
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Rollback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/versions/diff")
async def diff_versions(request: VersionDiffRequest):
    """Compare two versions.

    Args:
        request: Diff request

    Returns:
        Version differences
    """
    try:
        if not _version_manager:
            raise HTTPException(status_code=500, detail="Version manager not initialized")

        diff = await _version_manager.diff_versions(
            project=request.project,
            version_a=request.version_a,
            version_b=request.version_b
        )

        return diff

    except Exception as e:
        logger.error(f"Diff error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/versions/{project}/history")
async def get_version_history(
    project: str = Path(..., description="Project name"),
    since: date | None = Query(None, description="Start date"),
    until: date | None = Query(None, description="End date")
):
    """Get version history for a project within a time range.

    Args:
        project: Project name
        since: Start date
        until: End date

    Returns:
        List of versions in range
    """
    try:
        if not _version_manager:
            raise HTTPException(status_code=500, detail="Version manager not initialized")

        versions = await _version_manager.get_version_history(
            project=project,
            since=since,
            until=until
        )

        return {
            "project": project,
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "versions": [v.to_dict() for v in versions],
            "count": len(versions)
        }

    except Exception as e:
        logger.error(f"Version history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit/trail")
async def get_audit_trail(
    project: str | None = Query(None, description="Filter by project"),
    start_date: date | None = Query(None, description="Start date"),
    end_date: date | None = Query(None, description="End date"),
    action: str | None = Query(None, description="Filter by action"),
    user: str | None = Query(None, description="Filter by user"),
    limit: int = Query(1000, ge=1, le=10000, description="Maximum entries"),
    offset: int = Query(0, ge=0, description="Pagination offset")
):
    """Get audit trail with filtering options.

    Args:
        project: Filter by project
        start_date: Start date
        end_date: End date
        action: Filter by action
        user: Filter by user
        limit: Maximum entries
        offset: Pagination offset

    Returns:
        List of audit entries
    """
    try:
        if not _audit_logger:
            raise HTTPException(status_code=500, detail="Audit logger not initialized")

        audit_action = AuditAction(action) if action else None

        entries = await _audit_logger.get_audit_trail(
            project=project,
            start_date=start_date,
            end_date=end_date,
            action=audit_action,
            user=user,
            limit=limit,
            offset=offset
        )

        return {
            "entries": entries,
            "count": len(entries),
            "filters": {
                "project": project,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "action": action,
                "user": user
            }
        }

    except Exception as e:
        logger.error(f"Audit trail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit/summary")
async def get_audit_summary(
    project: str | None = Query(None, description="Filter by project"),
    days: int = Query(7, ge=1, le=365, description="Number of days to summarize")
):
    """Get audit summary for a project.

    Args:
        project: Project name
        days: Number of days to summarize

    Returns:
        Summary statistics
    """
    try:
        if not _audit_logger:
            raise HTTPException(status_code=500, detail="Audit logger not initialized")

        summary = await _audit_logger.get_audit_summary(
            project=project,
            days=days
        )

        return summary

    except Exception as e:
        logger.error(f"Audit summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/git/branch")
async def create_git_branch(request: GitBranchCreateRequest):
    """Create a new Git branch for config changes.

    Args:
        request: Branch creation request

    Returns:
        Created branch details
    """
    try:
        if not _git_ops:
            raise HTTPException(status_code=500, detail="GitOps manager not initialized")

        branch_name = await _git_ops.create_feature_branch(
            project=request.project,
            author=request.author,
            base_branch=request.base_branch
        )

        return {
            "branch": branch_name,
            "base_branch": request.base_branch,
            "project": request.project,
            "author": request.author
        }

    except Exception as e:
        logger.error(f"Branch creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/git/pr")
async def create_pull_request(request: PullRequestCreateRequest):
    """Create a pull request for configuration changes.

    Args:
        request: PR creation request

    Returns:
        PR details
    """
    try:
        if not _git_ops:
            raise HTTPException(status_code=500, detail="GitOps manager not initialized")

        pr_info = await _git_ops.create_pull_request(
            project=request.project,
            branch_name=request.branch_name,
            title=request.title,
            description=request.description,
            base_branch=request.base_branch
        )

        return pr_info

    except Exception as e:
        logger.error(f"PR creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/git/sync")
async def sync_from_git(
    branch: str = Query("develop", description="Branch to sync from")
):
    """Sync configurations from Git.

    Args:
        branch: Branch to sync from

    Returns:
        Sync result with changed projects
    """
    try:
        if not _git_ops:
            raise HTTPException(status_code=500, detail="GitOps manager not initialized")

        changed = await _git_ops.sync_from_git(branch=branch)

        # Log sync
        if _audit_logger:
            await _audit_logger.log(
                action=AuditAction.GIT_PULL,
                project="global",
                user="system",
                details={"branch": branch, "changed_projects": changed}
            )

        return {
            "branch": branch,
            "changed_projects": changed,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Git sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/git/status")
async def get_git_status():
    """Get Git repository status.

    Returns:
        Repository status information
    """
    try:
        if not _git_ops:
            raise HTTPException(status_code=500, detail="GitOps manager not initialized")

        status = await _git_ops.get_repo_status()

        return status

    except Exception as e:
        logger.error(f"Git status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/security/scan")
async def scan_config_for_secrets(config: dict[str, Any]):
    """Scan configuration for potential secrets.

    Args:
        config: Configuration to scan

    Returns:
        Scan results with secret field locations
    """
    global _security
    try:
        if not _security:
            # Create security instance if not set
            _security = ConfigSecurity()

        secrets = _security.scan_for_secrets(config)

        return {
            "total_secrets": sum(len(v) for v in secrets.values()),
            "categories": secrets
        }

    except Exception as e:
        logger.error(f"Security scan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/security/sanitize")
async def sanitize_config(
    config: dict[str, Any],
    level: str = Query("internal", description="Security level (public, internal, confidential)")
):
    """Sanitize configuration for safe display.

    Args:
        config: Configuration to sanitize
        level: Security level

    Returns:
        Sanitized configuration
    """
    try:
        from app.config.security import SecurityLevel

        global _security
        if not _security:
            _security = ConfigSecurity()

        security_level = SecurityLevel(level)
        sanitized = _security.sanitize_config(config, security_level)

        return {"config": sanitized, "level": level}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Sanitize error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def config_health():
    """Get configuration module health status.

    Returns:
        Health status of all config components
    """
    components = {
        "validator": _validator is not None,
        "version_manager": _version_manager is not None,
        "git_ops": _git_ops is not None,
        "audit_logger": _audit_logger is not None,
        "security": _security is not None
    }

    all_healthy = all(components.values())

    return {
        "status": "healthy" if all_healthy else "degraded",
        "components": components
    }
