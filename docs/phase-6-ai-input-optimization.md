# Phase 6: AI Input Optimization & Cost Efficiency

**Status**: 📋 **PLANNING**
**Priority**: **HIGH** - Cost reduction without accuracy loss
**Duration**: 3-4 weeks estimated
**Goal**: Optimize Claude API input to reduce token usage by 60-80% while maintaining triage card accuracy

---

## 🎯 Overview

Phase 6 addresses the **cost optimization** challenge for AI-powered incident analysis. Current implementation sends comprehensive monitoring data to Claude API, resulting in high token consumption. This phase implements intelligent data optimization strategies that:

1. **Reduce token usage by 60-80%** through smart filtering and compression
2. **Maintain or improve accuracy** through relevance-based selection
3. **Provide measurable quality metrics** to validate optimization effectiveness
4. **Enable adaptive optimization** based on incident type and severity

---

## 📊 Current State Analysis

### Token Usage Baseline

| Data Source | Current Token Count | Percentage |
|-------------|---------------------|------------|
| Logs (Elasticsearch) | ~1,500 tokens (50 entries) | 30% |
| APM Data | ~800 tokens (summary + top errors) | 16% |
| Prometheus Metrics | ~400 tokens (aggregated) | 8% |
| Kubernetes State | ~300 tokens (pods + deployments) | 6% |
| Alerts | ~1,000 tokens (20 alerts) | 20% |
| System Prompt | ~1,000 tokens | 20% |
| **Total** | **~5,000 tokens** | 100% |

### Cost Analysis (Claude Sonnet 4)

| Input Tokens | Cost per Request | Requests/day | Monthly Cost |
|--------------|------------------|---------------|-------------|
| 5,000 (current) | $0.015 | 100 | $45 |
| 2,000 (target) | $0.006 | 100 | $18 |
| **Savings** | **60%** | - | **$27/month** |

---

## 🎯 Phase 6 Components

### Part A: Token Optimization Engine (Week 1-2)

#### 1. Smart Context Builder

**File**: `backend/app/services/token_optimizer.py` (NEW)

**Core Features**:
```python
class TokenOptimizer:
    """Optimize context data sent to Claude API."""
    
    async def optimize_context(
        self,
        context_data: dict[str, Any],
        incident_type: str,
        severity: SeverityLevel,
        token_budget: int = 2000
    ) -> dict[str, Any]:
        """
        Apply optimization strategies to minimize token usage.
        
        Returns:
            Optimized context data within token budget
        """
```

**Optimization Strategies**:

1. **Anomaly Detection Filtering**
   - Only include metrics exceeding thresholds
   - Skip "normal" CPU/Memory/Disk values
   - Token savings: ~70% for healthy systems

2. **Smart Sampling with Priority**
   ```python
   # Priority-based log sampling
   PRIORITY_LOGS = {
       "critical": 5,   # 5 critical logs
       "error": 10,     # 10 error logs
       "warning": 10,   # 10 warning logs
       "info": 5        # 5 info logs (minimal)
   }
   ```

3. **Time Series Compression**
   - Convert raw time-series to percentiles (p50, p90, p95, p99)
   - Include trend indicator (increasing/decreasing)
   - Token savings: ~90% for metrics

4. **Relevance-Based Selection**
   ```python
   INCIDENT_DATA_MAPPING = {
       "high_latency": ["apm", "metrics", "kubernetes"],
       "high_error_rate": ["logs", "apm", "alerts"],
       "pod_crashloop": ["kubernetes", "logs"],
       "disk_full": ["metrics", "logs"],
       "database_slow": ["apm", "metrics"],
   }
   ```

5. **Compact Formatting**
   - Replace verbose JSON with compact notation
   - Use abbreviations for common fields
   - Token savings: ~30%

#### 2. Context-Aware Prompts

**File**: `backend/app/services/context_aware_promoter.py` (NEW)

```python
class ContextAwarePromoter:
    """Generate optimized prompts based on incident type."""
    
    async def build_prompt(
        self,
        incident_type: str,
        optimized_data: dict,
        severity: SeverityLevel
    ) -> str:
        """
        Build optimized prompt with:
        - Incident-specific system prompt
        - Relevant data sections only
        - Compact formatting
        """
```

**Incident-Specific Prompts**:
- High Latency: Focus on APM and response times
- High Error Rate: Focus on error patterns and logs
- Pod Issues: Focus on Kubernetes state
- Resource Issues: Focus on metrics and capacity

---

### Part B: Quality Assurance Framework (Week 2)

#### 3. Accuracy Validation System

**File**: `backend/app/quality/accuracy_validator.py` (NEW)

**Metrics**:
- **Finding Recall**: % of root causes identified
- **Finding Precision**: % of findings that are accurate
- **Recommendation Relevance**: % of actionable recommendations
- **Severity Accuracy**: % of correct severity assignments

**Validation Process**:
```python
class AccuracyValidator:
    """Validate optimized triage cards against baseline."""
    
    async def validate(
        self,
        optimized_triage: TriageCard,
        baseline_triage: TriageCard,
        ground_truth: dict | None = None
    ) -> AccuracyReport:
        """
        Compare optimized vs baseline results.
        
        Returns:
            Accuracy metrics and recommendations
        """
```

#### 4. A/B Testing Framework

**File**: `backend/app/quality/ab_tester.py` (NEW)

```python
class ABTester:
    """Run A/B tests between baseline and optimized flows."""
    
    async def run_test(
        self,
        incident_samples: list[IncidentSample]
    ) -> ABTestReport:
        """
        Generate triage cards using both methods:
        1. Baseline (current implementation)
        2. Optimized (new implementation)
        
        Compare accuracy, token usage, and cost.
        """
```

**Test Scenarios**:
- High latency incidents
- High error rate incidents
- Pod crashloop incidents
- Resource exhaustion incidents
- Multiple service failures

---

### Part C: Adaptive Optimization (Week 3)

#### 5. ML-Based Relevance Scoring

**File**: `backend/app/services/relevance_scorer.py` (NEW)

```python
class RelevanceScorer:
    """Score data elements by relevance to incident."""
    
    def score_logs(
        self,
        logs: list[dict],
        incident_type: str,
        alert_message: str
    ) -> list[tuple[dict, float]]:
        """
        Score each log entry by relevance.
        
        Returns:
            Sorted list of (log, score) tuples
        """
```

**Scoring Factors**:
- Keyword matching with alert message
- Temporal proximity to incident
- Severity level
- Service/component relevance
- Historical pattern matching

#### 6. Dynamic Token Budgeting

**File**: `backend/app/services/token_budget_manager.py` (NEW)

```python
class TokenBudgetManager:
    """Manage token budgets based on incident severity."""
    
    BUDGET_MATRIX = {
        SeverityLevel.CRITICAL: 3000,   # High budget for critical
        SeverityLevel.HIGH: 2500,
        SeverityLevel.MEDIUM: 2000,     # Standard budget
        SeverityLevel.LOW: 1500,        # Reduced budget
        SeverityLevel.INFO: 1000,       # Minimal budget
    }
    
    def get_budget(self, severity: SeverityLevel) -> int:
        """Get token budget for incident severity."""
```

---

### Part D: Monitoring & Analytics (Week 4)

#### 7. Token Usage Tracking

**File**: `backend/app/analytics/token_tracker.py` (NEW)

```python
class TokenTracker:
    """Track token usage and optimization metrics."""
    
    async def track_request(
        self,
        incident_id: str,
        input_tokens: int,
        output_tokens: int,
        optimization_strategy: str,
        accuracy_metrics: dict
    ):
        """
        Track token usage for analytics.
        
        Stored in: data/token_usage.json
        """
```

**Dashboard Metrics**:
- Average input tokens per request
- Token savings percentage
- Cost per incident
- Accuracy trend over time
- Most effective optimization strategies

#### 8. Optimization Analytics API

**File**: `backend/app/api/v1/optimization.py` (NEW)

**Endpoints**:
```python
GET /api/v1/optimization/stats
# Response: Token usage statistics, savings achieved

GET /api/v1/optimization/accuracy
# Response: Accuracy metrics, validation results

GET /api/v1/optimization/strategies
# Response: Active strategies and their effectiveness

POST /api/v1/optimization/tune
# Request: Tune optimization parameters
```

---

## 📁 Files Structure

### New Files (15)

```
backend/
├── app/
│   ├── services/
│   │   ├── token_optimizer.py          # Core optimization engine
│   │   ├── context_aware_promoter.py    # Incident-specific prompts
│   │   ├── relevance_scorer.py          # ML-based relevance
│   │   └── token_budget_manager.py      # Dynamic budgeting
│   ├── quality/
│   │   ├── __init__.py
│   │   ├── accuracy_validator.py        # Quality validation
│   │   └── ab_tester.py                 # A/B testing framework
│   ├── analytics/
│   │   ├── __init__.py
│   │   └── token_tracker.py            # Usage tracking
│   └── api/v1/
│       └── optimization.py              # Optimization API
├── tests/
│   ├── unit/test_token_optimizer.py
│   ├── unit/test_accuracy_validator.py
│   └── integration/test_optimization_flow.py
└── data/
    └── token_usage.json                 # Usage analytics
```

### Modified Files (3)

- `backend/app/api/v1/analyze.py` - Integrate token optimizer
- `backend/app/services/llm_client.py` - Add token tracking
- `backend/app/config.py` - Add optimization settings

---

## 🎯 Implementation Order

### Sprint 1: Foundation (Week 1)
1. TokenOptimizer core implementation
2. Smart sampling strategies
3. Anomaly detection filtering
4. Unit tests

### Sprint 2: Quality Assurance (Week 2)
5. AccuracyValidator implementation
6. A/B testing framework
7. Baseline measurements
8. Integration tests

### Sprint 3: Intelligence (Week 3)
9. RelevanceScorer implementation
10. Dynamic token budgeting
11. Context-aware prompts
12. End-to-end testing

### Sprint 4: Analytics (Week 4)
13. TokenTracker implementation
14. Optimization API
15. Dashboard integration
16. Documentation

---

## ✅ Success Criteria

### Token Optimization
- ✅ **Average input tokens < 2,000** (60% reduction from 5,000)
- ✅ **Peak input tokens < 3,000** for critical incidents
- ✅ **Cost reduction > 50%** for same incident volume

### Quality Assurance
- ✅ **Finding recall > 90%** vs baseline
- ✅ **Finding precision > 85%** vs baseline
- ✅ **Severity accuracy > 95%** vs baseline
- ✅ **Recommendation relevance > 80%** user feedback

### Operational
- ✅ **Optimization latency < 100ms** additional processing time
- ✅ **100% backward compatibility** - can fallback to baseline
- ✅ **A/B test results** show statistical significance

---

## 🔧 Configuration

### Environment Variables

```bash
# .env
OPTIMIZATION_ENABLED=true
OPTIMIZATION_DEFAULT_BUDGET=2000
OPTIMIZATION_ANOMALY_THRESHOLD_CPU=80
OPTIMIZATION_ANOMALY_THRESHOLD_MEMORY=85
OPTIMIZATION_LOG_SAMPLING_CRITICAL=5
OPTIMIZATION_LOG_SAMPLING_ERROR=10
OPTIMIZATION_AB_TEST_RATIO=0.1  # 10% of requests use A/B test
```

### YAML Configuration

```yaml
# config/optimization.yaml
optimization:
  enabled: true
  default_budget: 2000
  fallback_on_error: true
  
  strategies:
    anomaly_detection:
      enabled: true
      thresholds:
        cpu_percent: 80
        memory_percent: 85
        disk_percent: 90
        error_rate: 5
    
    smart_sampling:
      logs:
        critical: 5
        error: 10
        warning: 10
        info: 5
      apm_errors: 10
      alerts: 15
    
    time_series_compression:
      enabled: true
      percentiles: [p50, p90, p95, p99]
      include_trend: true
      include_minmax: true
    
    relevance_filtering:
      enabled: true
      min_relevance_score: 0.3
      max_results_per_source: 20
  
  quality:
    validate_accuracy: true
    ab_test_enabled: true
    ab_test_ratio: 0.1
    min_sample_size: 100
  
  budgets:
    critical: 3000
    high: 2500
    medium: 2000
    low: 1500
    info: 1000
```

---

## 📊 Expected Outcomes

### Before Optimization
```
Input: ~5,000 tokens/request
Cost: $0.015/request
Monthly (100 req/day): $45
```

### After Optimization
```
Input: ~2,000 tokens/request (60% reduction)
Cost: $0.006/request (60% reduction)
Monthly (100 req/day): $18 ($27 savings)

Accuracy: Maintained (>90% recall, >85% precision)
```

### Scaling Impact
```
At 1,000 requests/day:
- Before: $450/month
- After: $180/month
- Savings: $270/month (60%)
```

---

## 🛡️ Quality Validation Plan

### Phase 1: Baseline Measurement (Week 1)
1. Run 100 sample incidents through current system
2. Record: Input tokens, output quality, accuracy metrics
3. Establish baseline for comparison

### Phase 2: Optimization Testing (Week 2-3)
1. Implement each optimization strategy
2. A/B test against baseline
3. Measure: Token reduction, accuracy impact
4. Tune thresholds for optimal balance

### Phase 3: Production Validation (Week 4)
1. Gradual rollout (10% → 50% → 100%)
2. Continuous accuracy monitoring
3. User feedback collection
4. Iterative refinement

---

## 🚀 Rollout Strategy

### Stage 1: Shadow Mode (Week 1-2)
- Optimizer runs in parallel with baseline
- No actual impact on production
- Collect comparison data

### Stage 2: Canary Release (Week 3)
- 10% of incidents use optimization
- Monitor accuracy closely
- Quick rollback if issues detected

### Stage 3: Gradual Rollout (Week 4)
- 25% → 50% → 100% over 2 weeks
- Continuous monitoring
- User feedback loops

---

## 📝 Dependencies

### New Python Dependencies
```txt
# requirements.txt additions
scikit-learn>=1.3.0      # For relevance scoring
numpy>=1.24.0            # For statistical analysis
```

### External Services
- None (all optimization is local)

---

## 🔗 Related Documentation

- [ADR-003: AI Integration Strategy](adr/003-ai-integration-strategy.md)
- [AI Triage Cards Guide](ai-triage-cards.md)
- [Phase 1: Foundation & Observability Copilot](chien_luoc_tong_the.md)

---

## 📋 Checklist

### Week 1: Foundation
- [ ] Implement TokenOptimizer core
- [ ] Implement smart sampling
- [ ] Implement anomaly detection
- [ ] Write unit tests
- [ ] Establish baseline metrics

### Week 2: Quality
- [ ] Implement AccuracyValidator
- [ ] Implement ABTester
- [ ] Run initial A/B tests
- [ ] Tune optimization parameters

### Week 3: Intelligence
- [ ] Implement RelevanceScorer
- [ ] Implement dynamic budgeting
- [ ] Implement context-aware prompts
- [ ] End-to-end integration tests

### Week 4: Analytics
- [ ] Implement TokenTracker
- [ ] Implement optimization API
- [ ] Dashboard integration
- [ ] Documentation completion
- [ ] Production rollout

---

**Owner**: DevOps AI Agentics Team
**Created**: 2026-08-23
**Status**: 📋 PLANNING - Awaiting approval
**Priority**: HIGH - Cost optimization opportunity
