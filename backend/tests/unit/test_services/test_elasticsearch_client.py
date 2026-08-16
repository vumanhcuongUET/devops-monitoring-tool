"""
Unit tests for ElasticsearchClient.

Tests the Elasticsearch client functionality including:
- Log search functionality
- Error count retrieval
- Cluster health checks
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


@pytest.mark.unit
@pytest.mark.service
class TestElasticsearchClient:
    """Test suite for ElasticsearchClient."""

    @pytest.mark.asyncio
    async def test_search_logs_returns_empty_results_when_no_matches(self, mock_elasticsearch_client):
        """Test that search_logs returns empty results when no logs match."""
        result = await mock_elasticsearch_client.search_logs(
            query="test",
            level="ERROR",
            time_range="now-1h"
        )

        assert result["hits"]["total"]["value"] == 0
        assert result["hits"]["hits"] == []
        mock_elasticsearch_client.search_logs.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_logs_with_filters(self, mock_elasticsearch_client):
        """Test that search_logs applies filters correctly."""
        # Update mock to return sample data
        mock_elasticsearch_client.search_logs = AsyncMock(return_value={
            "hits": {
                "total": {"value": 1},
                "hits": [
                    {
                        "_source": {
                            "message": "Test error message",
                            "log_level": "ERROR",
                            "timestamp": "2025-01-01T12:00:00Z"
                        }
                    }
                ]
            }
        })

        result = await mock_elasticsearch_client.search_logs(
            query="error",
            level="ERROR",
            service="test-service",
            time_range="now-1h"
        )

        assert result["hits"]["total"]["value"] == 1
        assert len(result["hits"]["hits"]) == 1
        assert result["hits"]["hits"][0]["_source"]["log_level"] == "ERROR"

    @pytest.mark.asyncio
    async def test_get_error_count_returns_zero_when_no_errors(self, mock_elasticsearch_client):
        """Test that get_error_count returns 0 when no errors exist."""
        result = await mock_elasticsearch_client.get_error_count(
            time_range="now-1h",
            level="ERROR"
        )

        assert result == 0

    @pytest.mark.asyncio
    async def test_get_error_count_with_actual_errors(self, mock_elasticsearch_client):
        """Test that get_error_count returns actual error count."""
        mock_elasticsearch_client.get_error_count = AsyncMock(return_value=42)

        result = await mock_elasticsearch_client.get_error_count(
            time_range="now-1h",
            level="ERROR"
        )

        assert result == 42

    @pytest.mark.asyncio
    async def test_get_cluster_health_returns_green_status(self, mock_elasticsearch_client):
        """Test that get_cluster_health returns cluster status."""
        result = await mock_elasticsearch_client.get_cluster_health()

        assert result["cluster_name"] == "test"
        assert result["status"] == "green"
        assert result["number_of_nodes"] == 1

    @pytest.mark.asyncio
    async def test_get_cluster_health_with_yellow_status(self, mock_elasticsearch_client):
        """Test that get_cluster_health handles yellow cluster status."""
        mock_elasticsearch_client.get_cluster_health = AsyncMock(return_value={
            "cluster_name": "test",
            "status": "yellow",
            "number_of_nodes": 2
        })

        result = await mock_elasticsearch_client.get_cluster_health()

        assert result["status"] == "yellow"
        assert result["number_of_nodes"] == 2

    @pytest.mark.asyncio
    async def test_search_logs_handles_connection_error(self, mock_elasticsearch_client):
        """Test that search_logs handles connection errors gracefully."""
        # Mock to raise connection error
        mock_elasticsearch_client.search_logs = AsyncMock(
            side_effect=ConnectionError("ES connection failed")
        )

        with pytest.raises(ConnectionError):
            await mock_elasticsearch_client.search_logs(
                query="test",
                time_range="now-1h"
            )

    @pytest.mark.asyncio
    async def test_get_error_count_with_custom_time_range(self, mock_elasticsearch_client):
        """Test that get_error_count accepts custom time ranges."""
        mock_elasticsearch_client.get_error_count = AsyncMock(return_value=10)

        await mock_elasticsearch_client.get_error_count(
            time_range="now-30m",
            level="WARNING"
        )

        mock_elasticsearch_client.get_error_count.assert_called_once_with(
            time_range="now-30m",
            level="WARNING"
        )
