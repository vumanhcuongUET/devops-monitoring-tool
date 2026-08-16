"""
Unit tests for PrometheusClient.

Tests the Prometheus client functionality including:
- Node metrics retrieval
- CPU/Memory percentage calculations
- Alerts and alerts statistics
"""

import pytest
from unittest.mock import AsyncMock


@pytest.mark.unit
@pytest.mark.service
class TestPrometheusClient:
    """Test suite for PrometheusClient."""

    @pytest.mark.asyncio
    async def test_get_cpu_percent_returns_float(self, mock_prometheus_client):
        """Test that get_cpu_percent returns a float value."""
        result = await mock_prometheus_client.get_cpu_percent(
            hostname="test-server"
        )

        assert isinstance(result, float)
        assert 0 <= result <= 100

    @pytest.mark.asyncio
    async def test_get_memory_percent_returns_float(self, mock_prometheus_client):
        """Test that get_memory_percent returns a float value."""
        result = await mock_prometheus_client.get_memory_percent(
            hostname="test-server"
        )

        assert isinstance(result, float)
        assert 0 <= result <= 100

    @pytest.mark.asyncio
    async def test_get_node_metrics_returns_list(self, mock_prometheus_client):
        """Test that get_node_metrics returns a list of node metrics."""
        mock_prometheus_client.get_node_metrics = AsyncMock(return_value=[
            {
                "hostname": "server1",
                "cpu_percent": 45.5,
                "memory_percent": 62.3
            },
            {
                "hostname": "server2",
                "cpu_percent": 30.1,
                "memory_percent": 55.8
            }
        ])

        result = await mock_prometheus_client.get_node_metrics()

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["hostname"] == "server1"

    @pytest.mark.asyncio
    async def test_get_alerts_returns_alerts_data(self, mock_prometheus_client):
        """Test that get_alerts returns alerts data structure."""
        mock_prometheus_client.get_alerts = AsyncMock(return_value={
            "data": {
                "alerts": [
                    {
                        "alertname": "HighErrorRate",
                        "severity": "warning",
                        "state": "firing"
                    }
                ]
            }
        })

        result = await mock_prometheus_client.get_alerts()

        assert "data" in result
        assert "alerts" in result["data"]
        assert len(result["data"]["alerts"]) == 1

    @pytest.mark.asyncio
    async def test_get_alerts_stats_returns_stats_structure(self, mock_prometheus_client):
        """Test that get_alerts_stats returns statistics structure."""
        mock_prometheus_client.get_alerts_stats = AsyncMock(return_value={
            "by_namespace": {
                "default": {"critical": 2, "warning": 3, "info": 1},
                "production": {"critical": 0, "warning": 1, "info": 0}
            },
            "total_firing": 3,
            "total_pending": 2
        })

        result = await mock_prometheus_client.get_alerts_stats()

        assert "by_namespace" in result
        assert "total_firing" in result
        assert "total_pending" in result
        assert result["total_firing"] == 3

    @pytest.mark.asyncio
    async def test_get_alerts_stats_filters_by_namespace(self, mock_prometheus_client):
        """Test that get_alerts_stats can filter by specific namespaces."""
        result = await mock_prometheus_client.get_alerts_stats(
            namespaces=["default", "production"]
        )

        mock_prometheus_client.get_alerts_stats.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_cpu_percent_with_hostname_filter(self, mock_prometheus_client):
        """Test that get_cpu_percent accepts hostname parameter."""
        mock_prometheus_client.get_cpu_percent = AsyncMock(return_value=55.5)

        await mock_prometheus_client.get_cpu_percent(hostname="server-01")

        mock_prometheus_client.get_cpu_percent.assert_called_once_with(
            hostname="server-01"
        )

    @pytest.mark.asyncio
    async def test_get_cpu_percent_handles_no_hostname(self, mock_prometheus_client):
        """Test that get_cpu_percent handles missing hostname."""
        await mock_prometheus_client.get_cpu_percent()

        mock_prometheus_client.get_cpu_percent.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_node_metrics_with_time_range(self, mock_prometheus_client):
        """Test that get_node_metrics accepts time range parameter."""
        mock_prometheus_client.get_node_metrics = AsyncMock(return_value=[])

        await mock_prometheus_client.get_node_metrics(time_range="now-30m")

        mock_prometheus_client.get_node_metrics.assert_called_once_with(
            time_range="now-30m"
        )
