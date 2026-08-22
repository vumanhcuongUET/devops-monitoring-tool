# Claude Code Skill: observability - Observability Analysis

## Overview

**Skill Name**: `observability`
**Purpose**: Analyze metrics, traces, and dashboards for observability insights
**Trigger**: User requests related to metrics, traces, dashboards, Prometheus, Grafana
**Version**: 1.0

---

## Skill Definition

```yaml
name: observability
description: Observability analysis assistant for metrics, traces, dashboards, and anomaly detection
triggers:
  - "metrics"
  - "prometheus"
  - "observability"
  - "trace"
  - "tracing"
  - "jaeger"
  - "opentelemetry"
  - "dashboard"
  - "grafana"
  - "anomaly"
  - "slo"
  - "sli"
examples:
  - "Analyze Prometheus metrics for anomalies"
  - "Trace slow requests in distributed system"
  - "Audit Grafana dashboards"
  - "Check SLO compliance"
```

---

## Capabilities

### 1. Metrics Analysis

#### Prometheus Query Analysis
```yaml
# Input: Query pattern, time range
command: "Show me HTTP error rates in the last hour"

promql_queries:
  - sum(rate(http_requests_total{status=~"5.."}[5m]))
  - sum(rate(http_requests_total[5m]))

analysis:
  query: |
    # Calculate error rate percentage
    (
      sum(rate(http_requests_total{status=~"5.."}[5m])) /
      sum(rate(http_requests_total[5m]))
    ) * 100
  
  results:
    current_error_rate: 0.8%
    baseline: 0.3%
    status: ⚠️ Elevated (+166% from baseline)
    
  correlations:
    - High error rate coincides with:
      - Deployment at 14:30 UTC
      - Memory spike in backend-3 pod
      - Database connection pool exhaustion
```

#### Latency Percentile Analysis
```yaml
# Input: Service name, percentiles
command: "Show p50, p95, p99 latencies for all services"

percentiles:
  p50: "Median - 50% of requests"
  p95: "95th percentile - SLO target"
  p99: "99th percentile - tail latency"
  
promql:
  p50: histogram_quantile(0.5, rate(http_request_duration_seconds_bucket[5m]))
  p95: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
  p99: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

output:
  Service: backend-api
    p50: 45ms
    p95: 234ms ⚠️ SLO target: <100ms
    p99: 1.2s
    Status: VIOLATION
    
  Service: frontend
    p50: 12ms
    p95: 45ms
    p99: 120ms
    Status: OK
```

#### Resource Utilization
```yaml
# Input: Deployment, namespace
command: "Analyze resource utilization for backend deployment"

metrics:
  cpu_utilization:
    query: sum(rate(container_cpu_usage_seconds_total{namespace="default",pod=~"backend-.*"}[5m])) / sum(kube_pod_container_resource_requests{namespace="default",pod=~"backend-.*",resource="cpu"})
    current: 78%
    status: Normal
    
  memory_utilization:
    query: sum(container_memory_working_set_bytes{namespace="default",pod=~"backend-.*"}) / sum(kube_pod_container_resource_limits{namespace="default",pod=~"backend-.*",resource="memory"})
    current: 92%
    status: ⚠️ Near limit
    
  recommendations:
    - Increase memory limits (512Mi → 1Gi)
    - Consider HPA based on memory metrics
```

---

### 2. Distributed Tracing

#### Trace Analysis
```yaml
# Input: Trace ID or service name
command: "Analyze trace for slow API request"

trace_id: "abc123xyz789"

analysis:
  total_duration: 1.8s
  span_count: 23
  
  critical_path:
    1. ingress-nginx: 50ms
    2. api-gateway: 75ms
    3. backend-service: 1.2s ← BOTTLENECK
    4. elasticsearch: 350ms
    5. database: 180ms
    
  span_breakdown:
    backend-service:
      - request_validation: 15ms
      - authentication: 45ms
      - business_logic: 850ms ← SLOW
      - response_format: 90ms
      
  findings:
    - Business logic taking 850ms (47% of total)
    - Database query called synchronously (could parallelize)
    - No caching for frequently accessed data
    
  recommendations:
    - Implement Redis cache for business logic
    - Parallelize independent database queries
    - Add caching layer for Elasticsearch results
```

#### Service Dependency Map
```yaml
# Input: Service name, time range
command: "Show service dependencies and their health"

service: backend-api

dependencies:
  upstream:
    - service: elasticsearch
      avg_latency: 250ms
      error_rate: 0.1%
      status: ✅ Healthy
      
    - service: postgres
      avg_latency: 180ms
      error_rate: 0.3%
      status: ✅ Healthy
      
  downstream:
    - service: frontend
      calls_per_minute: 1250
      status: ✅ Healthy
      
    - service: mobile-app
      calls_per_minute: 450
      status: ⚠️ High latency
```

---

### 3. Dashboard Auditing

#### Coverage Analysis
```yaml
# Input: Project/namespace
command: "Audit dashboard coverage for all services"

services_inventory:
  - backend-api
  - frontend
  - worker
  - api-gateway

dashboard_coverage:
  backend-api:
    dashboards: 3
      - API Overview ✅
      - SLO Dashboard ✅
      - Resource Usage ✅
    coverage: Complete
    
  frontend:
    dashboards: 1
      - Page Load Times ✅
    missing:
      - Error Rate Dashboard
      - Resource Usage
    coverage: Partial ⚠️
    
  worker:
    dashboards: 0
    missing:
      - Job Processing Dashboard
      - Queue Depth Dashboard
      - Error Dashboard
    coverage: None ❌
```

#### Dashboard Health Check
```yaml
# Input: Dashboard name or folder
command: "Check health of all dashboards"

health_checks:
  connectivity:
    - Verify Prometheus data source connection
    - Verify Elasticsearch data source connection
    
  query_validity:
    - Check for broken queries
    - Identify deprecated metrics
    - Detect syntax errors
    
  freshness:
    - Last successful query time
    - Data recency check
    
  duplicates:
    - Find duplicate dashboards
    - Identify overlapping panels
    
output:
  dashboard_health:
    total: 15
    healthy: 12
    warnings: 2
    errors: 1
    
  issues:
    - ❌ "Backend Latency" - Prometheus connection failed
    - ⚠️ "API Overview" - Using deprecated metric
    - ⚠️ Duplicate: "Service Errors" exists in 2 folders
```

---

### 4. Anomaly Detection

#### Statistical Analysis
```yaml
# Input: Metric name, time window
command: "Detect anomalies in request rate metric"

metric: http_requests_total
window: 24h
sensitivity: medium

methods:
  z_score:
    threshold: 3
    anomalies_found: 2
    
  iqr_method:
    multiplier: 1.5
    anomalies_found: 3
    
  seasonal_decomposition:
    pattern: Daily
    anomalies_found: 1
    
results:
  anomalies:
    - time: "2026-08-22 14:30:00"
      value: 1250 req/s
      baseline: 450 req/s
      deviation: +178%
      severity: High
      likely_cause: Deployment surge
      
    - time: "2026-08-22 03:15:00"
      value: 50 req/s
      baseline: 380 req/s
      deviation: -87%
      severity: Medium
      likely_cause: Nightly maintenance
      
  correlated_events:
    - Deployment: backend v2.3.1 at 14:28
    - Scaling event: backend pods 2→8 at 14:32
    - Alert: HighMemory triggered at 14:35
```

#### Pattern Recognition
```yaml
# Input: Multiple metrics
command: "Find unusual patterns across all metrics"

pattern_types:
  sudden_spikes:
    - metric: error_rate
      time: 14:30-14:45
      magnitude: +400%
      
  sudden_drops:
    - metric: request_rate
      time: 03:00-03:30
      magnitude: -85%
      
  slow_drifts:
    - metric: memory_usage
      period: 7 days
      trend: +15% per day
      status: ⚠️ Memory leak suspected
      
  periodic:
    - metric: cpu_usage
      pattern: Daily cycle
      peak: 15:00 UTC (85%)
      trough: 03:00 UTC (20%)
```

---

### 5. SLO/SI Analysis

#### SLO Compliance
```yaml
# Input: SLO config, time range
command: "Check SLO compliance for all services"

slo_configs:
  backend-api:
    availability_target: 99.9%
    latency_target: p95 < 100ms
    
compliance:
  availability:
    7d rolling: 99.85%
    status: ✅ Within target
    error_budget_remaining: 58%
    
  latency:
    7d rolling p95: 145ms
    status: ❌ VIOLATION
    gap: 45ms above target
    breach_probability: 78%
    
recommendations:
  - Optimize slow endpoints (/api/v1/analyze: 850ms p95)
  - Add caching for frequently accessed data
  - Consider increasing SLO latency target to 150ms
```

#### Error Budget Calculation
```yaml
# Input: SLO, time window
command: "Calculate error budget for frontend availability"

slo:
  target: 99.9% availability
  window: 30d rolling

calculation:
  total_requests: 125,000,000
  allowed_errors: 125,000 (0.1%)
  actual_errors: 45,000
  
  error_budget:
    remaining: 64%
    burned: 36%
    burn_rate: 1.2% per day
    
  projection:
    days_until_exhausted: 30
    status: ⚠️ On track to stay within budget
```

---

## Integration with Claude Code

### File Context Awareness

The skill should:
1. **Locate Prometheus queries** in backend code
2. **Find Grafana dashboard definitions** in project
3. **Read SLO configs** from backend/app/alerting/
4. **Access trace data** from Jaeger/OTLP endpoint
5. **Understand service topology** from K8s manifests

### Tool Usage

```python
# Tools the skill should use:
- Bash: promtool, kubectl commands
- Read: Dashboard JSONs, SLO configs, manifest files
- WebFetch: Prometheus API, Grafana API, Jaeger API
- dataviz: Generate metrics charts and visualizations
```

---

## Examples

### Example 1: Analyze Performance Anomaly
```
User: Why did response times spike at 2 PM today?

Claude:
I'll analyze the metrics around 2 PM to identify the cause.

[Queries Prometheus and traces]

Findings:
- 14:30 UTC: p95 latency spiked from 85ms → 450ms (+429%)
- 14:28 UTC: New deployment (backend v2.3.1)
- 14:32 UTC: HPA scaled pods from 2 → 8
- 14:35 UTC: Memory pressure alerts on all pods

Root Cause: New deployment introduced memory leak, causing OOM and pod restarts.

Recommendation: Rollback to v2.3.0 or hotfix the memory issue.
```

### Example 2: Trace Bottleneck Analysis
```
User: The checkout API is slow, can you trace it?

Claude:
I'll trace the checkout request to find the bottleneck.

[Analyzes traces from Jaeger]

Checkout Request Flow (Total: 2.3s):
1. API Gateway: 50ms (2%)
2. Backend Service: 850ms (37%) ← SLOW
   - User lookup: 350ms
   - Cart fetch: 180ms
   - Payment processing: 320ms ← SLOWEST
3. Inventory Service: 180ms (8%)
4. Payment Gateway: 950ms (41%) ← EXTERNAL SLOW
5. Database: 270ms (12%)

Bottlenecks:
- Payment Gateway API: 950ms (consider caching or retry)
- User lookup query: 350ms (add database index)

Recommendations:
- Add timeout and circuit breaker for Payment Gateway
- Cache user lookup results (5min TTL)
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-22 | Initial skill definition |

---

## Dependencies

### Required Tools
- `promtool` - PromQL tool (optional)
- `jaeger-cli` - Jaeger CLI (optional)

### Python Libraries
```python
import requests  # Prometheus, Grafana, Jaeger APIs
import json
from datetime import datetime, timedelta
import numpy as np  # Statistical analysis
```

---

## Related Skills

- **`perf`** - For detailed performance analysis and profiling
- **`k8s`** - For Kubernetes-level observability
- **`dataviz`** - For generating metrics visualizations

---

**Skill Type**: Analysis/Reporting
**Confidence**: High
**Production Ready**: Yes
