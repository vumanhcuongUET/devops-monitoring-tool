"""Action Engine for converting Triage Card recommendations into executable actions."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.actions.parser import get_command_parser
from app.actions.validator import get_command_validator, ValidationResult
from app.actions.rate_limiter import get_rate_limiter, RateLimitConfig
from app.actions.impact_estimator import get_impact_estimator, ImpactEstimate, ImpactLevel
from app.actions.rollback_executor import get_rollback_executor, RollbackStatus
from app.actions.executor import get_command_executor
from app.actions.environment_executor import get_executor
from app.approvals.store import get_approval_tracker, get_approval_history
from app.audit.logger import get_audit_logger
from app.governance.permission_checker import get_permission_checker
from app.governance.ai_rbac import get_ai_permission_matrix, AIPermission
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
        self.permission_checker = get_permission_checker()
        self.env_aware_executor = get_executor()

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

        # Get environment from project configuration
        project_config = self.registry.get_project(request.project)
        environment = "production"  # Default
        if project_config and hasattr(project_config, "tags"):
            environment = project_config.tags.get("environment", "production")

        # Check permissions using RBAC (Phase 3 integration)
        permission_result = self.permission_checker.check_command(
            command=command,
            environment=environment,
            project=request.project,
        )

        # Determine risk level from validation and permission check
        risk_level = validation.risk_level
        if not validation.allowed or not permission_result.allowed:
            risk_level = RiskLevel.CRITICAL

        # Determine if approval is required
        requires_approval = (
            validation.requires_approval or
            permission_result.requires_approval
        )

        # High and Critical impact actions require approval (Phase 8 Day 7)
        if impact_estimate.impact_level in (ImpactLevel.HIGH, ImpactLevel.CRITICAL):
            requires_approval = True

        # Critical impact actions may require executive approval
        requires_executive_approval = impact_estimate.impact_level == ImpactLevel.CRITICAL

        # Estimate impact (Phase 8 Day 7)
        impact_estimator = get_impact_estimator()
        # Try to get k8s client for real impact estimation
        k8s_client = None
        try:
            from app.main import app_state
            if app_state and app_state.k8s_client:
                k8s_client = app_state.k8s_client
        except ImportError:
            pass

        impact_estimate = impact_estimator.estimate(
            action_id=action_id,
            command=command,
            k8s_client=k8s_client,
            dry_run=True,  # Use heuristics for now, can be configurable
        )

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
            status=ActionStatus.PENDING if requires_approval else ActionStatus.APPROVED,
            context={
                "validation": validation.to_dict(),
                "priority": recommendation.priority,
                "permission_check": permission_result.to_dict(),
                "environment": environment,
                "impact_estimate": {
                    "impact_level": impact_estimate.impact_level.value,
                    "total_affected_resources": impact_estimate.total_affected_resources,
                    "resource_impacts": [
                        {
                            "resource_type": r.resource_type,
                            "affected_count": r.affected_count,
                            "namespace": r.namespace,
                        }
                        for r in impact_estimate.resource_impacts
                    ],
                    "risk_factors": impact_estimate.risk_factors,
                    "recommendations": impact_estimate.recommendations,
                    "estimated_duration_seconds": impact_estimate.estimated_duration_seconds,
                },
                "requires_executive_approval": requires_executive_approval,
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
                "permission_check": permission_result.to_dict(),
            },
        })

        logger.info(
            f"Created action {action_id} for project {request.project} "
            f"(env={environment}, permission={permission_result.required_permission.value}, "
            f"allowed={permission_result.allowed})"
        )
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
        # Build action kwargs from state, filtering None values
        action_kwargs = {
            "id": action_id,
            "status": ActionStatus.APPROVED,
            "approved_by": request.approved_by,
            "approved_at": datetime.now(timezone.utc),
        }

        # Add optional fields from state if present
        if "command_type" in state:
            action_kwargs["command_type"] = state["command_type"]
        if "command" in state:
            action_kwargs["command"] = state["command"]
        if "parsed_params" in state and state["parsed_params"]:
            action_kwargs["parsed_params"] = state["parsed_params"]
        if "project" in state:
            action_kwargs["project"] = state["project"]
        if "title" in state:
            action_kwargs["title"] = state["title"]
        if "description" in state:
            action_kwargs["description"] = state["description"]
        if "triage_card_id" in state:
            action_kwargs["triage_card_id"] = state["triage_card_id"]
        if "recommendation_id" in state:
            action_kwargs["recommendation_id"] = state["recommendation_id"]
        if "risk_level" in state:
            action_kwargs["risk_level"] = state["risk_level"]
        if "estimated_impact" in state:
            action_kwargs["estimated_impact"] = state["estimated_impact"]
        if "created_at" in state:
            action_kwargs["created_at"] = state["created_at"]
        if "context" in state:
            action_kwargs["context"] = state["context"]

        return Action(**action_kwargs)

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
        # Build action kwargs from state, filtering None values
        action_kwargs = {
            "id": action_id,
            "status": ActionStatus.REJECTED,
            "rejected_by": request.rejected_by,
            "rejected_at": datetime.now(timezone.utc),
            "rejection_reason": request.reason,
        }

        # Add optional fields from state if present
        if "command_type" in state:
            action_kwargs["command_type"] = state["command_type"]
        if "command" in state:
            action_kwargs["command"] = state["command"]
        if "parsed_params" in state and state["parsed_params"]:
            action_kwargs["parsed_params"] = state["parsed_params"]
        if "project" in state:
            action_kwargs["project"] = state["project"]
        if "title" in state:
            action_kwargs["title"] = state["title"]
        if "description" in state:
            action_kwargs["description"] = state["description"]
        if "triage_card_id" in state:
            action_kwargs["triage_card_id"] = state["triage_card_id"]
        if "recommendation_id" in state:
            action_kwargs["recommendation_id"] = state["recommendation_id"]
        if "risk_level" in state:
            action_kwargs["risk_level"] = state["risk_level"]
        if "estimated_impact" in state:
            action_kwargs["estimated_impact"] = state["estimated_impact"]
        if "created_at" in state:
            action_kwargs["created_at"] = state["created_at"]
        if "context" in state:
            action_kwargs["context"] = state["context"]

        return Action(**action_kwargs)

    async def execute_action(self, action_id: str, request: ExecuteActionRequest) -> Action:
        """Execute an approved action with RBAC permission checking."""
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

        # Get environment from context
        context = state.get("context", {})
        environment = context.get("environment", "production")
        project = state.get("project", "")

        # Parse command to get action type for rate limiting
        parsed_params = state.get("parsed_params")
        action_type = parsed_params.action if parsed_params else "unknown"

        # Check rate limits before execution (Phase 8)
        rate_limiter = get_rate_limiter()
        rate_allowed, rate_reason, rate_metadata = rate_limiter.check(
            project=project,
            action_type=action_type,
            user=request.executed_by,
        )

        if not rate_allowed:
            # Log the rate limit event for audit trail (Phase 8 Day 6)
            chain_count = rate_metadata.get("chain_count", 0)
            chain_limit = rate_metadata.get("chain_limit", 0)

            # Determine which type of rate limit event to log
            if "chain limit" in rate_reason.lower():
                self.audit_logger.log_chain_limit_exceeded(
                    action_id=action_id,
                    project=project,
                    action_type=action_type,
                    chain_count=chain_count,
                    chain_limit=chain_limit,
                    user=request.executed_by,
                )
            elif "cooldown" in rate_reason.lower():
                cooldown_remaining = rate_metadata.get("cooldown_remaining", 0)
                self.audit_logger.log_cooldown_active(
                    action_id=action_id,
                    project=project,
                    action_type=action_type,
                    cooldown_remaining=cooldown_remaining,
                    user=request.executed_by,
                )
            else:  # Rate limit exceeded
                rate_limit = rate_metadata.get("limit", 0)
                self.audit_logger.log_rate_limit_exceeded(
                    action_id=action_id,
                    project=project,
                    action_type=action_type,
                    rate_limit=rate_limit,
                    user=request.executed_by,
                )

            raise PermissionError(
                f"Rate limit exceeded for action {action_id}: {rate_reason}"
            )

        # Final permission check before execution (Phase 3 integration)
        permission_result = self.permission_checker.check_command(
            command=command,
            environment=environment,
            project=project,
            user=request.executed_by,
        )

        if not permission_result.allowed:
            raise PermissionError(
                f"Permission denied for action {action_id}: {permission_result.reason}"
            )

        # Execute the command using environment-aware executor (Phase 3 integration)
        start_time = datetime.now(timezone.utc)
        try:
            # Convert environment string to enum
            from app.actions.environment_executor import ExecutionEnvironment
            env_enum = ExecutionEnvironment(environment)

            result = await self.env_aware_executor.execute(
                command=command,
                environment=env_enum,
                timeout_seconds=getattr(request, 'timeout_seconds', 30) or 30,
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

            # Log execution with permission context
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
                "environment": environment,
                "details": {
                    "success": success,
                    "duration_seconds": duration,
                    "dry_run": request.dry_run,
                    "permission_check": permission_result.to_dict(),
                },
            })

            logger.info(
                f"Action {action_id} executed by {request.executed_by} in {environment}: "
                f"{'SUCCESS' if success else 'FAILED'}"
            )

            # Rollback handling for failed actions (Phase 8 Day 8)
            rollback_executor = get_rollback_executor()
            if not success:
                # Create rollback plan before execution
                rollback_plan = rollback_executor.create_rollback_plan(
                    action_id=action_id,
                    command=command,
                    context={"environment": environment, "project": project},
                )

                # Check if rollback should be triggered
                execution_context = {
                    "execution_success": success,
                    "environment": environment,
                    "project": project,
                    "duration_seconds": duration,
                }

                should_rollback, triggered_conditions = rollback_executor.should_rollback(
                    action_id=action_id,
                    execution_context=execution_context,
                )

                if should_rollback and rollback_plan:
                    # Log rollback trigger
                    self.audit_logger.log_event(
                        event_type="rollback_triggered",
                        user=request.executed_by,
                        action_id=action_id,
                        project=project,
                        details={
                            "triggered_conditions": triggered_conditions,
                            "rollback_command": rollback_plan.rollback_command,
                        },
                    )
                    logger.warning(
                        f"Rollback triggered for action {action_id} due to: {triggered_conditions}"
                    )

                    # For now, rollback requires manual approval
                    # Automatic rollback can be configured via settings
                    # In production, this would trigger an approval workflow

            # Record action in rate limiter after successful execution (Phase 8)
            if success:
                rate_limiter.record_action(
                    project=project,
                    action_type=action_type,
                    user=request.executed_by,
                )
                logger.info(
                    f"Rate limiter: Recorded action '{action_type}' for project '{project}' "
                    f"(metadata: {rate_metadata})"
                )

            # Convert result to ExecutionResult if it's a mock
            if isinstance(result, ExecutionResult):
                exec_result = result
            else:
                exec_result = ExecutionResult(
                    success=getattr(result, 'success', True),
                    exit_code=getattr(result, 'exit_code', 0),
                    stdout=getattr(result, 'stdout', ''),
                    stderr=getattr(result, 'stderr', ''),
                    duration_seconds=getattr(result, 'duration_seconds', duration),
                )

            # Build action kwargs from state, filtering None values
            action_kwargs = {
                "id": action_id,
                "status": new_status,
                "executed_by": request.executed_by,
                "executed_at": datetime.now(timezone.utc),
                "execution_result": exec_result,
            }

            # Add optional fields from state if present
            if "command_type" in state:
                action_kwargs["command_type"] = state["command_type"]
            if "command" in state:
                action_kwargs["command"] = state["command"]
            if "parsed_params" in state and state["parsed_params"]:
                action_kwargs["parsed_params"] = state["parsed_params"]
            if "project" in state:
                action_kwargs["project"] = state["project"]
            if "title" in state:
                action_kwargs["title"] = state["title"]
            if "description" in state:
                action_kwargs["description"] = state["description"]
            if "triage_card_id" in state:
                action_kwargs["triage_card_id"] = state["triage_card_id"]
            if "recommendation_id" in state:
                action_kwargs["recommendation_id"] = state["recommendation_id"]
            if "risk_level" in state:
                action_kwargs["risk_level"] = state["risk_level"]
            if "estimated_impact" in state:
                action_kwargs["estimated_impact"] = state["estimated_impact"]
            if "created_at" in state:
                action_kwargs["created_at"] = state["created_at"]
            if "context" in state:
                action_kwargs["context"] = state["context"]

            return Action(**action_kwargs)

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

        # Count by status (use original all_state for accurate counts)
        counts = {s: 0 for s in ActionStatus}
        for state in all_state.values():
            status_val = state.get("status")
            if status_val in counts:
                counts[status_val] += 1

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

        # Convert to Action objects
        actions = []
        for action_id, state in list(all_state.items())[:limit]:
            # Add id to state dict if not present
            state_with_id = {"id": action_id, **state}
            actions.append(Action(**state_with_id))

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
