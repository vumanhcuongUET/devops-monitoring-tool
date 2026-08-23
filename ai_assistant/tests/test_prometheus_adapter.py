"""
Tests for Prometheus adapter.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from services.prometheus_adapter import PrometheusAdapter, BACKEND_AVAILABLE


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend not available")
@pytest.mark.unit
class TestPrometheusAdapter:
    """Tests for Prometheus adapter."""

    def test_init_with_backend_available(self):
        """Test initialization when backend is available."""
        # Mock the backend client
        with patch("services.prometheus_adapter.PrometheusClient") as mock_client:
            mock_client.return_value = MagicMock()

            adapter = PrometheusAdapter()
            assert adapter._client is not None

    def test_init_with_fallback_disabled(self):
        """Test initialization with fallback disabled."""
        with patch("services.prometheus_adapter.BACKEND_AVAILABLE", False):
            with pytest.raises(RuntimeError):
                PrometheusAdapter(fallback_enabled=False)

    def test_available_property(self, mock_prometheus_client):
        """Test available property reflects client state."""
        adapter = PrometheusAdapter()
        assert adapter.available is True

    def test_query_method(self, mock_prometheus_client):
        """Test query method calls backend client."""
        adapter = PrometheusAdapter()

        adapter._client._query = AsyncMock(return_value={
            "data": {
                "resultType": "vector",
                "result": [{"metric": {"__name__": "up"}, "value": [1234567890, "1"]}]
            }
        })

        result = adapter.query('up')

        assert "data" in result
        assert result["data"]["resultType"] == "vector"

    def test_query_range_method(self, mock_prometheus_client):
        """Test query_range method."""
        adapter = PrometheusAdapter()

        adapter._client._query_range = AsyncMock(return_value={
            "data": {
                "resultType": "matrix",
                "result": [{"metric": {"__name__": "up"}, "values": [[1234567890, "1"]]}]
            }
        })

        result = adapter.query_range('up', '2024-01-01T00:00:00Z', '2024-01-01T01:00:00Z', '1m')

        assert "data" in result
        assert result["data"]["resultType"] == "matrix"

    def test_get_alerts_method(self, mock_prometheus_client):
        """Test get_alerts method."""
        adapter = PrometheusAdapter()

        mock_alerts = [
            {"alert": {"alertname": "HighErrorRate", "severity": "warning"}, "state": "firing"}
        ]
        adapter._client.get_alerts = AsyncMock(return_value=mock_alerts)

        result = adapter.get_alerts()

        assert len(result) == 1
        assert result[0]["alert"]["alertname"] == "HighErrorRate"

    def test_unavailable_adapter_raises_error(self):
        """Test that unavailable adapter raises appropriate error."""
        adapter = PrometheusAdapter()
        adapter._client = None

        with pytest.raises(RuntimeError, match="not available"):
            adapter.query("up")

    def test_unavailable_adapter_returns_empty_alerts(self):
        """Test that unavailable adapter returns empty list for alerts."""
        adapter = PrometheusAdapter()
        adapter._client = None

        result = adapter.get_alerts()
        assert result == []
