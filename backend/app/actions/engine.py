"""Action Engine for converting Triage Card recommendations into executable actions."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.actions.parser import get_command_parser
from app.actions.validator import get_command_validator, ValidationResult
from app.actions.executor import get_command_executor
from app.approvals.store import get_approval_tracker, get_approval_history
from app.audit.logger import get_audit_logger
from app.models.actions import (
    Action,
    ActionStatus,
    CommandType,
    CreateActionRequest,
    ApproveActionRequest,
    RejectActionRequest,
    ExecuteActionRequest,
    ExecutionResult,
    CommandParams,
    RiskLevel,
    ActionListResponse,
)
from app.models.triage_card import Recommendation
from app.registry.loader import get_registry

logger = logging.getLogger(__name__)


class ActionEngine:
    """Engine for managing action lifecycle: create, validate, approve, execute."""

    def __init__(self):
        self.parser = get_command_parser()
        self.validator = get_command_validator()
        self.executor = get_command_executor()
        self.approval_tracker = get_approval_tracker()
        self.approval_history = get_approval_history()
        self.audit_logger = get_audit_logger()
        self.registry = get_registry()

    async def create_action_from_recommendation(
        self,
        request: CreateActionRequest,
        recommendation: Recommendation,
    ) -> Action:
        """Create an Action from a Triage Card recommendation."""
        # Generate unique action ID
        action_id = str(uuid.uuid4())

        # Parse the command
        command = recommendation.command or ""
        parsed_params = self.parser.parse(command)

        # Validate the command
        validation = self.validator.validate(
            command=command,
            project=request.project,
        )

        # Determine risk level from validation
        risk_level = validation.risk_level
        if not validation.allowed:
            risk_level = RiskLevel.CRITICAL

        # Create the action
        action = Action(
            id=action_id,
            triage_card_id=request.triage_card_id,
            recommendation_id=request.recommendation_id,
            command_type=parsed_params.command_type,
            command=command,
            parsed_params=parsed_params,
            project=request.project,
            title=recommendation.action,
            description=recommendation.reason,
            risk_level=risk_level,
            estimated_impact=recommendation.estimated_impact or "",
            status=ActionStatus.PENDING if validation.requires_approval else ActionStatus.APPROVED,
            context={
                "validation": validation.to_dict(),
                "priority": recommendation.priority,
            },
        )

        # Log action creation
        self.audit_logger.log_action_created(
            action_id=action_id,
            triage_card_id=request.triage_card_id,
            project=request.project,
            command=command,
        )

        # Add to approval tracker
        self.approval_tracker.set_status(
            action_id=action_id,
            status=action.status,
        )

        # Add to history
        self.approval_history.add({
            "id": str(uuid.uuid4()),
            "action_id": action_id,
            "event": "created",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": {
                "command": command,
                "validation": validation.to_dict(),
            },
        })

        logger.info(f"Created action {action_id} for project {request.project}")
        return action

    async def approve_action(self, action_id: str, request: ApproveActionRequest) -> Action:
        """Approve an action for execution."""
        # Get current state
        state = self.approval_tracker.get(action_id)
        if not state:
            raise ValueError(f"Action {action_id} not found")

        if state.get("status") != ActionStatus.PENDING:
            raise ValueError(f"Action {action_id} is not pending (current: {state.get('status')})")

        # Update status
        self.approval_tracker.set_status(
            action_id=action_id,
            status=ActionStatus.APPROVED,
            user=request.approved_by,
        )

        # Log approval
        self.audit_logger.log_action_approved(
            action_id=action_id,
            approved_by=request.approved_by,
            comment=request.comment,
        )

        # Add to history
        self.approval_history.add({
            "id": str(uuid.uuid4()),
            "action_id": action_id,
            "event": "approved",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user": request.approved_by,
            "details": {"comment": request.comment} if request.comment else {},
        })

        logger.info(f"Action {action_id} approved by {request.approved_by}")
        # Return updated action (would load from store in real implementation)
        return Action(
            id=action_id,
            status=ActionStatus.APPROVED,
            approved_by=request.approved_by,
            approved_at=datetime.now(timezone.utc),
        )

    async def reject_action(self, action_id: str, request: RejectActionRequest) -> Action:
        """Reject an action."""
        # Get current state
        state = self.approval_tracker.get(action_id)
        if not state:
            raise ValueError(f"Action {action_id} not found")

        if state.get("status") != ActionStatus.PENDING:
            raise ValueError(f"Action {action_id} is not pending (current: {state.get('status')})")

        # Update status
        self.approval_tracker.set_status(
            action_id=action_id,
            status=ActionStatus.REJECTED,
            user=request.rejected_by,
            reason=request.reason,
        )

        # Log rejection
        self.audit_logger.log_action_rejected(
            action_id=action_id,
            rejected_by=request.rejected_by,
            reason=request.reason,
        )

        # Add to history
        self.approval_history.add({
            "id": str(uuid.uuid4()),
            "action_id": action_id,
            "event": "rejected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user": request.rejected_by,
            "details": {"reason": request.reason},
        })

        logger.info(f"Action {action_id} rejected by {request.rejected_by}: {request.reason}")
        return Action(
            id=action_id,
            status=ActionStatus.REJECTED,
            rejected_by=request.rejected_by,
            rejected_at=datetime.now(timezone.utc),
        )

    async def execute_action(self, action_id: str, request: ExecuteActionRequest) -> Action:
        """Execute an approved action."""
        # Get current state
        state = self.approval_tracker.get(action_id)
        if not state:
            raise ValueError(f"Action {action_id} not found")

        if state.get("status") != ActionStatus.APPROVED:
            raise ValueError(f"Action {action_id} is not approved (current: {state.get('status')})")

        # Get command from state
        command = state.get("command", "")
        if not command:
            raise ValueError(f"Action {action_id} has no command to execute")

        # Execute the command
        start_time = datetime.now(timezone.utc)
        try:
            result = await self.executor.execute(
                command=command,
                dry_run=request.dry_run,
            )
            success = result.success
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Update status based on result
            new_status = ActionStatus.EXECUTED if success else ActionStatus.FAILED
            self.approval_tracker.set_status(
                action_id=action_id,
                status=new_status,
                user=request.executed_by,
            )

            # Log execution
            self.audit_logger.log_action_executed(
                action_id=action_id,
                executed_by=request.executed_by,
                success=success,
                duration_seconds=duration,
                output=result.stdout if success else result.stderr,
            )

            # Add to history
            self.approval_history.add({
                "id": str(uuid.uuid4()),
                "action_id": action_id,
                "event": "executed" if success else "failed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user": request.executed_by,
                "details": {
                    "success": success,
                    "duration_seconds": duration,
                    "dry_run": request.dry_run,
                },
            })

            logger.info(f"Action {action_id} executed by {request.executed_by}: {'SUCCESS' if success else 'FAILED'}")

            return Action(
                id=action_id,
                status=new_status,
                executed_by=request.executed_by,
                executed_at=datetime.now(timezone.utc),
                execution_result=result,
            )

        except Exception as e:
            # Execution failed with exception
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.approval_tracker.set_status(
                action_id=action_id,
                status=ActionStatus.FAILED,
                user=request.executed_by,
            )

            # Log failure
            self.audit_logger.log_action_executed(
                action_id=action_id,
                executed_by=request.executed_by,
                success=False,
                duration_seconds=duration,
                output=str(e),
            )

            logger.error(f"Action {action_id} execution failed: {e}")
            raise

    def get_action(self, action_id: str) -> Optional[dict]:
        """Get action details."""
        state = self.approval_tracker.get(action_id)
        if not state:
            return None
        return state

    def list_actions(
        self,
        project: Optional[str] = None,
        status: Optional[ActionStatus] = None,
        limit: int = 100,
    ) -> ActionListResponse:
        """List actions with optional filters."""
        all_state = self.approval_tracker.get_all()

        # Filter by project
        if project:
            all_state = {
                aid: s for aid, s in all_state.items()
                if s.get("project") == project
            }

        # Filter by status
        if status:
            all_state = {
                aid: s for aid, s in all_state.items()
                if s.get("status") == status
            }

        # Count by status
        counts = {s: 0 for s in ActionStatus}
        for state in self.approval_tracker.get_all().values():
            status_val = state.get("status")
            if status_val in counts:
                counts[status_val] += 1

        # Convert to Action objects
        actions = []
        for action_id, state in list(all_state.items())[:limit]:
            actions.append(Action(id=action_id, **state))

        return ActionListResponse(
            total=len(actions),
            pending=counts[ActionStatus.PENDING],
            approved=counts[ActionStatus.APPROVED],
            rejected=counts[ActionStatus.REJECTED],
            executed=counts[ActionStatus.EXECUTED],
            failed=counts[ActionStatus.FAILED],
            actions=actions,
        )


# Singleton instance
_action_engine: Optional[ActionEngine] = None


def get_action_engine() -> ActionEngine:
    """Get or create the singleton ActionEngine instance."""
    global _action_engine
    if _action_engine is None:
        _action_engine = ActionEngine()
    return _action_engine
