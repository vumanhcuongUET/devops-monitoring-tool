"""
Tests for APM adapter.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from services.apm_adapter import ApmAdapter, BACKEND_AVAILABLE


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend not available")
@pytest.mark.unit
class TestApmAdapter:
    """Tests for APM adapter."""

    def test_init_with_backend_available(self):
        """Test initialization when backend is available."""
        # Mock the backend clients
        with patch("services.apm_adapter.ElasticsearchClient") as mock_es, \
             patch("services.apm_adapter.ApmClient") as mock_apm:
            mock_es.return_value = MagicMock()
            mock_apm.return_value = MagicMock()

            adapter = ApmAdapter()
            assert adapter._client is not None

    def test_init_with_fallback_disabled(self):
        """Test initialization with fallback disabled."""
        with patch("services.apm_adapter.BACKEND_AVAILABLE", False):
            with pytest.raises(RuntimeError):
                ApmAdapter(fallback_enabled=False)

    def test_available_property(self, mock_apm_client):
        """Test available property reflects client state."""
        adapter = ApmAdapter()
        assert adapter.available is True

    def test_get_transactions_method(self, mock_apm_client):
        """Test get_transactions method."""
        adapter = ApmAdapter()

        mock_return = {
            "transactions": [
                {"name": "/api/users", "duration": 150},
                {"name": "/api/orders", "duration": 320}
            ]
        }
        adapter._client.get_transactions = AsyncMock(return_value=mock_return)

        result = adapter.get_transactions(service_name="meinvoice-api", size=10)

        assert "transactions" in result
        assert len(result["transactions"]) == 2

    def test_get_errors_method(self, mock_apm_client):
        """Test get_errors method."""
        adapter = ApmAdapter()

        mock_errors = [
            {"error": {"type": "ConnectionError", "count": 15}},
            {"error": {"type": "Timeout", "count": 8}}
        ]
        adapter._client.get_errors = AsyncMock(return_value=mock_errors)

        result = adapter.get_errors(service_name="meinvoice-api", size=10)

        assert len(result) == 2
        assert result[0]["error"]["type"] == "ConnectionError"

    def test_get_errors_without_size_limit(self, mock_apm_client):
        """Test get_errors without size parameter returns all results."""
        adapter = ApmAdapter()

        mock_errors = [{"error": {"type": "Error"}} for _ in range(25)]
        adapter._client.get_errors = AsyncMock(return_value=mock_errors)

        result = adapter.get_errors()

        # Should return all (unbounded)
        assert len(result) == 25

    def test_get_summary_method(self, mock_apm_client):
        """Test get_summary method."""
        adapter = ApmAdapter()

        mock_summary = {
            "latency_p50": 45,
            "latency_p95": 150,
            "latency_p99": 320,
            "error_rate_percent": 2.5,
            "throughput": 1200
        }
        adapter._client.get_summary = AsyncMock(return_value=mock_summary)

        result = adapter.get_summary()

        assert result["latency_p50"] == 45
        assert result["latency_p95"] == 150
        assert result["error_rate_percent"] == 2.5

    def test_unavailable_adapter_returns_empty_transactions(self):
        """Test that unavailable adapter returns empty dict for transactions."""
        adapter = ApmAdapter()
        adapter._client = None

        result = adapter.get_transactions("test-service")
        assert result == {"transactions": []}

    def test_unavailable_adapter_returns_empty_errors(self):
        """Test that unavailable adapter returns empty list for errors."""
        adapter = ApmAdapter()
        adapter._client = None

        result = adapter.get_errors("test-service")
        assert result == []

    def test_unavailable_adapter_returns_zero_summary(self):
        """Test that unavailable adapter returns zero metrics."""
        adapter = ApmAdapter()
        adapter._client = None

        result = adapter.get_summary()

        assert result["latency_p50"] == 0
        assert result["error_rate_percent"] == 0
        assert result["throughput"] == 0
