"""
Triage Card Schema - Standardized output format for AI-generated incident analysis.

This schema defines the structure of AI-generated incident reports (Triage Cards)
that help DevOps teams quickly understand and respond to system issues.

Based on the strategic roadmap: docs/chien_luoc_tong_the.md (Giai đoạn 1)
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SeverityLevel(str, Enum):
    """Severity level for incidents and findings."""
    CRITICAL = "critical"  # Requires immediate action (P0)
    HIGH = "high"  # Urgent, affects production (P1)
    MEDIUM = "medium"  # Important but not urgent (P2)
    LOW = "low"  # Minor issue (P3)
    INFO = "info"  # Informational only


class FindingType(str, Enum):
    """Type of finding or issue detected."""
    ROOT_CAUSE = "root_cause"  # Likely root cause of the incident
    SYMPTOM = "symptom"  # Observable symptom
    CONTRIBUTING_FACTOR = "contributing_factor"  # May have contributed
    ANOMALY = "anomaly"  # Unusual pattern detected
    CONFIGURATION_ISSUE = "configuration_issue"  # Config problem
    DEPENDENCY_ISSUE = "dependency_issue"  # External dependency problem


class Finding(BaseModel):
    """A single finding or observation in the incident analysis."""
    type: FindingType = Field(..., description="Type of finding")
    title: str = Field(..., description="Brief title of the finding")
    description: str = Field(..., description="Detailed description")
    severity: SeverityLevel = Field(..., description="Severity level")
    source: str = Field(..., description="Data source (e.g., 'elasticsearch', 'prometheus', 'kubernetes')")
    evidence: Optional[str] = Field(None, description="Supporting evidence or data points")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence score (0-1)")


class Recommendation(BaseModel):
    """An action recommendation for incident response."""
    priority: int = Field(..., ge=1, le=10, description="Execution priority (1=highest)")
    action: str = Field(..., description="Action description (what to do)")
    command: Optional[str] = Field(None, description="Suggested command or API call")
    reason: str = Field(..., description="Why this action is recommended")
    risk: SeverityLevel = Field(..., description="Risk level if not taken")
    estimated_impact: Optional[str] = Field(None, description="Expected impact of the action")


class TriageCard(BaseModel):
    """
    Complete Triage Card for incident analysis.

    This is the standardized output format that AI agents generate when
    analyzing incidents. It provides a structured view of the situation,
    findings, and recommended actions.
    """

    # Metadata
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="When this card was generated")
    project: str = Field(..., description="Project or service name")
    incident_id: Optional[str] = Field(None, description="Incident or alert ID")

    # Summary
    summary: str = Field(..., description="One-paragraph executive summary")
    severity: SeverityLevel = Field(..., description="Overall severity assessment")
    status: str = Field(default="investigating", description="Current status (investigating, mitigating, resolved)")

    # Time context
    time_window_start: Optional[datetime] = Field(None, description="Analysis window start")
    time_window_end: Optional[datetime] = Field(None, description="Analysis window end")

    # Findings - what the AI discovered
    findings: list[Finding] = Field(default_factory=list, description="List of findings and observations")

    # Recommendations - what to do
    recommendations: list[Recommendation] = Field(
        default_factory=list, description="Action recommendations in priority order"
    )

    # Additional context
    related_alerts: list[str] = Field(default_factory=list, description="Related alert IDs")
    affected_services: list[str] = Field(default_factory=list, description="Services potentially affected")

    # AI metadata
    model_used: Optional[str] = Field(None, description="AI model used for analysis")
    tokens_used: Optional[int] = Field(None, description="Tokens consumed for generation")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class TriageCardRequest(BaseModel):
    """Request schema for generating a Triage Card."""
    project: str = Field(..., description="Project or service name")
    incident_id: Optional[str] = Field(None, description="Incident or alert ID")
    alert_message: Optional[str] = Field(None, description="Alert message or description")
    time_range_minutes: int = Field(default=60, description="Time range to analyze (minutes)")
    include_recommendations: bool = Field(default=True, description="Whether to include action recommendations")
    severity_threshold: SeverityLevel = Field(
        default=SeverityLevel.MEDIUM, description="Minimum severity to include in findings"
    )


class TriageCardResponse(BaseModel):
    """Response schema for Triage Card generation."""
    success: bool
    triage_card: Optional[TriageCard] = None
    error: Optional[str] = None
    debug_info: Optional[dict] = None  # For debugging, includes raw LLM response, etc.
