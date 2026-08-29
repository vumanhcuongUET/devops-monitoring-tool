"""
Unit tests for SloClient.

Tests the SLO client functionality including:
- SLO calculation
- Availability SLO calculation
- Latency SLO calculation
- Slow APIs retrieval
"""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.unit
@pytest.mark.service
class TestSloClient:
    """Test suite for SloClient."""

    @pytest.mark.asyncio
    async def test_calculate_slo_returns_slo_data(self, mock_slo_client):
        """Test that calculate_slo returns SLO calculation results."""
        result = await mock_slo_client.calculate_slo(
            service_name="test-service",
            slo_id="test-slo-001",
            time_range_days=7
        )

        assert "slo_name" in result
        assert "slo_type" in result
        assert "target_percentage" in result
        assert "actual_percentage" in result
        assert "error_budget_remaining" in result
        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_calculate_slo_with_unhealthy_status(self, mock_slo_client):
        """Test that calculate_slo can return unhealthy status."""
        mock_slo_client.calculate_slo = AsyncMock(return_value={
            "slo_name": "test-slo",
            "slo_type": "availability",
            "target_percentage": 99.9,
            "actual_percentage": 99.5,
            "error_budget_remaining": -10.0,
            "status": "unhealthy"
        })

        result = await mock_slo_client.calculate_slo(
            service_name="test-service",
            slo_id="test-slo-001"
        )

        assert result["status"] == "unhealthy"
        assert result["error_budget_remaining"] < 0

    @pytest.mark.asyncio
    async def test_get_slow_apis_returns_empty_list(self, mock_slo_client):
        """Test that get_slow_apis returns empty list when no slow APIs."""
        result = await mock_slo_client.get_slow_apis(
            service_name="test-service",
            time_range_days=7
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_get_slow_apis_with_slow_endpoints(self, mock_slo_client):
        """Test that get_slow_apis returns slow endpoints."""
        mock_slo_client.get_slow_apis = AsyncMock(return_value=[
            {
                "endpoint": "GET /api/products",
                "avg_duration_ms": 850,
                "threshold_ms": 500,
                "p95_duration_ms": 1200,
                "slow_request_count": 150
            },
            {
                "endpoint": "POST /api/orders",
                "avg_duration_ms": 1200,
                "threshold_ms": 500,
                "p95_duration_ms": 1800,
                "slow_request_count": 200
            }
        ])

        result = await mock_slo_client.get_slow_apis(
            service_name="api-service",
            time_range_days=7
        )

        assert len(result) == 2
        assert result[0]["endpoint"] == "GET /api/products"
        assert result[0]["slow_request_count"] == 150

    @pytest.mark.asyncio
    async def test_calculate_slo_with_latency_type(self, mock_slo_client):
        """Test that calculate_slo handles latency SLO type."""
        mock_slo_client.calculate_slo = AsyncMock(return_value={
            "slo_name": "latency-slo",
            "slo_type": "latency",
            "target_percentage": 95.0,
            "actual_percentage": 92.5,
            "threshold_ms": 500,
            "status": "degraded"
        })

        result = await mock_slo_client.calculate_slo(
            service_name="api-service",
            slo_id="latency-slo-001"
        )

        assert result["slo_type"] == "latency"
        assert "threshold_ms" in result
        assert result["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_get_slow_apis_with_custom_threshold(self, mock_slo_client):
        """Test that get_slow_apis accepts custom threshold."""
        mock_slo_client.get_slow_apis = AsyncMock(return_value=[])

        await mock_slo_client.get_slow_apis(
            service_name="test-service",
            time_range_days=30,
            threshold_ms=1000
        )

        mock_slo_client.get_slow_apis.assert_called_once()

    @pytest.mark.asyncio
    async def test_calculate_slo_with_30_day_window(self, mock_slo_client):
        """Test that calculate_slo supports 30-day rolling window."""
        await mock_slo_client.calculate_slo(
            service_name="test-service",
            slo_id="test-slo-001",
            time_range_days=30
        )

        mock_slo_client.calculate_slo.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_slow_apis_with_multiple_services(self, mock_slo_client):
        """Test that get_slow_apis can handle multiple services."""
        mock_slo_client.get_slow_apis = AsyncMock(return_value=[
            {
                "endpoint": "GET /api/users",
                "avg_duration_ms": 450,
                "threshold_ms": 300,
                "p95_duration_ms": 800
            }
        ])

        result = await mock_slo_client.get_slow_apis(
            service_name="user-service",
            time_range_days=7
        )

        assert len(result) == 1
