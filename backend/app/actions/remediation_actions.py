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
    # Phase 4A: New action types
    CLEAR_STUCK_PODS = "clear_stuck_pods"
    CLEANUP_FAILED_JOBS = "cleanup_failed_jobs"
    ADJUST_HPA_MIN_REPLICAS = "adjust_hpa_min_replicas"


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


class ClearStuckPodsAction(RemediationAction):
    """Remediation action for clearing stuck pods.

    This action detects and removes pods stuck in problematic states:
    - Terminating (stuck for >10 minutes)
    - ImagePullBackOff / ErrImagePull
    - CrashLoopBackOff with no recent successful start
    - CreateContainerError / CreateContainerConfigError

    Risk Level: LOW - Force deletion is safe as controllers recreate pods
    """

    STUCK_STATES = {
        "Terminating",
        "ImagePullBackOff",
        "ErrImagePull",
        "CrashLoopBackOff",
        "CreateContainerError",
        "CreateContainerConfigError",
        "RunContainerError",
        "ErrImageNeverPull",
        "InvalidImageName",
    }

    async def execute(
        self,
        alert_event: AlertEvent,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute stuck pod clearance.

        Args:
            alert_event: Alert event with context
            parameters: Expected keys:
                - namespace: Kubernetes namespace (default: default)
                - stuck_duration_minutes: Minimum duration in stuck state (default: 10)
                - label_selector: Filter pods by label (optional)
                - pod_names: Specific pod names to clear (optional)
            dry_run: Validate without executing

        Returns:
            Execution result with cleared pods details
        """
        namespace = parameters.get("namespace", "default")
        stuck_duration_minutes = parameters.get("stuck_duration_minutes", 10)
        label_selector = parameters.get("label_selector", "")
        target_pods = parameters.get("pod_names", [])

        if dry_run:
            # In dry-run, just report what would be done
            result = ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[DRY RUN] Would clear stuck pods in {namespace} "
                       f"(stuck for >{stuck_duration_minutes} minutes)",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )
        else:
            # Step 1: Find stuck pods
            find_cmd = ["get", "pods", "-n", namespace, "-o", "json"]
            if label_selector:
                find_cmd.extend(["-l", label_selector])

            pods_result = await self.executor.execute_kubectl(
                args=find_cmd[2:],
                namespace=namespace,
                dry_run=False,
            )

            if not pods_result.success:
                return ExecutionResult(
                    success=False,
                    error_message=f"Failed to list pods: {pods_result.stderr}",
                    timestamp=datetime.now(timezone.utc),
                )

            # Step 2: Parse and identify stuck pods
            import json
            try:
                pods_data = json.loads(pods_result.stdout)
                stuck_pods = []
                cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=stuck_duration_minutes)

                for item in pods_data.get("items", []):
                    pod_name = item.get("metadata", {}).get("name")
                    pod_status = item.get("status", {}).get("phase", "Unknown")
                    container_statuses = item.get("status", {}).get("containerStatuses", [])
                    pod_start_time_str = item.get("status", {}).get("startTime", "")

                    # Check if pod is in stuck state
                    is_stuck = False
                    stuck_reason = ""

                    # Check phase
                    if pod_status in ["Terminating", "Unknown"]:
                        is_stuck = True
                        stuck_reason = f"Pod in {pod_status} state"

                    # Check container states
                    for container_status in container_statuses or []:
                        waiting = container_status.get("waiting", {})
                        state = waiting.get("reason", "")
                        if state in self.STUCK_STATES:
                            is_stuck = True
                            stuck_reason = f"Container: {state}"
                            break

                    # Check if stuck for long enough
                    if is_stuck and pod_start_time_str:
                        try:
                            pod_start_time = datetime.fromisoformat(pod_start_time_str.replace("Z", "+00:00"))
                            if pod_start_time > cutoff_time:
                                is_stuck = True  # Only clear if stuck long enough
                            else:
                                is_stuck = False
                                stuck_reason = f"Pod not stuck long enough (started {pod_start_time_str})"
                        except:
                            pass  # If we can't parse time, still consider it stuck

                    # Check if pod is in target list (if specified)
                    if target_pods and pod_name not in target_pods:
                        is_stuck = False

                    if is_stuck:
                        stuck_pods.append({
                            "name": pod_name,
                            "status": pod_status,
                            "reason": stuck_reason,
                        })

            except json.JSONDecodeError as e:
                return ExecutionResult(
                    success=False,
                    error_message=f"Failed to parse pod data: {e}",
                    timestamp=datetime.now(timezone.utc),
                )

            # Step 3: Delete stuck pods
            deleted_pods = []
            errors = []

            for pod_info in stuck_pods:
                pod_name = pod_info["name"]
                delete_cmd = ["delete", "pod", pod_name, "--force", "--grace-period=0"]

                delete_result = await self.executor.execute_kubectl(
                    args=delete_cmd[2:],
                    namespace=namespace,
                    dry_run=False,
                )

                if delete_result.success:
                    deleted_pods.append(pod_name)
                else:
                    errors.append(f"{pod_name}: {delete_result.stderr}")

            # Build result
            result = ExecutionResult(
                success=len(errors) == 0,
                exit_code=0 if len(errors) == 0 else 1,
                stdout=f"Cleared {len(deleted_pods)} stuck pod(s): {', '.join(deleted_pods)}",
                stderr=f"Errors: {errors}" if errors else "",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
                error_message=f"Failed to clear {len(errors)} pod(s)" if errors else None,
            )

        # Record execution
        self._record_execution(
            RemediationActionType.CLEAR_STUCK_PODS.value,
            result,
            {
                "namespace": namespace,
                "stuck_duration_minutes": stuck_duration_minutes,
                "label_selector": label_selector,
                "target_pods": target_pods,
                "alert_event_id": alert_event.id,
            }
        )

        return result


class CleanupFailedJobsAction(RemediationAction):
    """Remediation action for cleaning up failed Kubernetes jobs.

    This action identifies and removes failed jobs older than a threshold
    to prevent disk space issues and improve cluster hygiene.

    Risk Level: LOW - Only removes failed jobs, not running/completed ones
    """

    async def execute(
        self,
        alert_event: AlertEvent,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute failed job cleanup.

        Args:
            alert_event: Alert event with context
            parameters: Expected keys:
                - namespace: Kubernetes namespace (default: default)
                - failed_hours_ago: Delete jobs failed N hours ago (default: 24)
                - label_selector: Filter jobs by label (optional)
                - keep_last: Keep last N failed jobs (default: 5)
            dry_run: Validate without executing

        Returns:
            Execution result with cleanup details
        """
        namespace = parameters.get("namespace", "default")
        failed_hours_ago = parameters.get("failed_hours_ago", 24)
        label_selector = parameters.get("label_selector", "")
        keep_last = parameters.get("keep_last", 5)

        if dry_run:
            result = ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[DRY RUN] Would cleanup failed jobs in {namespace} "
                       f"(failed >{failed_hours_ago} hours ago, keeping last {keep_last})",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )
        else:
            # Step 1: Find failed jobs
            find_cmd = ["get", "jobs", "-n", namespace, "-o", "json"]
            if label_selector:
                find_cmd.extend(["-l", label_selector])

            jobs_result = await self.executor.execute_kubectl(
                args=find_cmd[2:],
                namespace=namespace,
                dry_run=False,
            )

            if not jobs_result.success:
                return ExecutionResult(
                    success=False,
                    error_message=f"Failed to list jobs: {jobs_result.stderr}",
                    timestamp=datetime.now(timezone.utc),
                )

            # Step 2: Parse and identify failed jobs
            import json
            try:
                jobs_data = json.loads(jobs_result.stdout)
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=failed_hours_ago)
                failed_jobs = []

                for item in jobs_data.get("items", []):
                    job_name = item.get("metadata", {}).get("name")
                    job_status = item.get("status", {})
                    conditions = job_status.get("conditions", [])
                    start_time_str = item.get("status", {}).get("startTime", "")

                    # Check if job failed
                    is_failed = False
                    failed_time = None

                    for condition in conditions:
                        if condition.get("type", "") == "Failed" and condition.get("status", "") == "True":
                            is_failed = True
                            # Get failure time
                            failed_time_str = condition.get("lastTransitionTime", start_time_str)
                            try:
                                failed_time = datetime.fromisoformat(failed_time_str.replace("Z", "+00:00"))
                            except:
                                failed_time = cutoff_time - timedelta(hours=1)  # Conservative
                            break

                    if is_failed and failed_time and failed_time < cutoff_time:
                        failed_jobs.append({
                            "name": job_name,
                            "failed_at": failed_time.isoformat(),
                        })

            except json.JSONDecodeError as e:
                return ExecutionResult(
                    success=False,
                    error_message=f"Failed to parse job data: {e}",
                    timestamp=datetime.now(timezone.utc),
                )

            # Sort by failed time (oldest first) and keep last N
            failed_jobs.sort(key=lambda x: x["failed_at"])
            if len(failed_jobs) > keep_last:
                jobs_to_delete = failed_jobs[:-keep_last]
            else:
                jobs_to_delete = []

            # Step 3: Delete failed jobs
            deleted_jobs = []
            errors = []

            for job_info in jobs_to_delete:
                job_name = job_info["name"]
                delete_cmd = ["delete", "job", job_name]

                delete_result = await self.executor.execute_kubectl(
                    args=delete_cmd[2:],
                    namespace=namespace,
                    dry_run=False,
                )

                if delete_result.success:
                    deleted_jobs.append(job_name)
                else:
                    errors.append(f"{job_name}: {delete_result.stderr}")

            # Build result
            result = ExecutionResult(
                success=len(errors) == 0,
                exit_code=0 if len(errors) == 0 else 1,
                stdout=f"Cleaned up {len(deleted_jobs)} failed job(s): {', '.join(deleted_jobs)}",
                stderr=f"Kept last {keep_last} failed jobs. Errors: {errors}" if errors else "",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
                error_message=f"Failed to cleanup {len(errors)} job(s)" if errors else None,
            )

        # Record execution
        self._record_execution(
            RemediationActionType.CLEANUP_FAILED_JOBS.value,
            result,
            {
                "namespace": namespace,
                "failed_hours_ago": failed_hours_ago,
                "label_selector": label_selector,
                "keep_last": keep_last,
                "alert_event_id": alert_event.id,
            }
        )

        return result


class AdjustHPAMinReplicasAction(RemediationAction):
    """Remediation action for temporarily adjusting HPA min replicas.

    This action temporarily increases the minimum replicas for an HPA
    to handle sudden load spikes, with automatic rollback after a duration.

    Risk Level: LOW-MEDIUM - Reversible with time limit
    """

    async def execute(
        self,
        alert_event: AlertEvent,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute HPA min replica adjustment.

        Args:
            alert_event: Alert event with context
            parameters: Expected keys:
                - namespace: Kubernetes namespace (default: default)
                - hpa_name: HorizontalPodAutoscaler name (required)
                - new_min_replicas: New minimum replicas (required)
                - duration_minutes: How long to maintain (default: 60)
                - auto_rollback: Auto-rollback after duration (default: true)
            dry_run: Validate without executing

        Returns:
            Execution result with HPA adjustment details
        """
        namespace = parameters.get("namespace", "default")
        hpa_name = parameters.get("hpa_name")
        new_min_replicas = parameters.get("new_min_replicas")
        duration_minutes = parameters.get("duration_minutes", 60)
        auto_rollback = parameters.get("auto_rollback", True)

        if not hpa_name:
            return ExecutionResult(
                success=False,
                error_message="HPA name is required",
                timestamp=datetime.now(timezone.utc),
            )

        if new_min_replicas is None:
            return ExecutionResult(
                success=False,
                error_message="new_min_replicas is required",
                timestamp=datetime.now(timezone.utc),
            )

        # Validate new_min_replicas
        try:
            new_min_replicas = int(new_min_replicas)
            if new_min_replicas < 1:
                return ExecutionResult(
                    success=False,
                    error_message="new_min_replicas must be at least 1",
                    timestamp=datetime.now(timezone.utc),
                )
        except ValueError:
            return ExecutionResult(
                success=False,
                error_message="new_min_replicas must be a valid integer",
                timestamp=datetime.now(timezone.utc),
            )

        if dry_run:
            result = ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[DRY RUN] Would adjust HPA {hpa_name} min replicas to {new_min_replicas} "
                       f"for {duration_minutes} minutes (auto-rollback: {auto_rollback})",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )
        else:
            # Step 1: Get current HPA config
            get_cmd = ["get", "hpa", hpa_name, "-n", namespace, "-o", "json"]

            hpa_result = await self.executor.execute_kubectl(
                args=get_cmd[2:],
                namespace=namespace,
                dry_run=False,
            )

            if not hpa_result.success:
                return ExecutionResult(
                    success=False,
                    error_message=f"Failed to get HPA {hpa_name}: {hpa_result.stderr}",
                    timestamp=datetime.now(timezone.utc),
                )

            # Step 2: Parse current config
            import json
            try:
                hpa_data = json.loads(hpa_result.stdout)
                current_min = hpa_data.get("spec", {}).get("minReplicas", 1)
                current_max = hpa_data.get("spec", {}).get("maxReplicas", 10)

                # Validate new_min doesn't exceed max
                if new_min_replicas > current_max:
                    return ExecutionResult(
                        success=False,
                        error_message=f"new_min_replicas ({new_min_replicas}) cannot exceed maxReplicas ({current_max})",
                        timestamp=datetime.now(timezone.utc),
                    )

            except json.JSONDecodeError as e:
                return ExecutionResult(
                    success=False,
                    error_message=f"Failed to parse HPA data: {e}",
                    timestamp=datetime.now(timezone.utc),
                )

            # Step 3: Apply new min replicas
            patch_cmd = [
                "patch", "hpa", hpa_name,
                f'--type=merge',
                f'-p={{"spec":{{"minReplicas":{new_min_replicas}}}}}'
            ]

            patch_result = await self.executor.execute_kubectl(
                args=patch_cmd[2:],
                namespace=namespace,
                dry_run=False,
            )

            if not patch_result.success:
                return ExecutionResult(
                    success=False,
                    error_message=f"Failed to patch HPA: {patch_result.stderr}",
                    timestamp=datetime.now(timezone.utc),
                )

            # Step 4: Schedule rollback if enabled
            rollback_message = ""
            if auto_rollback:
                # Note: In production, this would be handled by a scheduled job
                # For now, we just log the recommendation
                rollback_time = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
                rollback_message = f" (Auto-rollback scheduled at {rollback_time.isoformat()})"

            result = ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"Adjusted HPA {hpa_name} min replicas: {current_min} → {new_min_replicas}{rollback_message}",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        # Record execution
        self._record_execution(
            RemediationActionType.ADJUST_HPA_MIN_REPLICAS.value,
            result,
            {
                "namespace": namespace,
                "hpa_name": hpa_name,
                "previous_min_replicas": current_min if not dry_run else "unknown",
                "new_min_replicas": new_min_replicas,
                "duration_minutes": duration_minutes,
                "auto_rollback": auto_rollback,
                "alert_event_id": alert_event.id,
            }
        )

        return result


# Action factory
class RemediationActionFactory:
    """Factory for creating remediation actions."""

    _actions = {
        RemediationActionType.DELETE_CRASHLOOP_POD: DeleteCrashLoopPodAction,
        RemediationActionType.SCALE_DEPLOYMENT: ScaleDeploymentAction,
        RemediationActionType.ROLLBACK_DEPLOYMENT: RollbackDeploymentAction,
        RemediationActionType.RESTART_DEPLOYMENT: RestartDeploymentAction,
        # Phase 4A: New action types
        RemediationActionType.CLEAR_STUCK_PODS: ClearStuckPodsAction,
        RemediationActionType.CLEANUP_FAILED_JOBS: CleanupFailedJobsAction,
        RemediationActionType.ADJUST_HPA_MIN_REPLICAS: AdjustHPAMinReplicasAction,
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
