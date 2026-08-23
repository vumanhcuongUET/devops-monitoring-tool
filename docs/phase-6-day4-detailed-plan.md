# Phase 6: Sprint 1 - Day 4 Detailed Implementation Plan

**Date**: Day 4 of Sprint 1  
**Focus**: Time Series Compression Integration  
**Duration**: 8 hours  
**Status**: 📋 READY FOR EXECUTION

---

## 📋 Day 4 Objectives

### Primary Goals
1. ✅ Integrate compression with Prometheus client
2. ✅ Compress APM latency/throughput/error data
3. ✅ Implement trend detection algorithm
4. ✅ Build end-to-end optimization flow
5. ✅ Test with 50 real-world incidents

### Success Metrics
| Metric | Target | How to Measure |
|--------|--------|----------------|
| Prometheus Compression | >80% token reduction | Comparison test |
| APM Compression | >80% token reduction | Comparison test |
| Trend Detection | 4 states accurate | Unit tests |
| End-to-End Flow | Functional | Integration tests |
| Real-World Testing | 50 incidents | Test execution |

---

## 🌅 Morning Session (4 Hours)

### Task 1: Prometheus Client Integration (1.5h)

**File**: `backend/app/services/prometheus_client.py`

```python
from app.services.time_series_compressor import TimeSeriesCompressor

class PrometheusClient:
    """Enhanced with time series compression."""
    
    def __init__(self):
        self.compressor = TimeSeriesCompressor()
    
    async def get_node_metrics_compressed(
        self,
        minutes: int = 60
    ) -> dict:
        """
        Get node metrics with compression applied.
        
        Returns compressed format instead of raw time-series.
        
        Args:
            minutes: Time range for metrics
        
        Returns:
            {
                "cpu": {...compressed...},
                "memory": {...compressed...},
                "disk": {...compressed...},
                "network": {...compressed...}
            }
        """
        # Get raw metrics
        raw_metrics = await self.get_node_metrics_raw(minutes=minutes)
        
        # Compress each metric
        compressed = {}
        for metric_name, time_series in raw_metrics.items():
            compressed[metric_name] = self.compressor.compress_timeseries(
                time_series
            )
        
        return compressed
    
    async def get_history_compressed(
        self,
        metric: str,
        minutes: int = 60
    ) -> dict:
        """
        Get metric history with compression.
        
        Returns percentile statistics instead of raw points.
        
        Args:
            metric: Metric name (e.g., 'node_cpu_usage')
            minutes: Time range
        
        Returns:
            {
                "metric": str,
                "current": float,
                "p50": float,
                "p90": float,
                "p95": float,
                "p99": float,
                "min": float,
                "max": float,
                "trend": str,
                "volatility": float,
                "sample_count": int
            }
        """
        # Query Prometheus
        query_result = await self.query_range(
            query=metric,
            minutes=minutes,
            step='1m'  # 1-minute resolution
        )
        
        # Extract time series values
        if not query_result or 'data' not in query_result:
            return self._empty_compressed_result(metric)
        
        values = []
        for result in query_result['data'].get('result', []):
            values.extend([float(v[1]) for v in result['values']])
        
        if not values:
            return self._empty_compressed_result(metric)
        
        # Compress using percentiles
        return self.compressor.compress_values(values, metric)
    
    def _empty_compressed_result(self, metric: str) -> dict:
        """Return empty result structure."""
        return {
            "metric": metric,
            "current": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "min": 0.0,
            "max": 0.0,
            "trend": "unknown",
            "volatility": 0.0,
            "sample_count": 0
        }
```

**Acceptance Criteria**:
- [ ] Compressed metrics accessible via API
- [ ] Backward compatible with existing methods
- [ ] Token savings >80% for time-series
- [ ] Handles empty results gracefully

---

### Task 2: APM Data Compression (1h)

**File**: `backend/app/services/apm_client.py`

```python
from app.services.time_series_compressor import TimeSeriesCompressor

class ApmClient:
    """Enhanced with time series compression."""
    
    def __init__(self):
        self.compressor = TimeSeriesCompressor()
    
    async def get_latency_history_compressed(
        self,
        service_name: str,
        minutes: int = 60
    ) -> dict:
        """
        Get latency history compressed to percentiles.
        
        Returns:
            {
                "service": str,
                "current_ms": float,
                "p50_ms": float,
                "p95_ms": float,
                "p99_ms": float,
                "trend": str,
                "volatility": float
            }
        """
        # Query APM for latency data
        raw_data = await self.query_latency_distribution(
            service_name=service_name,
            minutes=minutes
        )
        
        # Extract latency values
        values = raw_data.get('latency_values', [])
        
        if not values:
            return self._empty_latency_result(service_name)
        
        # Compress
        compressed = self.compressor.compress_values(values, 'latency')
        
        return {
            "service": service_name,
            "current_ms": compressed['current'],
            "p50_ms": compressed['p50'],
            "p95_ms": compressed['p95'],
            "p99_ms": compressed['p99'],
            "trend": compressed['trend'],
            "volatility": compressed['volatility']
        }
    
    async def get_throughput_history_compressed(
        self,
        service_name: str,
        minutes: int = 60
    ) -> dict:
        """Get throughput history compressed."""
        raw_data = await self.query_throughput(service_name, minutes)
        values = raw_data.get('requests_per_minute', [])
        
        compressed = self.compressor.compress_values(values, 'throughput')
        
        return {
            "service": service_name,
            "current_rpm": compressed['current'],
            "p50_rpm": compressed['p50'],
            "p95_rpm": compressed['p95'],
            "trend": compressed['trend'],
            "volatility": compressed['volatility']
        }
    
    async def get_error_rate_history_compressed(
        self,
        service_name: str,
        minutes: int = 60
    ) -> dict:
        """Get error rate history compressed."""
        raw_data = await self.query_error_rate(service_name, minutes)
        values = raw_data.get('error_rates', [])
        
        compressed = self.compressor.compress_values(values, 'error_rate')
        
        return {
            "service": service_name,
            "current_pct": compressed['current'],
            "p50_pct": compressed['p50'],
            "p95_pct": compressed['p95'],
            "trend": compressed['trend'],
            "volatility": compressed['volatility']
        }
```

**Acceptance Criteria**:
- [ ] Latency history compressed
- [ ] Throughput history compressed
- [ ] Error rate history compressed
- [ ] All metrics include trend
- [ ] Token savings >80%

---

### Task 3: Trend Detection Algorithm (1.5h)

**File**: `backend/app/services/time_series_compressor.py`

```python
import numpy as np
from enum import Enum
from typing import List

class Trend(Enum):
    """Trend states."""
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    VOLATILE = "volatile"

class TimeSeriesCompressor:
    """Enhanced with trend detection."""
    
    def detect_trend(
        self,
        values: List[float],
        window_size: int = 5
    ) -> str:
        """
        Detect trend using moving average.
        
        Algorithm:
        1. Calculate moving average
        2. Compare first vs last MA
        3. Check volatility (std/mean ratio)
        4. Classify trend
        
        Args:
            values: List of numeric values
            window_size: Moving average window
        
        Returns:
            Trend state: 'increasing', 'decreasing', 'stable', 'volatile'
        """
        if len(values) < window_size:
            return 'unknown'
        
        # Convert to numpy array
        arr = np.array(values)
        
        # Calculate moving averages
        ma_values = []
        for i in range(len(arr) - window_size + 1):
            window = arr[i:i + window_size]
            ma_values.append(np.mean(window))
        
        if len(ma_values) < 2:
            return 'unknown'
        
        # Calculate volatility
        std = np.std(ma_values)
        mean = np.mean(ma_values)
        
        if mean > 0:
            volatility_ratio = std / mean
        else:
            volatility_ratio = float('inf') if std > 0 else 0
        
        # High volatility → volatile trend
        if volatility_ratio > 0.3:
            return Trend.VOLATILE.value
        
        # Compare first and last moving averages
        first_ma = ma_values[0]
        last_ma = ma_values[-1]
        
        # Calculate percent change
        if first_ma > 0:
            change_pct = (last_ma - first_ma) / abs(first_ma)
        else:
            change_pct = 0
        
        # Classify trend
        if change_pct > 0.1:  # >10% increase
            return Trend.INCREASING.value
        elif change_pct < -0.1:  # >10% decrease
            return Trend.DECREASING.value
        else:
            return Trend.STABLE.value
    
    def compress_values(self, values: List[float], metric_name: str) -> dict:
        """
        Compress values to key statistics.
        
        Returns:
            {
                "metric": str,
                "current": float,
                "p50": float,
                "p90": float,
                "p95": float,
                "p99": float,
                "min": float,
                "max": float,
                "trend": str,
                "volatility": float,
                "sample_count": int
            }
        """
        if not values:
            return self._empty_result(metric_name)
        
        arr = np.array(values)
        
        return {
            "metric": metric_name,
            "current": float(arr[-1]) if len(arr) > 0 else 0.0,
            "p50": float(np.percentile(arr, 50)),
            "p90": float(np.percentile(arr, 90)),
            "p95": float(np.percentile(arr, 95)),
            "p99": float(np.percentile(arr, 99)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "trend": self.detect_trend(values),
            "volatility": float(np.std(arr)) if len(arr) > 1 else 0.0,
            "sample_count": len(arr)
        }
    
    def _empty_result(self, metric_name: str) -> dict:
        """Return empty result structure."""
        return {
            "metric": metric_name,
            "current": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "min": 0.0,
            "max": 0.0,
            "trend": "unknown",
            "volatility": 0.0,
            "sample_count": 0
        }
```

**Acceptance Criteria**:
- [ ] 4 trend states detected correctly
- [ ] Volatility threshold configurable
- [ ] Handles edge cases (short series, zeros)
- [ ] Trend detection accurate

---

## 🌤️ Afternoon Session (4 Hours)

### Task 4: End-to-End Optimization Flow (2h)

**File**: `backend/app/services/token_optimizer.py`

```python
from typing import Optional
from datetime import datetime

@dataclass
class OptimizationResult:
    """Result of optimization process."""
    optimized_context: dict
    original_token_count: int
    optimized_token_count: int
    token_reduction_pct: float
    processing_time_ms: float
    strategies_applied: list
    anomalies: list
    logs_sampled: int
    metrics_compressed: bool

class TokenOptimizer:
    """Complete optimization engine."""
    
    def __init__(self):
        self.anomaly_detector = AnomalyDetector()
        self.log_sampler = LogSampler()
        self.ts_compressor = TimeSeriesCompressor()
        self.relevance_scorer = None  # Sprint 3
    
    async def optimize_comprehensive(
        self,
        context_data: dict,
        incident_type: str,
        severity: str,
        request_id: Optional[str] = None
    ) -> OptimizationResult:
        """
        Apply all optimization strategies with compression.
        
        Flow:
        1. Anomaly detection on metrics
        2. Smart sampling on logs
        3. Time series compression
        4. Relevance filtering
        5. Compact formatting
        
        Args:
            context_data: Full incident context
            incident_type: Type of incident
            severity: Severity level
            request_id: Request identifier for tracking
        
        Returns:
            OptimizationResult with all metrics
        """
        import time
        start_time = time.time()
        
        strategies_applied = []
        original_count = self._estimate_tokens(context_data)
        
        optimized = {}
        
        # 1. Anomaly Detection
        if 'metrics' in context_data:
            anomalies = self.anomaly_detector.detect_all(
                context_data['metrics']
            )
            optimized['anomalies'] = [a.to_dict() for a in anomalies]
            optimized['metrics_summary'] = self._summarize_metrics(
                context_data['metrics'],
                anomalies
            )
            strategies_applied.append('anomaly_detection')
        else:
            anomalies = []
            optimized['anomalies'] = []
        
        # 2. Time Series Compression
        if 'time_series' in context_data:
            compressed_ts = {}
            for metric_name, values in context_data['time_series'].items():
                compressed_ts[metric_name] = self.ts_compressor.compress_values(
                    values, metric_name
                )
            optimized['time_series'] = compressed_ts
            strategies_applied.append('time_series_compression')
        else:
            optimized['time_series'] = {}
        
        # 3. Smart Log Sampling
        if 'logs' in context_data:
            incident_config = {
                'timestamp': datetime.fromisoformat(
                    context_data.get('incident_timestamp', datetime.now().isoformat())
                ),
                'alert_message': context_data.get('alert_message', ''),
                'service': context_data.get('service'),
                'severity': severity
            }
            
            sampled_logs = self.log_sampler.sample_logs_smart(
                context_data['logs'],
                incident_config,
                max_results=50
            )
            optimized['logs'] = sampled_logs[:20]  # Further reduce to 20
            strategies_applied.append('smart_sampling')
        else:
            optimized['logs'] = []
        
        # 4. APM Error Sampling
        if 'apm_errors' in context_data:
            sampled_errors = self.log_sampler.sample_apm_errors_smart(
                context_data['apm_errors'],
                incident_config,
                max_results=10
            )
            optimized['apm_errors'] = sampled_errors[:5]
            strategies_applied.append('apm_error_sampling')
        else:
            optimized['apm_errors'] = []
        
        # 5. Compact formatting
        optimized = self._apply_compact_formatting(optimized)
        
        # Calculate metrics
        processing_time = (time.time() - start_time) * 1000
        optimized_count = self._estimate_tokens(optimized)
        reduction_pct = (
            (original_count - optimized_count) / original_count * 100
            if original_count > 0 else 0
        )
        
        return OptimizationResult(
            optimized_context=optimized,
            original_token_count=original_count,
            optimized_token_count=optimized_count,
            token_reduction_pct=reduction_pct,
            processing_time_ms=processing_time,
            strategies_applied=strategies_applied,
            anomalies=anomalies,
            logs_sampled=len(optimized.get('logs', [])),
            metrics_compressed='time_series_compression' in strategies_applied
        )
    
    def _summarize_metrics(self, metrics: dict, anomalies: list) -> dict:
        """Summarize metrics focusing on anomalies."""
        summary = {}
        
        for metric_name, value in metrics.items():
            is_anomalous = any(a.metric == metric_name for a in anomalies)
            summary[metric_name] = {
                'current': value,
                'anomalous': is_anomalous
            }
        
        return summary
    
    def _apply_compact_formatting(self, context: dict) -> dict:
        """Apply compact formatting to reduce tokens."""
        # Remove redundant fields
        if 'logs' in context:
            for log in context['logs']:
                # Keep only essential fields
                essential_keys = {'@timestamp', 'severity', 'message', 'service'}
                log_copy = {k: log[k] for k in essential_keys if k in log}
                log.clear()
                log.update(log_copy)
        
        return context
    
    def _estimate_tokens(self, data: dict) -> int:
        """Estimate token count from data."""
        import json
        text = json.dumps(data, separators=(',', ':'))
        # Rough estimate: ~4 chars per token
        return len(text) // 4
```

**Acceptance Criteria**:
- [ ] All 5 strategies applied
- [ ] Token savings >60%
- [ ] Processing time <100ms
- [ ] Fallback handles errors

---

### Task 5: Real-World Testing (2h)

**File**: `backend/tests/integration/test_real_world_incidents.py`

```python
import pytest
from app.services.token_optimizer import TokenOptimizer
from app.services.__tests__.data_generator import TestDataGenerator

class TestRealWorldIncidents:
    """Test with realistic incident patterns."""
    
    @pytest.fixture
    def optimizer(self):
        return TokenOptimizer()
    
    @pytest.fixture
    def generator(self):
        return TestDataGenerator()
    
    @pytest.mark.asyncio
    async def test_high_latency_incident(self, optimizer, generator):
        """Test with high latency incident."""
        incident = generator.generate_incident(
            incident_type='high_latency',
            severity='high',
            complexity=0.6
        )
        
        result = await optimizer.optimize_comprehensive(
            incident,
            incident_type='high_latency',
            severity='high'
        )
        
        assert result.token_reduction_pct > 50
        assert 'smart_sampling' in result.strategies_applied
        assert 'time_series_compression' in result.strategies_applied
    
    @pytest.mark.asyncio
    async def test_error_spike_incident(self, optimizer, generator):
        """Test with error spike incident."""
        incident = generator.generate_incident(
            incident_type='error_spike',
            severity='critical',
            complexity=0.7
        )
        
        result = await optimizer.optimize_comprehensive(
            incident,
            incident_type='error_spike',
            severity='critical'
        )
        
        assert len(result.anomalies) > 0  # Should detect errors
        assert result.token_reduction_pct > 50
    
    @pytest.mark.asyncio
    async def test_pod_crashloop_incident(self, optimizer, generator):
        """Test with pod crashloop incident."""
        incident = generator.generate_incident(
            incident_type='pod_crashloop',
            severity='high',
            complexity=0.5
        )
        
        result = await optimizer.optimize_comprehensive(
            incident,
            incident_type='pod_crashloop',
            severity='high'
        )
        
        assert 'anomaly_detection' in result.strategies_applied
        assert result.processing_time_ms < 200
    
    @pytest.mark.asyncio
    async def test_50_incidents_batch(self, optimizer, generator):
        """Test processing 50 diverse incidents."""
        results = []
        
        incident_types = [
            'high_latency', 'error_spike', 'pod_crashloop',
            'resource_exhaustion', 'database_slow', 'network_issue'
        ]
        
        for i in range(50):
            incident_type = incident_types[i % len(incident_types)]
            severity = ['low', 'medium', 'high', 'critical'][i % 4]
            
            incident = generator.generate_incident(
                incident_type=incident_type,
                severity=severity,
                complexity=0.5
            )
            
            result = await optimizer.optimize_comprehensive(
                incident,
                incident_type=incident_type,
                severity=severity
            )
            
            results.append(result)
        
        # Verify all succeeded
        assert len(results) == 50
        
        # Check average token reduction
        avg_reduction = sum(
            r.token_reduction_pct for r in results
        ) / len(results)
        
        assert avg_reduction > 60, f"Average reduction: {avg_reduction}%"
        
        # Check processing time
        avg_time = sum(
            r.processing_time_ms for r in results
        ) / len(results)
        
        assert avg_time < 150, f"Average time: {avg_time}ms"
```

**Acceptance Criteria**:
- [ ] 50 incidents processed successfully
- [ ] Average token savings >60%
- [ ] Average processing time <150ms
- [ ] All incident types supported

---

## 📊 Day 4 Deliverables

### Code Deliverables
1. Prometheus client with compression
2. APM client with compression
3. Trend detection algorithm
4. End-to-end optimization flow
5. Real-world test suite

### Test Deliverables
1. Compression integration tests
2. Trend detection tests
3. End-to-end optimization tests
4. 50-incident batch test

### Documentation Deliverables
1. Day 4 summary document
2. Updated INDEX.md

---

## ✅ Day 4 Success Criteria Checklist

### Must Achieve
- [ ] Time-series token savings >80%
- [ ] Trend detection accurate
- [ ] End-to-end optimization >60% savings
- [ ] 50 incidents tested successfully

### Should Achieve
- [ ] Processing time <100ms average
- [ ] All compression strategies functional
- [ ] Integration tests passing

---

**Document Version**: 1.0  
**Status**: ✅ READY FOR EXECUTION
