"""Context Registry models for project-specific configuration."""

from typing import Any

from pydantic import BaseModel, Field


class ClusterConfig(BaseModel):
    """Cluster configuration for a project."""

    name: str = Field(..., description="Cluster name")
    context: str | None = Field(None, description="Kubeconfig context")
    region: str | None = Field(None, description="Cloud region")
    platform: str = Field(default="kubernetes", description="Platform: kubernetes, ecs, etc.")


class NamespaceMapping(BaseModel):
    """Namespace mapping for different components."""

    app: str | None = Field(None, description="Application namespace")
    database: str | None = Field(None, description="Database namespace")
    monitoring: str | None = Field(None, description="Monitoring namespace")
    # Can add more as needed


class OwnerContact(BaseModel):
    """Contact information for a project owner."""

    user: str = Field(..., description="Username")
    email: str | None = Field(None, description="Email address")
    slack: str | None = Field(None, description="Slack user ID")
    teams: str | None = Field(None, description="Microsoft Teams ID")


class RbacConstraints(BaseModel):
    """RBAC constraints for actions."""

    allowed_actions: list[str] = Field(
        default_factory=list,
        description="Actions allowed without approval (e.g., kubectl_get, kubectl_describe)"
    )
    requires_approval: list[str] = Field(
        default_factory=list,
        description="Actions that require approval (e.g., kubectl_delete, kubectl_scale)"
    )
    forbidden_actions: list[str] = Field(
        default_factory=list,
        description="Actions that are never allowed"
    )
    max_restarts_per_hour: int = Field(
        default=5,
        description="Maximum number of restart actions allowed per hour"
    )
    requires_comment_for: list[str] = Field(
        default_factory=list,
        description="Actions that require a comment before approval"
    )


class ProjectConfig(BaseModel):
    """Project-specific configuration for context-aware actions."""

    name: str = Field(..., description="Project/service name")
    display_name: str | None = Field(None, description="Human-readable name")
    cluster: ClusterConfig = Field(..., description="Cluster configuration")
    namespaces: NamespaceMapping = Field(
        default_factory=NamespaceMapping,
        description="Namespace mappings"
    )
    owners: list[OwnerContact] = Field(
        default_factory=list,
        description="Project owners and their contacts"
    )
    rbac: RbacConstraints = Field(
        default_factory=RbacConstraints,
        description="RBAC constraints for actions"
    )
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Custom tags for categorization"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )


class RegistryConfig(BaseModel):
    """Top-level registry configuration."""

    projects: list[ProjectConfig] = Field(default_factory=list)
    default_cluster: ClusterConfig | None = Field(None, description="Default cluster if not specified")
    global_constraints: RbacConstraints | None = Field(
        None,
        description="Global RBAC constraints applied to all projects"
    )

    def get_project(self, name: str) -> ProjectConfig | None:
        """Get a project by name (None if not registered)."""
        return next((p for p in self.projects if p.name == name), None)
