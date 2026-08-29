"""
Agents API - Multi-agent AI analysis endpoints (Phase 10 Sprint 3).

Exposes the AgentOrchestrator for comprehensive incident analysis:
- POST /api/v1/agents/analyze   Run multi-agent analysis on a context
- GET  /api/v1/agents/health    Health status of all specialized agents
- GET  /api/v1/agents/history   Recent execution history

Orchestrator is injected from the FastAPI lifespan via set_agent_instances(),
matching the optimization/config API module pattern.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.agents.orchestrator import AgentOrchestrator
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])

# Injected from lifespan (see main.py)
_orchestrator: Optional[AgentOrchestrator] = None

VALID_AGENTS = ["log", "metrics", "k8s", "cost", "security", "performance"]
MAX_CONTEXT_BYTES = 512 * 1024  # 512KB payload guard
MAX_CONTEXT_KEYS = 50


def set_agent_instances(orchestrator: Optional[AgentOrchestrator]) -> None:
    """Inject the orchestrator instance from the application lifespan."""
    global _orchestrator
    _orchestrator = orchestrator


class AgentAnalysisRequest(BaseModel):
    """Request body for multi-agent analysis."""

    context: dict[str, Any] = Field(
        ...,
        description="Analysis context (logs, metrics, k8s_state, resources, security_data, traces)",
    )
    agents: Optional[list[str]] = Field(
        None,
        description=f"Specific agents to run (None = auto-select). Valid: {VALID_AGENTS}",
    )
    consensus_threshold: float = Field(
        0.6,
        ge=0.0,
        le=1.0,
        description="Minimum confidence below which consensus voting triggers",
    )

    @field_validator("agents")
    @classmethod
    def validate_agents(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return None
        invalid = [a for a in v if a not in VALID_AGENTS]
        if invalid:
            raise ValueError(
                f"Unknown agents: {invalid}. Valid agents: {VALID_AGENTS}"
            )
        return v


@router.post("/analyze")
async def analyze(request: AgentAnalysisRequest) -> dict:
    """Run multi-agent analysis over the provided context.

    Agents are auto-selected based on context keys unless `agents` is given.
    Results are aggregated with prioritized recommendations; consensus
    voting runs when overall confidence is low or recommendations conflict.
    """
    if _orchestrator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent orchestrator not initialized",
        )

    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANTHROPIC_API_KEY not configured - agents cannot query Claude",
        )

    # Payload guards: bound context size and key count
    try:
        context_size = len(json.dumps(request.context, default=str))
    except (TypeError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Context is not JSON-serializable: {e}",
        )
    if context_size > MAX_CONTEXT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Context too large ({context_size} bytes, max {MAX_CONTEXT_BYTES})",
        )
    if len(request.context) > MAX_CONTEXT_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many context keys ({len(request.context)}, max {MAX_CONTEXT_KEYS})",
        )

    try:
        result = await _orchestrator.analyze(
            request.context,
            agents=request.agents,
            consensus_threshold=request.consensus_threshold,
        )
    except Exception as e:
        logger.exception("Multi-agent analysis failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {type(e).__name__}",
        )

    if "error" in result and not result.get("agents_used"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"],
        )
    return result


@router.get("/health")
async def agent_health() -> dict:
    """Health status of every specialized agent."""
    if _orchestrator is None:
        return {
            "orchestrator": "unavailable",
            "agents": {},
            "total_agents": 0,
            "timestamp": datetime.utcnow().isoformat(),
        }
    return await _orchestrator.health_check()


@router.get("/history")
async def analysis_history() -> dict:
    """Recent agent execution history (last 100 analyses)."""
    if _orchestrator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent orchestrator not initialized",
        )
    return {
        "executions": _orchestrator.get_execution_history(),
        "timestamp": datetime.utcnow().isoformat(),
    }
