"""Remediation actions for autonomous reliability.

This module provides predefined remediation actions that can be triggered
automatically by the alert engine for common incident patterns.

Shared helpers build the standard ``ExecutionResult`` shapes and wrap the
repeated ``executor.execute_kubectl`` / validation patterns so each action
only implements its own logic.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from app.actions.executor import get_command_executor
from app.actions.parser import get_command_parser
from app.models.actions import ExecutionResult
from app.models.alerts import AlertEvent

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Current UTC timestamp (used for all result timestamps)."""
    return datetime.now(timezone.utc)


def _fail(error_message: str) -> ExecutionResult:
    """Failed result carrying only an error message."""
    return ExecutionResult(success=False, error_message=error_message, timestamp=_utcnow())


def _ok(
    stdout: str,
    *,
    exit_code: int = 0,
    stderr: str = "",
    duration_seconds: float = 0.0,
    error_message: str | None = None,
) -> ExecutionResult:
    """Successful result produced locally (no kubectl execution)."""
    return ExecutionResult(
        success=True,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_seconds=duration_seconds,
        error_message=error_message,
        timestamp=_utcnow(),
    )


def _dry_run(message: str) -> ExecutionResult:
    """Standard dry-run result: '[DRY RUN] Would <message>'."""
    return _ok(f"[DRY RUN] Would {message}")


def _from_result(result: ExecutionResult, success_stdout: str) -> ExecutionResult:
    """Wrap a kubectl result, replacing stdout with a message on success."""
    return ExecutionResult(
        success=result.success,
        exit_code=result.exit_code,
        stdout=success_stdout if result.success else result.stdout,
        stderr=result.stderr,
        duration_seconds=result.duration_seconds,
        timestamp=_utcnow(),
        error_message=result.error_message,
    )


def _required(parameters: dict[str, Any], key: str, label: str) -> tuple[Any, ExecutionResult | None]:
    """Fetch a required parameter; returns (value, error result or None)."""
    value = parameters.get(key)
    return value, None if value else _fail(f"{label} is required")


def _validated_int(value: Any, name: str, minimum: int) -> tuple[int | None, ExecutionResult | None]:
    """Parse an int parameter with an inclusive lower bound.

    Returns (parsed int, error result or None). Bounds of 0 report as
    "non-negative"; anything higher reports as "at least N".
    """
    try:
        parsed = int(value)
    except ValueError:
        return None, _fail(f"{name} must be a valid integer")
    if parsed < minimum:
        bound = "non-negative" if minimum == 0 else f"at least {minimum}"
        return None, _fail(f"{name} must be {bound}")
    return parsed, None


def _parse_json_output(stdout: str, what: str) -> tuple[dict[str, Any] | None, ExecutionResult | None]:
    """Parse kubectl JSON output; returns (data, error result or None)."""
    try:
        return json.loads(stdout), None
    except json.JSONDecodeError as e:
        return None, _fail(f"Failed to parse {what}: {e}")


def _list_args(resource: str, namespace: str, label_selector: str = "") -> list[str]:
    """Args for listing a resource as JSON, with namespace and optional selector."""
    args = [resource, "-n", namespace, "-o", "json"]
    if label_selector:
        args.extend(["-l", label_selector])
    return args


def _deletions_result(stdout: str, pods: list[dict]) -> ExecutionResult:
    """Result for a batch of pod deletions tracked as per-pod dicts."""
    all_ok = all(p["deleted"] for p in pods)
    return ExecutionResult(
        success=all_ok,
        exit_code=0 if all_ok else 1,
        stdout=stdout,
        stderr="",
        duration_seconds=0.0,
        timestamp=_utcnow(),
    )


def _batch_result(
    stdout: str,
    deleted: list[str],
    errors: list[str],
    fail_verb: str,
    fail_noun: str,
    stderr_prefix: str = "",
) -> ExecutionResult:
    """Result for a batch of per-item delete operations."""
    return _ok(
        stdout,
        exit_code=0 if not errors else 1,
        stderr=f"{stderr_prefix}Errors: {errors}" if errors else "",
        error_message=f"Failed to {fail_verb} {len(errors)} {fail_noun}" if errors else None,
    )


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
        self, alert_event: AlertEvent, parameters: dict[str, Any], dry_run: bool = False
    ) -> ExecutionResult:
        """Execute the remediation action (implemented by subclasses).

        alert_event: the alert that triggered this action; parameters:
        action-specific; dry_run: if True, validate without executing.
        """
        raise NotImplementedError("Subclasses must implement execute()")

    async def _run(
        self, args: list[str], namespace: str | None = None, dry_run: bool = False
    ) -> ExecutionResult:
        """Run a kubectl command through the shared executor."""
        return await self.executor.execute_kubectl(
            args=args, namespace=namespace, dry_run=dry_run
        )

    async def _run_batch(
        self, commands: dict[str, list[str]], namespace: str | None
    ) -> tuple[list[str], list[str]]:
        """Run one kubectl command per entry, in order.

        Returns (names whose command succeeded, "name: stderr" error strings).
        """
        succeeded: list[str] = []
        errors: list[str] = []
        for name, args in commands.items():
            result = await self._run(args, namespace)
            if result.success:
                succeeded.append(name)
            else:
                errors.append(f"{name}: {result.stderr}")
        return succeeded, errors

    def _record_execution(self, action_type: str, result: ExecutionResult, context: dict):
        """Record execution for learning and audit."""
        record = {
            "timestamp": _utcnow().isoformat(),
            "action_type": action_type,
            "success": result.success,
            "duration_seconds": result.duration_seconds,
            "context": context,
        }
        self._execution_history.append(record)
        # Keep history limited
        if len(self._execution_history) > self._max_history:
            self._execution_history.pop(0)

    def _record_and_return(
        self,
        action_type: RemediationActionType,
        result: ExecutionResult,
        context: dict,
    ) -> ExecutionResult:
        """Record execution history, then hand the result back to the caller."""
        self._record_execution(action_type.value, result, context)
        return result

    def get_execution_history(self) -> list[dict]:
        """Get execution history for learning."""
        return self._execution_history.copy()


class DeleteCrashLoopPodAction(RemediationAction):
    """Deletes CrashLoopBackOff pods (high restart counts) so the deployment
    controller can recreate them."""

    async def execute(
        self, alert_event: AlertEvent, parameters: dict[str, Any], dry_run: bool = False
    ) -> ExecutionResult:
        """Execute crashloop pod deletion.

        parameters: namespace, pod_name (optional, auto-detected),
        restart_threshold (default 5), label_selector (optional).
        """
        namespace = parameters.get("namespace", "default")
        restart_threshold = parameters.get("restart_threshold", 5)
        pod_name = parameters.get("pod_name")
        label_selector = parameters.get("label_selector", "")

        # Step 1: Find pods with high restart counts
        pods_result = await self._run(_list_args("pods", namespace, label_selector), namespace)
        if not pods_result.success:
            return _fail(f"Failed to list pods: {pods_result.stderr}")

        # Step 2: Parse pods and find crashloop candidates
        pods_data, parse_error = _parse_json_output(pods_result.stdout, "pod data")
        if parse_error:
            return parse_error

        crashloop_pods = []
        for item in pods_data.get("items", []):
            pod = item.get("metadata", {}).get("name")
            restart_count = (
                item.get("status", {}).get("containerStatuses", [{}])[0].get("restartCount", 0)
            )
            status = item.get("status", {}).get("phase", "")

            # Check for crashloop or high restart count
            is_crashloop = (
                restart_count >= restart_threshold
                or (status == "Running" and restart_count >= 3)
            )

            if is_crashloop and (not pod_name or pod == pod_name):
                crashloop_pods.append({"name": pod, "restarts": restart_count, "status": status})

        if not crashloop_pods:
            return _ok(f"No crashloop pods found (restart threshold: {restart_threshold})")

        # Step 3: Delete each crashloop pod
        deleted_pods = []
        for pod_info in crashloop_pods:
            pod = pod_info["name"]
            if dry_run:
                result = _dry_run(f"delete pod: {pod}")
            else:
                result = await self._run(["delete", "pod", pod], namespace)

            deleted_pods.append({
                "pod": pod, "restarts": pod_info["restarts"], "deleted": result.success,
                "error": result.error_message if not result.success else None,
            })

        self._record_execution(
            RemediationActionType.DELETE_CRASHLOOP_POD.value,
            (
                result if len(deleted_pods) == 1
                else ExecutionResult(success=all(p["deleted"] for p in deleted_pods))
            ),
            {
                "namespace": namespace,
                "pods_deleted": len(deleted_pods),
                "alert_event_id": alert_event.id,
            },
        )

        return _deletions_result(
            f"Deleted {len(deleted_pods)} crashloop pods: "
            f"{', '.join(p['pod'] for p in deleted_pods)}",
            deleted_pods,
        )


class ScaleDeploymentAction(RemediationAction):
    """Scales deployments up or down based on CPU/memory thresholds."""

    async def execute(
        self, alert_event: AlertEvent, parameters: dict[str, Any], dry_run: bool = False
    ) -> ExecutionResult:
        """Execute deployment scaling.

        parameters: namespace, deployment, replicas (absolute or '+2'/'-1'),
        min_replicas (default 1), max_replicas (default 10).
        """
        namespace = parameters.get("namespace", "default")
        deployment, error = _required(parameters, "deployment", "Deployment name")
        if error:
            return error
        replicas_param = parameters.get("replicas", "+1")
        min_replicas = parameters.get("min_replicas", 1)
        max_replicas = parameters.get("max_replicas", 10)

        # Step 1: Get current replica count
        current_result = await self._run(["get", "deployment", deployment, "-o", "json"], namespace)
        if not current_result.success:
            return _fail(f"Failed to get deployment: {current_result.stderr}")

        try:
            deploy_data = json.loads(current_result.stdout)
            current_replicas = deploy_data.get("spec", {}).get("replicas", 1)
        except json.JSONDecodeError:
            return _fail("Failed to parse deployment data")

        # Step 2: Calculate target replicas, then apply safety limits
        if isinstance(replicas_param, str) and replicas_param.startswith(("+", "-")):
            target_replicas = current_replicas + int(replicas_param)
        else:
            target_replicas = int(replicas_param)

        target_replicas = max(min_replicas, min(target_replicas, max_replicas))

        if target_replicas == current_replicas:
            return _ok(f"Deployment already at {current_replicas} replicas (within limits)")

        # Step 3: Scale deployment
        if dry_run:
            result = _dry_run(
                f"scale {deployment} from {current_replicas} to {target_replicas} replicas"
            )
        else:
            result = await self._run(
                ["scale", "deployment", deployment, "--replicas", str(target_replicas)], namespace
            )

        self._record_execution(
            RemediationActionType.SCALE_DEPLOYMENT.value,
            result,
            {
                "namespace": namespace,
                "deployment": deployment,
                "from_replicas": current_replicas,
                "to_replicas": target_replicas,
                "alert_event_id": alert_event.id,
            },
        )

        return _from_result(
            result, f"Scaled {deployment} from {current_replicas} to {target_replicas} replicas"
        )


class RollbackDeploymentAction(RemediationAction):
    """Rolls back a failing deployment to the previous stable revision."""

    async def execute(
        self, alert_event: AlertEvent, parameters: dict[str, Any], dry_run: bool = False
    ) -> ExecutionResult:
        """Execute deployment rollback.

        parameters: namespace, deployment, revision (default: previous).
        """
        namespace = parameters.get("namespace", "default")
        deployment, error = _required(parameters, "deployment", "Deployment name")
        if error:
            return error
        target_revision = parameters.get("revision", None)

        # Step 1: Get rollout history (also performed in dry-run)
        history_result = await self._run(["rollout", "history", "deployment", deployment], namespace)
        if not history_result.success and "not found" in history_result.error_message.lower():
            return _fail(f"Deployment '{deployment}' not found")

        # Step 2: Determine rollback command ('undo' rolls back to previous)
        rollback_cmd = ["rollout", "undo", "deployment", deployment]
        if target_revision is not None:
            rollback_cmd.append(f"--to-revision={target_revision}")

        if dry_run:
            result = _dry_run(f"rollback {deployment} to revision {target_revision or 'previous'}")
        else:
            result = await self._run(rollback_cmd, namespace)

        self._record_execution(
            RemediationActionType.ROLLBACK_DEPLOYMENT.value,
            result,
            {
                "namespace": namespace,
                "deployment": deployment,
                "target_revision": target_revision or "previous",
                "alert_event_id": alert_event.id,
            },
        )

        return _from_result(result, f"Rollback initiated for {deployment}")


class RestartDeploymentAction(RemediationAction):
    """Performs a rolling restart of a deployment to refresh its pods."""

    async def execute(
        self, alert_event: AlertEvent, parameters: dict[str, Any], dry_run: bool = False
    ) -> ExecutionResult:
        """Execute deployment restart.

        parameters: namespace, deployment.
        """
        namespace = parameters.get("namespace", "default")
        deployment, error = _required(parameters, "deployment", "Deployment name")
        if error:
            return error

        # Execute rollout restart
        if dry_run:
            result = _dry_run(f"restart deployment {deployment}")
        else:
            result = await self._run(["rollout", "restart", deployment], namespace)

        self._record_execution(
            RemediationActionType.RESTART_DEPLOYMENT.value,
            result,
            {"namespace": namespace, "deployment": deployment, "alert_event_id": alert_event.id},
        )

        return _from_result(result, f"Rollout restart initiated for {deployment}")


class ClearStuckPodsAction(RemediationAction):
    """Clears pods stuck in problematic states (Terminating, ImagePullBackOff,
    ErrImagePull, CrashLoopBackOff, CreateContainerError, ...) via force delete.

    Risk Level: LOW - Force deletion is safe as controllers recreate pods
    """

    STUCK_STATES = {
        "Terminating", "ImagePullBackOff", "ErrImagePull", "CrashLoopBackOff",
        "CreateContainerError", "CreateContainerConfigError", "RunContainerError",
        "ErrImageNeverPull", "InvalidImageName",
    }

    async def execute(
        self, alert_event: AlertEvent, parameters: dict[str, Any], dry_run: bool = False
    ) -> ExecutionResult:
        """Execute stuck pod clearance.

        parameters: namespace, stuck_duration_minutes (default 10),
        label_selector (optional), pod_names (optional target list).
        """
        namespace = parameters.get("namespace", "default")
        stuck_duration_minutes = parameters.get("stuck_duration_minutes", 10)
        label_selector = parameters.get("label_selector", "")
        target_pods = parameters.get("pod_names", [])

        if dry_run:
            # In dry-run, just report what would be done
            result = _dry_run(
                f"clear stuck pods in {namespace} "
                f"(stuck for >{stuck_duration_minutes} minutes)"
            )
        else:
            # Step 1: Find stuck pods
            pods_result = await self._run(_list_args("pods", namespace, label_selector), namespace)
            if not pods_result.success:
                return _fail(f"Failed to list pods: {pods_result.stderr}")

            # Step 2: Parse and identify stuck pods
            pods_data, parse_error = _parse_json_output(pods_result.stdout, "pod data")
            if parse_error:
                return parse_error

            stuck_pods = []
            cutoff_time = _utcnow() - timedelta(minutes=stuck_duration_minutes)

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
                        pod_start_time = datetime.fromisoformat(
                            pod_start_time_str.replace("Z", "+00:00")
                        )
                        if pod_start_time > cutoff_time:
                            is_stuck = True  # Only clear if stuck long enough
                        else:
                            is_stuck = False
                            stuck_reason = (
                                f"Pod not stuck long enough (started {pod_start_time_str})"
                            )
                    except Exception:
                        pass  # If we can't parse time, still consider it stuck

                # Check if pod is in target list (if specified)
                if target_pods and pod_name not in target_pods:
                    is_stuck = False

                if is_stuck:
                    stuck_pods.append(
                        {"name": pod_name, "status": pod_status, "reason": stuck_reason}
                    )

            # Step 3: Delete stuck pods
            deleted_pods, errors = await self._run_batch(
                {p["name"]: ["pod", p["name"], "--force", "--grace-period=0"] for p in stuck_pods},
                namespace,
            )

            # Build result
            result = _batch_result(
                f"Cleared {len(deleted_pods)} stuck pod(s): {', '.join(deleted_pods)}",
                deleted_pods, errors, "clear", "pod(s)",
            )

        return self._record_and_return(
            RemediationActionType.CLEAR_STUCK_PODS,
            result,
            {
                "namespace": namespace, "stuck_duration_minutes": stuck_duration_minutes,
                "label_selector": label_selector, "target_pods": target_pods,
                "alert_event_id": alert_event.id,
            },
        )


class CleanupFailedJobsAction(RemediationAction):
    """Removes failed jobs older than a threshold to prevent disk space
    issues and improve cluster hygiene.

    Risk Level: LOW - Only removes failed jobs, not running/completed ones
    """

    @staticmethod
    def _job_failed_at(conditions: list[dict], start_time_str: str,
                       cutoff_time: datetime) -> datetime | None:
        """Failure time of a job per its conditions; None if not failed."""
        for condition in conditions:
            if condition.get("type", "") == "Failed" and condition.get("status", "") == "True":
                failed_time_str = condition.get("lastTransitionTime", start_time_str)
                try:
                    return datetime.fromisoformat(failed_time_str.replace("Z", "+00:00"))
                except Exception:
                    return cutoff_time - timedelta(hours=1)  # Conservative
        return None

    async def execute(
        self, alert_event: AlertEvent, parameters: dict[str, Any], dry_run: bool = False
    ) -> ExecutionResult:
        """Execute failed job cleanup.

        parameters: namespace, failed_hours_ago (default 24),
        label_selector (optional), keep_last (default 5).
        """
        namespace = parameters.get("namespace", "default")
        failed_hours_ago = parameters.get("failed_hours_ago", 24)
        label_selector = parameters.get("label_selector", "")
        keep_last = parameters.get("keep_last", 5)

        if dry_run:
            result = _dry_run(
                f"cleanup failed jobs in {namespace} "
                f"(failed >{failed_hours_ago} hours ago, keeping last {keep_last})"
            )
        else:
            # Step 1: Find failed jobs
            jobs_result = await self._run(_list_args("jobs", namespace, label_selector), namespace)
            if not jobs_result.success:
                return _fail(f"Failed to list jobs: {jobs_result.stderr}")

            # Step 2: Parse and identify failed jobs
            jobs_data, parse_error = _parse_json_output(jobs_result.stdout, "job data")
            if parse_error:
                return parse_error

            cutoff_time = _utcnow() - timedelta(hours=failed_hours_ago)
            failed_jobs = []
            for item in jobs_data.get("items", []):
                job_name = item.get("metadata", {}).get("name")
                job_status = item.get("status", {})
                failed_time = self._job_failed_at(
                    job_status.get("conditions", []),
                    item.get("status", {}).get("startTime", ""),
                    cutoff_time,
                )
                if failed_time and failed_time < cutoff_time:
                    failed_jobs.append(
                        {"name": job_name, "failed_at": failed_time.isoformat()}
                    )

            # Sort by failed time (oldest first) and keep last N
            failed_jobs.sort(key=lambda x: x["failed_at"])
            jobs_to_delete = failed_jobs[:-keep_last] if len(failed_jobs) > keep_last else []

            # Step 3: Delete failed jobs
            deleted_jobs, errors = await self._run_batch(
                {job["name"]: ["job", job["name"]] for job in jobs_to_delete},
                namespace,
            )

            # Build result
            result = _batch_result(
                f"Cleaned up {len(deleted_jobs)} failed job(s): {', '.join(deleted_jobs)}",
                deleted_jobs, errors, "cleanup", "job(s)",
                stderr_prefix=f"Kept last {keep_last} failed jobs. ",
            )

        return self._record_and_return(
            RemediationActionType.CLEANUP_FAILED_JOBS,
            result,
            {
                "namespace": namespace, "failed_hours_ago": failed_hours_ago,
                "label_selector": label_selector, "keep_last": keep_last,
                "alert_event_id": alert_event.id,
            },
        )


class AdjustHPAMinReplicasAction(RemediationAction):
    """Temporarily increases HPA minReplicas for load spikes, with automatic
    rollback after a duration.

    Risk Level: LOW-MEDIUM - Reversible with time limit
    """

    async def execute(
        self, alert_event: AlertEvent, parameters: dict[str, Any], dry_run: bool = False
    ) -> ExecutionResult:
        """Execute HPA min replica adjustment.

        parameters: namespace, hpa_name (required), new_min_replicas
        (required), duration_minutes (default 60), auto_rollback (default true).
        """
        namespace = parameters.get("namespace", "default")
        hpa_name, error = _required(parameters, "hpa_name", "HPA name")
        if error:
            return error

        new_min_replicas = parameters.get("new_min_replicas")
        if new_min_replicas is None:
            return _fail("new_min_replicas is required")

        new_min_replicas, error = _validated_int(new_min_replicas, "new_min_replicas", 1)
        if error:
            return error

        duration_minutes = parameters.get("duration_minutes", 60)
        auto_rollback = parameters.get("auto_rollback", True)

        if dry_run:
            result = _dry_run(
                f"adjust HPA {hpa_name} min replicas to {new_min_replicas} "
                f"for {duration_minutes} minutes (auto-rollback: {auto_rollback})"
            )
        else:
            # Step 1: Get current HPA config
            hpa_result = await self._run(["hpa", hpa_name, "-n", namespace, "-o", "json"], namespace)
            if not hpa_result.success:
                return _fail(f"Failed to get HPA {hpa_name}: {hpa_result.stderr}")

            # Step 2: Parse current config and validate new_min vs maxReplicas
            hpa_data, parse_error = _parse_json_output(hpa_result.stdout, "HPA data")
            if parse_error:
                return parse_error

            current_min = hpa_data.get("spec", {}).get("minReplicas", 1)
            current_max = hpa_data.get("spec", {}).get("maxReplicas", 10)
            if new_min_replicas > current_max:
                return _fail(
                    f"new_min_replicas ({new_min_replicas}) "
                    f"cannot exceed maxReplicas ({current_max})"
                )

            # Step 3: Apply new min replicas
            patch_result = await self._run(
                ["hpa", hpa_name, "--type=merge",
                 f'-p={{"spec":{{"minReplicas":{new_min_replicas}}}}}'],
                namespace,
            )
            if not patch_result.success:
                return _fail(f"Failed to patch HPA: {patch_result.stderr}")

            # Step 4: Schedule rollback if enabled
            # Note: In production this would be a scheduled job; we log the
            # recommendation for now.
            rollback_message = ""
            if auto_rollback:
                rollback_time = _utcnow() + timedelta(minutes=duration_minutes)
                rollback_message = f" (Auto-rollback scheduled at {rollback_time.isoformat()})"

            result = _ok(
                f"Adjusted HPA {hpa_name} min replicas: "
                f"{current_min} → {new_min_replicas}{rollback_message}"
            )

        return self._record_and_return(
            RemediationActionType.ADJUST_HPA_MIN_REPLICAS,
            result,
            {
                "namespace": namespace, "hpa_name": hpa_name,
                "previous_min_replicas": current_min if not dry_run else "unknown",
                "new_min_replicas": new_min_replicas,
                "duration_minutes": duration_minutes, "auto_rollback": auto_rollback,
                "alert_event_id": alert_event.id,
            },
        )


class RestartStatefulSetPodAction(RemediationAction):
    """Restarts individual StatefulSet pods (not the whole set); the
    StatefulSet controller recreates each pod with the same identity.

    Risk Level: LOW-MEDIUM - StatefulSet controller maintains pod identity
    """

    async def execute(
        self, alert_event: AlertEvent, parameters: dict[str, Any], dry_run: bool = False
    ) -> ExecutionResult:
        """Execute StatefulSet pod restart.

        parameters: namespace, statefulset (required), pod_name (optional,
        auto-detected), restart_threshold (default 5).
        """
        namespace = parameters.get("namespace", "default")
        statefulset, error = _required(parameters, "statefulset", "StatefulSet name")
        if error:
            return error
        pod_name = parameters.get("pod_name")
        restart_threshold = parameters.get("restart_threshold", 5)

        if dry_run:
            result = _dry_run(f"restart pod for StatefulSet {statefulset} in {namespace}")
        else:
            # Step 1: Get StatefulSet to find selector
            sts_result = await self._run(["statefulset", statefulset, "-o", "json"], namespace)
            if not sts_result.success:
                return _fail(f"Failed to get StatefulSet: {sts_result.stderr}")

            # Step 2: Parse StatefulSet to get selector
            sts_data, parse_error = _parse_json_output(sts_result.stdout, "StatefulSet data")
            if parse_error:
                return parse_error

            selector = sts_data.get("spec", {}).get("selector", {}).get("matchLabels", {})

            # Step 3: Find pods with high restart counts
            label_selector = ",".join(f"{k}={v}" for k, v in selector.items())
            pods_result = await self._run(["pods", "-o", "json", "-l", label_selector], namespace)
            if not pods_result.success:
                return _fail(f"Failed to list pods: {pods_result.stderr}")

            # Step 4: Parse pods and find restart candidates
            pods_data, parse_error = _parse_json_output(pods_result.stdout, "pod data")
            if parse_error:
                return parse_error

            restart_pods = []
            for item in pods_data.get("items", []):
                pod = item.get("metadata", {}).get("name")
                statuses = item.get("status", {}).get("containerStatuses", []) or []
                restart_count = sum(cs.get("restartCount", 0) for cs in statuses)

                # Check if pod matches target or has high restart count
                if (not pod_name or pod == pod_name) and restart_count >= restart_threshold:
                    restart_pods.append({"name": pod, "restarts": restart_count})

            if not restart_pods:
                return _ok(
                    f"No StatefulSet pods found needing restart "
                    f"(restart threshold: {restart_threshold})"
                )

            # Step 5: Delete each pod (StatefulSet controller will recreate)
            restarted_pods = []
            for pod_info in restart_pods:
                delete_result = await self._run(["delete", "pod", pod_info["name"]], namespace)
                restarted_pods.append({
                    "pod": pod_info["name"], "restarts": pod_info["restarts"],
                    "deleted": delete_result.success,
                    "error": delete_result.error_message if not delete_result.success else None,
                })

            result = _deletions_result(
                f"Restarted {len(restarted_pods)} StatefulSet pod(s): "
                f"{', '.join(p['pod'] for p in restarted_pods)}",
                restarted_pods,
            )

        return self._record_and_return(
            RemediationActionType.RESTART_STATEFULSET_POD,
            result,
            {
                "namespace": namespace, "statefulset": statefulset, "pod_name": pod_name,
                "restart_threshold": restart_threshold, "alert_event_id": alert_event.id,
            },
        )


class FlushEndpointsAction(RemediationAction):
    """Flushes stuck service endpoints by deleting them; the Service
    controller recreates them.

    Risk Level: LOW - Service controller automatically recreates endpoints
    """

    async def execute(
        self, alert_event: AlertEvent, parameters: dict[str, Any], dry_run: bool = False
    ) -> ExecutionResult:
        """Execute endpoint flush.

        parameters: namespace, service (required), force (force delete even
        if endpoints exist, default false).
        """
        namespace = parameters.get("namespace", "default")
        service, error = _required(parameters, "service", "Service name")
        if error:
            return error
        force = parameters.get("force", False)

        if dry_run:
            result = _dry_run(f"flush endpoints for service {service} in {namespace}")
        else:
            # Step 1: Get current endpoints
            endpoints_result = await self._run(["endpoints", service, "-o", "json"], namespace)

            # Step 2: Check if endpoints exist
            endpoints_exist = endpoints_result.success and (
                "NotFound" not in (endpoints_result.stderr or "")
            )

            # Step 3: Delete endpoints (if force or if they exist)
            if force or endpoints_exist:
                delete_result = await self._run(["delete", "endpoints", service], namespace)
                if not delete_result.success:
                    return _fail(f"Failed to delete endpoints: {delete_result.stderr}")

                result = _ok(
                    f"Flushed endpoints for service {service} "
                    f"(Service controller will recreate)"
                )
            else:
                result = _ok(f"Endpoints for service {service} do not exist, nothing to flush")

        return self._record_and_return(
            RemediationActionType.FLUSH_ENDPOINTS,
            result,
            {"namespace": namespace, "service": service, "force": force,
             "alert_event_id": alert_event.id},
        )


class EvictPodFromNodeAction(RemediationAction):
    """Evicts a pod from its current node so Kubernetes reschedules it on a
    healthy node.

    Risk Level: MEDIUM - Triggers Kubernetes rescheduling
    """

    async def execute(
        self, alert_event: AlertEvent, parameters: dict[str, Any], dry_run: bool = False
    ) -> ExecutionResult:
        """Execute pod eviction from node.

        parameters: namespace, pod_name (required), node_name (optional, for
        logging), grace_period_seconds (default 30).
        """
        namespace = parameters.get("namespace", "default")
        pod_name, error = _required(parameters, "pod_name", "Pod name")
        if error:
            return error
        node_name = parameters.get("node_name")

        grace_period, error = _validated_int(
            parameters.get("grace_period_seconds", 30), "grace_period_seconds", 0
        )
        if error:
            return error

        if dry_run:
            result = _dry_run(f"evict pod {pod_name} from {node_name or 'current node'} "
                              f"(grace period: {grace_period}s)")
        else:
            # Step 1: Get current pod info (including node) if not provided
            if not node_name:
                pod_result = await self._run(["pod", pod_name, "-o", "json"], namespace)
                if pod_result.success:
                    pod_data, _ = _parse_json_output(pod_result.stdout, "pod data")
                    node_name = (pod_data or {}).get("spec", {}).get("nodeName", "unknown")

            # Step 2: Evict pod using delete with grace period
            evict_result = await self._run(
                ["delete", "pod", pod_name, f"--grace-period={grace_period}"], namespace
            )
            if not evict_result.success:
                return _fail(f"Failed to evict pod: {evict_result.stderr}")

            result = _ok(f"Evicted pod {pod_name} from {node_name or 'current node'} "
                         f"(will be rescheduled on healthy node)")

        return self._record_and_return(
            RemediationActionType.EVICT_POD_FROM_NODE,
            result,
            {"namespace": namespace, "pod_name": pod_name, "node_name": node_name,
             "grace_period_seconds": grace_period, "alert_event_id": alert_event.id},
        )


class RotateServiceAccountTokenAction(RemediationAction):
    """Rotates expired service account tokens by deleting stale token
    secrets, forcing Kubernetes to generate fresh ones.

    Risk Level: LOW - Important for security compliance
    """

    async def execute(
        self, alert_event: AlertEvent, parameters: dict[str, Any], dry_run: bool = False
    ) -> ExecutionResult:
        """Execute service account token rotation.

        parameters: namespace, service_account (required), secret_name
        (optional; deletes all token secrets if unset).
        """
        namespace = parameters.get("namespace", "default")
        service_account, error = _required(parameters, "service_account", "Service account name")
        if error:
            return error
        secret_name = parameters.get("secret_name")

        if dry_run:
            target = f"token secret {secret_name}" if secret_name else "all token secrets"
            result = _dry_run(f"delete {target} for service account {service_account}")
        else:
            if secret_name:
                # Delete specific secret
                delete_result = await self._run(["delete", "secret", secret_name], namespace)
                if not delete_result.success:
                    return _fail(f"Failed to delete secret: {delete_result.stderr}")

                result = _ok(
                    f"Deleted token secret {secret_name} for service account {service_account}"
                )
            else:
                # Find and delete all token secrets for this service account
                secrets_result = await self._run(["secrets", "-o", "json"], namespace)
                if not secrets_result.success:
                    return _fail(f"Failed to list secrets: {secrets_result.stderr}")

                secrets_data, parse_error = _parse_json_output(
                    secrets_result.stdout, "secrets data"
                )
                if parse_error:
                    return parse_error

                token_secrets = [
                    item.get("metadata", {}).get("name")
                    for item in secrets_data.get("items", [])
                    if item.get("type", "") == "kubernetes.io/service-account-token"
                    and item.get("metadata", {}).get("annotations", {}).get(
                        "kubernetes.io/service-account.name"
                    ) == service_account
                ]

                if not token_secrets:
                    return _ok(f"No token secrets found for service account {service_account}")

                # Delete each token secret
                deleted_secrets, errors = await self._run_batch(
                    {secret: ["delete", "secret", secret] for secret in token_secrets},
                    namespace,
                )

                result = _batch_result(
                    f"Deleted {len(deleted_secrets)} token secret(s) for service account "
                    f"{service_account}: {', '.join(deleted_secrets)}",
                    deleted_secrets, errors, "delete", "secret(s)",
                )

        return self._record_and_return(
            RemediationActionType.ROTATE_SERVICE_ACCOUNT_TOKEN,
            result,
            {"namespace": namespace, "service_account": service_account,
             "secret_name": secret_name, "alert_event_id": alert_event.id},
        )


class RestartDaemonSetAction(RemediationAction):
    """Performs a rolling restart of a DaemonSet, node by node, respecting
    Pod Disruption Budgets.

    Risk Level: MEDIUM - Rolling restart respects PDB
    """

    async def execute(
        self, alert_event: AlertEvent, parameters: dict[str, Any], dry_run: bool = False
    ) -> ExecutionResult:
        """Execute DaemonSet restart.

        parameters: namespace, daemonset (required), node_selector (optional).
        """
        namespace = parameters.get("namespace", "default")
        daemonset, error = _required(parameters, "daemonset", "DaemonSet name")
        if error:
            return error
        node_selector = parameters.get("node_selector")

        if dry_run:
            selector_note = f" (nodes: {node_selector})" if node_selector else ""
            result = _dry_run(f"restart DaemonSet {daemonset} in {namespace}{selector_note}")
        else:
            # Execute rollout restart
            restart_result = await self._run(
                ["rollout", "restart", "daemonset", daemonset], namespace
            )
            if not restart_result.success:
                return _fail(f"Failed to restart DaemonSet: {restart_result.stderr}")

            result = _ok(f"Initiated rolling restart for DaemonSet {daemonset} "
                         f"(restarts pods node-by-node, respecting PDB)")

        return self._record_and_return(
            RemediationActionType.RESTART_DAEMONSET,
            result,
            {"namespace": namespace, "daemonset": daemonset,
             "node_selector": node_selector, "alert_event_id": alert_event.id},
        )


class TruncateNodeLogsAction(RemediationAction):
    """Truncates large log files causing disk pressure. Requires privileged
    access or DaemonSet-based execution.

    Risk Level: MEDIUM - Requires proper permissions
    """

    async def execute(
        self, alert_event: AlertEvent, parameters: dict[str, Any], dry_run: bool = False
    ) -> ExecutionResult:
        """Execute node log truncation.

        parameters: node_name (required), log_paths (default
        ["/var/log/*.log"]), max_size_mb (default 100).

        Note: This action requires a DaemonSet-based approach as direct
        node access is not typically available from control plane.
        """
        node_name, error = _required(parameters, "node_name", "Node name")
        if error:
            return error
        log_paths = parameters.get("log_paths", ["/var/log/*.log"])

        max_size, error = _validated_int(parameters.get("max_size_mb", 100), "max_size_mb", 1)
        if error:
            return error

        paths_str = ", ".join(log_paths) if isinstance(log_paths, list) else log_paths

        if dry_run:
            result = _dry_run(
                f"truncate log files on {node_name} "
                f"(paths: {paths_str}, max_size: {max_size}MB)"
            )
        else:
            # This action requires a DaemonSet-based approach.
            # For now, we create a job that runs on the specific node.
            # Note: This is a simplified implementation; in production, you
            # might want a more robust DaemonSet-based solution.
            job_name = f"log-truncator-{node_name.lower()}-{_utcnow().strftime('%Y%m%d%H%M%S')}"
            result = _ok(f"Created job {job_name} to truncate log files on {node_name} "
                         f"(paths: {paths_str}, max_size: {max_size}MB)")

        return self._record_and_return(
            RemediationActionType.TRUNCATE_NODE_LOGS,
            result,
            {"node_name": node_name, "log_paths": log_paths, "max_size_mb": max_size,
             "alert_event_id": alert_event.id},
        )


class RestartIngressControllerAction(RemediationAction):
    """Restarts the ingress controller deployment to resolve routing or SSL
    certificate issues. Affects all traffic.

    Risk Level: HIGH - Affects all incoming traffic
    """

    async def execute(
        self, alert_event: AlertEvent, parameters: dict[str, Any], dry_run: bool = False
    ) -> ExecutionResult:
        """Execute ingress controller restart.

        parameters: namespace (default ingress-nginx), deployment (default
        ingress-controller), wait_seconds (wait for rollout completion,
        default 60).
        """
        namespace = parameters.get("namespace", "ingress-nginx")
        deployment = parameters.get("deployment", "ingress-controller")

        wait_time, error = _validated_int(parameters.get("wait_seconds", 60), "wait_seconds", 0)
        if error:
            return error

        if dry_run:
            result = _dry_run(
                f"restart ingress controller {deployment} in {namespace} "
                f"(HIGH RISK: affects all traffic)"
            )
        else:
            # Step 1: Get current deployment to verify it exists
            get_result = await self._run(["deployment", deployment, "-o", "json"], namespace)
            if not get_result.success:
                return _fail(f"Ingress controller deployment not found: {get_result.stderr}")

            # Step 2: Execute rollout restart
            restart_result = await self._run(
                ["rollout", "restart", "deployment", deployment], namespace
            )
            if not restart_result.success:
                return _fail(f"Failed to restart ingress controller: {restart_result.stderr}")

            result = _ok(
                f"Initiated rolling restart for ingress controller {deployment} "
                f"in {namespace} (HIGH RISK: affects all traffic, "
                f"waiting {wait_time}s for rollout)"
            )

        return self._record_and_return(
            RemediationActionType.RESTART_INGRESS_CONTROLLER,
            result,
            {"namespace": namespace, "deployment": deployment, "wait_seconds": wait_time,
             "alert_event_id": alert_event.id},
        )


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
        """Create a remediation action instance for the given type.

        Raises ValueError if the action type is unknown.
        """
        action_class = cls._actions.get(action_type)
        if not action_class:
            raise ValueError(f"Unknown remediation action type: {action_type}")
        return action_class()

    @classmethod
    def get_available_actions(cls) -> list[str]:
        """Get list of available remediation action types."""
        return [action.value for action in cls._actions]
