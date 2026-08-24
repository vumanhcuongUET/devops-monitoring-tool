"""Audit logging models for Chain of Thought and execution history."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class AuditEventType(str, Enum):
    """Types of audit events."""

    ACTION_CREATED = "action_created"
    ACTION_APPROVED = "action_approved"
    ACTION_REJECTED = "action_rejected"
    ACTION_EXECUTED = "action_executed"
    ACTION_FAILED = "action_failed"
    ACTION_CANCELLED = "action_cancelled"
    CHAIN_OF_THOUGHT = "chain_of_thought"
    CONTEXT_COLLECTED = "context_collected"
    COMMAND_PARSED = "command_parsed"
    VALIDATION_CHECK = "validation_check"
    CHAIN_LIMIT_EXCEEDED = "chain_limit_exceeded"  # Action blocked due to chain limit
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"  # Action blocked due to rate limit
    COOLDOWN_ACTIVE = "cooldown_active"  # Action blocked due to cooldown period


class ChainOfThoughtEntry(BaseModel):
    """A single step in the AI's reasoning chain."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    step_number: int = Field(..., description="Step number in the chain")
    thought: str = Field(..., description="The reasoning step")
    data: Optional[dict[str, Any]] = Field(None, description="Supporting data for this step")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence in this reasoning")


class AuditEntry(BaseModel):
    """An audit log entry tracking all important events."""

    # Core fields
    id: str = Field(..., description="Unique audit entry ID")
    event_type: AuditEventType = Field(..., description="Type of event")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When the event occurred")

    # Actor
    user: Optional[str] = Field(None, description="User who initiated the event (if applicable)")
    service: str = Field(default="system", description="Service/component that generated the event")

    # Related entities
    action_id: Optional[str] = Field(None, description="Related action ID")
    triage_card_id: Optional[str] = Field(None, description="Related Triage Card ID")
    project: Optional[str] = Field(None, description="Related project name")

    # Event details
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific details"
    )

    # Chain of Thought (for AI-generated actions)
    chain_of_thought: Optional[list[ChainOfThoughtEntry]] = Field(
        None,
        description="AI reasoning chain (if applicable)"
    )

    # Execution details
    execution_duration_seconds: Optional[float] = Field(
        None,
        description="Duration of execution (if applicable)"
    )
    success: Optional[bool] = Field(None, description="Whether the operation succeeded")

    # Security context
    ip_address: Optional[str] = Field(None, description="IP address of the requestor")
    user_agent: Optional[str] = Field(None, description="User agent string")
    session_id: Optional[str] = Field(None, description="Session identifier")

    # Metadata
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )


class AuditLogQuery(BaseModel):
    """Query parameters for filtering audit logs."""

    event_types: Optional[list[AuditEventType]] = None
    action_id: Optional[str] = None
    triage_card_id: Optional[str] = None
    project: Optional[str] = None
    user: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class AuditLogResponse(BaseModel):
    """Response for audit log queries."""

    total: int
    entries: list[AuditEntry]
    has_more: bool
