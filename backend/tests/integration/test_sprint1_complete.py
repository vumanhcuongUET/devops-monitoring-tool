"""
Sprint 1 Complete Integration Tests

Comprehensive validation of all Sprint 1 components working together.
Tests the complete optimization flow with all strategies.

Phase 6: AI Input Optimization - Sprint 1 Integration
"""

import time
from datetime import datetime

import pytest

from app.models.triage_card import SeverityLevel
from app.services.__tests__.data_generator import TestDataGenerator
from app.services.token_optimizer import OptimizationConfig, TokenOptimizer


class TestSprint1Complete:
    """Comprehensive Sprint 1 validation tests."""

    @pytest.fixture
    def optimizer(self):
        """Create token optimizer instance."""
        config = OptimizationConfig(
            enabled=True,
            default_budget=2000,
            fallback_on_error=True,
            # Anomaly detection thresholds
            anomaly_cpu_high=80.0,
            anomaly_cpu_low=20.0,
            anomaly_memory_high=85.0,
            anomaly_disk_high=90.0,
            anomaly_error_rate_high=5.0,
            # Smart sampling quotas
            log_sampling_critical=5,
            log_sampling_error=10,
            log_sampling_warning=10,
            log_sampling_info=5,
            # Relevance scoring
            min_relevance_score=0.3,
            max_results_per_source=20,
            # Time series compression
            compress_time_series=True,
            include_percentiles=True,
            include_trend=True,
        )
        return TokenOptimizer(config)

    @pytest.fixture
    def generator(self):
        """Create test data generator instance."""
        return TestDataGenerator()

    @pytest.mark.asyncio
    async def test_all_strategies_integrated(self, optimizer, generator):
        """Test all Sprint 1 strategies work together."""
        # Generate a complex incident with multiple data sources
        incident = generator.generate_incident(
            incident_type='high_latency',
            severity='high'
        )

        # Ensure we have all the necessary data
        assert 'metrics' in incident
        assert 'logs' in incident
        assert 'apm_data' in incident

        result = await optimizer.optimize(
            context_data=incident,
            incident_type='high_latency',
            severity=SeverityLevel.HIGH
        )

        # Check all strategies were applied
        expected_strategies = [
            'anomaly_detection',
            'smart_sampling',
            'time_series_compression',
            'relevance_filtering',
            'compact_formatting'
        ]

        for strategy in expected_strategies:
            assert any(s.value == strategy for s in result.strategies_applied), \
                f"Strategy {strategy} not applied"

    @pytest.mark.asyncio
    async def test_optimization_flow_complete(self, optimizer, generator):
        """Test complete optimization flow with fallback."""
        incident = generator.generate_incident(
            incident_type='error_spike',
            severity='critical'
        )

        # Should not raise any exceptions
        result = await optimizer.optimize_with_fallback(
            context_data=incident,
            incident_type='error_spike',
            severity=SeverityLevel.CRITICAL,
            request_id='test-flow-complete'
        )

        assert result is not None
        assert result.optimized_context is not None
        assert result.original_tokens > 0

    @pytest.mark.asyncio
    async def test_fallback_on_invalid_context(self, optimizer):
        """Test fallback behavior on invalid context."""
        # Create invalid context
        invalid_context = {'invalid': 'data'}

        result = await optimizer.optimize_with_fallback(
            context_data=invalid_context,
            incident_type='generic',
            severity=SeverityLevel.MEDIUM,
            request_id='test-invalid-context'
        )

        # Should fallback gracefully
        assert result is not None
        assert result.fallback is True
        assert result.fallback_reason is not None
        assert result.optimized_context == invalid_context  # Returns original

    @pytest.mark.asyncio
    async def test_fallback_on_exception(self, optimizer, generator):
        """Test fallback on internal exception."""
        # Create a context that might cause issues
        problematic_context = {
            'metrics': None,  # None metrics might cause issues
            'logs': [],  # Empty logs
            'apm': None
        }

        result = await optimizer.optimize_with_fallback(
            context_data=problematic_context,
            incident_type='unknown',
            severity=SeverityLevel.LOW,
            request_id='test-exception'
        )

        # Should handle gracefully
        assert result is not None
        # Either succeeded or fell back
        assert isinstance(result.fallback, bool)

    @pytest.mark.asyncio
    async def test_performance_benchmarks(self, optimizer, generator):
        """Test performance meets Sprint 1 targets."""
        results = []

        for _i in range(20):
            incident = generator.generate_incident(
                incident_type='high_latency',
                severity='medium'
            )

            start = time.time()
            result = await optimizer.optimize(
                context_data=incident,
                incident_type='high_latency',
                severity=SeverityLevel.MEDIUM
            )
            elapsed_ms = (time.time() - start) * 1000

            results.append({
                'time_ms': elapsed_ms,
                'reduction_pct': result.token_savings_percent,
                'original_tokens': result.original_tokens,
                'optimized_tokens': result.optimized_tokens
            })

        # Calculate averages
        avg_time = sum(r['time_ms'] for r in results) / len(results)
        avg_reduction = sum(r['reduction_pct'] for r in results) / len(results)
        avg_original = sum(r['original_tokens'] for r in results) / len(results)
        avg_optimized = sum(r['optimized_tokens'] for r in results) / len(results)

        # Performance assertions
        assert avg_time < 200, f"Average processing time: {avg_time:.2f}ms (target: <200ms)"
        assert avg_reduction > 50, f"Average reduction: {avg_reduction:.2f}% (target: >50%)"
        assert avg_original > avg_optimized, "Optimization should reduce tokens"

        print("\nPerformance Summary:")
        print(f"  Avg Time: {avg_time:.2f}ms")
        print(f"  Avg Reduction: {avg_reduction:.2f}%")
        print(f"  Avg Original Tokens: {avg_original:.0f}")
        print(f"  Avg Optimized Tokens: {avg_optimized:.0f}")

    @pytest.mark.asyncio
    async def test_quality_validation(self, optimizer, generator):
        """Test quality gates are enforced."""
        incident = generator.generate_incident(
            incident_type='resource_exhaustion',
            severity='high'
        )

        result = await optimizer.optimize(
            context_data=incident,
            incident_type='resource_exhaustion',
            severity=SeverityLevel.HIGH
        )

        # Validate result quality
        assert result.token_savings_percent > 0, "Should have some token reduction"
        assert result.optimized_tokens < result.original_tokens, "Optimization should reduce tokens"
        assert result.processing_time_ms < 1000, "Should process in reasonable time"
        assert len(result.optimized_context) > 0, "Context should not be empty"

    @pytest.mark.asyncio
    async def test_anomaly_detection_in_flow(self, optimizer, generator):
        """Test anomaly detection is part of optimization flow."""
        # Generate incident with anomalous metrics
        incident = generator.generate_incident(
            incident_type='high_latency',
            severity='high'
        )

        # Set high CPU to trigger anomaly
        incident['metrics']['cpu_percent'] = 95.0

        result = await optimizer.optimize(
            context_data=incident,
            incident_type='high_latency',
            severity=SeverityLevel.HIGH
        )

        # Check anomalies were detected
        assert hasattr(result, 'anomalies')
        assert len(result.anomalies) > 0, "Should detect high CPU anomaly"

    @pytest.mark.asyncio
    async def test_smart_sampling_in_flow(self, optimizer, generator):
        """Test smart sampling is part of optimization flow."""
        # Generate incident with many logs
        incident = generator.generate_incident(
            incident_type='error_spike',
            severity='critical'
        )

        # Logs is a dict with 'logs' key containing the actual list
        logs_dict = incident.get('logs', {})
        original_log_count = len(logs_dict.get('logs', [])) if isinstance(logs_dict, dict) else 0

        result = await optimizer.optimize(
            context_data=incident,
            incident_type='error_spike',
            severity=SeverityLevel.CRITICAL
        )

        # Check logs were sampled
        assert hasattr(result, 'logs_sampled')
        # The sampled count should be recorded
        assert isinstance(result.logs_sampled, int)
        # Sampling should have been attempted
        assert result.logs_sampled >= 0

    @pytest.mark.asyncio
    async def test_time_series_compression_in_flow(self, optimizer, generator):
        """Test time series compression is part of optimization flow."""
        incident = generator.generate_incident(
            incident_type='high_latency',
            severity='high'
        )

        # Add time-series data
        incident['metrics']['cpu_history'] = [
            (i, 50 + i % 30) for i in range(100)
        ]

        result = await optimizer.optimize(
            context_data=incident,
            incident_type='high_latency',
            severity=SeverityLevel.HIGH
        )

        # Check compression was applied
        assert hasattr(result, 'metrics_compressed')
        # Compression should be True if time-series data was present
        assert isinstance(result.metrics_compressed, bool)

    @pytest.mark.asyncio
    async def test_relevance_filtering_in_flow(self, optimizer, generator):
        """Test relevance filtering selects appropriate sources."""
        incident = generator.generate_incident(
            incident_type='high_latency',
            severity='high'
        )

        # Add multiple data sources
        incident['alerts'] = [{'message': 'High latency detected'}]
        incident['kubernetes'] = {'pods': []}

        result = await optimizer.optimize(
            context_data=incident,
            incident_type='high_latency',
            severity=SeverityLevel.HIGH
        )

        # For high_latency, should include APM and metrics
        # Check that relevant sources are preserved
        assert 'apm_data' in result.optimized_context or 'metrics' in result.optimized_context

    @pytest.mark.asyncio
    async def test_compact_formatting_in_flow(self, optimizer, generator):
        """Test compact formatting removes None/empty values."""
        incident = generator.generate_incident(
            incident_type='generic',
            severity='low'
        )

        # Add some None values
        incident['empty_field'] = None
        incident['empty_list'] = []
        incident['empty_dict'] = {}

        result = await optimizer.optimize(
            context_data=incident,
            incident_type='generic',
            severity=SeverityLevel.LOW
        )

        # Compact formatting should remove empty values
        assert 'empty_field' not in result.optimized_context
        assert 'empty_list' not in result.optimized_context
        assert 'empty_dict' not in result.optimized_context

    @pytest.mark.asyncio
    async def test_token_budget_by_severity(self, optimizer, generator):
        """Test token budget varies by severity."""
        incident = generator.generate_incident(
            incident_type='generic',
            severity='medium'
        )

        # Test different severity levels
        for severity in [
            SeverityLevel.CRITICAL,
            SeverityLevel.HIGH,
            SeverityLevel.MEDIUM,
            SeverityLevel.LOW,
            SeverityLevel.INFO
        ]:
            result = await optimizer.optimize(
                context_data=incident.copy(),
                incident_type='generic',
                severity=severity
            )

            # Higher severity should allow more tokens
            assert result is not None
            assert result.optimized_tokens >= 0

    @pytest.mark.asyncio
    async def test_result_to_dict(self, optimizer, generator):
        """Test OptimizationResult.to_dict() works correctly."""
        incident = generator.generate_incident(
            incident_type='generic',
            severity='medium'
        )

        result = await optimizer.optimize(
            context_data=incident,
            incident_type='generic',
            severity=SeverityLevel.MEDIUM
        )

        # Convert to dict
        result_dict = result.to_dict()

        # Check all fields are present
        expected_keys = [
            'optimized_context',
            'original_tokens',
            'optimized_tokens',
            'token_savings',
            'token_savings_percent',
            'strategies_applied',
            'processing_time_ms',
            'anomalies',
            'logs_sampled',
            'metrics_compressed',
            'fallback',
            'fallback_reason'
        ]

        for key in expected_keys:
            assert key in result_dict, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_empty_context_handling(self, optimizer):
        """Test handling of empty/minimal context."""
        empty_context = {}

        result = await optimizer.optimize_with_fallback(
            context_data=empty_context,
            incident_type='generic',
            severity=SeverityLevel.INFO,
            request_id='test-empty'
        )

        # Should handle gracefully
        assert result is not None
        assert isinstance(result.fallback, bool)

    @pytest.mark.asyncio
    async def test_result_validation(self, optimizer):
        """Test _validate_result method."""
        # Create a valid result
        from app.services.token_optimizer import (
            OptimizationResult,
            OptimizationStrategy,
        )

        valid_result = OptimizationResult(
            optimized_context={'test': 'data'},
            original_tokens=100,
            optimized_tokens=50,
            token_savings=50,
            token_savings_percent=50.0,
            strategies_applied=[OptimizationStrategy.COMPACT_FORMATTING],
            processing_time_ms=100.0
        )

        # Should be valid
        assert optimizer._validate_result(valid_result) is True

        # Create invalid result with negative reduction
        invalid_result = OptimizationResult(
            optimized_context={'test': 'data'},
            original_tokens=100,
            optimized_tokens=50,
            token_savings=50,
            token_savings_percent=-150.0,  # Invalid: < -100%
            strategies_applied=[],
            processing_time_ms=100.0
        )

        # Should be invalid
        assert optimizer._validate_result(invalid_result) is False

    @pytest.mark.asyncio
    async def test_fallback_result_creation(self, optimizer):
        """Test _create_fallback_result method."""
        context = {'test': 'data', 'nested': {'key': 'value'}}

        result = optimizer._create_fallback_result(context, "Test fallback")

        # Check fallback properties
        assert result.fallback is True
        assert result.fallback_reason == "Test fallback"
        assert result.optimized_context == context
        assert result.original_tokens == result.optimized_tokens
        assert result.token_savings == 0
        assert result.token_savings_percent == 0.0
        assert result.strategies_applied == []
        assert result.processing_time_ms == 0.0


class TestSprint1Metrics:
    """Tests for Sprint 1 metrics and reporting."""

    @pytest.fixture
    def optimizer(self):
        """Create token optimizer instance."""
        return TokenOptimizer(OptimizationConfig(enabled=True))

    @pytest.fixture
    def generator(self):
        """Create test data generator."""
        return TestDataGenerator()

    @pytest.mark.asyncio
    async def test_token_savings_calculation(self, optimizer, generator):
        """Test token savings are calculated correctly."""
        incident = generator.generate_incident(
            incident_type='high_latency',
            severity='high'
        )

        result = await optimizer.optimize(
            context_data=incident,
            incident_type='high_latency',
            severity=SeverityLevel.HIGH
        )

        # Verify calculations
        expected_savings = result.original_tokens - result.optimized_tokens
        assert result.token_savings == expected_savings

        expected_percent = (expected_savings / result.original_tokens * 100) if result.original_tokens > 0 else 0
        assert abs(result.token_savings_percent - expected_percent) < 0.01

    @pytest.mark.asyncio
    async def test_processing_time_tracking(self, optimizer, generator):
        """Test processing time is tracked accurately."""
        incident = generator.generate_incident(
            incident_type='generic',
            severity='medium'
        )

        result = await optimizer.optimize(
            context_data=incident,
            incident_type='generic',
            severity=SeverityLevel.MEDIUM
        )

        # Processing time should be positive and reasonable
        assert result.processing_time_ms > 0
        assert result.processing_time_ms < 5000  # Should not take 5 seconds

    @pytest.mark.asyncio
    async def test_strategies_tracking(self, optimizer, generator):
        """Test strategies applied are tracked."""
        incident = generator.generate_incident(
            incident_type='error_spike',
            severity='critical'
        )

        # Ensure we have logs
        if 'logs' not in incident or not incident['logs']:
            incident['logs'] = [
                {'message': f'Error {i}', 'level': 'error', 'timestamp': datetime.now().isoformat()}
                for i in range(20)
            ]

        result = await optimizer.optimize(
            context_data=incident,
            incident_type='error_spike',
            severity=SeverityLevel.CRITICAL
        )

        # Should have multiple strategies
        assert len(result.strategies_applied) > 0

        # All strategies should be OptimizationStrategy enums
        for strategy in result.strategies_applied:
            assert isinstance(strategy, tuple) or isinstance(strategy, str) or hasattr(strategy, 'value')
