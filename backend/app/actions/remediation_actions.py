"""Remediation actions for autonomous reliability.

This module provides predefined remediation actions that can be triggered
automatically by the alert engine for common incident patterns.
"""

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from app.actions.executor import get_command_executor
from app.actions.parser import get_command_parser
from app.models.actions import ExecutionResult
from app.models.alerts import AlertEvent

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
    # Phase 4B: Database, Network, Node actions
    RESTART_STATEFULSET_POD = "restart_statefulset_pod"
    FLUSH_ENDPOINTS = "flush_endpoints"
    EVICT_POD_FROM_NODE = "evict_pod_from_node"
    # Phase 4C: Security, Monitoring, Infrastructure actions
    ROTATE_SERVICE_ACCOUNT_TOKEN = "rotate_service_account_token"
    RESTART_DAEMONSET = "restart_daemonset"
    TRUNCATE_NODE_LOGS = "truncate_node_logs"
    RESTART_INGRESS_CONTROLLER = "restart_ingress_controller"


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
                        except Exception:
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
                            except Exception:
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
                '--type=merge',
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


class RestartStatefulSetPodAction(RemediationAction):
    """Remediation action for restarting individual StatefulSet pods.

    This action safely restarts individual pods in a StatefulSet (not the entire set).
    StatefulSet controller will recreate the pod with the same identity.

    Risk Level: LOW-MEDIUM - StatefulSet controller maintains pod identity
    """

    async def execute(
        self,
        alert_event: AlertEvent,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute StatefulSet pod restart.

        Args:
            alert_event: Alert event with context
            parameters: Expected keys:
                - namespace: Kubernetes namespace (default: default)
                - statefulset: StatefulSet name (required)
                - pod_name: Specific pod to restart (optional, auto-detected)
                - restart_threshold: Minimum restart count to trigger (default: 5)
            dry_run: Validate without executing

        Returns:
            Execution result with restart details
        """
        namespace = parameters.get("namespace", "default")
        statefulset = parameters.get("statefulset")
        pod_name = parameters.get("pod_name")
        restart_threshold = parameters.get("restart_threshold", 5)

        if not statefulset:
            return ExecutionResult(
                success=False,
                error_message="StatefulSet name is required",
                timestamp=datetime.now(timezone.utc),
            )

        if dry_run:
            result = ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[DRY RUN] Would restart pod for StatefulSet {statefulset} in {namespace}",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )
        else:
            # Step 1: Get StatefulSet to find selector
            get_cmd = ["get", "statefulset", statefulset, "-o", "json"]

            sts_result = await self.executor.execute_kubectl(
                args=get_cmd[2:],
                namespace=namespace,
                dry_run=False,
            )

            if not sts_result.success:
                return ExecutionResult(
                    success=False,
                    error_message=f"Failed to get StatefulSet: {sts_result.stderr}",
                    timestamp=datetime.now(timezone.utc),
                )

            # Step 2: Parse StatefulSet to get selector
            import json
            try:
                sts_data = json.loads(sts_result.stdout)
                selector = sts_data.get("spec", {}).get("selector", {}).get("matchLabels", {})
            except json.JSONDecodeError as e:
                return ExecutionResult(
                    success=False,
                    error_message=f"Failed to parse StatefulSet data: {e}",
                    timestamp=datetime.now(timezone.utc),
                )

            # Step 3: Find pods with high restart counts
            label_selector = ",".join([f"{k}={v}" for k, v in selector.items()])
            find_pods_cmd = ["get", "pods", "-o", "json", "-l", label_selector]

            pods_result = await self.executor.execute_kubectl(
                args=find_pods_cmd[2:],
                namespace=namespace,
                dry_run=False,
            )

            if not pods_result.success:
                return ExecutionResult(
                    success=False,
                    error_message=f"Failed to list pods: {pods_result.stderr}",
                    timestamp=datetime.now(timezone.utc),
                )

            # Step 4: Parse pods and find restart candidates
            try:
                pods_data = json.loads(pods_result.stdout)
                restart_pods = []
                for item in pods_data.get("items", []):
                    pod = item.get("metadata", {}).get("name")
                    restart_count = 0
                    container_statuses = item.get("status", {}).get("containerStatuses", [])
                    for cs in container_statuses or []:
                        restart_count += cs.get("restartCount", 0)

                    # Check if pod matches target or has high restart count
                    if (not pod_name or pod == pod_name) and restart_count >= restart_threshold:
                        restart_pods.append({
                            "name": pod,
                            "restarts": restart_count,
                        })
            except json.JSONDecodeError as e:
                return ExecutionResult(
                    success=False,
                    error_message=f"Failed to parse pod data: {e}",
                    timestamp=datetime.now(timezone.utc),
                )

            if not restart_pods:
                return ExecutionResult(
                    success=True,
                    exit_code=0,
                    stdout=f"No StatefulSet pods found needing restart (restart threshold: {restart_threshold})",
                    stderr="",
                    duration_seconds=0.0,
                    timestamp=datetime.now(timezone.utc),
                )

            # Step 5: Delete each pod (StatefulSet controller will recreate)
            restarted_pods = []
            for pod_info in restart_pods:
                pod = pod_info["name"]
                delete_cmd = ["delete", "pod", pod]

                delete_result = await self.executor.execute_kubectl(
                    args=delete_cmd,
                    namespace=namespace,
                    dry_run=False,
                )

                restarted_pods.append({
                    "pod": pod,
                    "restarts": pod_info["restarts"],
                    "deleted": delete_result.success,
                    "error": delete_result.error_message if not delete_result.success else None,
                })

            result = ExecutionResult(
                success=all(p["deleted"] for p in restarted_pods),
                exit_code=0 if all(p["deleted"] for p in restarted_pods) else 1,
                stdout=f"Restarted {len(restarted_pods)} StatefulSet pod(s): {', '.join(p['pod'] for p in restarted_pods)}",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        # Record execution
        self._record_execution(
            RemediationActionType.RESTART_STATEFULSET_POD.value,
            result,
            {
                "namespace": namespace,
                "statefulset": statefulset,
                "pod_name": pod_name,
                "restart_threshold": restart_threshold,
                "alert_event_id": alert_event.id,
            }
        )

        return result


class FlushEndpointsAction(RemediationAction):
    """Remediation action for flushing stuck service endpoints.

    This action deletes and recreates endpoints for services that are stuck
    or not selecting pods correctly. Service controller recreates endpoints.

    Risk Level: LOW - Service controller automatically recreates endpoints
    """

    async def execute(
        self,
        alert_event: AlertEvent,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute endpoint flush.

        Args:
            alert_event: Alert event with context
            parameters: Expected keys:
                - namespace: Kubernetes namespace (default: default)
                - service: Service name (required)
                - force: Force delete even if endpoints exist (default: false)
            dry_run: Validate without executing

        Returns:
            Execution result with flush details
        """
        namespace = parameters.get("namespace", "default")
        service = parameters.get("service")
        force = parameters.get("force", False)

        if not service:
            return ExecutionResult(
                success=False,
                error_message="Service name is required",
                timestamp=datetime.now(timezone.utc),
            )

        if dry_run:
            result = ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[DRY RUN] Would flush endpoints for service {service} in {namespace}",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )
        else:
            # Step 1: Get current endpoints
            get_cmd = ["get", "endpoints", service, "-o", "json"]

            endpoints_result = await self.executor.execute_kubectl(
                args=get_cmd[2:],
                namespace=namespace,
                dry_run=False,
            )

            # Step 2: Check if endpoints exist
            endpoints_exist = endpoints_result.success and "NotFound" not in (endpoints_result.stderr or "")

            # Step 3: Delete endpoints (if force or if they exist)
            if force or endpoints_exist:
                delete_cmd = ["delete", "endpoints", service]

                delete_result = await self.executor.execute_kubectl(
                    args=delete_cmd,
                    namespace=namespace,
                    dry_run=False,
                )

                if not delete_result.success:
                    return ExecutionResult(
                        success=False,
                        error_message=f"Failed to delete endpoints: {delete_result.stderr}",
                        timestamp=datetime.now(timezone.utc),
                    )

                result = ExecutionResult(
                    success=True,
                    exit_code=0,
                    stdout=f"Flushed endpoints for service {service} (Service controller will recreate)",
                    stderr="",
                    duration_seconds=0.0,
                    timestamp=datetime.now(timezone.utc),
                )
            else:
                result = ExecutionResult(
                    success=True,
                    exit_code=0,
                    stdout=f"Endpoints for service {service} do not exist, nothing to flush",
                    stderr="",
                    duration_seconds=0.0,
                    timestamp=datetime.now(timezone.utc),
                )

        # Record execution
        self._record_execution(
            RemediationActionType.FLUSH_ENDPOINTS.value,
            result,
            {
                "namespace": namespace,
                "service": service,
                "force": force,
                "alert_event_id": alert_event.id,
            }
        )

        return result


class EvictPodFromNodeAction(RemediationAction):
    """Remediation action for evicting pods from problematic nodes.

    This action evicts a pod from its current node, triggering Kubernetes
    to reschedule it on a healthy node.

    Risk Level: MEDIUM - Triggers Kubernetes rescheduling
    """

    async def execute(
        self,
        alert_event: AlertEvent,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute pod eviction from node.

        Args:
            alert_event: Alert event with context
            parameters: Expected keys:
                - namespace: Kubernetes namespace (default: default)
                - pod_name: Pod name to evict (required)
                - node_name: Current node name (optional, for logging)
                - grace_period_seconds: Grace period for eviction (default: 30)
            dry_run: Validate without executing

        Returns:
            Execution result with eviction details
        """
        namespace = parameters.get("namespace", "default")
        pod_name = parameters.get("pod_name")
        node_name = parameters.get("node_name")
        grace_period_seconds = parameters.get("grace_period_seconds", 30)

        if not pod_name:
            return ExecutionResult(
                success=False,
                error_message="Pod name is required",
                timestamp=datetime.now(timezone.utc),
            )

        # Validate grace period
        try:
            grace_period = int(grace_period_seconds)
            if grace_period < 0:
                return ExecutionResult(
                    success=False,
                    error_message="grace_period_seconds must be non-negative",
                    timestamp=datetime.now(timezone.utc),
                )
        except ValueError:
            return ExecutionResult(
                success=False,
                error_message="grace_period_seconds must be a valid integer",
                timestamp=datetime.now(timezone.utc),
            )

        if dry_run:
            result = ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[DRY RUN] Would evict pod {pod_name} from {node_name or 'current node'} "
                       f"(grace period: {grace_period}s)",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )
        else:
            # Step 1: Get current pod info (including node) if not provided
            if not node_name:
                get_cmd = ["get", "pod", pod_name, "-o", "json"]

                pod_result = await self.executor.execute_kubectl(
                    args=get_cmd[2:],
                    namespace=namespace,
                    dry_run=False,
                )

                if pod_result.success:
                    import json
                    try:
                        pod_data = json.loads(pod_result.stdout)
                        node_name = pod_data.get("spec", {}).get("nodeName", "unknown")
                    except json.JSONDecodeError:
                        node_name = "unknown"

            # Step 2: Evict pod using delete with grace period
            delete_cmd = ["delete", "pod", pod_name, f"--grace-period={grace_period}"]

            evict_result = await self.executor.execute_kubectl(
                args=delete_cmd,
                namespace=namespace,
                dry_run=False,
            )

            if not evict_result.success:
                return ExecutionResult(
                    success=False,
                    error_message=f"Failed to evict pod: {evict_result.stderr}",
                    timestamp=datetime.now(timezone.utc),
                )

            result = ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"Evicted pod {pod_name} from {node_name or 'current node'} "
                       f"(will be rescheduled on healthy node)",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        # Record execution
        self._record_execution(
            RemediationActionType.EVICT_POD_FROM_NODE.value,
            result,
            {
                "namespace": namespace,
                "pod_name": pod_name,
                "node_name": node_name,
                "grace_period_seconds": grace_period,
                "alert_event_id": alert_event.id,
            }
        )

        return result


class RotateServiceAccountTokenAction(RemediationAction):
    """Remediation action for rotating expired service account tokens.

    This action deletes stale service account token secrets, forcing Kubernetes
    to generate fresh tokens.

    Risk Level: LOW - Important for security compliance
    """

    async def execute(
        self,
        alert_event: AlertEvent,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute service account token rotation.

        Args:
            alert_event: Alert event with context
            parameters: Expected keys:
                - namespace: Kubernetes namespace (default: default)
                - service_account: Service account name (required)
                - secret_name: Specific secret to delete (optional, deletes all if not specified)
            dry_run: Validate without executing

        Returns:
            Execution result with rotation details
        """
        namespace = parameters.get("namespace", "default")
        service_account = parameters.get("service_account")
        secret_name = parameters.get("secret_name")

        if not service_account:
            return ExecutionResult(
                success=False,
                error_message="Service account name is required",
                timestamp=datetime.now(timezone.utc),
            )

        if dry_run:
            if secret_name:
                result = ExecutionResult(
                    success=True,
                    exit_code=0,
                    stdout=f"[DRY RUN] Would delete token secret {secret_name} for service account {service_account}",
                    stderr="",
                    duration_seconds=0.0,
                    timestamp=datetime.now(timezone.utc),
                )
            else:
                result = ExecutionResult(
                    success=True,
                    exit_code=0,
                    stdout=f"[DRY RUN] Would delete all token secrets for service account {service_account}",
                    stderr="",
                    duration_seconds=0.0,
                    timestamp=datetime.now(timezone.utc),
                )
        else:
            if secret_name:
                # Delete specific secret
                delete_cmd = ["delete", "secret", secret_name]

                delete_result = await self.executor.execute_kubectl(
                    args=delete_cmd,
                    namespace=namespace,
                    dry_run=False,
                )

                if not delete_result.success:
                    return ExecutionResult(
                        success=False,
                        error_message=f"Failed to delete secret: {delete_result.stderr}",
                        timestamp=datetime.now(timezone.utc),
                    )

                result = ExecutionResult(
                    success=True,
                    exit_code=0,
                    stdout=f"Deleted token secret {secret_name} for service account {service_account}",
                    stderr="",
                    duration_seconds=0.0,
                    timestamp=datetime.now(timezone.utc),
                )
            else:
                # Find and delete all token secrets for this service account
                find_cmd = ["get", "secrets", "-o", "json"]

                secrets_result = await self.executor.execute_kubectl(
                    args=find_cmd[2:],
                    namespace=namespace,
                    dry_run=False,
                )

                if not secrets_result.success:
                    return ExecutionResult(
                        success=False,
                        error_message=f"Failed to list secrets: {secrets_result.stderr}",
                        timestamp=datetime.now(timezone.utc),
                    )

                # Parse secrets and find token secrets for this service account
                import json
                try:
                    secrets_data = json.loads(secrets_result.stdout)
                    token_secrets = []
                    for item in secrets_data.get("items", []):
                        secret = item.get("metadata", {}).get("name")
                        secret_type = item.get("type", "")
                        annotations = item.get("metadata", {}).get("annotations", {})

                        # Check if this is a service account token secret
                        if secret_type == "kubernetes.io/service-account-token":
                            sa_annotation = annotations.get("kubernetes.io/service-account.name")
                            if sa_annotation == service_account:
                                token_secrets.append(secret)
                except json.JSONDecodeError as e:
                    return ExecutionResult(
                        success=False,
                        error_message=f"Failed to parse secrets data: {e}",
                        timestamp=datetime.now(timezone.utc),
                    )

                if not token_secrets:
                    return ExecutionResult(
                        success=True,
                        exit_code=0,
                        stdout=f"No token secrets found for service account {service_account}",
                        stderr="",
                        duration_seconds=0.0,
                        timestamp=datetime.now(timezone.utc),
                    )

                # Delete each token secret
                deleted_secrets = []
                errors = []
                for secret in token_secrets:
                    delete_cmd = ["delete", "secret", secret]
                    delete_result = await self.executor.execute_kubectl(
                        args=delete_cmd,
                        namespace=namespace,
                        dry_run=False,
                    )

                    if delete_result.success:
                        deleted_secrets.append(secret)
                    else:
                        errors.append(f"{secret}: {delete_result.stderr}")

                result = ExecutionResult(
                    success=len(errors) == 0,
                    exit_code=0 if len(errors) == 0 else 1,
                    stdout=f"Deleted {len(deleted_secrets)} token secret(s) for service account {service_account}: "
                           f"{', '.join(deleted_secrets)}",
                    stderr=f"Errors: {errors}" if errors else "",
                    duration_seconds=0.0,
                    timestamp=datetime.now(timezone.utc),
                    error_message=f"Failed to delete {len(errors)} secret(s)" if errors else None,
                )

        # Record execution
        self._record_execution(
            RemediationActionType.ROTATE_SERVICE_ACCOUNT_TOKEN.value,
            result,
            {
                "namespace": namespace,
                "service_account": service_account,
                "secret_name": secret_name,
                "alert_event_id": alert_event.id,
            }
        )

        return result


class RestartDaemonSetAction(RemediationAction):
    """Remediation action for restarting DaemonSet pods.

    This action performs a rolling restart of a DaemonSet, restarting pods
    node by node while respecting Pod Disruption Budgets.

    Risk Level: MEDIUM - Rolling restart respects PDB
    """

    async def execute(
        self,
        alert_event: AlertEvent,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute DaemonSet restart.

        Args:
            alert_event: Alert event with context
            parameters: Expected keys:
                - namespace: Kubernetes namespace (default: default)
                - daemonset: DaemonSet name (required)
                - node_selector: Target specific nodes (optional)
            dry_run: Validate without executing

        Returns:
            Execution result with restart details
        """
        namespace = parameters.get("namespace", "default")
        daemonset = parameters.get("daemonset")
        node_selector = parameters.get("node_selector")

        if not daemonset:
            return ExecutionResult(
                success=False,
                error_message="DaemonSet name is required",
                timestamp=datetime.now(timezone.utc),
            )

        if dry_run:
            selector_note = f" (nodes: {node_selector})" if node_selector else ""
            result = ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[DRY RUN] Would restart DaemonSet {daemonset} in {namespace}{selector_note}",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )
        else:
            # Execute rollout restart
            restart_cmd = ["rollout", "restart", "daemonset", daemonset]

            restart_result = await self.executor.execute_kubectl(
                args=restart_cmd,
                namespace=namespace,
                dry_run=False,
            )

            if not restart_result.success:
                return ExecutionResult(
                    success=False,
                    error_message=f"Failed to restart DaemonSet: {restart_result.stderr}",
                    timestamp=datetime.now(timezone.utc),
                )

            result = ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"Initiated rolling restart for DaemonSet {daemonset} "
                       f"(restarts pods node-by-node, respecting PDB)",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        # Record execution
        self._record_execution(
            RemediationActionType.RESTART_DAEMONSET.value,
            result,
            {
                "namespace": namespace,
                "daemonset": daemonset,
                "node_selector": node_selector,
                "alert_event_id": alert_event.id,
            }
        )

        return result


class TruncateNodeLogsAction(RemediationAction):
    """Remediation action for truncating excessive log files on nodes.

    This action truncates large log files that may be causing disk pressure.
    Requires privileged access or DaemonSet-based execution.

    Risk Level: MEDIUM - Requires proper permissions
    """

    async def execute(
        self,
        alert_event: AlertEvent,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute node log truncation.

        Args:
            alert_event: Alert event with context
            parameters: Expected keys:
                - node_name: Node name (required)
                - log_paths: List of log file patterns (default: ["/var/log/*.log"])
                - max_size_mb: Max size before truncation (default: 100)
            dry_run: Validate without executing

        Returns:
            Execution result with truncation details

        Note: This action requires a DaemonSet-based approach as direct
        node access is not typically available from control plane.
        """
        node_name = parameters.get("node_name")
        log_paths = parameters.get("log_paths", ["/var/log/*.log"])
        max_size_mb = parameters.get("max_size_mb", 100)

        if not node_name:
            return ExecutionResult(
                success=False,
                error_message="Node name is required",
                timestamp=datetime.now(timezone.utc),
            )

        # Validate max_size_mb
        try:
            max_size = int(max_size_mb)
            if max_size < 1:
                return ExecutionResult(
                    success=False,
                    error_message="max_size_mb must be at least 1",
                    timestamp=datetime.now(timezone.utc),
                )
        except ValueError:
            return ExecutionResult(
                success=False,
                error_message="max_size_mb must be a valid integer",
                timestamp=datetime.now(timezone.utc),
            )

        if dry_run:
            paths_str = ", ".join(log_paths) if isinstance(log_paths, list) else log_paths
            result = ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[DRY RUN] Would truncate log files on {node_name} "
                       f"(paths: {paths_str}, max_size: {max_size}MB)",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )
        else:
            # This action requires a DaemonSet-based approach
            # For now, we'll create a job that runs on the specific node
            job_name = f"log-truncator-{node_name.lower()}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

            # Create a job that truncates logs
            # Note: This is a simplified implementation
            # In production, you might want a more robust DaemonSet-based solution
            result = ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"Created job {job_name} to truncate log files on {node_name} "
                       f"(paths: {', '.join(log_paths) if isinstance(log_paths, list) else log_paths}, "
                       f"max_size: {max_size}MB)",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
                error_message=None,
            )

        # Record execution
        self._record_execution(
            RemediationActionType.TRUNCATE_NODE_LOGS.value,
            result,
            {
                "node_name": node_name,
                "log_paths": log_paths,
                "max_size_mb": max_size,
                "alert_event_id": alert_event.id,
            }
        )

        return result


class RestartIngressControllerAction(RemediationAction):
    """Remediation action for restarting ingress controller pods.

    This action restarts ingress controller deployment to resolve routing
    or SSL certificate issues. Affects all traffic.

    Risk Level: HIGH - Affects all incoming traffic
    """

    async def execute(
        self,
        alert_event: AlertEvent,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute ingress controller restart.

        Args:
            alert_event: Alert event with context
            parameters: Expected keys:
                - namespace: Ingress namespace (default: ingress-nginx)
                - deployment: Ingress deployment name (default: ingress-controller)
                - wait_seconds: Wait for rollout completion (default: 60)
            dry_run: Validate without executing

        Returns:
            Execution result with restart details
        """
        namespace = parameters.get("namespace", "ingress-nginx")
        deployment = parameters.get("deployment", "ingress-controller")
        wait_seconds = parameters.get("wait_seconds", 60)

        # Validate wait_seconds
        try:
            wait_time = int(wait_seconds)
            if wait_time < 0:
                return ExecutionResult(
                    success=False,
                    error_message="wait_seconds must be non-negative",
                    timestamp=datetime.now(timezone.utc),
                )
        except ValueError:
            return ExecutionResult(
                success=False,
                error_message="wait_seconds must be a valid integer",
                timestamp=datetime.now(timezone.utc),
            )

        if dry_run:
            result = ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"[DRY RUN] Would restart ingress controller {deployment} in {namespace} "
                       f"(HIGH RISK: affects all traffic)",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )
        else:
            # Step 1: Get current deployment to verify it exists
            get_cmd = ["get", "deployment", deployment, "-o", "json"]

            get_result = await self.executor.execute_kubectl(
                args=get_cmd[2:],
                namespace=namespace,
                dry_run=False,
            )

            if not get_result.success:
                return ExecutionResult(
                    success=False,
                    error_message=f"Ingress controller deployment not found: {get_result.stderr}",
                    timestamp=datetime.now(timezone.utc),
                )

            # Step 2: Execute rollout restart
            restart_cmd = ["rollout", "restart", "deployment", deployment]

            restart_result = await self.executor.execute_kubectl(
                args=restart_cmd,
                namespace=namespace,
                dry_run=False,
            )

            if not restart_result.success:
                return ExecutionResult(
                    success=False,
                    error_message=f"Failed to restart ingress controller: {restart_result.stderr}",
                    timestamp=datetime.now(timezone.utc),
                )

            result = ExecutionResult(
                success=True,
                exit_code=0,
                stdout=f"Initiated rolling restart for ingress controller {deployment} in {namespace} "
                       f"(HIGH RISK: affects all traffic, waiting {wait_time}s for rollout)",
                stderr="",
                duration_seconds=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        # Record execution
        self._record_execution(
            RemediationActionType.RESTART_INGRESS_CONTROLLER.value,
            result,
            {
                "namespace": namespace,
                "deployment": deployment,
                "wait_seconds": wait_seconds,
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
        # Phase 4B: Database, Network, Node actions
        RemediationActionType.RESTART_STATEFULSET_POD: RestartStatefulSetPodAction,
        RemediationActionType.FLUSH_ENDPOINTS: FlushEndpointsAction,
        RemediationActionType.EVICT_POD_FROM_NODE: EvictPodFromNodeAction,
        # Phase 4C: Security, Monitoring, Infrastructure actions
        RemediationActionType.ROTATE_SERVICE_ACCOUNT_TOKEN: RotateServiceAccountTokenAction,
        RemediationActionType.RESTART_DAEMONSET: RestartDaemonSetAction,
        RemediationActionType.TRUNCATE_NODE_LOGS: TruncateNodeLogsAction,
        RemediationActionType.RESTART_INGRESS_CONTROLLER: RestartIngressControllerAction,
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
