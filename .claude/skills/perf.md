# Claude Code Skill: perf - Performance Analysis

## Overview

**Skill Name**: `perf`
**Purpose**: Performance analysis, load testing, and bottleneck detection
**Trigger**: User requests related to performance, metrics, load testing, profiling
**Version**: 1.0

---

## Skill Definition

```yaml
name: perf
description: Performance analysis assistant for metrics, load testing, profiling, and bottleneck detection
triggers:
  - "performance"
  - "perf"
  - "latency"
  - "throughput"
  - "bottleneck"
  - "slow"
  - "load test"
  - "locust"
  - "k6"
  - "profiling"
  - "metrics"
  - "prometheus"
  - "flame graph"
  - "p95"
  - "p99"
examples:
  - "Analyze performance metrics"
  - "Parse Locust load test results"
  - "Identify bottlenecks"
  - "Generate flame graph"
  - "Check response times"
```

---

## Capabilities

### 1. Prometheus Metrics Analysis

#### Query & Analysis
```yaml
# Input: Prometheus endpoint, query, time range
command: "Analyze HTTP request rate over last hour"

promql_query:
  rate(http_requests_total[5m])

analysis:
  - Current rate: 245 req/s
  - Peak rate: 512 req/s (14:30 UTC)
  - Trend: Increasing
  - Anomaly: +40% spike detected
  
visualizations:
  - Time series chart
  - Histogram distribution
  - Heatmap by endpoint
```

#### Latency Analysis
```yaml
# Input: Service name, percentiles
command: "Show p50, p95, p99 latencies for backend API"

queries:
  - histogram_quantile(0.5, rate(http_request_duration_seconds_bucket[5m]))
  - histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
  - histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

results:
  p50: 45ms
  p95: 234ms  ⚠️ Above SLO
  p99: 1.2s   ⚠️ Critical
  
slo_status:
  target: p95 < 100ms
  current: 234ms
  status: ❌ VIOLATION
```

#### Error Rate Analysis
```yaml
# Input: Service, time range
command: "Check error rates for all services"

query:
  sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))

output:
  backend: 0.8% (2% above baseline)
  frontend: 0.1% ✅
  api-gateway: 0.3% ✅
  
correlation:
  High error rate correlates with:
  - Increased latency (backend)
  - Memory pressure (backend-5 pod)
```

---

### 2. Load Test Results Analysis

#### Locust Results
```yaml
# Input: Locust HTML report or stats.json
command: "Analyze Locust load test results from locust-report.html"

parsed_metrics:
  - Total requests: 125,000
  - Failures: 234 (0.19%)
  - RPS: 450 (average)
  - Median response time: 85ms
  - 95th percentile: 450ms
  
analysis:
  ✅ PASS: Throughput (target: 400 RPS)
  ❌ FAIL: p95 latency (target: <200ms, actual: 450ms)
  ✅ PASS: Error rate (target: <1%, actual: 0.19%)
  
bottlenecks:
  1. /api/v1/analyze - 850ms p95 (LLM processing)
  2. /api/v1/overview - 320ms p95 (ES aggregation)
  
recommendations:
  - Cache /api/v1/overview results (30s TTL)
  - Optimize LLM prompt or increase timeout
```

#### k6 Results
```yaml
# Input: k6 JSON output
command: "Parse k6 load test summary"

metrics:
  - http_req_duration: p95=234ms, p99=1.2s
  - http_req_failed: 0.3%
  - iterations: 50,000
  - vus: 100 virtual users
  
checks:
  ✅ 95% response under 500ms
  ✅ Error rate below 1%
  ❌ p95 latency under 100ms (failed)
  
threshold_analysis:
  latency_threshold: "95% under 100ms"
  actual: "95% at 234ms"
  guidance: "Investigate /api/v1/analyze endpoint"
```

---

### 3. Bottleneck Detection

#### Database Query Analysis
```yaml
# Input: Application logs, slow query log
command: "Identify slow database queries"

sources:
  - PostgreSQL slow query log
  - Application query logs
  - Prometheus query metrics

findings:
  1. SELECT * FROM large_table - 8.5s (index missing)
  2. JOIN users/orders without WHERE - 2.3s (N+1 query)
  3. Analytics aggregation - 5.2s (full table scan)

recommendations:
  - Add index on large_table.created_at
  - Implement pagination for users list
  - Create materialized view for analytics
```

#### Memory Profiling
```yaml
# Input: Python memory profiler output
command: "Analyze memory profile and identify leaks"

tools:
  - memory_profiler
  - tracemalloc
  - heapy (Python heap analysis)

analysis:
  Total allocations: 1.2GB
  Top allocators:
    1. pandas.DataFrame: 450MB
    2. JSON response cache: 280MB
    3. Query result cache: 150MB
  
  Memory leaks detected:
    - Response cache not expiring (growth: +50MB/hour)
    - Connection pool not releasing (growth: +10MB/hour)
```

#### CPU Profiling
```yaml
# Input: Python cProfile output
command: "Profile CPU usage and find hotspots"

tools:
  - cProfile
  - py-spy
  - snakeviz

output:
  Function calls: 125,000
  Total time: 45.3s
  
  Hotspots:
    1. elasticsearch_client.query: 12.5s (27%)
    2. json.loads: 8.2s (18%)
    3. datetime parsing: 3.1s (7%)
  
  recommendations:
    - Batch ES queries
    - Use orjson for JSON parsing
    - Cache datetime objects
```

---

### 4. Flame Graph Generation

#### Python Flame Graph
```yaml
# Input: Profiling data, output format
command: "Generate flame graph from profiling data"

tools:
  - flameprof
  - py-spy
  - viztracer

output:
  Generates interactive SVG flame graph showing:
  - Function call hierarchy
  - Time spent per function
  - Call paths
  
visualization:
  Width = Time spent
  Color = Temperature (red = hot)
  Height = Call stack depth
```

#### Trace Analysis
```yaml
# Input: Distributed trace data
command: "Analyze trace from Jaeger"

trace_id: "abc123xyz789"

analysis:
  Total duration: 1.2s
  Span count: 15
  
  Critical path:
    ingress (50ms) → api-gateway (30ms) → 
    backend (800ms) → elasticsearch (250ms) →
    backend (150ms) → response (50ms)
  
  Bottlenecks:
    1. backend processing: 800ms (67% of total)
       - LLM API call: 650ms
       - Data aggregation: 100ms
       - Response formatting: 50ms
    
    2. Elasticsearch query: 250ms (21%)
       - Complex aggregation query
       - Large result set
```

---

### 5. Performance Comparison

#### Baseline Comparison
```yaml
# Input: Current test results, baseline file
command: "Compare current performance with baseline"

metrics:
  Metric | Baseline | Current | Change | Status
  -------|----------|---------|--------|--------
  RPS | 400 | 450 | +12.5% | ✅
  p50 | 50ms | 55ms | +10% | ⚠️
  p95 | 200ms | 234ms | +17% | ❌
  p99 | 500ms | 1200ms | +140% | ❌
  Errors | 0.5% | 0.8% | +60% | ❌

summary:
  Regression detected in p95 and p99 latencies
  Error rate increased by 60%
  Recommendation: Investigate recent deployment
```

#### A/B Test Analysis
```yaml
# Input: Two load test results
command: "Compare performance between version A and B"

comparison:
  Version | RPS | p95 | Errors | Winner
  --------|-----|-----|--------|--------
  A (v1.2) | 420 | 180ms | 0.3% | ✅
  B (v1.3) | 450 | 234ms | 0.8% | ❌

conclusion:
  Version B has higher throughput (7% gain)
  But worse latency (30% regression) and errors
  
  Recommendation: Stick with version A, investigate v1.3 degradation
```

---

### 6. Performance Recommendations

#### Optimization Suggestions
```yaml
# Input: Performance analysis results
command: "Generate optimization recommendations"

categories:
  
  Caching:
    - Add Redis cache for /api/v1/overview (30s TTL)
    - Cache Prometheus metrics (60s TTL)
    - Implement response caching for LLM results
    
  Database:
    - Add connection pooling (max 20 connections)
    - Implement prepared statement caching
    - Add composite indexes for common queries
    
  Async Operations:
    - Parallelize independent API calls
    - Use async/await for I/O operations
    - Implement background job queue
    
  Resource Limits:
    - Increase backend memory limits (512Mi → 1Gi)
    - Add CPU limits for monitoring agents
    - Configure HPA based on memory metrics
```

---

## Integration with Claude Code

### File Context Awareness

The skill should:
1. **Locate load test results** (locust-report.html, stats.json)
2. **Find Prometheus configuration** in project
3. **Read profiling data** (.prof files, traces)
4. **Understand application metrics** from codebase
5. **Reference performance baselines** if defined

### Tool Usage

```python
# Tools the skill should use:
- Bash: k6, locust, flameprof commands
- Read: Test reports, profiling data, traces
- WebFetch: Prometheus API if endpoint available
- dataviz: Generate performance charts
```

---

## Performance Baselines

### SLO Templates
```yaml
# Standard SLO definitions
common_slos:
  api_latency:
    target: p95 < 100ms
    warning: p95 < 200ms
    critical: p95 < 500ms
    
  availability:
    target: 99.9%
    warning: 99.5%
    critical: 99.0%
    
  error_rate:
    target: 0.1%
    warning: 0.5%
    critical: 1.0%
```

### Benchmark Targets
```yaml
# Recommended benchmarks per tier
tier_1_services:
  rps: 1000
  p95: <50ms
  p99: <200ms
  
tier_2_services:
  rps: 500
  p95: <100ms
  p99: <500ms
  
tier_3_services:
  rps: 100
  p95: <200ms
  p99: <1000ms
```

---

## Examples

### Example 1: Analyze Prometheus Metrics
```
User: Show me the p95 latency for all endpoints in the last hour

Claude:
I'll query Prometheus for p95 latencies across all endpoints.

[Queries Prometheus]
GET /api/v1/overview - p95: 85ms ✅
GET /api/v1/analyze - p95: 1.2s ❌
GET /api/v1/actions - p95: 45ms ✅

The /api/v1/analyze endpoint is significantly slower. This involves LLM processing.
Consider caching results or optimizing the prompt.
```

### Example 2: Parse Load Test
```
User: Analyze the Locust report and tell me if we met our targets

Claude:
I'll analyze locust-report.html for performance metrics.

[Parses Locust HTML]
Target: 400 RPS with p95 < 200ms

Results:
- Throughput: 450 RPS ✅ (12.5% above target)
- p95 latency: 234ms ❌ (17% above target)
- Error rate: 0.19% ✅ (well below 1% target)

Status: PARTIAL - Need to optimize for latency target
```

### Example 3: Bottleneck Detection
```
User: What's causing the slowdown in the overview endpoint?

Claude:
I'll analyze the overview endpoint performance.

[Profiles and traces data]
Bottlenecks identified:
1. Elasticsearch aggregation: 180ms (67% of total time)
2. Serial API calls: 45ms (17%)
3. JSON serialization: 30ms (11%)

Recommendations:
- Add parallel execution for service calls
- Cache ES query results (30s TTL)
- Use orjson for faster serialization
```

---

## Error Handling

### Common Errors
```yaml
prometheus_unreachable:
  message: "Cannot connect to Prometheus"
  solution: "Check PROMETHEUS_URL and network connectivity"

no_test_results:
  message: "No load test results found"
  solution: "Run load test first or specify results file"

unsupported_format:
  message: "Unsupported load test format"
  solution: "Supported formats: Locust HTML, k6 JSON"

missing_baseline:
  message: "Baseline file not found"
  solution: "Create baseline or run comparison without baseline"
```

---

## Charts & Visualizations

### Performance Dashboard
```yaml
# When used with dataviz skill
charts:
  latency_time_series:
    type: line
    x_axis: time
    y_axis: latency (ms)
    series: p50, p95, p99
    slo_line: 100ms
    
  request_rate_histogram:
    type: bar
    x_axis: response time buckets
    y_axis: request count
    
  error_rate_heatmap:
    type: heatmap
    x_axis: service
    y_axis: time
    color: error_rate
    
  throughput_comparison:
    type: grouped_bar
    groups: [before, after]
    values: RPS
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
- `locust` - Load testing (optional)
- `k6` - Load testing (optional)
- `flameprof` - Flame graph generation (optional)

### Python Libraries (if implementing as tool)
```python
import requests  # Prometheus API
import json
import re
from datetime import datetime, timedelta
```

---

## Related Skills

- **`dataviz`** - For generating performance charts and dashboards
- **`k8s`** - For Kubernetes-level performance analysis
- **`simplify`** - For performance-related code optimization

---

**Skill Type**: Analysis/Reporting
**Confidence**: High
**Production Ready**: Yes
