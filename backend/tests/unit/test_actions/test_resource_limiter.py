"""Unit tests for ResourceLimiter."""

from unittest.mock import Mock

import pytest

from app.actions.resource_limiter import (
    ResourceLimiter,
    ResourceStatus,
    ResourceThreshold,
    ResourceType,
    get_resource_limiter,
)


@pytest.fixture
def mock_k8s_client():
    """Create a mock Kubernetes client."""
    client = Mock()

    # Mock nodes
    client.list_nodes = Mock(return_value=[
        {
            "capacity": {
                "cpu": "4",
                "memory": "16Gi",
                "pods": "110",
            },
            "allocatable": {
                "cpu": "3900m",  # 100m used
                "memory": "15Gi",  # 1Gi used
                "pods": "110",
            },
        },
        {
            "capacity": {
                "cpu": "8",
                "memory": "32Gi",
                "pods": "110",
            },
            "allocatable": {
                "cpu": "7500m",  # 500m used
                "memory": "30Gi",  # 2Gi used
                "pods": "110",
            },
        },
    ])

    # Mock pods
    client.list_pods = Mock(return_value=[{"name": f"pod-{i}"} for i in range(50)])

    return client


class TestResourceThreshold:
    """Test ResourceThreshold dataclass."""

    def test_threshold_creation(self):
        """Test creating a resource threshold."""
        threshold = ResourceThreshold(
            resource_type=ResourceType.CPU,
            warning_percent=70.0,
            critical_percent=85.0,
        )

        assert threshold.resource_type == ResourceType.CPU
        assert threshold.warning_percent == 70.0
        assert threshold.critical_percent == 85.0


class TestResourceStatus:
    """Test ResourceStatus dataclass."""

    def test_status_creation(self):
        """Test creating a resource status."""
        status = ResourceStatus(
            resource_type=ResourceType.MEMORY,
            total_capacity=1024,
            used_capacity=512,
            available_capacity=512,
            usage_percent=50.0,
            status="healthy",
        )

        assert status.resource_type == ResourceType.MEMORY
        assert status.usage_percent == 50.0
        assert status.available_capacity == 512


class TestResourceLimiter:
    """Test ResourceLimiter functionality."""

    def test_initial_state(self):
        """Test that limiter starts with default thresholds."""
        limiter = ResourceLimiter()

        assert ResourceType.CPU in limiter._thresholds
        assert ResourceType.MEMORY in limiter._thresholds
        assert ResourceType.PODS in limiter._thresholds

    def test_default_thresholds(self):
        """Test default threshold values."""
        limiter = ResourceLimiter()

        cpu_threshold = limiter.get_threshold(ResourceType.CPU)
        assert cpu_threshold.warning_percent == 70.0
        assert cpu_threshold.critical_percent == 85.0

    def test_set_custom_threshold(self):
        """Test setting a custom threshold."""
        limiter = ResourceLimiter()

        custom = ResourceThreshold(
            resource_type=ResourceType.CPU,
            warning_percent=80.0,
            critical_percent=90.0,
        )

        limiter.set_threshold(custom)

        retrieved = limiter.get_threshold(ResourceType.CPU)
        assert retrieved.warning_percent == 80.0
        assert retrieved.critical_percent == 90.0

    def test_parse_cpu_cores(self):
        """Test parsing CPU in cores."""
        limiter = ResourceLimiter()

        cores = limiter._parse_cpu_resource("4")
        assert cores == 4.0

    def test_parse_cpu_millicores(self):
        """Test parsing CPU in millicores."""
        limiter = ResourceLimiter()

        cores = limiter._parse_cpu_resource("4000m")
        assert cores == 4.0

    def test_parse_cpu_invalid(self):
        """Test parsing invalid CPU string."""
        limiter = ResourceLimiter()

        cores = limiter._parse_cpu_resource("invalid")
        assert cores == 0.0

    def test_parse_memory_gib(self):
        """Test parsing memory in Gi."""
        limiter = ResourceLimiter()

        bytes_val = limiter._parse_memory_resource("16Gi")
        assert bytes_val == 16 * 1024 ** 3

    def test_parse_memory_mib(self):
        """Test parsing memory in Mi."""
        limiter = ResourceLimiter()

        bytes_val = limiter._parse_memory_resource("512Mi")
        assert bytes_val == 512 * 1024 ** 2

    def test_parse_memory_invalid(self):
        """Test parsing invalid memory string."""
        limiter = ResourceLimiter()

        bytes_val = limiter._parse_memory_resource("invalid")
        assert bytes_val == 0.0

    def test_check_resources_healthy(self, mock_k8s_client):
        """Test resource check when resources are healthy."""
        limiter = ResourceLimiter()

        result = limiter.check_resources(mock_k8s_client)

        # With default thresholds and mock data (low usage)
        assert result.allowed is True
        assert "passed" in result.reason.lower()

    def test_check_resources_critical_pods(self, mock_k8s_client):
        """Test resource check when pods are at critical capacity."""
        limiter = ResourceLimiter()

        # Set critical threshold very low
        limiter.set_threshold(ResourceThreshold(
            resource_type=ResourceType.PODS,
            warning_percent=10.0,
            critical_percent=20.0,
        ))

        # Update mock to have high pod count
        mock_k8s_client.list_pods = Mock(return_value=[
            {"name": f"pod-{i}"} for i in range(180)
        ])

        result = limiter.check_resources(mock_k8s_client, [ResourceType.PODS])

        # Should be blocked due to high pod count
        assert result.allowed is False
        assert result.blocking_resource == ResourceType.PODS

    def test_check_pod_status(self, mock_k8s_client):
        """Test getting pod status."""
        limiter = ResourceLimiter()

        status = limiter._get_pod_status(mock_k8s_client)

        assert status.resource_type == ResourceType.PODS
        assert status.used_capacity == 50  # 50 pods from mock
        assert status.usage_percent >= 0

    def test_check_cpu_status(self, mock_k8s_client):
        """Test getting CPU status."""
        limiter = ResourceLimiter()

        status = limiter._get_cpu_status(mock_k8s_client)

        assert status.resource_type == ResourceType.CPU
        # Mock has 4 + 8 = 12 cores total
        # 100m + 500m = 600m used
        assert status.total_capacity == 12.0
        assert status.used_capacity == pytest.approx(0.6, abs=0.01)

    def test_check_memory_status(self, mock_k8s_client):
        """Test getting memory status."""
        limiter = ResourceLimiter()

        status = limiter._get_memory_status(mock_k8s_client)

        assert status.resource_type == ResourceType.MEMORY
        # Mock has 16Gi + 32Gi = 48Gi total
        # 1Gi + 2Gi = 3Gi used
        assert status.total_capacity == 48 * 1024 ** 3
        assert status.used_capacity == 3 * 1024 ** 3

    def test_check_disk_status(self, mock_k8s_client):
        """Test getting disk status (returns unknown)."""
        limiter = ResourceLimiter()

        status = limiter._get_disk_status(mock_k8s_client)

        assert status.resource_type == ResourceType.DISK
        assert status.status == "unknown"

    def test_status_classification_warning(self, mock_k8s_client):
        """Test status classification at warning level."""
        limiter = ResourceLimiter()

        # Set warning threshold low
        limiter.set_threshold(ResourceThreshold(
            resource_type=ResourceType.PODS,
            warning_percent=10.0,
            critical_percent=85.0,
        ))

        status = limiter._get_pod_status(mock_k8s_client)

        # 50 pods / 220 capacity = ~23% - above 10% warning
        assert status.status == "warning"

    def test_status_classification_critical(self, mock_k8s_client):
        """Test status classification at critical level."""
        limiter = ResourceLimiter()

        # Set critical threshold low
        limiter.set_threshold(ResourceThreshold(
            resource_type=ResourceType.PODS,
            warning_percent=5.0,
            critical_percent=15.0,
        ))

        status = limiter._get_pod_status(mock_k8s_client)

        # 50 pods / 220 capacity = ~23% - above 15% critical
        assert status.status == "critical"

    def test_recommendations_generated(self, mock_k8s_client):
        """Test that recommendations are generated when needed."""
        limiter = ResourceLimiter()

        # Set low critical threshold
        limiter.set_threshold(ResourceThreshold(
            resource_type=ResourceType.PODS,
            warning_percent=5.0,
            critical_percent=15.0,
        ))

        result = limiter.check_resources(mock_k8s_client, [ResourceType.PODS])

        assert len(result.recommendations) > 0

    def test_get_all_thresholds(self):
        """Test getting all thresholds."""
        limiter = ResourceLimiter()

        thresholds = limiter.get_all_thresholds()

        assert len(thresholds) >= 4
        assert ResourceType.CPU in thresholds
        assert ResourceType.MEMORY in thresholds

    def test_check_specific_resource_types(self, mock_k8s_client):
        """Test checking only specific resource types."""
        limiter = ResourceLimiter()

        result = limiter.check_resources(
            mock_k8s_client,
            check_types=[ResourceType.PODS],
        )

        assert len(result.resource_statuses) == 1
        assert result.resource_statuses[0].resource_type == ResourceType.PODS


class TestGlobalResourceLimiter:
    """Test global resource limiter singleton."""

    @pytest.fixture(autouse=True)
    def reset_limiter(self):
        """Reset the global limiter before each test."""
        global _resource_limiter
        from app.actions.resource_limiter import _resource_limiter
        _resource_limiter = None
        yield
        _resource_limiter = None

    def test_singleton(self):
        """Test that get_resource_limiter returns same instance."""
        limiter1 = get_resource_limiter()
        limiter2 = get_resource_limiter()

        assert limiter1 is limiter2

    def test_singleton_persistence(self):
        """Test that singleton persists across calls."""
        limiter1 = get_resource_limiter()
        custom = ResourceThreshold(
            resource_type=ResourceType.CPU,
            warning_percent=80.0,
        )
        limiter1.set_threshold(custom)

        limiter2 = get_resource_limiter()
        retrieved = limiter2.get_threshold(ResourceType.CPU)
        assert retrieved.warning_percent == 80.0
