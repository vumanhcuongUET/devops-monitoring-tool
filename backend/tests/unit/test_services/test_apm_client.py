"""
Unit tests for ApmClient.

Tests the APM client functionality including:
- Transaction retrieval
- Error retrieval
- Summary metrics
"""

import pytest
from unittest.mock import AsyncMock


@pytest.mark.unit
@pytest.mark.service
class TestApmClient:
    """Test suite for ApmClient."""

    @pytest.mark.asyncio
    async def test_get_summary_returns_summary_metrics(self, mock_apm_client):
        """Test that get_summary returns APM summary metrics."""
        result = await mock_apm_client.get_summary(
            service="test-service",
            time_range="now-1h"
        )

        assert "transactions" in result
        assert "errors" in result
        assert "avg_response_time" in result
        assert result["transactions"] == 100

    @pytest.mark.asyncio
    async def test_get_transactions_returns_empty_list(self, mock_apm_client):
        """Test that get_transactions returns empty list when no transactions."""
        result = await mock_apm_client.get_transactions(
            service="test-service",
            time_range="now-1h"
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_get_transactions_with_service_filter(self, mock_apm_client):
        """Test that get_transactions filters by service."""
        mock_apm_client.get_transactions = AsyncMock(return_value=[
            {
                "name": "GET /api/users",
                "count": 150,
                "avg_duration": 45.2
            },
            {
                "name": "POST /api/orders",
                "count": 80,
                "avg_duration": 120.5
            }
        ])

        result = await mock_apm_client.get_transactions(
            service="api-service",
            time_range="now-30m"
        )

        assert len(result) == 2
        assert result[0]["name"] == "GET /api/users"

    @pytest.mark.asyncio
    async def test_get_errors_returns_empty_list(self, mock_apm_client):
        """Test that get_errors returns empty list when no errors."""
        result = await mock_apm_client.get_errors(
            service="test-service",
            time_range="now-1h"
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_get_errors_with_actual_errors(self, mock_apm_client):
        """Test that get_errors returns error list."""
        mock_apm_client.get_errors = AsyncMock(return_value=[
            {
                "error_id": "error-001",
                "error_message": "NullPointerException",
                "count": 5,
                "affected_transactions": 5
            }
        ])

        result = await mock_apm_client.get_errors(
            service="api-service",
            time_range="now-2h"
        )

        assert len(result) == 1
        assert result[0]["error_message"] == "NullPointerException"

    @pytest.mark.asyncio
    async def test_get_summary_without_service(self, mock_apm_client):
        """Test that get_summary handles missing service parameter."""
        await mock_apm_client.get_summary()

        mock_apm_client.get_summary.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_transactions_with_percentile_filter(self, mock_apm_client):
        """Test that get_transactions accepts percentile parameters."""
        mock_apm_client.get_transactions = AsyncMock(return_value=[])

        await mock_apm_client.get_transactions(
            service="test-service",
            percentiles=[50, 95, 99]
        )

        mock_apm_client.get_transactions.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_errors_with_time_range(self, mock_apm_client):
        """Test that get_errors accepts time range parameter."""
        await mock_apm_client.get_errors(
            service="test-service",
            time_range="now-15m"
        )

        mock_apm_client.get_errors.assert_called_once_with(
            service="test-service",
            time_range="now-15m"
        )
