"""
Tests for Optimizer adapter.
"""

import pytest
from unittest.mock import AsyncMock, patch

from services.optimizer_adapter import OptimizerAdapter


@pytest.mark.unit
class TestOptimizerAdapter:
    """Tests for Optimizer adapter."""

    def test_init_with_backend_available(self):
        """Test initialization when backend is available."""
        # Note: Backend might not be available in test environment
        adapter = OptimizerAdapter()
        # Should not raise even if backend unavailable (fallback enabled)
        assert adapter is not None

    def test_init_with_fallback_disabled(self):
        """Test initialization with fallback disabled."""
        with patch("services.optimizer_adapter.BACKEND_AVAILABLE", False):
            with pytest.raises(RuntimeError):
                OptimizerAdapter(fallback_enabled=False)

    def test_available_property(self):
        """Test available property reflects client state."""
        adapter = OptimizerAdapter()
        # Could be available or not depending on backend
        assert isinstance(adapter.available, bool)

    def test_optimize_method_with_available_backend(self):
        """Test optimize method when backend is available."""
        adapter = OptimizerAdapter()

        # If backend is available, mock the optimizer
        if adapter.available:
            adapter._optimizer.optimize = AsyncMock(return_value={
                "context": {"optimized": True},
                "optimized": True,
                "original_tokens": 1000,
                "optimized_tokens": 300,
                "token_savings": 700
            })

            result = adapter.optimize(
                context={"logs": ["test"]},
                incident_type="high_latency",
                severity="medium"
            )

            assert result["optimized"] is True
            assert result["token_savings"] == 700

    def test_optimize_with_unavailable_backend(self):
        """Test optimize returns unoptimized when backend unavailable."""
        adapter = OptimizerAdapter()
        adapter._optimizer = None  # Force unavailable

        context = {"logs": ["test log"]}
        result = adapter.optimize(context, "high_latency", "medium")

        assert result["optimized"] is False
        assert result["fallback"] is True
        assert result["context"] == context

    def test_optimize_with_fallback_on_error(self):
        """Test optimize_with_fallback handles errors gracefully."""
        adapter = OptimizerAdapter()

        # Mock an error
        if adapter.available:
            adapter._optimizer.optimize = AsyncMock(
                side_effect=Exception("Backend error")
            )

        result = adapter.optimize_with_fallback(
            context={"logs": ["test"]},
            incident_type="high_latency"
        )

        # Should not raise, return original context
        assert "context" in result
        assert result.get("fallback") is True

    def test_estimate_tokens(self):
        """Test token estimation."""
        adapter = OptimizerAdapter()

        data = {"message": "hello world", "count": 5}
        tokens = adapter.estimate_tokens(data)

        # Rough approximation: 4 chars ≈ 1 token
        assert tokens > 0
        assert isinstance(tokens, int)

    def test_estimate_tokens_with_large_data(self):
        """Test token estimation with larger dataset."""
        adapter = OptimizerAdapter()

        large_data = {"logs": [f"log message {i}" for i in range(100)]}
        tokens = adapter.estimate_tokens(large_data)

        # Should handle larger datasets
        assert tokens > 100

    def test_optimize_with_severity_levels(self):
        """Test optimize with different severity levels."""
        adapter = OptimizerAdapter()

        if adapter.available:
            adapter._optimizer.optimize = AsyncMock(return_value={
                "context": {},
                "optimized": True,
                "token_savings": 500
            })

        severities = ["low", "medium", "high", "critical"]
        for severity in severities:
            result = adapter.optimize({}, "test_incident", severity)
            assert "optimized" in result or "fallback" in result

    def test_optimize_with_different_incident_types(self):
        """Test optimize with different incident types."""
        adapter = OptimizerAdapter()

        if adapter.available:
            adapter._optimizer.optimize = AsyncMock(return_value={
                "context": {},
                "optimized": True
            })

        incident_types = ["high_latency", "high_error_rate", "high_cpu", "high_memory"]
        for incident_type in incident_types:
            result = adapter.optimize({}, incident_type, "medium")
            assert "optimized" in result or "fallback" in result
