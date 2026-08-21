"""Remediation actions for autonomous reliability.

This module provides predefined remediation actions that can be triggered
automatically by the alert engine for common incident patterns.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from enum import Enum

from app.actions.executor import CommandExecutor, get_command_executor
from app.actions.parser import CommandParser, get_command_parser
from app.models.actions import CommandParams, ExecutionResult
from app.models.alerts import AlertEvent, AlertRule

logger = logging.getLogger(__name__)


class RemediationActionType(str, Enum):
    """Types of remediation actions."""
    DELETE_CRASHLOOP_POD = "delete_crashloop_pod"
    SCALE_DEPLOYMENT = "scale_deployment"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    RESTART_DEPLOYMENT = "restart_deployment"


class RemediationAction:
    """Base class for remediation actions."""

    def __init__(self):
        self.executor = get_command_executor()
        self.parser = get_command_parser()
        self._execution_history: list[dict] = []
        self._max_history = 1000

    async def execute(
        self,
        alert_event: AlertEvent,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute the remediation action.

        Args:
            alert_event: The alert that triggered this action
            parameters: Action-specific parameters
            dry_run: If True, validate without executing

        Returns:
            Execution result with status and details
        """
        raise NotImplementedError("Subclasses must implement execute()")

    def _record_execution(self, action_type: str, result: ExecutionResult, context: dict):
        """Record execution for learning and audit."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action_type": action_type,
            "success": result.success,
            "duration_seconds": result.duration_seconds,
            "context": context,
        }
        self._execution_history.append(record)
        # Keep history limited
        if len(self._execution_history) > self._max_history:
            self._execution_history.pop(0)

    def get_execution_history(self) -> list[dict]:
        """Get execution history for learning."""
        return self._execution_history.copy()


class DeleteCrashLoopPodAction(RemediationAction):
    """Remediation action for deleting CrashLoopBackOff pods.

    This action detects pods with high restart counts and safely deletes them
    to allow the deployment controller to recreate them.
    """

    async def execute(
        self,
        alert_event: AlertEvent,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute crashloop pod deletion.

        Args:
            alert_event: Alert event with context
            parameters: Expected keys:
                - namespace: Kubernetes namespace
                - pod_name: Name of the pod (optional, auto-detected)
                - restart_threshold: Minimum restart count (default: 5)
                - label_selector: Additional pod selector (optional)
            dry_run: Validate without executing

        Returns:
            Execution result with deleted pod information
        """
        namespace = parameters.get("namespace", "default")
        restart_threshold = parameters.get("restart_threshold", 5)
        pod_name = parameters.get("pod_name")
        label_selector = parameters.get("label_selector", "")

        # Step 1: Find pods with high restart counts
        find_pods_cmd = ["kubectl", "get", "pods", "-n", namespace, "-o", "json"]

        if label_selector:
            find_pods_cmd.extend(["-l", label_selector])

        pods_result = await self.executor.execute_kubectl(
            args=find_pods_cmd[2:],  # Skip 'kubectl'
            namespace=namespace,
            dry_run=False,  # We need actual data
        )

        if not pods_result.success:
            return ExecutionResult(
                success=False,
                error_message=f"Failed to list pods: {pods_result.stderr}",
                timestamp=datetime.now(timezone.utc),
            )

        # Step 2: Parse pods and find crashloop candidates
        import json
        try:
            pods_data = json.loads(pods_result.stdout)
            crashloop_pods = []
            for item in pods_data.get("items", []):
                pod = item.get("metadata", {}).get("name")
                restart_count = item.get("status", {}).get("containerStatuses", [{}])[0].get("restartCount", 0)
                status = item.get("status", {}).get("phase", "")

                # Check for crashloop or high restart count
                is_crashloop = (
                    restart_count >= restart_threshold or
                    (status == "Running" and restart_count >= 3)
                )

                if is_crashloop and (not pod_name or pod == pod):
                    crashloop_pods.append({
                        "name": pod,
                        "restarts": restart_count,
                        "status": status,
                    })
        except json.JSONDecodeError as e:
            return ExecutionResult(
                success=False,
                error_message=f"Failed to parse pod data: {e}",
                timestamp=datetime.now(timezone.utc),
            )

        if not crashloop_pods:
            return ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"No crashloop pods found (restart threshold: {restart_threshold})",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        # Step 3: Delete each crashloop pod
        deleted_pods = []
        for pod_info in crashloop_pods:
            pod = pod_info["name"]
            delete_cmd = ["delete", "pod", pod]

            if dry_run:
                result = ExecutionResult(
                    success=True,
                    exit_code=0,
                    stdout=f"[DRY RUN] Would delete pod: {pod}",
                    stderr="",
                    duration_seconds=0.0,
                    timestamp=datetime.now(timezone.utc),
                )
            else:
                result = await self.executor.execute_kubectl(
                    args=delete_cmd,
                    namespace=namespace,
                    dry_run=False,
                )

            deleted_pods.append({
                "pod": pod,
                "restarts": pod_info["restarts"],
                "deleted": result.success,
                "error": result.error_message if not result.success else None,
            })

        # Record execution
        self._record_execution(
            RemediationActionType.DELETE_CRASHLOOP_POD.value,
            result if len(deleted_pods) == 1 else ExecutionResult(success=all(p["deleted"] for p in deleted_pods)),
            {
                "namespace": namespace,
                "pods_deleted": len(deleted_pods),
                "alert_event_id": alert_event.id,
            }
        )

        return ExecutionResult(
            success=all(p["deleted"] for p in deleted_pods),
            exit_code=0 if all(p["deleted"] for p in deleted_pods) else 1,
            stdout=f"Deleted {len(deleted_pods)} crashloop pods: {', '.join(p['pod'] for p in deleted_pods)}",
            stderr="",
            duration_seconds=0.0,
            timestamp=datetime.now(timezone.utc),
        )


class ScaleDeploymentAction(RemediationAction):
    """Remediation action for scaling deployments based on metrics.

    This action scales deployments up or down based on CPU/memory thresholds.
    """

    async def execute(
        self,
        alert_event: AlertEvent,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute deployment scaling.

        Args:
            alert_event: Alert event with context
            parameters: Expected keys:
                - namespace: Kubernetes namespace
                - deployment: Deployment name
                - replicas: Target replica count (or adjustment like +2, -1)
                - min_replicas: Minimum replicas (safety limit, default: 1)
                - max_replicas: Maximum replicas (safety limit, default: 10)
            dry_run: Validate without executing

        Returns:
            Execution result with scaling details
        """
        namespace = parameters.get("namespace", "default")
        deployment = parameters.get("deployment")
        replicas_param = parameters.get("replicas", "+1")
        min_replicas = parameters.get("min_replicas", 1)
        max_replicas = parameters.get("max_replicas", 10)

        if not deployment:
            return ExecutionResult(
                success=False,
                error_message="Deployment name is required",
                timestamp=datetime.now(timezone.utc),
            )

        # Step 1: Get current replica count
        get_cmd = ["get", "deployment", deployment, "-o", "json"]
        current_result = await self.executor.execute_kubectl(
            args=get_cmd,
            namespace=namespace,
            dry_run=False,
        )

        if not current_result.success:
            return ExecutionResult(
                success=False,
                error_message=f"Failed to get deployment: {current_result.stderr}",
                timestamp=datetime.now(timezone.utc),
            )

        import json
        try:
            deploy_data = json.loads(current_result.stdout)
            current_replicas = deploy_data.get("spec", {}).get("replicas", 1)
        except json.JSONDecodeError:
            return ExecutionResult(
                success=False,
                error_message="Failed to parse deployment data",
                timestamp=datetime.now(timezone.utc),
            )

        # Step 2: Calculate target replicas
        if isinstance(replicas_param, str) and replicas_param.startswith(("+", "-")):
            target_replicas = current_replicas + int(replicas_param)
        else:
            target_replicas = int(replicas_param)

        # Step 3: Apply safety limits
        target_replicas = max(min_replicas, min(target_replicas, max_replicas))

        if target_replicas == current_replicas:
            return ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"Deployment already at {current_replicas} replicas (within limits)",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        # Step 4: Scale deployment
        scale_cmd = ["scale", "deployment", deployment, "--replicas", str(target_replicas)]

        if dry_run:
            result = ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[DRY RUN] Would scale {deployment} from {current_replicas} to {target_replicas} replicas",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )
        else:
            result = await self.executor.execute_kubectl(
                args=scale_cmd,
                namespace=namespace,
                dry_run=False,
            )

        # Record execution
        self._record_execution(
            RemediationActionType.SCALE_DEPLOYMENT.value,
            result,
            {
                "namespace": namespace,
                "deployment": deployment,
                "from_replicas": current_replicas,
                "to_replicas": target_replicas,
                "alert_event_id": alert_event.id,
            }
        )

        return ExecutionResult(
            success=result.success,
            exit_code=result.exit_code,
            stdout=f"Scaled {deployment} from {current_replicas} to {target_replicas} replicas" if result.success else result.stdout,
            stderr=result.stderr,
            duration_seconds=result.duration_seconds,
            timestamp=datetime.now(timezone.utc),
            error_message=result.error_message,
        )


class RollbackDeploymentAction(RemediationAction):
    """Remediation action for rolling back failing deployments.

    This action rolls back a deployment to the previous stable revision
    when critical failures are detected.
    """

    async def execute(
        self,
        alert_event: AlertEvent,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute deployment rollback.

        Args:
            alert_event: Alert event with context
            parameters: Expected keys:
                - namespace: Kubernetes namespace
                - deployment: Deployment name
                - revision: Target revision (default: previous revision)
            dry_run: Validate without executing

        Returns:
            Execution result with rollback details
        """
        namespace = parameters.get("namespace", "default")
        deployment = parameters.get("deployment")
        target_revision = parameters.get("revision", None)

        if not deployment:
            return ExecutionResult(
                success=False,
                error_message="Deployment name is required",
                timestamp=datetime.now(timezone.utc),
            )

        # Step 1: Get rollout history
        history_cmd = ["rollout", "history", "deployment", deployment]
        history_result = await self.executor.execute_kubectl(
            args=history_cmd,
            namespace=namespace,
            dry_run=False,
        )

        if not history_result.success and "not found" in history_result.error_message.lower():
            return ExecutionResult(
                success=False,
                error_message=f"Deployment '{deployment}' not found",
                timestamp=datetime.now(timezone.utc),
            )

        # Step 2: Determine target revision
        if target_revision is None:
            # Default to previous revision (current - 1)
            # Parse history to find current revision
            # For simplicity, we'll use 'undo' command which rolls back to previous
            rollback_cmd = ["rollout", "undo", "deployment", deployment]
        else:
            rollback_cmd = ["rollout", "undo", "deployment", deployment, f"--to-revision={target_revision}"]

        if dry_run:
            result = ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[DRY RUN] Would rollback {deployment} to revision {target_revision or 'previous'}",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )
        else:
            result = await self.executor.execute_kubectl(
                args=rollback_cmd,
                namespace=namespace,
                dry_run=False,
            )

        # Record execution
        self._record_execution(
            RemediationActionType.ROLLBACK_DEPLOYMENT.value,
            result,
            {
                "namespace": namespace,
                "deployment": deployment,
                "target_revision": target_revision or "previous",
                "alert_event_id": alert_event.id,
            }
        )

        return ExecutionResult(
            success=result.success,
            exit_code=result.exit_code,
            stdout=f"Rollback initiated for {deployment}" if result.success else result.stdout,
            stderr=result.stderr,
            duration_seconds=result.duration_seconds,
            timestamp=datetime.now(timezone.utc),
            error_message=result.error_message,
        )


class RestartDeploymentAction(RemediationAction):
    """Remediation action for restarting deployments via rollout.

    This action performs a rolling restart of a deployment to refresh pods.
    """

    async def execute(
        self,
        alert_event: AlertEvent,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute deployment restart.

        Args:
            alert_event: Alert event with context
            parameters: Expected keys:
                - namespace: Kubernetes namespace
                - deployment: Deployment name
            dry_run: Validate without executing

        Returns:
            Execution result with restart details
        """
        namespace = parameters.get("namespace", "default")
        deployment = parameters.get("deployment")

        if not deployment:
            return ExecutionResult(
                success=False,
                error_message="Deployment name is required",
                timestamp=datetime.now(timezone.utc),
            )

        # Execute rollout restart
        restart_cmd = ["rollout", "restart", deployment]

        if dry_run:
            result = ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[DRY RUN] Would restart deployment {deployment}",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )
        else:
            result = await self.executor.execute_kubectl(
                args=restart_cmd,
                namespace=namespace,
                dry_run=False,
            )

        # Record execution
        self._record_execution(
            RemediationActionType.RESTART_DEPLOYMENT.value,
            result,
            {
                "namespace": namespace,
                "deployment": deployment,
                "alert_event_id": alert_event.id,
            }
        )

        return ExecutionResult(
            success=result.success,
            exit_code=result.exit_code,
            stdout=f"Rollout restart initiated for {deployment}" if result.success else result.stdout,
            stderr=result.stderr,
            duration_seconds=result.duration_seconds,
            timestamp=datetime.now(timezone.utc),
            error_message=result.error_message,
        )


# Action factory
class RemediationActionFactory:
    """Factory for creating remediation actions."""

    _actions = {
        RemediationActionType.DELETE_CRASHLOOP_POD: DeleteCrashLoopPodAction,
        RemediationActionType.SCALE_DEPLOYMENT: ScaleDeploymentAction,
        RemediationActionType.ROLLBACK_DEPLOYMENT: RollbackDeploymentAction,
        RemediationActionType.RESTART_DEPLOYMENT: RestartDeploymentAction,
    }

    @classmethod
    def create(cls, action_type: RemediationActionType) -> RemediationAction:
        """Create a remediation action instance.

        Args:
            action_type: Type of remediation action

        Returns:
            Remediation action instance

        Raises:
            ValueError: If action type is unknown
        """
        action_class = cls._actions.get(action_type)
        if not action_class:
            raise ValueError(f"Unknown remediation action type: {action_type}")
        return action_class()

    @classmethod
    def get_available_actions(cls) -> list[str]:
        """Get list of available remediation action types."""
        return [action.value for action in cls._actions]
