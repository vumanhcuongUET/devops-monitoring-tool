"""Action and Approval models for Phase 2: Human-in-the-loop & Action Proposer."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CommandType(str, Enum):
    """Types of commands that can be executed."""

    KUBECTL = "kubectl"
    HELM = "helm"
    ARGOCD = "argocd"
    SCRIPT = "script"
    API = "api"


class ActionStatus(str, Enum):
    """Status of an action through its lifecycle."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskLevel(str, Enum):
    """Risk level of executing an action."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    SAFE = "safe"


class CommandParams(BaseModel):
    """Parsed parameters from a command."""

    command_type: CommandType
    resource_type: str | None = None  # e.g., "pod", "deployment", "service"
    resource_name: str | None = None
    namespace: str | None = None
    action: str | None = None  # e.g., "get", "delete", "restart", "scale"
    flags: dict[str, str] = Field(default_factory=dict)
    args: list[str] = Field(default_factory=list)


class ExecutionResult(BaseModel):
    """Result of executing an action."""

    success: bool
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Action(BaseModel):
    """An executable action derived from a Triage Card recommendation."""

    # Core identification
    id: str = Field(..., description="Unique action ID")
    triage_card_id: str | None = Field(None, description="Source Triage Card ID")
    recommendation_id: str | None = Field(None, description="Source recommendation ID")

    # Command details
    command_type: CommandType = Field(..., description="Type of command")
    command: str = Field(..., description="Original command string")
    parsed_params: CommandParams = Field(..., description="Parsed command parameters")

    # Metadata
    project: str = Field(..., description="Project/service name")
    title: str = Field(..., description="Human-readable action title")
    description: str = Field(..., description="Detailed description of what this does")

    # Risk assessment
    risk_level: RiskLevel = Field(default=RiskLevel.MEDIUM, description="Risk level")
    estimated_impact: str = Field(default="", description="Expected impact of execution")

    # Approval state
    status: ActionStatus = Field(default=ActionStatus.PENDING, description="Current status")
    approved_by: str | None = Field(None, description="User who approved (if applicable)")
    approved_at: datetime | None = Field(None, description="Approval timestamp")
    rejected_by: str | None = Field(None, description="User who rejected (if applicable)")
    rejected_at: datetime | None = Field(None, description="Rejection timestamp")
    rejection_reason: str | None = Field(None, description="Reason for rejection")

    # Execution
    executed_by: str | None = Field(None, description="User who triggered execution")
    executed_at: datetime | None = Field(None, description="Execution timestamp")
    execution_result: ExecutionResult | None = Field(None, description="Execution output")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")

    # Additional context
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context")


class CreateActionRequest(BaseModel):
    """Request to create an action from a Triage Card recommendation."""

    triage_card_id: str = Field(..., description="Source Triage Card ID")
    recommendation_id: str = Field(..., description="Recommendation to convert")
    project: str = Field(..., description="Project/service name")


class ApproveActionRequest(BaseModel):
    """Request to approve an action."""

    approved_by: str = Field(..., description="User approving the action")
    comment: str | None = Field(None, description="Optional approval comment")


class RejectActionRequest(BaseModel):
    """Request to reject an action."""

    rejected_by: str = Field(..., description="User rejecting the action")
    reason: str = Field(..., description="Reason for rejection")


class ExecuteActionRequest(BaseModel):
    """Request to execute an approved action."""

    executed_by: str = Field(..., description="User triggering execution")
    dry_run: bool = Field(default=False, description="If true, validate but don't execute")


class ActionListResponse(BaseModel):
    """Response for listing actions."""

    total: int
    pending: int
    approved: int
    rejected: int
    executed: int
    failed: int
    actions: list[Action]
