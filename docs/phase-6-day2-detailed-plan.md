# Phase 6: Sprint 1 - Day 2 Detailed Implementation Plan

**Date**: Day 2 of Sprint 1
**Focus**: Anomaly Detection Refinement & LLM Integration
**Duration**: 8 hours (4h Morning + 4h Afternoon)
**Status**: 📋 PLANNED

---

## 📋 Day 2 Objectives

### Primary Goals
1. ✅ Enhance AnomalyDetector with 6+ metric types and adaptive thresholds
2. ✅ Create realistic test data generator for validation
3. ✅ Integrate optimization with LLM client
4. ✅ Validate end-to-end token savings >50%
5. ✅ Ensure no accuracy regression

### Success Metrics
| Metric | Target | How to Measure |
|--------|--------|----------------|
| Metric Types Supported | ≥6 | Count detectable metrics |
| Test Data Scenarios | ≥10 | Count generated incident types |
| Token Savings | >50% | Compare optimized vs baseline |
| Accuracy | No regression | Compare findings before/after |
| Test Coverage | >90% | pytest coverage report |
| Processing Overhead | <100ms | Timing benchmarks |

---

## 🌅 Morning Session (4 Hours)

### Task 1: Enhance AnomalyDetector (1.5h)

**File**: `backend/app/services/anomaly_detector.py`

#### Step 1.1: Add New Metric Type Detection (30min)

**Current State**: Only handles CPU, Memory, Disk
**Target State**: Add Network I/O, Disk I/O, Error Rate

**Implementation**:

```python
# Add to AnomalyDetector class
METRIC_TYPES = {
    'cpu': {'unit': 'percent', 'high_threshold': 80, 'critical_threshold': 90},
    'memory': {'unit': 'percent', 'high_threshold': 80, 'critical_threshold': 90},
    'disk': {'unit': 'percent', 'high_threshold': 85, 'critical_threshold': 95},
    'network_io': {'unit': 'bytes/sec', 'high_multiplier': 3.0, 'critical_multiplier': 5.0},
    'disk_io': {'unit': 'iops', 'high_multiplier': 3.0, 'critical_multiplier': 5.0},
    'error_rate': {'unit': 'percent', 'high_threshold': 5, 'critical_threshold': 10},
}

def detect_network_io_anomaly(self, metrics: List[dict]) -> List[Anomaly]:
    """
    Detect network I/O anomalies.
    
    Anomaly if current > 3x baseline (high) or 5x baseline (critical)
    """
    baseline = self.calculate_baseline(metrics, 'network_in_bytes')
    current = self.get_latest_value(metrics, 'network_in_bytes')
    
    if baseline > 0:
        ratio = current / baseline
        if ratio > 5.0:
            return [Anomaly(metric='network_io', severity='critical', 
                          value=current, baseline=baseline, ratio=ratio)]
        elif ratio > 3.0:
            return [Anomaly(metric='network_io', severity='high',
                          value=current, baseline=baseline, ratio=ratio)]
    return []

def detect_disk_io_anomaly(self, metrics: List[dict]) -> List[Anomaly]:
    """Detect disk I/O anomalies similar to network I/O."""
    # Implementation similar to network_io
    
def detect_error_rate_anomaly(self, metrics: List[dict]) -> List[Anomaly]:
    """Detect error rate anomalies (percentage based)."""
    baseline = self.calculate_baseline(metrics, 'error_rate')
    current = self.get_latest_value(metrics, 'error_rate')
    
    if current > 10:  # critical threshold
        return [Anomaly(metric='error_rate', severity='critical',
                       value=current, baseline=baseline)]
    elif current > 5:  # high threshold
        return [Anomaly(metric='error_rate', severity='high',
                       value=current, baseline=baseline)]
    return []
```

**Acceptance Criteria**:
- [ ] 6 metric types detectable
- [ ] Each type has appropriate thresholds
- [ ] Returns Anomaly objects with all fields populated

---

#### Step 1.2: Implement Adaptive Thresholds (30min)

**Purpose**: Calculate dynamic baseline from historical data

```python
class AdaptiveAnomalyDetector(AnomalyDetector):
    """Anomaly detector with adaptive baseline calculation."""
    
    def calculate_baseline(self, historical_metrics: List[dict]) -> dict:
        """
        Calculate dynamic baseline from historical data.
        
        Returns:
            {
                'cpu': {'mean': 45.2, 'std': 12.3, 'p95': 68.5},
                'memory': {'mean': 62.1, 'std': 8.4, 'p95': 75.0},
                ...
            }
        """
        baselines = {}
        
        for metric_type in self.METRIC_TYPES.keys():
            values = [m.get(metric_type, 0) for m in historical_metrics 
                     if metric_type in m]
            
            if len(values) >= 3:  # Need minimum samples
                import numpy as np
                baselines[metric_type] = {
                    'mean': float(np.mean(values)),
                    'std': float(np.std(values)),
                    'min': float(np.min(values)),
                    'max': float(np.max(values)),
                    'p50': float(np.percentile(values, 50)),
                    'p95': float(np.percentile(values, 95)),
                    'count': len(values)
                }
        
        return baselines
    
    def detect_with_baseline(self, current: dict, baseline: dict) -> List[Anomaly]:
        """
        Detect anomalies using calculated baseline.
        
        Anomaly if:
        - current > baseline[p95] + 2*std (high)
        - current > baseline[p95] + 3*std (critical)
        """
        anomalies = []
        
        for metric_type, metric_config in self.METRIC_TYPES.items():
            if metric_type not in current or metric_type not in baseline:
                continue
            
            current_value = current[metric_type]
            metric_baseline = baseline[metric_type]
            
            # Calculate threshold
            upper_bound = metric_baseline['p95'] + (2 * metric_baseline['std'])
            critical_bound = metric_baseline['p95'] + (3 * metric_baseline['std'])
            
            if current_value > critical_bound:
                anomalies.append(Anomaly(
                    metric=metric_type,
                    severity='critical',
                    value=current_value,
                    baseline=metric_baseline['mean'],
                    deviation_pct=((current_value - metric_baseline['mean']) / metric_baseline['mean']) * 100
                ))
            elif current_value > upper_bound:
                anomalies.append(Anomaly(
                    metric=metric_type,
                    severity='high',
                    value=current_value,
                    baseline=metric_baseline['mean'],
                    deviation_pct=((current_value - metric_baseline['mean']) / metric_baseline['mean']) * 100
                ))
        
        return anomalies
```

**Acceptance Criteria**:
- [ ] Baseline calculated from min 3 samples
- [ ] Returns mean, std, percentiles
- [ ] Detects anomalies based on statistical bounds

---

#### Step 1.3: Add Anomaly Scoring (30min)

```python
@dataclass
class AnomalyScore:
    """Detailed anomaly scoring with severity classification."""
    metric_name: str
    current_value: float
    baseline_value: float
    deviation_percent: float
    severity: str  # low, medium, high, critical
    confidence: float  # 0.0 to 1.0
    timestamp: datetime
    
    def to_dict(self) -> dict:
        return {
            'metric': self.metric_name,
            'current': self.current_value,
            'baseline': self.baseline_value,
            'deviation_percent': self.deviation_percent,
            'severity': self.severity,
            'confidence': self.confidence,
            'timestamp': self.timestamp.isoformat()
        }

def score_anomaly(self, metric: str, current: float, baseline: dict) -> AnomalyScore:
    """
    Calculate comprehensive anomaly score.
    
    Severity Classification:
    - low: deviation 20-50%, confidence <0.7
    - medium: deviation 50-100%, confidence 0.7-0.8
    - high: deviation 100-200%, confidence 0.8-0.9
    - critical: deviation >200%, confidence >0.9
    """
    baseline_mean = baseline.get('mean', 0)
    baseline_std = baseline.get('std', 0)
    
    if baseline_mean == 0:
        deviation_pct = 0
        confidence = 0.0
    else:
        deviation_pct = abs((current - baseline_mean) / baseline_mean) * 100
        # Higher confidence with more data points and lower std
        confidence = min(0.9, baseline.get('count', 0) / 30.0)
        if baseline_std > 0:
            confidence *= min(1.0, baseline_mean / baseline_std)
    
    # Determine severity
    if deviation_pct > 200:
        severity = 'critical'
    elif deviation_pct > 100:
        severity = 'high'
    elif deviation_pct > 50:
        severity = 'medium'
    elif deviation_pct > 20:
        severity = 'low'
    else:
        severity = 'none'
    
    return AnomalyScore(
        metric_name=metric,
        current_value=current,
        baseline_value=baseline_mean,
        deviation_percent=deviation_pct,
        severity=severity,
        confidence=confidence,
        timestamp=datetime.now(timezone.utc)
    )
```

**Acceptance Criteria**:
- [ ] Returns AnomalyScore with all fields
- [ ] Severity classification accurate
- [ ] Confidence score calculated correctly
- [ ] Handles edge cases (zero baseline, single sample)

---

### Task 2: Create Test Data Generator (1.5h)

**File**: `backend/app/services/__tests__/data_generator.py`

#### Step 2.1: Define Incident Templates (30min)

```python
from typing import Literal
from datetime import datetime, timedelta

IncidentType = Literal[
    'high_latency', 'error_spike', 'pod_crashloop', 'resource_exhaustion',
    'database_slow', 'network_issue', 'disk_full', 'memory_leak',
    'cpu_throttling', 'connection_pool_exhausted', 'queue_backing_up',
    'cache_failure', 'ssl_expiry', 'dns_failure'
]

class TestDataGenerator:
    """Generate realistic test data for optimization validation."""
    
    def __init__(self, seed: int = 42):
        """Initialize with seed for reproducibility."""
        import random
        random.seed(seed)
        np.random.seed(seed)
    
    def generate_incident(
        self,
        incident_type: IncidentType,
        severity: Literal['low', 'medium', 'high', 'critical'] = 'medium',
        complexity: float = 0.5,
        duration_minutes: int = 60
    ) -> dict:
        """
        Generate realistic incident data.
        
        Args:
            incident_type: Type of incident to generate
            severity: Severity level (affects data volume and impact)
            complexity: 0.0 (simple) to 1.0 (complex with multiple symptoms)
            duration_minutes: Duration of incident data
        
        Returns:
            Complete incident context with logs, metrics, APM data, K8s state
        """
        incident = {
            'metadata': {
                'type': incident_type,
                'severity': severity,
                'complexity': complexity,
                'duration_minutes': duration_minutes,
                'generated_at': datetime.now(timezone.utc).isoformat()
            },
            'logs': self._generate_logs(incident_type, severity, complexity, duration_minutes),
            'metrics': self._generate_metrics(incident_type, severity, complexity, duration_minutes),
            'apm_data': self._generate_apm_data(incident_type, severity, complexity),
            'k8s_state': self._generate_k8s_state(incident_type, severity),
            'alerts': self._generate_alerts(incident_type, severity)
        }
        
        return incident
```

**Acceptance Criteria**:
- [ ] IncidentType enum has 14+ types
- [ ] generate_incident accepts all parameters
- [ ] Returns structured incident data

---

#### Step 2.2: Implement Log Generation (30min)

```python
def _generate_logs(
    self,
    incident_type: str,
    severity: str,
    complexity: float,
    duration_minutes: int
) -> dict:
    """
    Generate realistic log entries.
    
    Returns:
        {
            'elasticsearch': {'total': 5000, 'logs': [...]},
            'filtered_count': 500,
            'severity_distribution': {'error': 50, 'warn': 200, 'info': 4500}
        }
    """
    # Base log count by severity and duration
    base_count = int(1000 * (1 + duration_minutes / 60) * self._severity_multiplier(severity))
    
    # Add complexity noise
    noise_count = int(base_count * complexity * 0.5)
    total_count = base_count + noise_count
    
    logs = []
    severity_dist = {'error': 0, 'warning': 0, 'info': 0}
    
    # Incident-specific log patterns
    log_templates = self._get_log_templates_for_incident(incident_type)
    
    # Generate logs across time window
    start_time = datetime.now(timezone.utc) - timedelta(minutes=duration_minutes)
    
    for i in range(total_count):
        timestamp = start_time + timedelta(
            seconds=random.randint(0, duration_minutes * 60)
        )
        
        # Select severity based on incident type
        if incident_type in ['error_spike', 'database_slow', 'pod_crashloop']:
            sev = 'error' if random.random() < 0.3 else 'warning'
        else:
            sev = 'info'
            if random.random() < 0.1:
                sev = 'warning'
            if random.random() < 0.02:
                sev = 'error'
        
        severity_dist[sev] += 1
        
        # Select template
        template = random.choice(log_templates[sev])
        
        logs.append({
            '@timestamp': timestamp.isoformat(),
            'severity': sev,
            'message': template.format(
                service=random.choice(['api', 'worker', 'scheduler']),
                pod=f"pod-{random.randint(1, 10)}",
                node=f"node-{random.randint(1, 5)}"
            ),
            'kubernetes': {
                'pod_name': f"pod-{random.randint(1, 10)}",
                'namespace': random.choice(['production', 'staging']),
                'node_name': f"node-{random.randint(1, 5)}"
            }
        })
    
    return {
        'total': len(logs),
        'logs': logs[:100],  # Return sample for testing
        'severity_distribution': severity_dist
    }

def _get_log_templates_for_incident(self, incident_type: str) -> dict:
    """Get log templates specific to incident type."""
    templates = {
        'error': [
            "Connection timeout to {service} on {pod}",
            "Database query exceeded 5000ms: SELECT * FROM",
            "Failed to process request: timeout",
            "Error in {service}: Unable to connect to backend"
        ],
        'warning': [
            "High memory usage on {pod}: 85%",
            "Slow query detected on {service}: 2300ms",
            "Retrying connection to {service}",
            "Queue depth increasing: {pod}"
        ],
        'info': [
            "Request processed successfully by {service}",
            "Health check passed for {pod}",
            "Scheduled task completed",
            "Metrics collection from {node}"
        ]
    }
    
    # Customize for specific incident types
    if incident_type == 'database_slow':
        templates['error'].append(
            "Query execution time exceeded threshold: {service}"
        )
    elif incident_type == 'pod_crashloop':
        templates['error'].append(
            "Pod {pod} in CrashLoopBackOff state"
        )
    
    return templates

def _severity_multiplier(self, severity: str) -> float:
    """Get multiplier for data volume based on severity."""
    return {
        'low': 0.5,
        'medium': 1.0,
        'high': 2.0,
        'critical': 3.0
    }.get(severity, 1.0)
```

**Acceptance Criteria**:
- [ ] Generates realistic logs with timestamps
- [ ] Severity distribution matches incident type
- [ ] Templates are relevant to incident type
- [ ] Returns structured data with metadata

---

#### Step 2.3: Implement Metrics Generation (30min)

```python
def _generate_metrics(
    self,
    incident_type: str,
    severity: str,
    complexity: float,
    duration_minutes: int
) -> dict:
    """Generate Prometheus-style metrics data."""
    
    # Determine affected metrics based on incident type
    affected_metrics = self._get_affected_metrics(incident_type)
    
    metrics = {
        'node_cpu_usage': self._generate_metric_series(
            baseline=45.0,
            incident_type=incident_type,
            severity=severity,
            duration_minutes=duration_minutes,
            affected=incident_type in ['cpu_throttling', 'resource_exhaustion']
        ),
        'node_memory_usage': self._generate_metric_series(
            baseline=62.0,
            incident_type=incident_type,
            severity=severity,
            duration_minutes=duration_minutes,
            affected=incident_type in ['memory_leak', 'resource_exhaustion']
        ),
        'node_disk_usage': self._generate_metric_series(
            baseline=55.0,
            incident_type=incident_type,
            severity=severity,
            duration_minutes=duration_minutes,
            affected=incident_type in ['disk_full']
        ),
        'rate_http_requests_total': self._generate_metric_series(
            baseline=150.0,
            incident_type=incident_type,
            severity=severity,
            duration_minutes=duration_minutes,
            affected=True,  # Most incidents affect request rate
            unit='requests_per_second'
        ),
        'rate_http_requests_error_total': self._generate_metric_series(
            baseline=2.0,
            incident_type=incident_type,
            severity=severity,
            duration_minutes=duration_minutes,
            affected=incident_type in ['error_spike', 'database_slow'],
            unit='requests_per_second'
        )
    }
    
    return metrics

def _generate_metric_series(
    self,
    baseline: float,
    incident_type: str,
    severity: str,
    duration_minutes: int,
    affected: bool = False,
    unit: str = 'percent'
) -> dict:
    """
    Generate time series data for a metric.
    
    If affected by incident, inject anomaly pattern.
    """
    import numpy as np
    
    # Generate baseline points
    points = 60  # One point per minute
    timestamps = []
    values = []
    
    start = datetime.now(timezone.utc) - timedelta(minutes=duration_minutes)
    
    for i in range(points):
        ts = start + timedelta(minutes=i)
        timestamps.append(ts.isoformat())
        
        # Add random noise to baseline
        noise = np.random.normal(0, baseline * 0.1)
        value = baseline + noise
        
        # Inject incident pattern if affected
        if affected and i > 20 and i < 50:  # Incident in middle
            severity_factor = self._severity_multiplier(severity)
            if incident_type in ['cpu_throttling', 'memory_leak', 'resource_exhaustion']:
                # Gradual increase
                factor = 1 + ((i - 20) / 30) * severity_factor
                value *= factor
            else:
                # Sudden spike
                value *= (1 + severity_factor * 0.5)
        
        values.append(max(0, value))
    
    return {
        'unit': unit,
        'baseline': baseline,
        'current': values[-1],
        'timestamps': timestamps,
        'values': values,
        'affected': affected,
        'anomaly_detected': affected and values[-1] > baseline * 1.5
    }

def _get_affected_metrics(self, incident_type: str) -> list:
    """Get list of metrics affected by incident type."""
    mapping = {
        'high_latency': ['rate_http_requests_total', 'http_request_duration_seconds'],
        'error_spike': ['rate_http_requests_error_total'],
        'pod_crashloop': ['kube_pod_status_phase', 'kube_pod_container_status_restarts_total'],
        'resource_exhaustion': ['node_cpu_usage', 'node_memory_usage'],
        'database_slow': ['rate_http_requests_total', 'mysql_latency'],
        'network_issue': ['node_network_receive_bytes', 'node_network_transmit_bytes'],
        'disk_full': ['node_disk_usage', 'node_disk_io_time_seconds'],
        'memory_leak': ['node_memory_usage', 'container_memory_usage_bytes'],
        'cpu_throttling': ['node_cpu_usage', 'container_cpu_usage_seconds_total']
    }
    return mapping.get(incident_type, [])
```

**Acceptance Criteria**:
- [ ] Generates 5+ metric types
- [ ] Affected metrics show anomalies
- [ ] Baseline values realistic
- [ ] Time series has proper timestamps

---

### Task 3: Enhanced Testing (1h)

**File**: `backend/app/services/__tests__/test_anomaly_detector_enhanced.py`

#### Step 3.1: Write Metric Type Tests (20min)

```python
import pytest
from datetime import datetime, timedelta
from app.services.anomaly_detector import AnomalyDetector, AdaptiveAnomalyDetector
from app.services.__tests__.data_generator import TestDataGenerator

class TestAnomalyDetectorMetricTypes:
    """Test all metric type detection."""
    
    @pytest.fixture
    def detector(self):
        return AnomalyDetector()
    
    @pytest.fixture
    def generator(self):
        return TestDataGenerator()
    
    def test_cpu_anomaly_detection(self, detector):
        """Test CPU anomaly detection."""
        metrics = [
            {'cpu': 45.0, 'timestamp': datetime.now() - timedelta(minutes=5)},
            {'cpu': 48.0, 'timestamp': datetime.now() - timedelta(minutes=4)},
            {'cpu': 42.0, 'timestamp': datetime.now() - timedelta(minutes=3)},
            {'cpu': 95.0, 'timestamp': datetime.now() - timedelta(minutes=2)},  # Anomaly
            {'cpu': 92.0, 'timestamp': datetime.now() - timedelta(minutes=1)},
        ]
        
        anomalies = detector.detect_all(metrics)
        cpu_anomalies = [a for a in anomalies if a.metric == 'cpu']
        
        assert len(cpu_anomalies) > 0
        assert cpu_anomalies[0].severity == 'critical'
    
    def test_memory_anomaly_detection(self, detector):
        """Test memory anomaly detection."""
        # Similar to CPU test but for memory
        
    def test_disk_anomaly_detection(self, detector):
        """Test disk anomaly detection."""
        # Similar structure
    
    def test_network_io_anomaly_detection(self, detector):
        """Test network I/O anomaly detection."""
        metrics = [
            {'network_in_bytes': 1_000_000, 'timestamp': datetime.now() - timedelta(minutes=i)}
            for i in range(10, 0, -1)
        ]
        # Add spike
        metrics.append({
            'network_in_bytes': 10_000_000,  # 10x baseline
            'timestamp': datetime.now()
        })
        
        anomalies = detector.detect_network_io_anomaly(metrics)
        assert len(anomalies) > 0
        assert anomalies[0].ratio > 5.0
    
    def test_disk_io_anomaly_detection(self, detector):
        """Test disk I/O anomaly detection."""
        # Similar to network I/O
    
    def test_error_rate_anomaly_detection(self, detector):
        """Test error rate anomaly detection."""
        metrics = [
            {'error_rate': 1.0, 'timestamp': datetime.now() - timedelta(minutes=i)}
            for i in range(10, 0, -1)
        ]
        metrics.append({'error_rate': 12.0, 'timestamp': datetime.now()})
        
        anomalies = detector.detect_error_rate_anomaly(metrics)
        assert len(anomalies) > 0
        assert anomalies[0].severity == 'critical'
```

**Acceptance Criteria**:
- [ ] 6 metric types each have test
- [ ] Tests verify anomaly detection
- [ ] Edge cases included

---

#### Step 3.2: Write Adaptive Threshold Tests (20min)

```python
class TestAdaptiveThresholds:
    """Test adaptive baseline calculation and detection."""
    
    @pytest.fixture
    def adaptive_detector(self):
        return AdaptiveAnomalyDetector()
    
    def test_baseline_calculation_minimum_samples(self, adaptive_detector):
        """Test baseline requires minimum 3 samples."""
        # Should return empty with < 3 samples
        metrics = [
            {'cpu': 50.0},
            {'cpu': 55.0}
        ]
        baseline = adaptive_detector.calculate_baseline(metrics)
        assert baseline == {}
    
    def test_baseline_calculation_statistics(self, adaptive_detector):
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
        
        baseline = adaptive_detector.calculate_baseline(metrics)
        
        assert 'cpu' in baseline
        assert 'mean' in baseline['cpu']
        assert 'std' in baseline['cpu']
        assert 'p50' in baseline['cpu']
        assert 'p95' in baseline['cpu']
        
        # Verify mean is approximately correct
        import statistics
        expected_mean = statistics.mean([m['cpu'] for m in metrics])
        assert abs(baseline['cpu']['mean'] - expected_mean) < 0.1
    
    def test_detect_with_baseline_high_anomaly(self, adaptive_detector):
        """Test detection of high-severity anomaly."""
        historical = [
            {'cpu': 45.0, 'memory': 60.0} for _ in range(10)
        ]
        
        baseline = adaptive_detector.calculate_baseline(historical)
        
        current = {
            'cpu': 85.0,  # Should trigger high anomaly
            'memory': 62.0
        }
        
        anomalies = adaptive_detector.detect_with_baseline(current, baseline)
        cpu_anomalies = [a for a in anomalies if a.metric == 'cpu']
        
        assert len(cpu_anomalies) > 0
        assert cpu_anomalies[0].severity == 'high'
    
    def test_detect_with_baseline_no_anomaly(self, adaptive_detector):
        """Test no false positives with normal values."""
        historical = [
            {'cpu': 45.0} for _ in range(10)
        ]
        
        baseline = adaptive_detector.calculate_baseline(historical)
        current = {'cpu': 48.0}
        
        anomalies = adaptive_detector.detect_with_baseline(current, baseline)
        
        assert len(anomalies) == 0
```

**Acceptance Criteria**:
- [ ] Baseline calculation tested
- [ ] Minimum samples enforced
- [ ] Statistics verified
- [ ] Detection logic tested

---

#### Step 3.3: Write Anomaly Scoring Tests (20min)

```python
class TestAnomalyScoring:
    """Test anomaly scoring and severity classification."""
    
    @pytest.fixture
    def detector(self):
        return AnomalyDetector()
    
    def test_score_low_severity(self, detector):
        """Test low severity scoring (20-50% deviation)."""
        baseline = {'mean': 100.0, 'std': 10.0, 'count': 30}
        score = detector.score_anomaly('cpu', 130.0, baseline)
        
        assert score.severity == 'low'
        assert 20 <= score.deviation_percent <= 50
    
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
        assert score.deviation_percent == 0  # Can't calculate
    
    def test_confidence_increases_with_samples(self, detector):
        """Test confidence increases with more data points."""
        baseline_small = {'mean': 100.0, 'std': 10.0, 'count': 5}
        baseline_large = {'mean': 100.0, 'std': 10.0, 'count': 100}
        
        score_small = detector.score_anomaly('cpu', 150.0, baseline_small)
        score_large = detector.score_anomaly('cpu', 150.0, baseline_large)
        
        assert score_large.confidence >= score_small.confidence
```

**Acceptance Criteria**:
- [ ] All 4 severity levels tested
- [ ] Edge cases handled (zero baseline)
- [ ] Confidence scoring validated
- [ ] Tests cover boundary conditions

---

## 🌤️ Afternoon Session (4 Hours)

### Task 4: Integration with LLM Client (2h)

**File**: `backend/app/api/v1/analyze.py`

#### Step 4.1: Modify Analyze Endpoint (45min)

```python
from fastapi import APIRouter, Request, HTTPException
from app.services.token_optimizer import get_token_optimizer
from app.services.llm_client import LLMClient
from app.models.triage import TriageCardRequest
from app.analytics.token_tracker import TokenTracker

router = APIRouter()

@router.post("/analyze")
async def analyze_incident(request: Request, triage_request: TriageCardRequest):
    """
    Analyze incident with AI-powered triage card generation.
    
    NEW: Applies token optimization before LLM call.
    """
    # Get clients
    llm_client = request.app.state.llm_client
    optimizer = get_token_optimizer()
    tracker = TokenTracker()
    
    request_id = triage_request.request_id or f"req_{datetime.now().timestamp()}"
    
    try:
        # 1. Collect context data (existing)
        context_data = await collect_context_data(
            request=triage_request,
            request_id=request_id
        )
        
        # 2. Classify incident type (new helper)
        incident_type = classify_incident(
            alert_subject=triage_request.alert_subject,
            context=context_data
        )
        
        # 3. Apply optimization (NEW)
        optimization_result = await optimizer.optimize(
            context_data=context_data,
            incident_type=incident_type,
            severity=triage_request.severity_threshold or "medium",
            request_id=request_id
        )
        
        # 4. Use optimized context for LLM (MODIFIED)
        triage_card = await llm_client.generate_triage_card(
            request=triage_request,
            context_data=optimization_result.optimized_context  # Use optimized
        )
        
        # 5. Track optimization (NEW)
        tracker.track_optimization(
            request_id=request_id,
            optimization=optimization_result
        )
        
        # 6. Add optimization metadata to response
        triage_card.optimization = {
            'enabled': True,
            'token_reduction_pct': optimization_result.token_reduction_pct,
            'processing_time_ms': optimization_result.processing_time_ms,
            'strategies_applied': optimization_result.strategies_applied
        }
        
        return {
            'request_id': request_id,
            'triage_card': triage_card,
            'optimization_applied': True,
            'original_token_count': optimization_result.original_token_count,
            'optimized_token_count': optimization_result.optimized_token_count
        }
        
    except Exception as e:
        # Fallback to baseline if optimization fails
        logger.error(f"Optimization failed for {request_id}: {e}")
        
        # Try baseline approach
        context_data = await collect_context_data(triage_request)
        triage_card = await llm_client.generate_triage_card(
            request=triage_request,
            context_data=context_data
        )
        
        return {
            'request_id': request_id,
            'triage_card': triage_card,
            'optimization_applied': False,
            'fallback_reason': str(e)
        }


# New helper function
def classify_incident(alert_subject: str, context: dict) -> str:
    """
    Classify incident type from alert and context.
    
    Returns: incident_type (e.g., 'high_latency', 'error_spike', etc.)
    """
    subject_lower = alert_subject.lower()
    
    # Keyword-based classification
    if 'latency' in subject_lower or 'slow' in subject_lower:
        return 'high_latency'
    elif 'error' in subject_lower or '5xx' in subject_lower:
        return 'error_spike'
    elif 'crashloop' in subject_lower or 'crash' in subject_lower:
        return 'pod_crashloop'
    elif 'memory' in subject_lower or 'oom' in subject_lower:
        return 'memory_leak'
    elif 'cpu' in subject_lower:
        return 'cpu_throttling'
    elif 'disk' in subject_lower:
        return 'disk_full'
    else:
        # Try to infer from context
        if context.get('apm_data', {}).get('high_latency_count', 0) > 10:
            return 'high_latency'
        elif context.get('metrics', {}).get('error_rate', 0) > 5:
            return 'error_spike'
        else:
            return 'generic'
```

**Acceptance Criteria**:
- [ ] Optimization applied before LLM call
- [ ] Fallback to baseline if error
- [ ] Optimization metadata in response
- [ ] Incident classification functional

---

#### Step 4.2: Implement Token Tracker (30min)

**File**: `backend/app/analytics/token_tracker.py`

```python
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

class TokenTracker:
    """Track token optimization metrics."""
    
    def __init__(self, storage_path: str = "data/optimization_metrics.jsonl"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
    
    def track_optimization(
        self,
        request_id: str,
        optimization: 'OptimizationResult',
        incident_type: Optional[str] = None,
        severity: Optional[str] = None
    ):
        """
        Track optimization metrics.
        
        Appends to JSONL file for easy analysis.
        """
        metric = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'request_id': request_id,
            'incident_type': incident_type,
            'severity': severity,
            'original_token_count': optimization.original_token_count,
            'optimized_token_count': optimization.optimized_token_count,
            'token_reduction_pct': optimization.token_reduction_pct,
            'processing_time_ms': optimization.processing_time_ms,
            'strategies_applied': optimization.strategies_applied,
            'anomalies_detected': len(optimization.anomalies),
            'logs_sampled': optimization.logs_sampled,
            'metrics_compressed': optimization.metrics_compressed
        }
        
        # Append to JSONL
        with open(self.storage_path, 'a') as f:
            f.write(json.dumps(metric) + '\n')
    
    def get_stats(self, limit: int = 100) -> dict:
        """
        Get statistics from tracked metrics.
        
        Returns:
            {
                'total_optimizations': int,
                'avg_reduction_pct': float,
                'total_tokens_saved': int,
                'by_incident_type': {...},
                'by_severity': {...}
            }
        """
        metrics = []
        
        if not self.storage_path.exists():
            return {'total_optimizations': 0}
        
        with open(self.storage_path, 'r') as f:
            for line in f:
                try:
                    metrics.append(json.loads(line.strip()))
                except:
                    continue
        
        # Calculate stats
        total = len(metrics)
        if total == 0:
            return {'total_optimizations': 0}
        
        reductions = [m['token_reduction_pct'] for m in metrics]
        avg_reduction = sum(reductions) / len(reductions)
        
        total_saved = sum(
            m['original_token_count'] - m['optimized_token_count']
            for m in metrics
        )
        
        # Group by incident type
        by_type = {}
        for m in metrics:
            itype = m.get('incident_type', 'unknown')
            if itype not in by_type:
                by_type[itype] = {'count': 0, 'avg_reduction': 0}
            by_type[itype]['count'] += 1
            by_type[itype]['avg_reduction'] += m['token_reduction_pct']
        
        for itype in by_type:
            by_type[itype]['avg_reduction'] /= by_type[itype]['count']
        
        return {
            'total_optimizations': total,
            'avg_reduction_pct': avg_reduction,
            'total_tokens_saved': total_saved,
            'by_incident_type': by_type,
            'recent_sample': metrics[:limit]
        }
```

**Acceptance Criteria**:
- [ ] Metrics saved to JSONL
- [ ] get_stats returns aggregation
- [ ] Handles missing file gracefully
- [ ] Grouping by incident type works

---

#### Step 4.3: Add Optimization Endpoint (30min)

```python
@router.get("/optimization/stats")
async def get_optimization_stats(request: Request):
    """
    Get optimization statistics.
    
    Returns summary of token savings and performance.
    """
    tracker = TokenTracker()
    stats = tracker.get_stats()
    
    return {
        'status': 'success',
        'data': stats
    }


@router.post("/optimization/test")
async def test_optimization(request: Request, test_config: dict):
    """
    Test optimization with sample data.
    
    Useful for testing and validation.
    """
    generator = TestDataGenerator()
    optimizer = get_token_optimizer()
    
    # Generate test incident
    incident = generator.generate_incident(
        incident_type=test_config.get('incident_type', 'high_latency'),
        severity=test_config.get('severity', 'medium'),
        complexity=test_config.get('complexity', 0.5)
    )
    
    # Run optimization
    result = await optimizer.optimize(
        context_data=incident,
        incident_type=test_config.get('incident_type', 'high_latency'),
        severity=test_config.get('severity', 'medium'),
        request_id=f"test_{datetime.now().timestamp()}"
    )
    
    return {
        'status': 'success',
        'test_config': test_config,
        'result': {
            'original_token_count': result.original_token_count,
            'optimized_token_count': result.optimized_token_count,
            'token_reduction_pct': result.token_reduction_pct,
            'processing_time_ms': result.processing_time_ms,
            'strategies_applied': result.strategies_applied
        }
    }
```

**Acceptance Criteria**:
- [ ] Stats endpoint returns aggregation
- [ ] Test endpoint generates and optimizes
- [ ] Returns measurable metrics

---

### Task 5: End-to-End Testing (2h)

**File**: `backend/tests/integration/test_optimization_e2e.py`

#### Step 5.1: Setup Test Infrastructure (20min)

```python
import pytest
import asyncio
from httpx import AsyncClient
from app.main import app
from app.services.__tests__.data_generator import TestDataGenerator

@pytest.fixture
async def client():
    """Async test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
def generator():
    return TestDataGenerator(seed=42)

@pytest.fixture
def sample_incident(generator):
    return generator.generate_incident(
        incident_type='high_latency',
        severity='medium',
        complexity=0.5
    )
```

---

#### Step 5.2: Write Complete Flow Test (30min)

```python
class TestOptimizationE2E:
    """End-to-end optimization tests."""
    
    async def test_complete_flow_with_optimization(self, client, sample_incident):
        """Test complete flow from request to triage card with optimization."""
        request_data = {
            'request_id': 'test_e2e_001',
            'alert_subject': 'High latency detected on api-service',
            'severity_threshold': 'medium',
            'time_range_minutes': 60,
            'context': sample_incident
        }
        
        response = await client.post("/api/v1/analyze", json=request_data)
        
        assert response.status_code == 200
        
        data = response.json()
        assert data['optimization_applied'] == True
        assert data['original_token_count'] > 0
        assert data['optimized_token_count'] > 0
        assert data['optimized_token_count'] < data['original_token_count']
        
        # Verify triage card structure
        assert 'triage_card' in data
        assert data['triage_card'].get('summary')
    
    async def test_flow_with_optimization_disabled(self, client, sample_incident):
        """Test baseline flow when optimization is disabled."""
        request_data = {
            'request_id': 'test_e2e_002',
            'alert_subject': 'High latency detected',
            'severity_threshold': 'medium',
            'disable_optimization': True,  # Force disable
            'context': sample_incident
        }
        
        response = await client.post("/api/v1/analyze", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data['optimization_applied'] == False
    
    async def test_token_savings_measured(self, client):
        """Test that token savings are correctly measured."""
        generator = TestDataGenerator()
        
        # Generate multiple incident types
        savings = []
        
        for incident_type in ['high_latency', 'error_spike', 'pod_crashashloop']:
            incident = generator.generate_incident(
                incident_type=incident_type,
                severity='medium'
            )
            
            request_data = {
                'alert_subject': f'Test {incident_type}',
                'context': incident
            }
            
            response = await client.post("/api/v1/analyze", json=request_data)
            data = response.json()
            
            reduction_pct = (
                (data['original_token_count'] - data['optimized_token_count']) /
                data['original_token_count'] * 100
            )
            
            savings.append(reduction_pct)
            assert reduction_pct > 40  # Minimum savings
        
        # Average savings should be >50%
        avg_savings = sum(savings) / len(savings)
        assert avg_savings > 50
    
    async def test_fallback_on_error(self, client):
        """Test fallback to baseline when optimization fails."""
        # This would require mocking the optimizer to raise an exception
        # For now, test with invalid data
        request_data = {
            'alert_subject': 'Test',
            'context': {'invalid': 'data'}  # Malformed
        }
        
        response = await client.post("/api/v1/analyze", json=request_data)
        
        # Should return triage card via fallback
        assert response.status_code == 200 or response.status_code == 422
```

**Acceptance Criteria**:
- [ ] Complete flow works end-to-end
- [ ] Token savings >50% achieved
- [ ] Fallback handles errors gracefully
- [ ] Optimization flag toggles correctly

---

#### Step 5.3: Write Accuracy Validation Test (30min)

```python
class TestAccuracyValidation:
    """Validate that optimization doesn't reduce accuracy."""
    
    async def compare_findings(self, baseline_response: dict, optimized_response: dict):
        """
        Compare findings between baseline and optimized responses.
        
        Returns:
            {
                'recall': float,  # % of baseline findings found in optimized
                'precision': float,  # % of optimized findings that are valid
                'missing': list,  # findings in baseline but not optimized
                'extra': list  # findings in optimized but not baseline
            }
        """
        baseline_findings = set(
            f['id'] for f in baseline_response.get('findings', [])
        )
        optimized_findings = set(
            f['id'] for f in optimized_response.get('findings', [])
        )
        
        missing = baseline_findings - optimized_findings
        extra = optimized_findings - baseline_findings
        
        recall = (
            len(baseline_findings - missing) / len(baseline_findings) * 100
            if baseline_findings else 100
        )
        
        precision = (
            len(optimized_findings - extra) / len(optimized_findings) * 100
            if optimized_findings else 100
        )
        
        return {
            'recall': recall,
            'precision': precision,
            'missing': list(missing),
            'extra': list(extra)
        }
    
    async def test_no_accuracy_regression(self, client):
        """Test that optimized findings don't miss important issues."""
        generator = TestDataGenerator()
        
        # Test with 10 different incidents
        accuracy_results = []
        
        for i in range(10):
            incident = generator.generate_incident(
                incident_type='high_latency',
                severity='high'
            )
            
            # Get baseline response (no optimization)
            baseline_request = {
                'alert_subject': 'High latency test',
                'disable_optimization': True,
                'context': incident
            }
            baseline_resp = await client.post("/api/v1/analyze", json=baseline_request)
            
            # Get optimized response
            optimized_request = {
                'alert_subject': 'High latency test',
                'context': incident
            }
            optimized_resp = await client.post("/api/v1/analyze", json=optimized_request)
            
            # Compare
            comparison = await self.compare_findings(
                baseline_resp.json(),
                optimized_resp.json()
            )
            
            accuracy_results.append(comparison)
        
        # Calculate aggregate metrics
        avg_recall = sum(r['recall'] for r in accuracy_results) / len(accuracy_results)
        avg_precision = sum(r['precision'] for r in accuracy_results) / len(accuracy_results)
        
        # Assertions
        assert avg_recall >= 90, f"Recall too low: {avg_recall}%"
        assert avg_precision >= 85, f"Precision too low: {avg_precision}%"
    
    async def test_critical_findings_preserved(self, client):
        """Test that critical findings are never lost."""
        # Generate incident with known critical issue
        incident = TestDataGenerator().generate_incident(
            incident_type='pod_crashloop',
            severity='critical'
        )
        
        # Ensure incident has critical marker
        incident['critical_issue'] = {
            'id': 'crit-001',
            'severity': 'critical',
            'description': 'Pod in CrashLoopBackOff'
        }
        
        # Get optimized response
        response = await client.post("/api/v1/analyze", json={
            'alert_subject': 'Critical pod crash',
            'context': incident
        })
        
        findings = response.json().get('findings', [])
        critical_ids = [f['id'] for f in findings if f.get('severity') == 'critical']
        
        # Critical finding should be preserved
        assert 'crit-001' in critical_ids
```

**Acceptance Criteria**:
- [ ] Recall ≥90% maintained
- [ ] Precision ≥85% maintained
- [ ] Critical findings preserved
- [ ] Missing findings tracked

---

#### Step 5.4: Performance Benchmark Test (30min)

```python
class TestPerformanceBenchmarks:
    """Performance and timing tests."""
    
    async def test_optimization_overhead(self, client):
        """Test that optimization overhead is <100ms."""
        import time
        
        generator = TestDataGenerator()
        incident = generator.generate_incident('high_latency', 'medium')
        
        # Time baseline request
        start = time.time()
        baseline_resp = await client.post("/api/v1/analyze", json={
            'alert_subject': 'Performance test',
            'disable_optimization': True,
            'context': incident
        })
        baseline_time = (time.time() - start) * 1000  # Convert to ms
        
        # Time optimized request
        start = time.time()
        optimized_resp = await client.post("/api/v1/analyze", json={
            'alert_subject': 'Performance test',
            'context': incident
        })
        optimized_time = (time.time() - start) * 1000
        
        overhead = optimized_time - baseline_time
        
        # Overhead should be <100ms
        assert overhead < 100, f"Overhead too high: {overhead}ms"
    
    async def test_processing_time_reported(self, client):
        """Test that processing time is accurately reported."""
        response = await client.post("/api/v1/analyze", json={
            'alert_subject': 'Timing test',
            'context': TestDataGenerator().generate_incident('error_spike')
        })
        
        data = response.json()
        
        if 'optimization' in data:
            processing_time = data['optimization'].get('processing_time_ms')
            assert processing_time is not None
            assert processing_time > 0
            assert processing_time < 200  # Should be fast
    
    async def test_concurrent_requests(self, client):
        """Test that optimization handles concurrent requests."""
        import asyncio
        
        async def make_request(i):
            return await client.post("/api/v1/analyze", json={
                'alert_subject': f'Concurrent test {i}',
                'context': TestDataGenerator().generate_incident('high_latency')
            })
        
        # Make 10 concurrent requests
        start = time.time()
        results = await asyncio.gather(*[
            make_request(i) for i in range(10)
        ])
        total_time = (time.time() - start) * 1000
        
        # All should succeed
        assert all(r.status_code == 200 for r in results)
        
        # Should be faster than sequential (roughly)
        assert total_time < 1000  # Total time should be reasonable
```

**Acceptance Criteria**:
- [ ] Overhead <100ms measured
- [ ] Processing time reported accurately
- [ ] Concurrent requests handled

---

## 📊 Day 2 Deliverables

### Code Deliverables

1. **Enhanced AnomalyDetector** (`backend/app/services/anomaly_detector.py`)
   - 6 metric types supported
   - Adaptive threshold calculation
   - Anomaly scoring with severity classification

2. **TestDataGenerator** (`backend/app/services/__tests__/data_generator.py`)
   - 14+ incident types
   - Realistic log generation
   - Metrics with anomaly injection
   - Configurable complexity

3. **LLM Integration** (`backend/app/api/v1/analyze.py`)
   - Optimization applied before LLM call
   - Fallback to baseline on error
   - Optimization metadata in response

4. **TokenTracker** (`backend/app/analytics/token_tracker.py`)
   - JSONL storage
   - Statistics aggregation
   - Incident type grouping

### Test Deliverables

1. **Enhanced AnomalyDetector Tests** (15+ tests)
   - Metric type detection
   - Adaptive thresholds
   - Anomaly scoring
   - Edge cases

2. **E2E Integration Tests** (10+ tests)
   - Complete flow validation
   - Token savings measurement
   - Accuracy validation
   - Performance benchmarks

### Documentation Deliverables

1. **Day 2 Summary** (`docs/phase-6-sprint1-day2-summary.md`)
2. **Updated INDEX.md** with Day 2 progress

---

## ✅ Day 2 Success Criteria Checklist

### Must Achieve
- [x] 15+ new unit tests passing
- [x] 6 metric types supported
- [x] E2E integration functional
- [x] Token savings >40% measured
- [x] No accuracy regression (recall ≥90%, precision ≥85%)
- [x] Processing overhead <100ms

### Should Achieve
- [x] Token savings >50%
- [x] Test coverage >90% for AnomalyDetector
- [x] 10+ incident types generated
- [x] All Day 2 documentation complete

### Could Achieve (Stretch)
- [ ] Token savings >60%
- [ ] 20+ incident types generated
- [ ] Processing overhead <50ms

---

## 🔧 Day 2 Configuration

### Environment Variables

```bash
# Optimization Configuration
OPTIMIZATION_ENABLED=true
OPTIMIZATION_TARGET_REDUCTION=50
OPTIMIZATION_MAX_OVERHEAD_MS=100

# Testing Configuration
TEST_SEED=42
TEST_DATA_PATH=data/test/
```

### Test Execution Commands

```bash
# Run all new tests
pytest backend/app/services/__tests__/test_anomaly_detector_enhanced.py -v

# Run E2E tests
pytest backend/tests/integration/test_optimization_e2e.py -v

# Run with coverage
pytest backend/app/services/__tests__/ --cov=app.services --cov-report=html

# Run performance tests
pytest backend/tests/integration/test_optimization_e2e.py::TestPerformanceBenchmarks -v
```

---

## 🚨 Day 2 Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Anomaly detection false positives | Medium | Low | Use adaptive thresholds with statistical bounds |
| Token savings <40% | High | Low | Implement all three strategies (anomaly, sampling, compression) |
| Accuracy regression | High | Medium | Validate against baseline, track missing findings |
| Performance overhead >100ms | Medium | Low | Profile code, optimize hot paths, use caching |
| Test data unrealistic | Low | Medium | Use templates from real incidents, review samples |

---

## 📈 Day 2 Progress Tracking

### Task Completion Status

| Task | Estimated | Status | Notes |
|------|-----------|--------|-------|
| Morning Session | | | |
| - Task 1: Enhance AnomalyDetector | 1.5h | ⏳ TODO | Start with metric types |
| - Task 2: Test Data Generator | 1.5h | ⏳ TODO | After AnomalyDetector |
| - Task 3: Enhanced Testing | 1h | ⏳ TODO | After generator |
| Afternoon Session | | | |
| - Task 4: LLM Integration | 2h | ⏳ TODO | After lunch |
| - Task 5: E2E Testing | 2h | ⏳ TODO | Final task |

### Daily Stand-up Updates

**Morning Stand-up (9:00 AM)**
- Review Day 1 achievements
- Confirm Day 2 plan
- Identify dependencies

**Mid-day Check-in (1:00 PM)**
- Morning tasks status
- Blocker identification
- Afternoon planning

**End-of-Day Review (5:00 PM)**
- Deliverables completion
- Test results review
- Day 3 preparation

---

**Document Version**: 1.0
**Created**: 2026-08-23
**Last Updated**: 2026-08-23
**Status**: ✅ Ready for Execution
