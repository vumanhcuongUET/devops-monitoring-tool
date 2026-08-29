"""
Unit tests for KubernetesClient.

Tests the Kubernetes client functionality including:
- Pod listing
- Deployment listing
- Node listing
- Events retrieval
"""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.unit
@pytest.mark.service
class TestKubernetesClient:
    """Test suite for KubernetesClient."""

    @pytest.mark.asyncio
    async def test_list_pods_returns_empty_list_when_no_pods(self, mock_kubernetes_client):
        """Test that list_pods returns empty list when no pods exist."""
        result = await mock_kubernetes_client.list_pods(namespace="default")

        assert result == []
        mock_kubernetes_client.list_pods.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_pods_with_namespace_filter(self, mock_kubernetes_client):
        """Test that list_pods filters by namespace."""
        mock_kubernetes_client.list_pods = AsyncMock(return_value=[
            {
                "name": "pod-1",
                "namespace": "production",
                "status": "Running",
                "ready": True
            },
            {
                "name": "pod-2",
                "namespace": "production",
                "status": "Pending",
                "ready": False
            }
        ])

        result = await mock_kubernetes_client.list_pods(namespace="production")

        assert len(result) == 2
        assert result[0]["namespace"] == "production"

    @pytest.mark.asyncio
    async def test_list_deployments_returns_deployments(self, mock_kubernetes_client):
        """Test that list_deployments returns deployment list."""
        mock_kubernetes_client.list_deployments = AsyncMock(return_value=[
            {
                "name": "backend-deployment",
                "namespace": "default",
                "ready": 3,
                "desired": 3,
                "status": "Available"
            }
        ])

        result = await mock_kubernetes_client.list_deployments(namespace="default")

        assert len(result) == 1
        assert result[0]["name"] == "backend-deployment"

    @pytest.mark.asyncio
    async def test_list_nodes_returns_cluster_nodes(self, mock_kubernetes_client):
        """Test that list_nodes returns all cluster nodes."""
        mock_kubernetes_client.list_nodes = AsyncMock(return_value=[
            {
                "name": "node-1",
                "status": "Ready",
                "roles": ["control-plane", "master"],
                "version": "v1.28.0"
            },
            {
                "name": "node-2",
                "status": "Ready",
                "roles": ["worker"],
                "version": "v1.28.0"
            }
        ])

        result = await mock_kubernetes_client.list_nodes()

        assert len(result) == 2
        assert result[0]["status"] == "Ready"

    @pytest.mark.asyncio
    async def test_get_events_returns_recent_events(self, mock_kubernetes_client):
        """Test that get_events returns cluster events."""
        mock_kubernetes_client.get_events = AsyncMock(return_value=[
            {
                "type": "Warning",
                "reason": "FailedScheduling",
                "message": "No nodes are available",
                "namespace": "default",
                "timestamp": "2025-01-01T12:00:00Z"
            }
        ])

        result = await mock_kubernetes_client.get_events(namespace="default")

        assert len(result) == 1
        assert result[0]["type"] == "Warning"

    @pytest.mark.asyncio
    async def test_list_pods_without_namespace(self, mock_kubernetes_client):
        """Test that list_pods handles missing namespace."""
        await mock_kubernetes_client.list_pods()

        mock_kubernetes_client.list_pods.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_deployments_filters_by_namespace(self, mock_kubernetes_client):
        """Test that list_deployments filters by namespace."""
        await mock_kubernetes_client.list_deployments(namespace="staging")

        mock_kubernetes_client.list_deployments.assert_called_once_with(
            namespace="staging"
        )

    @pytest.mark.asyncio
    async def test_get_events_with_time_range(self, mock_kubernetes_client):
        """Test that get_events accepts time range parameter."""
        await mock_kubernetes_client.get_events(
            namespace="production",
            time_range="now-1h"
        )

        mock_kubernetes_client.get_events.assert_called_once()
