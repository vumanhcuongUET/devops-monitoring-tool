"""Unit tests for Phase 4A Remediation Actions."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.actions.remediation_actions import (
    AdjustHPAMinReplicasAction,
    CleanupFailedJobsAction,
    ClearStuckPodsAction,
    RemediationActionFactory,
    RemediationActionType,
)
from app.models.actions import ExecutionResult
from app.models.alerts import AlertEvent, AlertSeverity


class TestClearStuckPodsAction:
    """Test stuck pod clearance action."""

    @pytest.fixture
    def action(self):
        return ClearStuckPodsAction()

    @pytest.fixture
    def mock_event(self):
        return AlertEvent(
            id="test-event-1",
            rule_id="stuck-pod-rule",
            rule_name="Stuck Pod Detected",
            severity=AlertSeverity.WARNING,
            status="firing",
            value=5.0,
            threshold=3.0,
            message="5 pods stuck in Terminating",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @pytest.mark.asyncio
    async def test_clear_stuck_pods_with_terminating_pods(self, action, mock_event):
        """Test clearing pods stuck in Terminating state."""
        mock_pods_data = {
            "items": [
                {
                    "metadata": {"name": "stuck-pod-1"},
                    "status": {
                        "phase": "Terminating",
                        "startTime": datetime.now(timezone.utc).isoformat()}
                },
                {
                    "metadata": {"name": "stuck-pod-2"},
                    "status": {
                        "containerStatuses": [
                            {"waiting": {"reason": "ImagePullBackOff"}}
                        ],
                        "startTime": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(),
                    },
                },
            ]
        }

        mock_list_result = ExecutionResult(
            success=True,
            stdout='{"items": []}',
            exit_code=0,
        )

        mock_delete_result = ExecutionResult(
            success=True,
            exit_code=0,
            stdout='pod "stuck-pod-1" deleted',
        )

        with patch.object(action.executor, "execute_kubectl", return_value=mock_list_result):
            with patch("json.loads", return_value=mock_pods_data):
                with patch.object(action.executor, "execute_kubectl", return_value=mock_delete_result):
                    result = await action.execute(
                        alert_event=mock_event,
                        parameters={"namespace": "default", "stuck_duration_minutes": 10},
                        dry_run=False,
                    )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_clear_stuck_pods_dry_run(self, action, mock_event):
        """Test dry-run mode for stuck pod clearance."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={"namespace": "default"},
            dry_run=True,
        )

        assert result.success is True
        assert "DRY RUN" in result.stdout
        assert "default" in result.stdout

    @pytest.mark.asyncio
    async def test_clear_stuck_pods_no_pods_found(self, action, mock_event):
        """Test when no stuck pods found."""
        mock_pods_data = {"items": []}

        mock_list_result = ExecutionResult(
            success=True,
            stdout='{"items": []}',
            exit_code=0,
        )

        with patch.object(action.executor, "execute_kubectl", return_value=mock_list_result):
            with patch("json.loads", return_value=mock_pods_data):
                result = await action.execute(
                    alert_event=mock_event,
                    parameters={"namespace": "default", "stuck_duration_minutes": 10},
                    dry_run=False,
                )

        assert result.success is True
        assert "0 stuck pod" in result.stdout


class TestCleanupFailedJobsAction:
    """Test failed job cleanup action."""

    @pytest.fixture
    def action(self):
        return CleanupFailedJobsAction()

    @pytest.fixture
    def mock_event(self):
        return AlertEvent(
            id="test-event-2",
            rule_id="failed-jobs-rule",
            rule_name="Too Many Failed Jobs",
            severity=AlertSeverity.WARNING,
            status="firing",
            value=25.0,
            threshold=20.0,
            message="25 failed jobs found",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @pytest.mark.asyncio
    async def test_cleanup_failed_jobs_with_old_failures(self, action, mock_event):
        """Test cleanup of jobs failed >24 hours ago."""
        mock_jobs_data = {
            "items": [
                {
                    "metadata": {"name": "failed-job-1"},
                    "status": {
                        "conditions": [
                            {
                                "type": "Failed",
                                "status": "True",
                                "lastTransitionTime": (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat(),
                            }
                        ],
                        "startTime": (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat(),
                    },
                },
                {
                    "metadata": {"name": "failed-job-2"},
                    "status": {
                        "conditions": [
                            {
                                "type": "Failed",
                                "status": "True",
                                "lastTransitionTime": (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(),
                            }
                        ],
                        "startTime": (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(),
                    },
                },
            ]
        }

        mock_list_result = ExecutionResult(
            success=True,
            stdout='{"items": []}',
            exit_code=0,
        )

        mock_delete_result = ExecutionResult(
            success=True,
            exit_code=0,
            stdout='job.batch "failed-job-1" deleted',
        )

        with patch.object(action.executor, "execute_kubectl", return_value=mock_list_result):
            with patch("json.loads", return_value=mock_jobs_data):
                with patch.object(action.executor, "execute_kubectl", return_value=mock_delete_result):
                    result = await action.execute(
                        alert_event=mock_event,
                        parameters={"namespace": "default", "failed_hours_ago": 24, "keep_last": 1},
                        dry_run=False,
                    )

        assert result.success is True
        assert "Cleaned up" in result.stdout

    @pytest.mark.asyncio
    async def test_cleanup_failed_jobs_keeps_recent_failures(self, action, mock_event):
        """Test that recent failed jobs are kept."""
        mock_jobs_data = {
            "items": [
                {
                    "metadata": {"name": "old-failed-job"},
                    "status": {
                        "conditions": [
                            {
                                "type": "Failed",
                                "status": "True",
                                "lastTransitionTime": (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat(),
                            }
                        ],
                        "startTime": (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat(),
                    },
                },
                {
                    "metadata": {"name": "recent-failed-job"},
                    "status": {
                        "conditions": [
                            {
                                "type": "Failed",
                                "status": "True",
                                "lastTransitionTime": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                            }
                        ],
                        "startTime": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                    },
                },
            ]
        }

        mock_list_result = ExecutionResult(
            success=True,
            stdout='{"items": []}',
            exit_code=0,
        )

        with patch.object(action.executor, "execute_kubectl", return_value=mock_list_result):
            with patch("json.loads", return_value=mock_jobs_data):
                result = await action.execute(
                    alert_event=mock_event,
                    parameters={"namespace": "default", "failed_hours_ago": 24, "keep_last": 5},
                    dry_run=False,
                )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_cleanup_failed_jobs_dry_run(self, action, mock_event):
        """Test dry-run mode for failed job cleanup."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={"namespace": "default"},
            dry_run=True,
        )

        assert result.success is True
        assert "DRY RUN" in result.stdout


class TestAdjustHPAMinReplicasAction:
    """Test HPA min replica adjustment action."""

    @pytest.fixture
    def action(self):
        return AdjustHPAMinReplicasAction()

    @pytest.fixture
    def mock_event(self):
        return AlertEvent(
            id="test-event-3",
            rule_id="hpa-scale-rule",
            rule_name="HPA Min Replica Adjustment",
            severity=AlertSeverity.WARNING,
            status="firing",
            value=90.0,
            threshold=85.0,
            message="High CPU usage, recommend HPA scale",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @pytest.mark.asyncio
    async def test_adjust_hpa_min_replicas_success(self, action, mock_event):
        """Test successful HPA min replica adjustment."""
        mock_hpa_data = {
            "spec": {
                "minReplicas": 2,
                "maxReplicas": 10,
            }
        }

        mock_get_result = ExecutionResult(
            success=True,
            stdout='{"spec": {"minReplicas": 2, "maxReplicas": 10}}',
            exit_code=0,
        )

        mock_patch_result = ExecutionResult(
            success=True,
            exit_code=0,
            stdout='horizontalpodautoscaler.autoscaling/myapp-hpa patched',
        )

        with patch.object(action.executor, "execute_kubectl", return_value=mock_get_result):
            with patch("json.loads", return_value=mock_hpa_data):
                with patch.object(action.executor, "execute_kubectl", return_value=mock_patch_result):
                    result = await action.execute(
                        alert_event=mock_event,
                        parameters={
                            "namespace": "default",
                            "hpa_name": "myapp-hpa",
                            "new_min_replicas": 5,
                            "duration_minutes": 60,
                        },
                        dry_run=False,
                    )

        assert result.success is True
        assert "2 → 5" in result.stdout

    @pytest.mark.asyncio
    async def test_adjust_hpa_min_replicas_exceeds_max(self, action, mock_event):
        """Test validation when new_min exceeds maxReplicas."""
        mock_hpa_data = {
            "spec": {
                "minReplicas": 2,
                "maxReplicas": 10,
            }
        }

        mock_get_result = ExecutionResult(
            success=True,
            stdout='{"spec": {"minReplicas": 2, "maxReplicas": 10}}',
            exit_code=0,
        )

        with patch.object(action.executor, "execute_kubectl", return_value=mock_get_result):
            with patch("json.loads", return_value=mock_hpa_data):
                result = await action.execute(
                    alert_event=mock_event,
                    parameters={
                        "namespace": "default",
                        "hpa_name": "myapp-hpa",
                        "new_min_replicas": 15,  # Exceeds maxReplicas (10)
                    },
                    dry_run=False,
                )

        assert result.success is False
        assert "cannot exceed maxReplicas" in result.error_message

    @pytest.mark.asyncio
    async def test_adjust_hpa_min_replicas_missing_hpa_name(self, action, mock_event):
        """Test validation when hpa_name is missing."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "namespace": "default",
                "new_min_replicas": 5,
            },
            dry_run=False,
        )

        assert result.success is False
        assert "HPA name is required" in result.error_message

    @pytest.mark.asyncio
    async def test_adjust_hpa_min_replicas_dry_run(self, action, mock_event):
        """Test dry-run mode for HPA adjustment."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "namespace": "default",
                "hpa_name": "myapp-hpa",
                "new_min_replicas": 5,
            },
            dry_run=True,
        )

        assert result.success is True
        assert "DRY RUN" in result.stdout


class TestPhase4AActionFactory:
    """Test factory for Phase 4A actions."""

    def test_create_clear_stuck_pods_action(self):
        """Test creating ClearStuckPodsAction."""
        action = RemediationActionFactory.create(RemediationActionType.CLEAR_STUCK_PODS)
        assert isinstance(action, ClearStuckPodsAction)

    def test_create_cleanup_failed_jobs_action(self):
        """Test creating CleanupFailedJobsAction."""
        action = RemediationActionFactory.create(RemediationActionType.CLEANUP_FAILED_JOBS)
        assert isinstance(action, CleanupFailedJobsAction)

    def test_create_adjust_hpa_min_replicas_action(self):
        """Test creating AdjustHPAMinReplicasAction."""
        action = RemediationActionFactory.create(RemediationActionType.ADJUST_HPA_MIN_REPLICAS)
        assert isinstance(action, AdjustHPAMinReplicasAction)

    def test_get_available_actions_includes_phase4a(self):
        """Test that Phase 4A actions are in available actions list."""
        available = RemediationActionFactory.get_available_actions()
        assert "clear_stuck_pods" in available
        assert "cleanup_failed_jobs" in available
        assert "adjust_hpa_min_replicas" in available
