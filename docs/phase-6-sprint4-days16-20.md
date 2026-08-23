# Phase 6: Sprint 4 - Days 16-20 Detailed Plans

**Status**: 📋 READY FOR EXECUTION

---

## 📅 Day 16: Token Usage Tracking

### Morning Session (4h)

**Task 1: TokenTracker Implementation (2h)**

```python
# backend/app/analytics/token_tracker.py
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

@dataclass
class TokenUsageRecord:
    """Token usage record for analytics."""
    request_id: str
    timestamp: datetime
    incident_type: str
    severity: str
    
    # Token metrics
    input_tokens: int
    output_tokens: int
    total_tokens: int
    
    # Optimization metrics
    optimization_strategy: str
    token_savings: int
    token_savings_percent: float
    
    # Quality metrics
    finding_recall: float
    finding_precision: float
    processing_time_ms: float
    
    # Cost metrics
    cost_baseline: float
    cost_optimized: float
    cost_savings: float
    
    def to_dict(self) -> Dict:
        return {
            'request_id': self.request_id,
            'timestamp': self.timestamp.isoformat(),
            'incident_type': self.incident_type,
            'severity': self.severity,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'total_tokens': self.total_tokens,
            'optimization_strategy': self.optimization_strategy,
            'token_savings': self.token_savings,
            'token_savings_percent': self.token_savings_percent,
            'finding_recall': self.finding_recall,
            'finding_precision': self.finding_precision,
            'processing_time_ms': self.processing_time_ms,
            'cost_baseline': self.cost_baseline,
            'cost_optimized': self.cost_optimized,
            'cost_savings': self.cost_savings
        }

class TokenTracker:
    """Track token usage and optimization metrics."""
    
    def __init__(self, storage_path: str = "data/token_usage.jsonl"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
    
    def track_request(
        self,
        request_id: str,
        incident: Dict,
        optimization_result: OptimizationResult,
        quality_metrics: Optional[Dict] = None
    ):
        """Track token usage and metrics."""
        
        # Calculate costs
        input_tokens = optimization_result.original_token_count
        output_tokens = optimization_result.optimized_token_count
        total_baseline = input_tokens + 1500  # Est. output
        total_optimized = output_tokens + 1500  # Est. output
        
        cost_baseline = total_baseline * 0.000003  # $3 per million
        cost_optimized = total_optimized * 0.000003
        
        record = TokenUsageRecord(
            request_id=request_id,
            timestamp=datetime.now(timezone.utc),
            incident_type=incident.get('incident_type', 'unknown'),
            severity=incident.get('severity', 'medium'),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=output_tokens,
            optimization_strategy='+'.join(optimization_result.strategies_applied),
            token_savings=input_tokens - output_tokens,
            token_savings_percent=optimization_result.token_reduction_pct,
            finding_recall=quality_metrics.get('recall', 0.0) if quality_metrics else 0.0,
            finding_precision=quality_metrics.get('precision', 0.0) if quality_metrics else 0.0,
            processing_time_ms=optimization_result.processing_time_ms,
            cost_baseline=cost_baseline,
            cost_optimized=cost_optimized,
            cost_savings=cost_baseline - cost_optimized
        )
        
        self._append_record(record)
    
    def _append_record(self, record: TokenUsageRecord):
        """Append record to JSONL file."""
        with open(self.storage_path, 'a') as f:
            f.write(json.dumps(record.to_dict()) + '\n')
    
    def get_stats(
        self,
        limit: int = 100,
        since: Optional[datetime] = None
    ) -> Dict:
        """Get aggregated statistics."""
        records = self._load_records(since)
        
        if not records:
            return {'total_requests': 0}
        
        total = len(records)
        
        # Calculate averages
        avg_savings_pct = sum(r['token_savings_percent'] for r in records) / total
        total_saved = sum(r['token_savings'] for r in records)
        total_cost_saved = sum(r['cost_savings'] for r in records)
        
        # Group by incident type
        by_type = {}
        for r in records:
            itype = r['incident_type']
            if itype not in by_type:
                by_type[itype] = {'count': 0, 'savings': 0}
            by_type[itype]['count'] += 1
            by_type[itype]['savings'] += r['token_savings']
        
        return {
            'total_requests': total,
            'avg_savings_percent': avg_savings_pct,
            'total_tokens_saved': total_saved,
            'total_cost_saved': total_cost_saved,
            'by_incident_type': by_type,
            'recent': records[:limit]
        }
```

**Task 2: Storage Implementation (2h)**
- JSON file storage with rotation
- Daily rotation
- Compression for old data

### Afternoon Session (4h)

**Task 3: Query Interface (2h)**
- Build query functions
- Add filtering options
- Create aggregation helpers

**Task 4: Testing (2h)**
- Unit tests
- Integration tests
- Performance validation

---

## 📅 Day 17: Optimization API Implementation

### Morning Session (4h)

**Task 1: API Endpoints Implementation (2h)**

```python
# backend/app/api/v1/optimization.py
from fastapi import APIRouter, HTTPException
from typing import Optional

router = APIRouter(prefix="/api/v1/optimization", tags=["optimization"])

@router.get("/stats")
async def get_optimization_stats(
    limit: int = 100,
    since: Optional[str] = None
):
    """
    Get token usage statistics.
    
    Returns:
        - Average tokens per request
        - Total tokens saved
        - Cost savings
        - Trend data
    """
    tracker = request.app.state.token_tracker
    
    since_dt = None
    if since:
        since_dt = datetime.fromisoformat(since)
    
    stats = tracker.get_stats(limit=limit, since=since_dt)
    
    return {
        'status': 'success',
        'data': stats
    }

@router.get("/accuracy")
async def get_accuracy_metrics():
    """
    Get accuracy metrics.
    
    Returns:
        - Finding recall trend
        - Finding precision trend
        - Comparison with baseline
    """
    validator = request.app.state.accuracy_validator
    tracker = request.app.state.token_tracker
    
    # Get recent accuracy data
    # ...
    
    return {
        'status': 'success',
        'data': {
            'finding_recall': 0.91,
            'finding_precision': 0.86,
            'trend': 'stable'
        }
    }

@router.get("/strategies")
async def get_active_strategies():
    """
    Get active optimization strategies.
    
    Returns:
        - List of active strategies
        - Effectiveness metrics
        - Configuration
    """
    config = request.app.state.optimization_config
    
    return {
        'status': 'success',
        'data': {
            'active_strategies': config.get('strategies', {}),
            'effectiveness': {
                'anomaly_detection': 0.85,
                'smart_sampling': 0.78,
                'time_series_compression': 0.92
            }
        }
    }

@router.post("/tune")
async def tune_parameters(params: TuningRequest):
    """
    Tune optimization parameters.
    
    Allows dynamic adjustment of:
        - Sampling quotas
        - Anomaly thresholds
        - Budget matrix
    """
    # Update configuration
    config = request.app.state.optimization_config
    
    if params.sampling_quotas:
        config['strategies']['smart_sampling']['quotas'].update(
            params.sampling_quotas
        )
    
    if params.anomaly_thresholds:
        config['strategies']['anomaly_detection']['thresholds'].update(
            params.anomaly_thresholds
        )
    
    # Save configuration
    # ...
    
    return {
        'status': 'success',
        'message': 'Parameters updated',
        'config': config
    }
```

**Task 2: API Documentation (2h)**
- OpenAPI specs
- Usage examples
- Error handling

### Afternoon Session (4h)

**Task 3: Testing (2h)**
- Unit tests for all endpoints
- Integration tests
- Documentation validation

**Task 4: Security (2h)**
- Add authentication
- Add rate limiting
- Add input validation

---

## 📅 Day 18: Dashboard Integration

### Morning Session (4h)

**Task 1: Dashboard Components (2h)**

```typescript
// frontend/src/components/optimization/TokenUsageChart.tsx
export function TokenUsageChart() {
  const [data, setData] = useState([]);
  
  useEffect(() => {
    fetch('/api/v1/optimization/stats')
      .then(r => r.json())
      .then(response => setData(response.data.recent));
  }, []);
  
  return (
    <div className="chart-container">
      <h3>Token Usage Over Time</h3>
      <LineChart data={data}>
        <XAxis dataKey="timestamp" />
        <YAxis />
        <CartesianGrid stroke="#eee" />
        <Tooltip />
        <Legend />
        <Line type="monotone" dataKey="input_tokens" stroke="#8884d8" />
        <Line type="monotone" dataKey="output_tokens" stroke="#82ca9d" />
      </LineChart>
    </div>
  );
}

// frontend/src/components/optimization/AccuracyMetrics.tsx
export function AccuracyMetrics() {
  const [metrics, setMetrics] = useState(null);
  
  return (
    <div className="metrics-grid">
      <MetricCard title="Finding Recall" value={metrics?.finding_recall} />
      <MetricCard title="Finding Precision" value={metrics?.finding_precision} />
      <MetricCard title="Processing Time" value={metrics?.processing_time_ms} unit="ms" />
    </div>
  );
}
```

**Task 2: Visualizations (2h)**
- Token usage trends
- Accuracy trends
- Cost savings charts
- Strategy effectiveness

### Afternoon Session (4h)

**Task 3: Layout & Design (2h)**
- Overview page layout
- Detailed analytics page
- Real-time monitoring page

**Task 4: Real-time Updates (2h)**
- WebSocket integration
- Auto-refresh
- Live metrics

---

## 📅 Day 19: Production Readiness

### Morning Session (4h)

**Task 1: Configuration Finalization (2h)**

```yaml
# config/optimization.yaml (final production)
optimization:
  enabled: true
  fallback_on_error: true
  max_overhead_ms: 100

strategies:
  anomaly_detection:
    enabled: true
    thresholds: { ... }
  smart_sampling:
    enabled: true
    quotas: { ... }
  time_series_compression:
    enabled: true
  relevance_scoring:
    enabled: true

quality:
  validate_accuracy: true
  min_recall: 0.90
  min_precision: 0.85

budgets:
  critical: 3000
  high: 2500
  medium: 2000
  low: 1500
  info: 1000

monitoring:
  track_all_requests: true
  metrics_storage: "data/optimization_metrics.jsonl"
  retention_days: 30
```

**Task 2: Feature Flags (2h)**

```python
# backend/app/config.py
class OptimizationConfig(Settings):
    # Master switches
    OPTIMIZATION_ENABLED: bool = True
    OPTIMIZATION_A_B_TEST_RATIO: float = 0.1
    OPTIMIZATION_FALLBACK_ENABLED: bool = True
    
    # Strategy flags
    ANOMALY_DETECTION_ENABLED: bool = True
    SMART_SAMPLING_ENABLED: bool = True
    TIME_SERIES_COMPRESSION_ENABLED: bool = True
    RELEVANCE_SCORING_ENABLED: bool = True
    
    # Feature flags
    DYNAMIC_BUDGETING_ENABLED: bool = True
    CONTEXT_AWARE_PROMPTS_ENABLED: bool = True
```

### Afternoon Session (4h)

**Task 3: Monitoring Setup (2h)**
- Prometheus metrics
- Alerting rules
- Dashboard queries

**Task 4: Runbook Creation (2h)**
```markdown
# Optimization Runbook

## How to Monitor
- Check dashboard for token savings
- Monitor accuracy metrics
- Watch for fallback events

## How to Tune Parameters
- Use POST /api/v1/optimization/tune
- Monitor A/B test results
- Adjust based on data

## How to Rollback
- Set OPTIMIZATION_ENABLED=false
- System reverts to baseline
- Investigate issue
```

---

## 📅 Day 20: Gradual Rollout

### Morning Session (4h)

**Task 1: Shadow Mode (2h)**

```python
# Shadow mode implementation
async def shadow_mode_triage(incident: Dict) -> Dict:
    """Run in parallel without affecting production."""
    
    # Baseline (production)
    baseline_triage = await generate_baseline_triage(incident)
    
    # Optimized (shadow)
    optimized_triage = await generate_optimized_triage(incident)
    
    # Compare and log
    log_comparison(baseline_triage, optimized_triage)
    
    # Use baseline
    return baseline_triage
```

**Task 2: Canary Release (2h)**

```python
# Canary release - 10% traffic
async def canary_release_triage(incident: Dict) -> Dict:
    """10% of requests use optimization."""
    
    if random.random() < 0.1:
        return await generate_optimized_triage(incident)
    else:
        return await generate_baseline_triage(incident)
```

### Afternoon Session (4h)

**Task 3: Gradual Rollout (2h)**
- Day 1: 25% optimization
- Day 2: 50% optimization
- Day 3: 100% optimization

**Task 4: Phase 6 Completion (2h)**
- Final report
- Metrics summary
- Lessons learned
- Next steps

---

## 📊 Sprint 4 Deliverables Summary

### Code (5 files)
1. `token_tracker.py`
2. `optimization.py` (API)
3. Dashboard components (3 files)

### Configuration (3 files)
1. `config/optimization.yaml`
2. `config/feature_flags.yaml`
3. Environment variables

### Documentation (10 files)
1. Day 16-20 summaries
2. Sprint 4 retrospective
3. Phase 6 final report
4. API documentation
5. Runbook

---

## ✅ Sprint 4 Success Criteria

- [ ] TokenTracker implemented
- [ ] All API endpoints functional
- [ ] Dashboard displays metrics
- [ ] Configuration production-ready
- [ ] Feature flags working
- [ ] Monitoring comprehensive
- [ ] Runbook complete
- [ ] Shadow mode successful
- [ ] Canary release stable
- [ ] Gradual rollout complete
- [ ] All metrics within targets
- [ ] Phase 6 complete

---

## 🎯 Phase 6 Final Success Criteria

### Must Achieve
- [x] Sprint 1 complete
- [x] Sprint 2 complete
- [x] Sprint 3 complete
- [ ] Sprint 4 complete
- [ ] Token reduction >60%
- [ ] Finding recall ≥90%
- [ ] Finding precision ≥85%
- [ ] Processing time ≤3000ms
- [ ] Production rollout successful
- [ ] All documentation complete

### Should Achieve
- [ ] Token reduction >70%
- [ ] Finding recall ≥92%
- [ ] Finding precision ≥88%
- [ ] Processing time <2500ms

---

**Document Version**: 1.0  
**Status**: ✅ READY FOR EXECUTION
