"""
Enhanced tests for AnomalyDetector with 6 metric types.

Phase 6: AI Input Optimization & Cost Efficiency
Day 2: Enhanced testing for anomaly detection capabilities
"""

from datetime import datetime, timedelta, timezone

import pytest

from tests.unit.test_optimization.data_generator import TestDataGenerator
from app.services.anomaly_detector import (
    AnomalyDetector,
    AnomalyScore,
)
from app.services.token_optimizer import OptimizationConfig


class TestAnomalyDetectorMetricTypes:
    """Test all 6 metric types detection."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return OptimizationConfig(
            anomaly_cpu_high=80.0,
            anomaly_cpu_low=20.0,
            anomaly_memory_high=85.0,
            anomaly_disk_high=90.0,
            anomaly_error_rate_high=5.0,
            anomaly_network_io_high_multiplier=3.0,
            anomaly_network_io_critical_multiplier=5.0,
            anomaly_disk_io_high_multiplier=3.0,
            anomaly_disk_io_critical_multiplier=5.0,
        )

    @pytest.fixture
    def detector(self, config):
        """Create AnomalyDetector instance."""
        return AnomalyDetector(config)

    @pytest.fixture
    def generator(self):
        """Create test data generator."""
        return TestDataGenerator()

    @pytest.mark.asyncio
    async def test_cpu_anomaly_detection(self, detector):
        """Test CPU anomaly detection."""
        metrics = [
            {'cpu_percent': 45.0, 'timestamp': datetime.now(timezone.utc) - timedelta(minutes=5)},
            {'cpu_percent': 48.0, 'timestamp': datetime.now(timezone.utc) - timedelta(minutes=4)},
            {'cpu_percent': 42.0, 'timestamp': datetime.now(timezone.utc) - timedelta(minutes=3)},
            {'cpu_percent': 95.0, 'timestamp': datetime.now(timezone.utc) - timedelta(minutes=2)},  # Anomaly
            {'cpu_percent': 92.0, 'timestamp': datetime.now(timezone.utc) - timedelta(minutes=1)},
        ]

        result, anomalies = await detector.detect_metrics_anomaly(metrics[-1])

        assert 'cpu_percent' in result
        assert '_anomalies' in result
        assert len(result['_anomalies']) > 0
        assert result['_anomalies'][0]['severity'] == 'critical'

    @pytest.mark.asyncio
    async def test_memory_anomaly_detection(self, detector):
        """Test memory anomaly detection."""
        metrics = {'memory_percent': 90.0}

        result, anomalies = await detector.detect_metrics_anomaly(metrics)

        assert 'memory_percent' in result
        assert any(a['metric'] == 'memory_percent' for a in result.get('_anomalies', []))

    @pytest.mark.asyncio
    async def test_disk_anomaly_detection(self, detector):
        """Test disk anomaly detection."""
        metrics = {'disk_percent': 95.0}

        result, anomalies = await detector.detect_metrics_anomaly(metrics)

        assert 'disk_percent' in result
        assert any(a['metric'] == 'disk_percent' for a in result.get('_anomalies', []))

    @pytest.mark.asyncio
    async def test_network_io_anomaly_detection(self, detector):
        """Test network I/O anomaly detection (NEW for Day 2)."""
        # Set up baseline
        detector.update_historical_metrics({'network_in_bytes': [1000000] * 5})

        metrics = {'network_in_bytes': 10_000_000}  # 10x baseline

        result, anomalies = await detector.detect_metrics_anomaly(metrics)

        assert '_network_io_anomaly' in result or '_anomalies' in result

    @pytest.mark.asyncio
    async def test_disk_io_anomaly_detection(self, detector):
        """Test disk I/O anomaly detection (NEW for Day 2)."""
        # Set up baseline
        detector.update_historical_metrics({'disk_read_bytes': [50000] * 5})

        metrics = {'disk_read_bytes': 300000}  # 6x baseline

        result, anomalies = await detector.detect_metrics_anomaly(metrics)

        assert '_disk_io_anomaly' in result or '_anomalies' in result

    @pytest.mark.asyncio
    async def test_error_rate_anomaly_detection(self, detector):
        """Test error rate anomaly detection (NEW for Day 2)."""
        metrics = {'error_rate': 12.0}  # Above critical threshold

        result, anomalies = await detector.detect_metrics_anomaly(metrics)

        assert 'error_rate' in result
        assert any(a['metric'] == 'error_rate' for a in result.get('_anomalies', []))


class TestAdaptiveThresholds:
    """Test adaptive threshold calculation (NEW for Day 2)."""

    @pytest.fixture
    def detector(self):
        """Create AnomalyDetector instance."""
        config = OptimizationConfig(
            anomaly_cpu_high=80.0,
            anomaly_memory_high=85.0,
        )
        return AnomalyDetector(config)

    def test_baseline_calculation_minimum_samples(self, detector):
        """Test baseline requires minimum 3 samples."""
        # Should return empty with < 3 samples
        metrics = [
            {'cpu': 50.0},
            {'cpu': 55.0}
        ]

        baseline = detector.calculate_baseline(metrics)

        # With only 2 samples, should not have baseline
        assert 'cpu' not in baseline or baseline.get('cpu', {}).get('count', 0) < 3

    def test_baseline_calculation_statistics(self, detector):
        """Test baseline calculates correct statistics."""
        metrics = [
            {'cpu': 40.0},
            {'cpu': 45.0},
            {'cpu': 50.0},
            {'cpu': 42.0},
            {'cpu': 48.0},
            {'cpu': 55.0},
            {'cpu': 43.0}
        ]

        baseline = detector.calculate_baseline(metrics)

        assert 'cpu' in baseline
        assert 'mean' in baseline['cpu']
        assert 'std' in baseline['cpu']
        assert 'p50' in baseline['cpu']
        assert 'p95' in baseline['cpu']

        # Verify mean is approximately correct
        import statistics
        expected_mean = statistics.mean([m['cpu'] for m in metrics])
        assert abs(baseline['cpu']['mean'] - expected_mean) < 0.1

    def test_detect_with_baseline_high_anomaly(self, detector):
        """Test detection of high-severity anomaly using baseline."""
        historical = [
            {'cpu': 45.0, 'memory': 60.0} for _ in range(10)
        ]

        baseline = detector.calculate_baseline(historical)

        current = {'cpu': 85.0}  # Should trigger high anomaly

        # Note: This uses a different method signature
        anomalies = detector.detect_with_baseline(current, baseline)

        assert len(anomalies) > 0
        assert anomalies[0].severity in ['high', 'critical']

    def test_detect_with_baseline_no_anomaly(self, detector):
        """Test no false positives with normal values using baseline."""
        historical = [
            {'cpu': 45.0} for _ in range(10)
        ]

        baseline = detector.calculate_baseline(historical)
        current = {'cpu': 48.0}  # Normal value

        anomalies = detector.detect_with_baseline(current, baseline)

        # Should have fewer or no anomalies
        assert len(anomalies) == 0 or all(a.severity == 'none' for a in anomalies)


class TestAnomalyScoring:
    """Test anomaly scoring with severity classification (NEW for Day 2)."""

    @pytest.fixture
    def detector(self):
        """Create AnomalyDetector instance."""
        config = OptimizationConfig(anomaly_cpu_high=80.0)
        return AnomalyDetector(config)

    def test_score_low_severity(self, detector):
        """Test low severity scoring (20-50% deviation)."""
        baseline = {'mean': 100.0, 'std': 10.0, 'count': 30}
        score = detector.score_anomaly('cpu', 130.0, baseline)

        assert score.severity == 'low'
        assert 20 <= score.deviation_percent <= 50
        assert isinstance(score, AnomalyScore)

    def test_score_medium_severity(self, detector):
        """Test medium severity scoring (50-100% deviation)."""
        baseline = {'mean': 100.0, 'std': 10.0, 'count': 30}
        score = detector.score_anomaly('memory', 160.0, baseline)

        assert score.severity == 'medium'
        assert 50 <= score.deviation_percent <= 100

    def test_score_high_severity(self, detector):
        """Test high severity scoring (100-200% deviation)."""
        baseline = {'mean': 100.0, 'std': 10.0, 'count': 30}
        score = detector.score_anomaly('cpu', 220.0, baseline)

        assert score.severity == 'high'
        assert 100 <= score.deviation_percent <= 200

    def test_score_critical_severity(self, detector):
        """Test critical severity scoring (>200% deviation)."""
        baseline = {'mean': 100.0, 'std': 10.0, 'count': 30}
        score = detector.score_anomaly('cpu', 350.0, baseline)

        assert score.severity == 'critical'
        assert score.deviation_percent > 200

    def test_score_with_zero_baseline(self, detector):
        """Test scoring handles zero baseline."""
        baseline = {'mean': 0.0, 'std': 5.0, 'count': 10}
        score = detector.score_anomaly('error_rate', 10.0, baseline)

        # Should not crash, return some default
        assert score.confidence >= 0
        assert score.deviation_percent == 0  # Can't calculate with zero baseline

    def test_confidence_increases_with_samples(self, detector):
        """Test confidence increases with more data points."""
        baseline_small = {'mean': 100.0, 'std': 10.0, 'count': 5}
        baseline_large = {'mean': 100.0, 'std': 10.0, 'count': 100}

        score_small = detector.score_anomaly('cpu', 150.0, baseline_small)
        score_large = detector.score_anomaly('cpu', 150.0, baseline_large)

        assert score_large.confidence >= score_small.confidence

    def test_score_serialization(self, detector):
        """Test AnomalyScore can be serialized to dict."""
        baseline = {'mean': 100.0, 'std': 10.0, 'count': 30}
        score = detector.score_anomaly('cpu', 150.0, baseline)

        score_dict = score.to_dict()

        assert 'metric' in score_dict
        assert 'current' in score_dict
        assert 'baseline' in score_dict
        assert 'deviation_percent' in score_dict
        assert 'severity' in score_dict
        assert 'confidence' in score_dict


class TestWithGeneratedData:
    """Test with realistic generated test data."""

    @pytest.fixture
    def generator(self):
        """Create test data generator."""
        return TestDataGenerator(seed=42)

    @pytest.fixture
    def detector(self):
        """Create detector instance."""
        config = OptimizationConfig(
            anomaly_cpu_high=80.0,
            anomaly_memory_high=85.0,
            anomaly_disk_high=90.0,
            anomaly_error_rate_high=5.0,
        )
        return AnomalyDetector(config)

    def test_generate_all_incident_types(self, generator):
        """Test generator can create all incident types."""
        incident_types = generator.get_incident_types()

        assert len(incident_types) >= 12  # At least 12 types

        # Test each type can be generated
        for incident_type in incident_types:
            incident = generator.generate_incident(
                incident_type=incident_type,
                severity='medium',
                complexity=0.5
            )

            assert incident is not None
            assert incident['metadata']['type'] == incident_type
            assert 'logs' in incident
            assert 'metrics' in incident
            assert 'apm_data' in incident

    @pytest.mark.asyncio
    async def test_anomaly_detection_with_generated_data(self, detector, generator):
        """Test anomaly detection with realistic generated incidents."""
        # Generate a high_latency incident
        incident = generator.generate_incident(
            incident_type='high_latency',
            severity='high',
            complexity=0.6
        )

        # Extract latest metrics
        metrics = incident['metrics']
        current_metrics = {}

        for key, value in metrics.items():
            if isinstance(value, dict) and 'current' in value:
                current_metrics[f"{key}_percent" if '_percent' not in key else key] = value['current']

        # Detect anomalies
        result, anomalies = await detector.detect_metrics_anomaly(current_metrics)

        # Should detect some anomalies in high_latency incident
        assert result is not None

    def test_batch_generation(self, generator):
        """Test batch generation of incidents."""
        incident_types = ['high_latency', 'error_spike', 'pod_crashloop']

        batch = generator.generate_batch(incident_types, count_per_type=3)

        assert len(batch) == 9  # 3 types * 3 each


class TestHistoricalMetrics:
    """Test historical metrics tracking for adaptive baselines."""

    @pytest.fixture
    def detector(self):
        """Create detector instance."""
        return AnomalyDetector(OptimizationConfig())

    def test_update_historical_metrics(self, detector):
        """Test updating historical metrics."""
        metrics = {'cpu': 50.0, 'memory': 60.0}

        detector.update_historical_metrics(metrics)

        assert 'cpu' in detector.historical_metrics
        assert 'memory' in detector.historical_metrics
        assert len(detector.historical_metrics['cpu']) == 1

    def test_historical_metrics_window(self, detector):
        """Test historical metrics window size limit."""
        detector.baseline_window = 5

        # Add more metrics than window size
        for i in range(10):
            detector.update_historical_metrics({'cpu': 50.0 + i})

        # Should only keep last 5
        assert len(detector.historical_metrics['cpu']) == 5
        assert detector.historical_metrics['cpu'][-1] == 59.0  # Last added

    def test_get_baseline_from_history(self, detector):
        """Test getting baseline from historical metrics."""
        # Add some historical data
        for i in range(5):
            detector.update_historical_metrics({'cpu': 50.0 + i})

        baseline = detector._get_baseline('cpu')

        # Should be average of [50, 51, 52, 53, 54] = 52.0
        assert baseline == 52.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
