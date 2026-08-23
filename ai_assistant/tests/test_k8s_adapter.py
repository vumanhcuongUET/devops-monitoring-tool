"""
Tests for Kubernetes adapter.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from services.k8s_adapter import KubernetesAdapter, BACKEND_AVAILABLE


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend not available")
@pytest.mark.unit
class TestKubernetesAdapter:
    """Tests for Kubernetes adapter."""

    def test_init_with_backend_available(self):
        """Test initialization when backend is available."""
        # Mock the backend client
        with patch("services.k8s_adapter.KubernetesClient") as mock_client:
            mock_client.return_value = MagicMock()

            adapter = KubernetesAdapter()
            assert adapter._client is not None

    def test_init_with_fallback_disabled(self):
        """Test initialization with fallback disabled."""
        with patch("services.kubernetes_adapter.BACKEND_AVAILABLE", False):
            with pytest.raises(RuntimeError):
                KubernetesAdapter(fallback_enabled=False)

    def test_available_property(self, mock_k8s_client):
        """Test available property reflects client state."""
        adapter = KubernetesAdapter()
        assert adapter.available is True

    def test_list_pods_method(self, mock_k8s_client):
        """Test list_pods method."""
        adapter = KubernetesAdapter()

        mock_pods = [
            {"name": "pod-1", "namespace": "default", "status": "Running", "ready": "1/1"},
            {"name": "pod-2", "namespace": "default", "status": "Pending", "ready": "0/1"}
        ]
        adapter._client.list_pods = AsyncMock(return_value=mock_pods)

        result = adapter.list_pods(namespace="default")

        assert len(result) == 2
        assert result[0]["name"] == "pod-1"

    def test_list_pods_all_namespaces(self, mock_k8s_client):
        """Test list_pods without namespace filter."""
        adapter = KubernetesAdapter()

        mock_pods = [
            {"name": "pod-1", "namespace": "default", "status": "Running"},
            {"name": "pod-2", "namespace": "kube-system", "status": "Running"}
        ]
        adapter._client.list_pods = AsyncMock(return_value=mock_pods)

        result = adapter.list_pods()

        assert len(result) == 2

    def test_list_deployments_method(self, mock_k8s_client):
        """Test list_deployments method."""
        adapter = KubernetesAdapter()

        mock_deployments = [
            {"name": "app-deployment", "namespace": "default", "ready": "3/3", "replicas": 3}
        ]
        adapter._client.list_deployments = AsyncMock(return_value=mock_deployments)

        result = adapter.list_deployments(namespace="default")

        assert len(result) == 1
        assert result[0]["name"] == "app-deployment"

    def test_list_nodes_method(self, mock_k8s_client):
        """Test list_nodes method."""
        adapter = KubernetesAdapter()

        mock_nodes = [
            {"name": "node-1", "status": "Ready", "roles": ["control-plane", "worker"]},
            {"name": "node-2", "status": "Ready", "roles": ["worker"]}
        ]
        adapter._client.list_nodes = AsyncMock(return_value=mock_nodes)

        result = adapter.list_nodes()

        assert len(result) == 2
        assert result[0]["name"] == "node-1"

    def test_unavailable_adapter_returns_empty_pods(self):
        """Test that unavailable adapter returns empty list for pods."""
        adapter = KubernetesAdapter()
        adapter._client = None

        result = adapter.list_pods()
        assert result == []

    def test_unavailable_adapter_returns_empty_deployments(self):
        """Test that unavailable adapter returns empty list for deployments."""
        adapter = KubernetesAdapter()
        adapter._client = None

        result = adapter.list_deployments()
        assert result == []

    def test_unavailable_adapter_returns_empty_nodes(self):
        """Test that unavailable adapter returns empty list for nodes."""
        adapter = KubernetesAdapter()
        adapter._client = None

        result = adapter.list_nodes()
        assert result == []
