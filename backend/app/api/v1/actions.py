"""Actions API endpoints for Phase 2: Human-in-the-loop & Action Proposer."""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.actions.engine import get_action_engine
from app.api.ws.live import manager
from app.models.actions import (
    Action,
    ActionListResponse,
    ActionStatus,
    ApproveActionRequest,
    CreateActionRequest,
    ExecuteActionRequest,
    RejectActionRequest,
)

router = APIRouter(prefix="/actions", tags=["actions"])
logger = logging.getLogger(__name__)


# Response models
class ActionResponse(BaseModel):
    """Response wrapper for action operations."""

    success: bool
    action: Action | None = None
    error: str | None = None


class BulkActionResponse(BaseModel):
    """Response for bulk action creation."""

    success: bool
    actions: list[Action] = []
    total_created: int = 0
    errors: list[str] = []


@router.post("", response_model=ActionResponse, status_code=201)
async def create_action(request: Request, body: CreateActionRequest) -> ActionResponse:
    """Create an action from a Triage Card recommendation.

    This endpoint converts a recommendation from a Triage Card into an executable action.
    The action is validated against project RBAC policies and may require approval.
    """
    try:
        engine = get_action_engine()

        # Get the Triage Card (would load from store in real implementation)
        # For now, we'll create a mock recommendation
        from app.models.triage_card import Recommendation, SeverityLevel

        mock_recommendation = Recommendation(
            priority=1,
            action="Mock action for testing",
            command="kubectl get pods",
            reason="Testing action creation",
            risk=SeverityLevel.LOW,
            estimated_impact="No impact (read-only)",
        )

        # Create the action
        action = await engine.create_action_from_recommendation(
            request=body,
            recommendation=mock_recommendation,
        )

        # Broadcast WebSocket event
        await manager.broadcast({
            "type": "action_created",
            "data": action.model_dump(),
        })

        return ActionResponse(success=True, action=action)

    except ValueError as e:
        logger.error(f"Failed to create action: {e}")
        return ActionResponse(success=False, error=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating action: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("", response_model=ActionListResponse)
async def list_actions(
    request: Request,
    project: str | None = None,
    status: ActionStatus | None = None,
    limit: int = 100,
) -> ActionListResponse:
    """List all actions with optional filtering.

    Query Parameters:
    - project: Filter by project name
    - status: Filter by action status
    - limit: Maximum number of actions to return (default: 100)
    """
    try:
        engine = get_action_engine()
        return await engine.list_actions(project=project, status=status, limit=limit)
    except Exception as e:
        logger.error(f"Failed to list actions: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{action_id}", response_model=ActionResponse)
async def get_action(request: Request, action_id: str) -> ActionResponse:
    """Get details of a specific action."""
    try:
        engine = get_action_engine()
        action_data = await engine.get_action(action_id)

        if not action_data:
            raise HTTPException(status_code=404, detail=f"Action {action_id} not found")

        return ActionResponse(success=True, action=Action(**action_data))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get action {action_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{action_id}/approve", response_model=ActionResponse)
async def approve_action(
    request: Request,
    action_id: str,
    body: ApproveActionRequest,
) -> ActionResponse:
    """Approve an action for execution.

    This approves an action that was in PENDING status, allowing it to be executed.
    """
    try:
        engine = get_action_engine()
        # Phase 13: authenticated identity wins over client-asserted body value
        user = getattr(request.state, "user", None)
        if user:
            if body.approved_by and body.approved_by != user:
                logger.warning(
                    "approved_by %r overridden by authenticated user %r",
                    body.approved_by, user,
                )
            body.approved_by = user
        action = await engine.approve_action(action_id, body, auth_user=user)

        # Broadcast WebSocket event
        await manager.broadcast({
            "type": "action_approved",
            "data": action.model_dump(),
        })

        return ActionResponse(success=True, action=action)

    except ValueError as e:
        logger.error(f"Failed to approve action {action_id}: {e}")
        return ActionResponse(success=False, error=str(e))
    except Exception as e:
        logger.error(f"Unexpected error approving action {action_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{action_id}/reject", response_model=ActionResponse)
async def reject_action(
    request: Request,
    action_id: str,
    body: RejectActionRequest,
) -> ActionResponse:
    """Reject an action.

    This rejects an action that was in PENDING status, preventing it from being executed.
    """
    try:
        engine = get_action_engine()
        # Phase 13: authenticated identity wins over client-asserted body value
        user = getattr(request.state, "user", None)
        if user:
            if body.rejected_by and body.rejected_by != user:
                logger.warning(
                    "rejected_by %r overridden by authenticated user %r",
                    body.rejected_by, user,
                )
            body.rejected_by = user
        action = await engine.reject_action(action_id, body, auth_user=user)

        # Broadcast WebSocket event
        await manager.broadcast({
            "type": "action_rejected",
            "data": action.model_dump(),
        })

        return ActionResponse(success=True, action=action)

    except ValueError as e:
        logger.error(f"Failed to reject action {action_id}: {e}")
        return ActionResponse(success=False, error=str(e))
    except Exception as e:
        logger.error(f"Unexpected error rejecting action {action_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{action_id}/execute", response_model=ActionResponse)
async def execute_action(
    request: Request,
    action_id: str,
    body: ExecuteActionRequest,
) -> ActionResponse:
    """Execute an approved action.

    This executes an action that has been approved. The command is run with appropriate
    safety constraints and the result is logged.
    """
    try:
        engine = get_action_engine()
        # Phase 13: authenticated identity wins over client-asserted body value
        user = getattr(request.state, "user", None)
        if user:
            if body.executed_by and body.executed_by != user:
                logger.warning(
                    "executed_by %r overridden by authenticated user %r",
                    body.executed_by, user,
                )
            body.executed_by = user
        action = await engine.execute_action(action_id, body, auth_user=user)

        # Broadcast WebSocket event
        await manager.broadcast({
            "type": "action_executed" if action.status == ActionStatus.EXECUTED else "action_failed",
            "data": action.model_dump(),
        })

        return ActionResponse(success=True, action=action)

    except ValueError as e:
        logger.error(f"Failed to execute action {action_id}: {e}")
        return ActionResponse(success=False, error=str(e))
    except Exception as e:
        logger.error(f"Unexpected error executing action {action_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/bulk", response_model=BulkActionResponse)
async def create_bulk_actions(
    request: Request,
    triage_card_id: str,
    project: str,
) -> BulkActionResponse:
    """Create actions from all recommendations in a Triage Card.

    This endpoint converts all recommendations from a Triage Card into actions.
    Useful for batch creating actions after incident analysis.
    """
    try:
        engine = get_action_engine()

        # Get the Triage Card (would load from store)
        # For now, create mock recommendations
        from app.models.triage_card import Recommendation, SeverityLevel

        mock_recommendations = [
            Recommendation(
                priority=1,
                action="Check pod status",
                command="kubectl get pods",
                reason="Verify pod health",
                risk=SeverityLevel.LOW,
                estimated_impact="No impact (read-only)",
            ),
            Recommendation(
                priority=2,
                action="Restart deployment",
                command="kubectl rollout restart deployment/api",
                reason="Restart to clear any transient issues",
                risk=SeverityLevel.HIGH,
                estimated_impact="Brief service interruption",
            ),
        ]

        actions = []
        errors = []

        for i, rec in enumerate(mock_recommendations):
            try:
                action = await engine.create_action_from_recommendation(
                    request=CreateActionRequest(
                        triage_card_id=triage_card_id,
                        recommendation_id=f"rec-{i}",
                        project=project,
                    ),
                    recommendation=rec,
                )
                actions.append(action)
            except Exception as e:
                errors.append(f"Failed to create action from recommendation {i}: {e}")

        # Broadcast WebSocket event
        if actions:
            await manager.broadcast({
                "type": "bulk_actions_created",
                "data": {"count": len(actions)},
            })

        return BulkActionResponse(
            success=len(actions) > 0,
            actions=actions,
            total_created=len(actions),
            errors=errors,
        )

    except Exception as e:
        logger.error(f"Failed to create bulk actions: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/stats/summary")
async def get_action_stats(request: Request) -> dict:
    """Get summary statistics about actions."""
    try:
        engine = get_action_engine()
        list_result = await engine.list_actions()

        return {
            "total": list_result.total,
            "pending": list_result.pending,
            "approved": list_result.approved,
            "rejected": list_result.rejected,
            "executed": list_result.executed,
            "failed": list_result.failed,
        }
    except Exception as e:
        logger.error(f"Failed to get action stats: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
