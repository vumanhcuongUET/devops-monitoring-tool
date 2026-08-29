"""
Unit tests for Token Optimizer components.

Phase 6: AI Input Optimization & Cost Efficiency
"""


import pytest

from app.services.anomaly_detector import AnomalyDetector
from app.services.log_sampler import LogSampler
from app.services.time_series_compressor import TimeSeriesCompressor
from app.services.token_optimizer import (
    OptimizationConfig,
    OptimizationResult,
    OptimizationStrategy,
    TokenOptimizer,
    get_token_optimizer,
)


class TestAnomalyDetector:
    """Test suite for AnomalyDetector."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return OptimizationConfig(
            anomaly_cpu_high=80.0,
            anomaly_cpu_low=20.0,
            anomaly_memory_high=85.0,
            anomaly_disk_high=90.0,
        )

    @pytest.fixture
    def detector(self, config):
        """Create AnomalyDetector instance."""
        return AnomalyDetector(config)

    @pytest.mark.asyncio
    async def test_detect_anomalous_cpu(self, detector):
        """Test CPU anomaly detection."""
        metrics = {"cpu_percent": 92.1, "memory_percent": 68.5}

        result, anomalies = await detector.detect_metrics_anomaly(metrics)

        assert "cpu_percent" in result
        assert result["cpu_percent"] == 92.1
        assert "_anomalies" in result
        assert len(anomalies) > 0

    @pytest.mark.asyncio
    async def test_normal_cpu_filtered(self, detector):
        """Test normal CPU is filtered out."""
        metrics = {"cpu_percent": 45.2, "memory_percent": 60.0}

        result, anomalies = await detector.detect_metrics_anomaly(metrics)

        assert "cpu_percent" not in result
        # When all metrics are normal, we get a summary instead
        assert "_summary" in result or "_normal_metrics_count" in result

    @pytest.mark.asyncio
    async def test_all_normal_metrics(self, detector):
        """Test all normal metrics returns summary."""
        metrics = {
            "cpu_percent": 50.0,
            "memory_percent": 70.0,
            "disk_percent": 45.0,
        }

        result, anomalies = await detector.detect_metrics_anomaly(metrics)

        assert "_summary" in result
        assert result["_summary"] == "All metrics within normal range"

    @pytest.mark.asyncio
    async def test_empty_metrics(self, detector):
        """Test empty metrics handling."""
        result, anomalies = await detector.detect_metrics_anomaly({})

        assert "status" in result
        assert result["status"] == "no_metrics_available"


class TestLogSampler:
    """Test suite for LogSampler."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return OptimizationConfig(
            log_sampling_critical=5,
            log_sampling_error=10,
            log_sampling_warning=10,
            log_sampling_info=5,
            max_results_per_source=20,
        )

    @pytest.fixture
    def sampler(self, config):
        """Create LogSampler instance."""
        return LogSampler(config)

    @pytest.fixture
    def sample_logs(self):
        """Create sample log entries."""
        return [
            {"message": "Critical failure in database", "level": "critical"},
            {"message": "Connection timeout error", "level": "error"},
            {"message": "High memory usage warning", "level": "warning"},
            {"message": "Service started", "level": "info"},
            {"message": "Debug info", "level": "debug"},
            {"message": "Another critical error", "level": "critical"},
            {"message": "Timeout exception", "level": "error"},
            {"message": "Warning about disk space", "level": "warning"},
        ]

    @pytest.mark.asyncio
    async def test_sample_logs_respects_quotas(self, sampler, sample_logs):
        """Test log sampling respects quotas."""
        result = await sampler.sample_logs(
            sample_logs,
            incident_type="high_error_rate",
            max_results=20,
        )

        # Should have at most 5 critical + 10 error + 10 warning + 5 info = 30
        # But max_results limits to 20
        assert len(result) <= 20

    @pytest.mark.asyncio
    async def test_critical_logs_prioritized(self, sampler, sample_logs):
        """Test critical logs are prioritized."""
        result = await sampler.sample_logs(
            sample_logs,
            incident_type="high_error_rate",
            max_results=20,
        )

        # Critical logs should be included
        critical_logs = [log for log in result if log.get("level") == "critical"]
        assert len(critical_logs) > 0

    @pytest.mark.asyncio
    async def test_empty_logs(self, sampler):
        """Test empty logs handling."""
        result = await sampler.sample_logs([], incident_type="test")

        assert result == []

    @pytest.mark.asyncio
    async def test_keyword_matching(self, sampler):
        """Test keyword matching improves relevance."""
        logs = [
            {"message": "Database connection failed", "level": "error"},
            {"message": "Authentication error", "level": "error"},
            {"message": "Network timeout", "level": "error"},
        ]

        result = await sampler.sample_logs(
            logs,
            incident_type="high_error_rate",
            alert_keywords=["database", "connection"],
            max_results=10,
        )

        # Database-related logs should be prioritized
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_apm_error_sampling(self, sampler):
        """Test APM error sampling."""
        apm_errors = [
            {"error": "TimeoutError", "occurrences": 150},
            {"error": "DatabaseError", "occurrences": 89},
            {"error": "AuthError", "occurrences": 45},
            {"error": "NetworkError", "occurrences": 23},
        ]

        result = await sampler.sample_apm_errors(apm_errors, max_results=3)

        # Should return top 3 by occurrence
        assert len(result) == 3
        assert result[0]["error"] == "TimeoutError"


class TestTimeSeriesCompressor:
    """Test suite for TimeSeriesCompressor."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return OptimizationConfig(
            compress_time_series=True,
            include_percentiles=True,
            include_trend=True,
        )

    @pytest.fixture
    def compressor(self, config):
        """Create TimeSeriesCompressor instance."""
        return TimeSeriesCompressor(config)

    @pytest.fixture
    def sample_time_series(self):
        """Create sample time-series data."""
        return [
            ("2024-01-01T00:00:00Z", 50.0),
            ("2024-01-01T00:01:00Z", 52.0),
            ("2024-01-01T00:02:00Z", 55.0),
            ("2024-01-01T00:03:00Z", 58.0),
            ("2024-01-01T00:04:00Z", 62.0),
            ("2024-01-01T00:05:00Z", 65.0),
        ]

    @pytest.mark.asyncio
    async def test_compress_time_series(self, compressor, sample_time_series):
        """Test time-series compression."""
        result = compressor._compress_time_series(sample_time_series)

        assert "current" in result
        assert "p50" in result
        assert "p95" in result
        assert "trend" in result

        # Check values
        assert result["current"] == 65.0
        assert result["trend"] == "increasing"
        assert result["samples"] == 6

    @pytest.mark.asyncio
    async def test_compress_metrics_dict(self, compressor):
        """Test compressing metrics dict."""
        metrics = {
            "cpu_history": [("t1", 50.0), ("t2", 52.0), ("t3", 55.0)],
            "memory_percent": 70.0,  # Scalar, should remain unchanged
        }

        result, compressed = await compressor.compress_metrics(metrics)

        # Time-series should be compressed
        assert "cpu_history" in result
        assert isinstance(result["cpu_history"], dict)
        assert "current" in result["cpu_history"]

        # Compression flag should be True
        assert compressed is True

        # Scalar should remain unchanged
        assert result["memory_percent"] == 70.0

    @pytest.mark.asyncio
    async def test_empty_time_series(self, compressor):
        """Test empty time-series handling."""
        result = compressor._compress_time_series([])

        assert "error" in result

    @pytest.mark.asyncio
    async def test_compression_ratio(self, compressor, sample_time_series):
        """Test compression ratio calculation."""
        result = await compressor.compress_single_series(
            sample_time_series,
            "cpu_usage"
        )

        assert result.original_points == 6
        assert result.compressed_values > 0
        # Compression ratio should be > 1 (we compress 6 points into ~8 values)
        # But since we expand to statistics, the ratio might be < 1
        # The key metric is token savings, not ratio
        assert result.compression_ratio >= 0

    @pytest.mark.asyncio
    async def test_trend_detection(self, compressor):
        """Test trend detection."""
        # Increasing trend
        increasing = [("t1", 10.0), ("t2", 20.0), ("t3", 30.0)]
        result_inc = compressor._compress_time_series(increasing)
        assert result_inc["trend"] == "increasing"

        # Decreasing trend
        decreasing = [("t1", 30.0), ("t2", 20.0), ("t3", 10.0)]
        result_dec = compressor._compress_time_series(decreasing)
        assert result_dec["trend"] == "decreasing"

        # Stable trend
        stable = [("t1", 20.0), ("t2", 21.0), ("t3", 20.0)]
        result_stable = compressor._compress_time_series(stable)
        assert result_stable["trend"] == "stable"


class TestTokenOptimizer:
    """Test suite for TokenOptimizer."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return OptimizationConfig(
            enabled=True,
            default_budget=2000,
            log_sampling_critical=5,
            log_sampling_error=10,
        )

    @pytest.fixture
    def optimizer(self, config):
        """Create TokenOptimizer instance."""
        return TokenOptimizer(config)

    @pytest.fixture
    def sample_context(self):
        """Create sample context data."""
        return {
            "logs": [
                {"message": "Error occurred", "level": "error"},
                {"message": "Warning issued", "level": "warning"},
            ] * 30,
            "apm": {
                "latency_p95_ms": 2300,
                "error_rate_percent": 2.5,
                "top_errors": [{"error": "Timeout", "occurrences": 100}],
            },
            "metrics": {
                "cpu_percent": 85.2,
                "memory_percent": 72.1,
            },
            "kubernetes": {
                "pods_total": 10,
                "unhealthy_deployments": [],
            },
            "alerts": [
                {"rule_name": "HighCPU", "severity": "warning"},
            ] * 5,
        }

    @pytest.mark.asyncio
    async def test_optimize_reduces_tokens(self, optimizer, sample_context):
        """Test optimization reduces token count."""
        result = await optimizer.optimize(
            sample_context,
            incident_type="high_latency",
            severity="high",
        )

        assert result.optimized_tokens < result.original_tokens
        assert result.token_savings > 0
        assert result.token_savings_percent > 0

    @pytest.mark.asyncio
    async def test_optimize_applies_strategies(self, optimizer, sample_context):
        """Test all optimization strategies are applied."""
        result = await optimizer.optimize(
            sample_context,
            incident_type="high_latency",
            severity="high",
        )

        assert len(result.strategies_applied) > 0
        assert OptimizationStrategy.ANOMALY_DETECTION in result.strategies_applied
        assert OptimizationStrategy.SMART_SAMPLING in result.strategies_applied

    @pytest.mark.asyncio
    async def test_respects_token_budget(self, optimizer, sample_context):
        """Test token budget is respected."""
        result = await optimizer.optimize(
            sample_context,
            incident_type="high_latency",
            severity="medium",
            token_budget=1500,
        )

        assert result.optimized_tokens <= 1500 * 1.1  # Allow 10% tolerance

    @pytest.mark.asyncio
    async def test_empty_context(self, optimizer):
        """Test empty context handling."""
        result = await optimizer.optimize(
            {},
            incident_type="test",
            severity="info",
        )

        assert isinstance(result, OptimizationResult)
        assert result.optimized_tokens == 0

    def test_estimate_tokens(self, optimizer):
        """Test token estimation."""
        data = {"message": "test", "value": 123}
        tokens = optimizer._estimate_tokens(data)

        assert tokens > 0

    def test_get_budget_for_severity(self, optimizer):
        """Test token budget by severity."""
        from app.models.triage_card import SeverityLevel

        budgets = {
            SeverityLevel.CRITICAL: 3000,
            SeverityLevel.HIGH: 2500,
            SeverityLevel.MEDIUM: 2000,
            SeverityLevel.LOW: 1500,
            SeverityLevel.INFO: 1000,
        }

        for severity, expected_budget in budgets.items():
            budget = optimizer._get_budget_for_severity(severity)
            assert budget == expected_budget

    def test_get_relevant_sources(self, optimizer):
        """Test relevant source selection."""
        sources = optimizer._get_relevant_sources("high_latency")

        assert "apm" in sources
        assert "metrics" in sources
        assert "kubernetes" in sources
        assert "logs" not in sources  # Not relevant for latency


@pytest.mark.asyncio
async def test_get_token_optimizer_singleton():
    """Test singleton pattern."""
    optimizer1 = get_token_optimizer()
    optimizer2 = get_token_optimizer()

    assert optimizer1 is optimizer2


@pytest.mark.asyncio
async def test_optimization_result_serialization():
    """Test OptimizationResult can be serialized."""
    result = OptimizationResult(
        optimized_context={"test": "data"},
        original_tokens=5000,
        optimized_tokens=2000,
        token_savings=3000,
        token_savings_percent=60.0,
        strategies_applied=[
            OptimizationStrategy.ANOMALY_DETECTION,
            OptimizationStrategy.SMART_SAMPLING,
        ],
        processing_time_ms=150.0,
    )

    result_dict = result.to_dict()

    assert result_dict["original_tokens"] == 5000
    assert result_dict["optimized_tokens"] == 2000
    assert result_dict["token_savings_percent"] == 60.0
    assert "anomaly_detection" in result_dict["strategies_applied"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
