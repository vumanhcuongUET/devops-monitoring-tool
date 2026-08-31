"""Action Engine for converting Triage Card recommendations into executable actions."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.actions.environment_executor import get_executor
from app.actions.executor import get_command_executor
from app.actions.impact_estimator import ImpactLevel, get_impact_estimator
from app.actions.parser import get_command_parser
from app.actions.rate_limiter import get_rate_limiter
from app.actions.rollback_executor import get_rollback_executor
from app.actions.time_window_enforcer import get_time_window_enforcer
from app.actions.validator import get_command_validator
from app.approvals.store import get_approval_history, get_approval_tracker
from app.audit.logger import get_audit_logger
from app.models.audit import AuditEventType
from app.config import settings
from app.feedback.collector import get_feedback_collector
from app.governance.permission_checker import get_permission_checker
from app.governance.opa_client import PolicyDecision, get_opa_client
from app.models.actions import (
    Action,
    ActionListResponse,
    ActionStatus,
    ApproveActionRequest,
    CreateActionRequest,
    ExecuteActionRequest,
    ExecutionResult,
    RejectActionRequest,
    RiskLevel,
)
from app.models.triage_card import Recommendation, SeverityLevel
from app.registry.loader import get_registry

logger = logging.getLogger(__name__)

# Fields copied from stored state into a reconstructed Action (when present).
_ACTION_STATE_FIELDS = (
    "command_type", "command", "parsed_params", "project", "title",
    "description", "triage_card_id", "recommendation_id", "risk_level",
    "estimated_impact", "created_at", "context",
)


def _action_kwargs_from_state(state: dict, base_kwargs: dict) -> dict:
    """Build Action kwargs: base status-change fields + stored optional fields."""
    kwargs = dict(base_kwargs)
    for f in _ACTION_STATE_FIELDS:
        if state.get(f) is not None:
            kwargs[f] = state[f]
    return kwargs


class ActionEngine:
    """Engine for managing action lifecycle: create, validate, approve, execute."""

    def __init__(self, k8s_client: Any | None = None):
        self.parser = get_command_parser()
        self.validator = get_command_validator()
        self.executor = get_command_executor()
        self.approval_tracker = get_approval_tracker(use_redis=settings.APPROVAL_STATE_USE_REDIS)
        self.approval_history = get_approval_history(use_redis=settings.APPROVAL_STATE_USE_REDIS)
        self.audit_logger = get_audit_logger()
        self.registry = get_registry()
        self.permission_checker = get_permission_checker()
        self.env_aware_executor = get_executor()
        self.feedback = get_feedback_collector()
        # Phase 14 TOCTOU fix: serialize decision/execution per action id so
        # concurrent approve/execute/reject can't both observe the old status
        # and double-run a mutating command. (Multi-process deployments still
        # need the Redis store's compare-and-set — this covers one process.)
        self._action_locks: dict[str, asyncio.Lock] = {}
        # Real cluster client for impact estimation (Phase 12 B3). Previously
        # resolved via `from app.main import app_state`, a symbol that never
        # existed — the import always failed silently and estimation ran on
        # heuristics alone.
        self.k8s_client = k8s_client

    def _action_lock(self, action_id: str) -> asyncio.Lock:
        lock = self._action_locks.get(action_id)
        if lock is None:
            lock = self._action_locks[action_id] = asyncio.Lock()
        return lock

    async def approve_action(
        self,
        action_id: str,
        request: ApproveActionRequest,
        auth_user: str | None = None,
    ) -> Action:
        """Approve an action (per-action serialized — Phase 14 TOCTOU fix)."""
        async with self._action_lock(action_id):
            return await self._approve_action_impl(action_id, request, auth_user)

    async def create_action_from_recommendation(
        self,
        request: CreateActionRequest,
        recommendation: Recommendation,
        auth_user: str | None = None,
    ) -> Action:
        """Create an Action from a Triage Card recommendation.

        auth_user: authenticated identity (Phase 14) — the creation-time
        permission check is narrowed by it exactly like execute, so a
        viewer can no longer stage actions born APPROVED.
        """
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

        # Check permissions using RBAC (Phase 3 integration; Phase 14: narrow
        # by the authenticated identity, same as execute).
        permission_result = self.permission_checker.check_command(
            command=command,
            environment=environment,
            project=request.project,
            user=auth_user,
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

        # Estimate impact (Phase 8 Day 7) — must precede the approval check below
        impact_estimator = get_impact_estimator()
        # Phase 12 B3: the engine holds the real cluster client (injected via
        # __init__/lifespan), so impact estimation can query actual resources
        # instead of silently degrading to heuristics.
        k8s_client = self.k8s_client

        impact_estimate = impact_estimator.estimate(
            action_id=action_id,
            command=command,
            k8s_client=k8s_client,
            dry_run=True,  # Use heuristics for now, can be configurable
        )

        # High and Critical impact actions require approval (Phase 8 Day 7)
        if impact_estimate.impact_level in (ImpactLevel.HIGH, ImpactLevel.CRITICAL):
            requires_approval = True

        # Critical impact actions may require executive approval
        requires_executive_approval = impact_estimate.impact_level == ImpactLevel.CRITICAL

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
                "permission_check_user": auth_user,
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

        # Add to approval tracker — full snapshot so get/list can rebuild the Action
        await self.approval_tracker.set_status(
            action_id=action_id,
            status=action.status,
            command=command,
            command_type=action.command_type.value,
            parsed_params=action.parsed_params.model_dump(mode="json"),
            project=action.project,
            title=action.title,
            description=action.description,
            triage_card_id=request.triage_card_id,
            recommendation_id=request.recommendation_id,
            risk_level=action.risk_level.value,
            estimated_impact=action.estimated_impact,
            context=action.context,
            created_by=request.created_by,
        )

        # Add to history
        await self.approval_history.add({
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

    def _check_decision_permission(
        self, state: dict, user: str, auth_user: str | None = None
    ) -> None:
        """Phase 12 S6: the decision-maker must hold `approve` for the env.

        Shared by approve and reject. `auth_user` (middleware-authenticated
        identity) drives per-user RBAC narrowing; the raw attribution label
        must never — otherwise an automation label colliding with a local
        username would silently change permission decisions.
        """
        env = (state.get("context") or {}).get("environment", "production")
        result = self.permission_checker.check(
            action="approve",
            environment=env,
            project=state.get("project"),
            user=auth_user,
        )
        if not result.allowed:
            raise PermissionError(
                f"User '{user}' lacks 'approve' permission in {env}: {result.reason}"
            )

    def _check_approval_integrity(
        self, state: dict, approver: str, auth_user: str | None = None
    ) -> None:
        """Phase 12 S6: block self-approval and permission-less approvers.

        - Self-approval (approver == creator attribution) is blocked unless
          settings.ALLOW_SELF_APPROVAL is set.
        - The approver must hold the `approve` permission for the action's
          environment; narrowing uses auth_user when provided (Phase 13).
        """
        created_by = state.get("created_by")

        if (
            created_by
            and approver
            and approver == created_by
            and not settings.ALLOW_SELF_APPROVAL
        ):
            raise PermissionError(
                f"Self-approval blocked: {approver} created action and ALLOW_SELF_APPROVAL is off"
            )

        self._check_decision_permission(state, approver, auth_user)

    async def _approve_action_impl(
        self,
        action_id: str,
        request: ApproveActionRequest,
        auth_user: str | None = None,
    ) -> Action:
        """Approve an action for execution.

        auth_user: authenticated identity from the API layer; drives RBAC
        narrowing only — attribution still records request.approved_by.
        """
        # Get current state
        state = await self.approval_tracker.get(action_id)
        if not state:
            raise ValueError(f"Action {action_id} not found")

        if state.get("status") != ActionStatus.PENDING:
            raise ValueError(f"Action {action_id} is not pending (current: {state.get('status')})")

        # Phase 12 S6: approval integrity — self-approval ban + approver permission check.
        self._check_approval_integrity(state, request.approved_by, auth_user)

        # Update status
        await self.approval_tracker.set_status(
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
        await self.approval_history.add({
            "id": str(uuid.uuid4()),
            "action_id": action_id,
            "event": "approved",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user": request.approved_by,
            "details": {"comment": request.comment} if request.comment else {},
        })

        logger.info(f"Action {action_id} approved by {request.approved_by}")

        # Phase 11: feed the learning loop (/autonomous/learning/* reads this)
        self.feedback.record_approval(action_id, request.approved_by, {"comment": request.comment})

        # Build action kwargs from state, filtering None values
        action_kwargs = _action_kwargs_from_state(state, {
            "id": action_id,
            "status": ActionStatus.APPROVED,
            "approved_by": request.approved_by,
            "approved_at": datetime.now(timezone.utc),
        })
        return Action(**action_kwargs)

    async def reject_action(
        self,
        action_id: str,
        request: RejectActionRequest,
        auth_user: str | None = None,
    ) -> Action:
        """Reject an action (per-action serialized — Phase 14 TOCTOU fix)."""
        async with self._action_lock(action_id):
            return await self._reject_action_impl(action_id, request, auth_user)

    async def _reject_action_impl(
        self,
        action_id: str,
        request: RejectActionRequest,
        auth_user: str | None = None,
    ) -> Action:
        """Reject an action.

        auth_user: authenticated identity from the API layer; drives RBAC
        narrowing only — attribution still records request.rejected_by.
        """
        # Get current state
        state = await self.approval_tracker.get(action_id)
        if not state:
            raise ValueError(f"Action {action_id} not found")

        if state.get("status") != ActionStatus.PENDING:
            raise ValueError(f"Action {action_id} is not pending (current: {state.get('status')})")

        # S6 (security recheck F1): reject is an approval-flow decision too —
        # it requires the `approve` permission. Self-reject stays allowed:
        # a creator cancelling their own pending request gains no privilege.
        self._check_decision_permission(state, request.rejected_by, auth_user)

        # Update status
        await self.approval_tracker.set_status(
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
        await self.approval_history.add({
            "id": str(uuid.uuid4()),
            "action_id": action_id,
            "event": "rejected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user": request.rejected_by,
            "details": {"reason": request.reason},
        })

        logger.info(f"Action {action_id} rejected by {request.rejected_by}: {request.reason}")

        # Phase 11: feed the learning loop (/autonomous/learning/* reads this)
        self.feedback.record_rejection(action_id, request.rejected_by, reason=request.reason)
        # Build action kwargs from state, filtering None values
        action_kwargs = _action_kwargs_from_state(state, {
            "id": action_id,
            "status": ActionStatus.REJECTED,
            "rejected_by": request.rejected_by,
            "rejected_at": datetime.now(timezone.utc),
            "rejection_reason": request.reason,
        })
        return Action(**action_kwargs)

    async def execute_action(
        self,
        action_id: str,
        request: ExecuteActionRequest,
        auth_user: str | None = None,
    ) -> Action:
        """Execute an approved action (per-action serialized — Phase 14)."""
        async with self._action_lock(action_id):
            return await self._execute_action_impl(action_id, request, auth_user)

    async def _execute_action_impl(
        self,
        action_id: str,
        request: ExecuteActionRequest,
        auth_user: str | None = None,
    ) -> Action:
        """Execute an approved action with RBAC permission checking."""
        # Get current state
        state = await self.approval_tracker.get(action_id)
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

        # Parse command to get action type for rate limiting. The tracker stores
        # parsed_params as a JSON dict; tolerate legacy attribute-style values.
        parsed_params = state.get("parsed_params")
        if isinstance(parsed_params, dict):
            action_type = parsed_params.get("action", "unknown")
        else:
            action_type = getattr(parsed_params, "action", "unknown")

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
            user=auth_user,  # narrowing by authenticated identity only
        )

        if not permission_result.allowed:
            raise PermissionError(
                f"Permission denied for action {action_id}: {permission_result.reason}"
            )

        # Optional OPA enforcement (Phase 12 Sprint 3, flag-gated, default off).
        # Phase 15: enforcement is fail-closed — DENY blocks, an undefined or
        # unevaluable policy blocks, and an unexpected evaluation error blocks.
        # (Previously exceptions were logged and the action allowed, and an
        # OPA `{}` response with no result evaluated to ALLOW.)
        if settings.OPA_ENFORCE:
            try:
                opa_result = await get_opa_client().evaluate_action(
                    action={"command": command, "id": action_id},
                    project=project,
                    environment=environment,
                    user=request.executed_by,
                )
            except Exception as e:
                raise PermissionError(
                    f"Action {action_id}: OPA enforcement could not evaluate the policy: {e}"
                ) from e
            if opa_result.decision == PolicyDecision.UNKNOWN:
                raise PermissionError(
                    f"Action {action_id}: OPA returned no policy decision (fail closed)"
                )
            if opa_result.decision == PolicyDecision.DENY:
                violations = [v.description for v in opa_result.violations]
                raise PermissionError(
                    f"Action {action_id} denied by OPA policy: {violations}"
                )

        # Time-window enforcement (Phase 12 Sprint 3 — wired into the real path):
        # executions outside the environment's safe window are blocked + audited.
        window_result = get_time_window_enforcer().check_time_window(environment=environment)
        if not window_result.is_allowed:
            self.audit_logger.log_event(
                event_type=AuditEventType.VALIDATION_CHECK,
                user=request.executed_by,
                action_id=action_id,
                project=project,
                success=False,
                details={"blocked_by": "time_window", "reason": window_result.reason},
            )
            raise PermissionError(
                f"Action {action_id} blocked by time window: {window_result.reason}"
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
                dry_run=request.dry_run,
            )

            success = result.success
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Phase 15: a dry run must not consume the approval. It used to
            # set EXECUTED (terminal), making a real execution impossible
            # afterwards; keep APPROVED so the operator can execute for real.
            if request.dry_run:
                new_status = ActionStatus.APPROVED
            else:
                new_status = ActionStatus.EXECUTED if success else ActionStatus.FAILED
            await self.approval_tracker.set_status(
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
            await self.approval_history.add({
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

            # Phase 11: feed the learning loop (/autonomous/learning/* reads this)
            self.feedback.record_execution(
                action_id,
                success,
                {"duration_seconds": duration, "dry_run": request.dry_run},
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
                        event_type=AuditEventType.ROLLBACK_TRIGGERED,
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

                    # Phase 12 Sprint 3: finish the feature — create a real
                    # PENDING rollback action so it enters the normal approval
                    # flow (previously this only logged the plan).
                    rollback_rec = Recommendation(
                        priority=1,
                        action=f"Rollback after failed action {action_id}",
                        command=rollback_plan.rollback_command,
                        reason=(
                            f"Automatic rollback triggered by failed action "
                            f"{action_id}: {triggered_conditions}"
                        ),
                        risk=SeverityLevel.HIGH,
                        estimated_impact="Restores pre-execution state",
                    )
                    rollback_request = CreateActionRequest(
                        triage_card_id=f"rollback-{action_id}",
                        recommendation_id=f"rollback-{action_id}",
                        project=project,
                        created_by=f"rollback:{action_id}",
                    )
                    rollback_action = await self.create_action_from_recommendation(
                        request=rollback_request,
                        recommendation=rollback_rec,
                    )
                    logger.info(
                        f"Rollback action {rollback_action.id} created "
                        f"(status={rollback_action.status.value}, pending approval)"
                    )

            # Record action in rate limiter after successful execution (Phase 8).
            # Dry runs are not recorded: they mutate nothing, and counting them
            # would burn the real execution's cooldown slot.
            if success and not request.dry_run:
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
            action_kwargs = _action_kwargs_from_state(state, {
                "id": action_id,
                "status": new_status,
                "executed_by": request.executed_by,
                "executed_at": datetime.now(timezone.utc),
                "execution_result": exec_result,
            })
            return Action(**action_kwargs)

        except Exception as e:
            # Execution failed with exception. If the failure happened AFTER
            # the command already ran and EXECUTED was persisted (e.g. the
            # rollback bookkeeping below it threw), do not overwrite the
            # terminal status — audit the error and re-raise instead.
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            current_status = (await self.approval_tracker.get(action_id) or {}).get("status")
            if current_status != ActionStatus.EXECUTED:
                await self.approval_tracker.set_status(
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

    async def get_action(self, action_id: str) -> dict | None:
        """Get action details."""
        state = await self.approval_tracker.get(action_id)
        if not state:
            return None
        # Stored state omits the id (it is the tracker key). Inject it so the
        # API response_model can rehydrate Action(**state) — found live by the
        # Phase 12 manual smoke: GET /actions/{id} 500'd on "id: Field required".
        state.setdefault("id", action_id)
        return state

    async def list_actions(
        self,
        project: str | None = None,
        status: ActionStatus | None = None,
        limit: int = 100,
    ) -> ActionListResponse:
        """List actions with optional filters."""
        all_state = await self.approval_tracker.get_all()

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
_action_engine: ActionEngine | None = None


def get_action_engine(k8s_client: Any | None = None) -> ActionEngine:
    """Get or create the singleton ActionEngine instance.

    k8s_client is honored on first construction (later calls return the
    existing singleton regardless).
    """
    global _action_engine
    if _action_engine is None:
        _action_engine = ActionEngine(k8s_client=k8s_client)
    return _action_engine
