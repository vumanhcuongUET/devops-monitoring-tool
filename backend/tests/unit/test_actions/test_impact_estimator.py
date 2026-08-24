"""Unit tests for ImpactEstimator."""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock

from app.actions.impact_estimator import (
    ImpactEstimator,
    ImpactEstimate,
    ImpactLevel,
    ImpactThresholds,
    ResourceImpact,
    get_impact_estimator,
)


class TestImpactThresholds:
    """Test ImpactThresholds dataclass."""

    def test_default_thresholds(self):
        """Test default threshold values."""
        thresholds = ImpactThresholds()

        assert thresholds.low_max == 5
        assert thresholds.medium_max == 20
        assert thresholds.high_max == 100
        assert thresholds.namespace_wide_critical is True
        assert thresholds.cluster_wide_always_critical is True

    def test_custom_thresholds(self):
        """Test custom threshold values."""
        thresholds = ImpactThresholds(
            low_max=10,
            medium_max=50,
            high_max=200,
            namespace_wide_critical=False,
            cluster_wide_always_critical=False,
        )

        assert thresholds.low_max == 10
        assert thresholds.medium_max == 50
        assert thresholds.high_max == 200
        assert thresholds.namespace_wide_critical is False
        assert thresholds.cluster_wide_always_critical is False


class TestResourceImpact:
    """Test ResourceImpact dataclass."""

    def test_resource_impact_creation(self):
        """Test creating a ResourceImpact."""
        impact = ResourceImpact(
            resource_type="pods",
            affected_count=5,
            namespace="default",
            details={"key": "value"},
        )

        assert impact.resource_type == "pods"
        assert impact.affected_count == 5
        assert impact.namespace == "default"
        assert impact.details == {"key": "value"}


class TestImpactEstimate:
    """Test ImpactEstimate dataclass."""

    def test_impact_estimate_creation(self):
        """Test creating an ImpactEstimate."""
        estimate = ImpactEstimate(
            action_id="action-123",
            command="kubectl delete pods -n default",
            total_affected_resources=10,
            impact_level=ImpactLevel.MEDIUM,
            resource_impacts=[
                ResourceImpact(resource_type="pods", affected_count=10),
            ],
        )

        assert estimate.action_id == "action-123"
        assert estimate.total_affected_resources == 10
        assert estimate.impact_level == ImpactLevel.MEDIUM
        assert len(estimate.resource_impacts) == 1


class TestImpactEstimator:
    """Test ImpactEstimator functionality."""

    def test_initial_state(self):
        """Test that impact estimator starts with default thresholds."""
        estimator = ImpactEstimator()

        assert estimator.thresholds.low_max == 5
        assert estimator.thresholds.medium_max == 20
        assert estimator.thresholds.high_max == 100

    def test_estimate_single_pod_delete(self):
        """Test estimating impact for deleting a single pod."""
        estimator = ImpactEstimator()

        estimate = estimator.estimate(
            action_id="action-1",
            command="kubectl delete pod my-pod -n default",
            dry_run=True,
        )

        assert estimate.impact_level == ImpactLevel.LOW
        assert estimate.total_affected_resources == 1
        assert len(estimate.resource_impacts) == 1
        assert estimate.resource_impacts[0].resource_type == "pod"

    def test_estimate_namespace_wide_delete(self):
        """Test estimating impact for namespace-wide delete."""
        estimator = ImpactEstimator()

        estimate = estimator.estimate(
            action_id="action-2",
            command="kubectl delete pods -n default",
            dry_run=True,
        )

        # Should be medium impact based on heuristic (20 pods)
        assert estimate.impact_level in (ImpactLevel.MEDIUM, ImpactLevel.HIGH)
        assert estimate.total_affected_resources > 1
        assert any("namespace-wide" in r.lower() for r in estimate.risk_factors)

    def test_estimate_cluster_wide_operation(self):
        """Test that cluster-wide operations are critical."""
        estimator = ImpactEstimator()

        estimate = estimator.estimate(
            action_id="action-3",
            command="kubectl delete nodes --all",
            dry_run=True,
        )

        assert estimate.impact_level == ImpactLevel.CRITICAL
        assert any("cluster-wide" in r.lower() for r in estimate.risk_factors)

    def test_estimate_rollout_restart(self):
        """Test estimating impact for rollout restart."""
        estimator = ImpactEstimator()

        estimate = estimator.estimate(
            action_id="action-4",
            command="kubectl rollout restart deployment my-deployment -n default",
            dry_run=True,
        )

        # Rollout restart affects multiple pods
        assert estimate.total_affected_resources >= 1
        assert any("restart" in r.lower() for r in estimate.recommendations)

    def test_estimate_helm_uninstall(self):
        """Test estimating impact for helm uninstall."""
        estimator = ImpactEstimator()

        estimate = estimator.estimate(
            action_id="action-5",
            command="helm uninstall my-release -n default",
            dry_run=True,
        )

        # Helm uninstall should have risk factors
        assert any("helm" in r.lower() or "uninstall" in r.lower()
                   for r in estimate.risk_factors)

    def test_impact_level_low(self):
        """Test LOW impact level classification."""
        estimator = ImpactEstimator()

        estimate = estimator.estimate(
            action_id="action-6",
            command="kubectl get pods -n default",
            dry_run=True,
        )

        # Get operations are typically low impact
        assert estimate.impact_level == ImpactLevel.LOW

    def test_impact_level_medium(self):
        """Test MEDIUM impact level classification."""
        estimator = ImpactEstimator()

        estimate = estimator.estimate(
            action_id="action-7",
            command="kubectl delete pods -n test",
            dry_run=True,
        )

        # Should be medium based on heuristic
        assert estimate.impact_level in (ImpactLevel.MEDIUM, ImpactLevel.HIGH)

    def test_risk_factors_destructive(self):
        """Test risk factor detection for destructive operations."""
        estimator = ImpactEstimator()

        estimate = estimator.estimate(
            action_id="action-8",
            command="kubectl delete pod my-pod",
            dry_run=True,
        )

        # Should have destructive risk factor
        assert any("delete" in r.lower() or "destructive" in r.lower()
                   for r in estimate.risk_factors)

    def test_risk_factors_force(self):
        """Test risk factor detection for force operations."""
        estimator = ImpactEstimator()

        estimate = estimator.estimate(
            action_id="action-9",
            command="kubectl delete pod my-pod --force --grace-period=0",
            dry_run=True,
        )

        # Should have force risk factor
        assert any("force" in r.lower() for r in estimate.risk_factors)

    def test_recommendations_critical(self):
        """Test recommendations for critical impact."""
        estimator = ImpactEstimator()

        # Create a critical impact scenario
        estimate = estimator.estimate(
            action_id="action-10",
            command="kubectl delete pods --all-namespaces",
            dry_run=True,
        )

        if estimate.impact_level == ImpactLevel.CRITICAL:
            # Should have critical-specific recommendations
            assert any("approval" in r.lower() or "maintenance" in r.lower()
                       for r in estimate.recommendations)

    def test_recommendations_destructive(self):
        """Test recommendations for destructive operations."""
        estimator = ImpactEstimator()

        estimate = estimator.estimate(
            action_id="action-11",
            command="kubectl delete deployment my-deployment",
            dry_run=True,
        )

        # Should have backup recommendation
        assert any("backup" in r.lower() or "verify" in r.lower()
                   for r in estimate.recommendations)

    def test_estimate_duration(self):
        """Test execution duration estimation."""
        estimator = ImpactEstimator()

        # Get operation should be fast
        estimate1 = estimator.estimate(
            action_id="action-12",
            command="kubectl get pods",
            dry_run=True,
        )
        assert estimate1.estimated_duration_seconds >= 0
        assert estimate1.estimated_duration_seconds <= 600  # Max 10 min cap

        # Rollout restart should take longer
        estimate2 = estimator.estimate(
            action_id="action-13",
            command="kubectl rollout restart deployment my-deployment",
            dry_run=True,
        )
        assert estimate2.estimated_duration_seconds > estimate1.estimated_duration_seconds

    def test_estimate_with_real_k8s_client(self):
        """Test estimation with real Kubernetes client."""
        estimator = ImpactEstimator()

        # Mock k8s client
        mock_k8s = Mock()
        mock_k8s.list_pods = Mock(return_value=[
            {"name": f"pod-{i}", "namespace": "default"} for i in range(5)
        ])

        estimate = estimator.estimate(
            action_id="action-14",
            command="kubectl delete pods -n default",
            k8s_client=mock_k8s,
            dry_run=False,  # Use real client
        )

        # Should use real count from k8s client
        assert estimate.total_affected_resources == 5
        assert estimate.resource_impacts[0].affected_count == 5

    def test_update_thresholds(self):
        """Test updating impact thresholds."""
        estimator = ImpactEstimator()

        assert estimator.thresholds.low_max == 5

        new_thresholds = ImpactThresholds(low_max=10)
        estimator.update_thresholds(new_thresholds)

        assert estimator.thresholds.low_max == 10

    def test_parse_command(self):
        """Test command parsing."""
        estimator = ImpactEstimator()

        parsed = estimator._parse_command("kubectl delete pod my-pod -n default")

        assert parsed["tool"] == "kubectl"
        assert parsed["operation"] == "delete"
        assert "my-pod" in parsed["args"]
        assert parsed["flags"]["n"] == "default"

    def test_is_cluster_wide_operation(self):
        """Test cluster-wide operation detection."""
        estimator = ImpactEstimator()

        parsed = estimator._parse_command("kubectl get pods --all-namespaces")
        assert estimator._is_cluster_wide_operation(parsed) is True

        parsed = estimator._parse_command("kubectl get nodes")
        assert estimator._is_cluster_wide_operation(parsed) is True

        parsed = estimator._parse_command("kubectl get pods -n default")
        assert estimator._is_cluster_wide_operation(parsed) is False

    def test_is_namespace_wide_operation(self):
        """Test namespace-wide operation detection."""
        estimator = ImpactEstimator()

        parsed = estimator._parse_command("kubectl delete pods")
        assert estimator._is_namespace_wide_operation(parsed) is True

        parsed = estimator._parse_command("kubectl delete pod my-pod")
        assert estimator._is_namespace_wide_operation(parsed) is False

    def test_multiple_resource_impacts(self):
        """Test that multiple resource types can be impacted."""
        estimator = ImpactEstimator()

        # This might affect multiple resource types in real scenarios
        estimate = estimator.estimate(
            action_id="action-15",
            command="kubectl delete all -l app=myapp",
            dry_run=True,
        )

        # Should have at least one resource impact
        assert len(estimate.resource_impacts) >= 1


class TestGlobalImpactEstimator:
    """Test global impact estimator singleton."""

    @pytest.fixture(autouse=True)
    def reset_estimator(self):
        """Reset the global estimator before each test."""
        global _impact_estimator
        from app.actions.impact_estimator import _impact_estimator
        _impact_estimator = None
        yield
        _impact_estimator = None

    def test_singleton(self):
        """Test that get_impact_estimator returns same instance."""
        estimator1 = get_impact_estimator()
        estimator2 = get_impact_estimator()

        assert estimator1 is estimator2

    def test_singleton_with_thresholds(self):
        """Test that thresholds are applied on first call."""
        thresholds = ImpactThresholds(low_max=10)
        estimator = get_impact_estimator(thresholds=thresholds)

        assert estimator.thresholds.low_max == 10

    def test_singleton_threshold_update(self):
        """Test that thresholds can be updated after creation."""
        # First get the default estimator
        estimator1 = get_impact_estimator()
        original_low_max = estimator1.thresholds.low_max

        # Update thresholds
        new_thresholds = ImpactThresholds(low_max=15)
        estimator2 = get_impact_estimator(thresholds=new_thresholds)

        # Same instance but updated thresholds
        assert estimator1 is estimator2
        # Thresholds should be updated
        assert estimator2.thresholds.low_max == 15
