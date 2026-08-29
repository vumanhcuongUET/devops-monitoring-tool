"""
Tests for Elasticsearch adapter.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from services.elasticsearch_adapter import ElasticsearchAdapter, BACKEND_AVAILABLE


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend not available")
@pytest.mark.unit
class TestElasticsearchAdapter:
    """Tests for Elasticsearch adapter."""

    def test_init_with_backend_available(self):
        """Test initialization when backend is available."""
        # Mock the backend client
        with patch("services.elasticsearch_adapter.ElasticsearchClient") as mock_client:
            mock_client.return_value = MagicMock()
            mock_client.return_value.client = MagicMock()

            adapter = ElasticsearchAdapter()

            # Should have client attribute
            assert adapter._client is not None

    def test_init_with_fallback_disabled(self, mock_elasticsearch_client):
        """Test initialization with fallback disabled."""
        # If backend unavailable and fallback disabled, should raise
        with patch("services.elasticsearch_adapter.BACKEND_AVAILABLE", False):
            with pytest.raises(RuntimeError):
                ElasticsearchAdapter(fallback_enabled=False)

    def test_available_property(self, mock_elasticsearch_client):
        """Test available property reflects client state."""
        adapter = ElasticsearchAdapter()
        assert adapter.available is True

    def test_search_method(self, mock_elasticsearch_client):
        """Test search method calls backend client."""
        adapter = ElasticsearchAdapter()

        # Mock the async client method
        adapter._client.client.search = AsyncMock(return_value={
            "hits": {"total": {"value": 5}, "hits": []}
        })

        result = adapter.search(index="test-*", body={"query": {"match_all": {}}})

        assert "hits" in result
        assert result["hits"]["total"]["value"] == 5

    def test_count_method(self, mock_elasticsearch_client):
        """Test count method."""
        adapter = ElasticsearchAdapter()

        adapter._client.client.count = AsyncMock(return_value={"count": 100})

        result = adapter.count(index="test-*", body={"query": {"match_all": {}}})

        assert result == 100

    def test_get_cluster_health(self, mock_elasticsearch_client):
        """Test cluster health method."""
        _adapter = ElasticsearchAdapter()

        mock_health = ElasticsearchAdapter()
        mock_health._client = mock_elasticsearch_client
        mock_health._client.get_cluster_health = AsyncMock(return_value={
            "status": "green",
            "cluster_name": "test"
        })

        result = mock_health.get_cluster_health()

        assert result["status"] == "green"

    def test_unavailable_adapter_raises_error(self, mock_elasticsearch_client):
        """Test that unavailable adapter raises appropriate error."""
        adapter = ElasticsearchAdapter()

        # Set client to None to simulate unavailable
        adapter._client = None

        with pytest.raises(RuntimeError, match="not available"):
            adapter.search(index="test", body={})
