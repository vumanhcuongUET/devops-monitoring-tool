# Claude Code Skill: reliability - Reliability & Resilience Analysis

## Overview

**Skill Name**: `reliability`
**Purpose**: Analyze scaling effectiveness, DLQ health, circuit breakers, and reliability metrics
**Trigger**: User requests related to HPA, scaling, DLQ, circuit breaker, resilience
**Version**: 1.0

---

## Skill Definition

```yaml
name: reliability
description: Reliability analysis assistant for scaling, DLQ monitoring, circuit breakers, and resilience
triggers:
  - "hpa"
  - "horizontal pod autoscaler"
  - "scaling"
  - "autoscaling"
  - "dlq"
  - "dead letter queue"
  - "circuit breaker"
  - "resilience"
  - "fault tolerance"
  - "retry"
  - "timeout"
examples:
  - "Analyze HPA effectiveness"
  - "Check DLQ health"
  - "Review circuit breaker states"
  - "Calculate SLO compliance"
```

---

## Capabilities

### 1. Horizontal Pod Autoscaler (HPA) Analysis

#### HPA Effectiveness Scoring
```yaml
# Input: Deployment name, namespace, time range
command: "Analyze HPA effectiveness for backend deployment"

deployment: backend
namespace: production
time_range: 7 days

metrics:
  current_state:
    replicas: 5
    min_replicas: 2
    max_replicas: 10
    target_cpu: 70%
    target_memory: 80%
    
  scaling_activity:
    total_events: 48
    scale_up: 23
    scale_down: 25
    average_scale_time: 45s
    
  utilization_patterns:
    time_at_min: 68% (2 replicas)
    time_at_max: 8% (10 replicas)
    time_in_optimal_range: 24%

effectiveness_score: 65/100 (Fair)

analysis:
  issues:
    - ⚠️ At max replicas 8% of time (under-provisioned)
    - ⚠️ At min replicas 68% of time (over-provisioned)
    - ✅ Scaling time is good (45s average)
    
  recommendations:
    - Increase max_replicas: 10 → 15 (to handle peaks)
    - Decrease min_replicas: 2 → 1 (save resources during low traffic)
    - Add custom metric (request latency) for better scaling decisions
```

#### Scaling Event Analysis
```yaml
# Input: HPA name, time range
command: "Show scaling events for backend-hpa in last 24h"

events:
  - timestamp: "2026-08-22 14:30:00"
    type: scale_up
    from: 3
    to: 5
    reason: CPU exceeded 70%
    duration: 38s
    
  - timestamp: "2026-08-22 15:15:00"
    type: scale_up
    from: 5
    to: 8
    reason: CPU exceeded 70%
    duration: 42s
    
  - timestamp: "2026-08-22 17:00:00"
    type: scale_down
    from: 8
    to: 4
    reason: CPU below 50% for 5 minutes
    duration: 52s
    
patterns:
  - Peak scaling: 14:00-16:00 (business hours)
  - Rapid scale-up events: 3 in 1 hour (consider predictive scaling)
  - Stabilization time: ~5 minutes after scale event
  
recommendations:
  - Implement predictive scaling based on schedule
  - Add custom metric for queue depth
  - Consider vertical pod autoscaler (VPA) for right-sizing
```

#### HPA Configuration Recommendations
```yaml
# Input: Deployment, current metrics
command: "Generate optimal HPA configuration for backend"

analysis:
  current_metrics:
    - avg_cpu: 75%
    - avg_memory: 85%
    - avg_requests_per_pod: 250
    
  peak_metrics:
    - max_cpu: 95%
    - max_memory: 98%
    - max_requests_per_pod: 500

recommended_hpa:
  apiVersion: autoscaling/v2
  kind: HorizontalPodAutoscaler
  metadata:
    name: backend-hpa
  spec:
    scaleTargetRef:
      apiVersion: apps/v1
      kind: Deployment
      name: backend
    minReplicas: 2
    maxReplicas: 15
    metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
    - type: Pods
      pods:
        metric:
          name: http_requests_per_pod
        target:
          type: AverageValue
          averageValue: "400"
    behavior:
      scaleDown:
        stabilizationWindowSeconds: 300
        policies:
        - type: Percent
          value: 50
          periodSeconds: 15
      scaleUp:
        stabilizationWindowSeconds: 0
        policies:
        - type: Percent
          value: 100
          periodSeconds: 15
        - type: Pods
          value: 2
          periodSeconds: 15
        selectPolicy: Max
```

---

### 2. Dead Letter Queue (DLQ) Monitoring

#### DLQ Health Analysis
```yaml
# Input: Time range, action type filter
command: "Analyze DLQ health and failure patterns"

time_range: 24h

overall_health:
  total_dlq_items: 127
  items_processed: 234
  items_retried: 45
  items_permanently_failed: 8

breakdown_by_action:
  autonomous_scale:
    failed: 23
    retried: 12
    success_rate: 52%
    top_failures:
      - RBAC_DENY: 15
      - QUOTA_EXCEEDED: 5
      - TIMEOUT: 3
      
  autonomous_restart:
    failed: 18
    retried: 8
    success_rate: 44%
    top_failures:
      - POD_NOT_FOUND: 10
      - CRASH_LOOP_BACKOFF: 5
      - INSUFFICIENT_RESOURCES: 3
      
  alert_webhook:
    failed: 86
    retried: 25
    success_rate: 29%
    top_failures:
      - ENDPOINT_UNREACHABLE: 65
      - TIMEOUT: 15
      - AUTH_ERROR: 6

health_score: 42/100 (Poor)

recommendations:
  - ⚠️ alert_webhook has 29% success rate - investigate endpoint
  - Fix RBAC permissions for autonomous_scale
  - Add retry exponential backoff for alert_webhook
```

#### Failure Pattern Analysis
```yaml
# Input: DLQ data, time range
command: "Identify failure patterns in DLQ"

patterns:
  time_based:
    - pattern: "Alert webhook failures spike 9-10 AM"
      count: 45
      likely_cause: "Morning traffic surge overwhelms webhook"
      
  action_based:
    - pattern: "autonomous_scale RBAC_DENY consistent"
      count: 15
      likely_cause: "Missing permissions for service account"
      
  dependency_based:
    - pattern: "Timeouts correlate with ES query duration"
      count: 23
      likely_cause: "Elasticsearch slow query affecting action"

failure_taxonomy:
  transient_errors: 68%
    - TIMEOUT (38)
    - RATE_LIMITED (18)
    - ENDPOINT_UNREACHABLE (12)
    action: "Implement retry with backoff"
    
  configuration_errors: 25%
    - RBAC_DENY (15)
    - AUTH_ERROR (8)
    action: "Fix configuration/permissions"
    
  permanent_errors: 7%
    - INVALID_PAYLOAD (5)
    - RESOURCE_DELETED (3)
    action: "Manual intervention required"
```

#### Retry Strategy Analysis
```yaml
# Input: Action type, retry configuration
command: "Analyze retry effectiveness"

action: alert_webhook

current_config:
  max_retries: 3
  backoff: fixed (5s)
  timeout: 30s

retry_analysis:
  attempt_1:
    tries: 86
    failures: 48
    success_rate: 44%
    
  attempt_2:
    tries: 48
    failures: 31
    success_rate: 35%
    
  attempt_3:
    tries: 31
    failures: 23
    success_rate: 26%

overall_success: 29% (25/86)

recommendations:
  - Change backoff: fixed → exponential (5s, 10s, 20s)
  - Increase timeout: 30s → 60s
  - Add jitter to prevent thundering herd
  - Consider circuit breaker for this webhook
```

---

### 3. Circuit Breaker Analysis

#### Circuit State Monitoring
```yaml
# Input: Service name, time range
command: "Monitor circuit breaker states for backend services"

services:
  payment_service:
    state: CLOSED
    failures: 2
    threshold: 5
    last_failure: 2 hours ago
    success_rate: 98.5%
    status: ✅ Healthy
    
  external_api:
    state: OPEN
    failures: 8
    threshold: 5
    opened_at: 14:30 UTC
    timeout: 60s remaining
    status: ⚠️ Circuit open
    
  database_connection:
    state: HALF_OPEN
    failures: 3
    threshold: 5
    test_requests: 2
    status: ⚠️ Testing recovery

summary:
  total_circuits: 10
  closed: 7 (70%)
  open: 2 (20%)
  half_open: 1 (10%)
```

#### Trip Frequency Analysis
```yaml
# Input: Service, time range
command: "Analyze circuit breaker trip patterns"

service: external_api_client
time_range: 7 days

trip_events:
  total_trips: 23
  avg_daily_trips: 3.3
  peak_day: 12 trips (Monday)

trip_patterns:
  - time_distribution:
      - 08:00-12:00: 8 trips
      - 12:00-16:00: 10 trips
      - 16:00-20:00: 4 trips
      - 20:00-08:00: 1 trip
      
  recovery_time:
    avg: 5m 30s
    min: 2m 15s
    max: 15m 45s
    
analysis:
  High trip frequency during business hours suggests:
  - Dependency is unreliable
  - Threshold may be too sensitive
  - Timeout may be too aggressive

recommendations:
  1. Investigate external_api reliability (SLA?)
  2. Consider increasing failure threshold: 5 → 10
  3. Add timeout: 30s → 60s
  4. Implement fallback service
```

#### Circuit Breaker Configuration
```yaml
# Input: Service, failure patterns
command: "Generate optimal circuit breaker configuration"

service: external_api

analysis:
  avg_response_time: 2.5s
  error_rate: 8%
  timeout_rate: 12%
  peak_concurrent_requests: 50

recommended_config:
  circuit_breaker:
    failure_threshold: 10
    success_threshold: 3
    timeout: 10s
    half_open_max_calls: 5
    
  bulkhead:
    max_concurrent_calls: 30
    max_wait_duration: 5s
    
  retry:
    max_attempts: 2
    wait_duration: 1s
    backoff: exponential
    
  fallback:
    enabled: true
    fallback_strategy: "cached_response"

rationale:
  - Higher threshold (10) to handle brief outages
  - Longer timeout (10s) for slow API responses
  - Bulkhead limits to prevent cascading failures
  - Fallback to cache during outages
```

---

### 4. SLO & Error Budget Analysis

#### SLO Compliance Tracking
```yaml
# Input: Service, SLO config
command: "Track SLO compliance for backend-api"

slo_config:
  availability:
    target: 99.9%
    window: 30d rolling
    
  latency:
    target: p95 < 100ms
    window: 7d rolling

compliance_status:
  availability:
    current: 99.85%
    target: 99.9%
    gap: 0.05%
    status: ⚠️ At risk
    
    error_budget:
      total_budget: 43.2 minutes/month
      burned: 31.5 minutes
      remaining: 11.7 minutes (27%)
      burn_rate: 1.5 minutes/day
      
    projection:
      days_until_exhausted: 8
      status: ⚠️ Will exceed budget if trend continues
      
  latency:
    current_p95: 145ms
    target: <100ms
    gap: 45ms
    status: ❌ VIOLATION
    
    breach_probability: 78%

recommendations:
  - Prioritize latency optimization (45ms above target)
  - Investigate slow endpoints (/api/v1/analyze: 850ms p95)
  - Consider increasing SLO target or optimizing service
```

#### Service Dependency Health
```yaml
# Input: Service name
command: "Analyze dependency health for backend"

dependency_map:
  direct:
    - name: elasticsearch
      health: Degraded
      latency: +200ms from baseline
      error_rate: 2% (baseline 0.1%)
      impact: HIGH
      status: ⚠️
      
    - name: postgres
      health: Healthy
      latency: 180ms (baseline)
      error_rate: 0.3%
      impact: LOW
      status: ✅
      
    - name: redis
      health: Healthy
      latency: 5ms (baseline)
      error_rate: 0%
      impact: LOW
      status: ✅

  indirect:
    - name: external-payment-api
      health: Unknown (no monitoring)
      impact: MEDIUM
      status: ❌ Unmonitored

cascading_risk:
  elasticsearch_degradation:
    affected_services:
      - backend (primary user)
      - analytics (reporting)
      - audit-logs (compliance)
    impact_assessment:
      - Backend SLO at risk if ES fails completely
      - 30% of backend features depend on ES
      
recommendations:
  - Add monitoring for external-payment-api
  - Implement ES fallback/caching
  - Add circuit breaker for ES dependency
```

---

## Integration with Claude Code

### File Context Awareness

The skill should:
1. **Read HPA configs** from k8s/ directory
2. **Find circuit breaker configs** in application code
3. **Access DLQ metrics** from backend API
4. **Read SLO configs** from backend/app/alerting/
5. **Understand service topology** from K8s and application

### Tool Usage

```python
# Tools the skill should use:
- Bash: kubectl for HPA and deployment status
- Read: HPA configs, circuit breaker configs, SLO configs
- WebFetch: Prometheus API for metrics
```

---

## Examples

### Example 1: HPA Analysis
```
User: Is our HPA configured optimally for the backend?

Claude:
I'll analyze the HPA configuration and effectiveness for backend deployment.

[Queries metrics and HPA status]

HPA Effectiveness Score: 65/100 (Fair)

Current Issues:
- At max replicas (10) for 8% of time → under-provisioned during peaks
- At min replicas (2) for 68% of time → over-provisioned most of the time
- Average scale time: 45s ✅ (good)

Recommendations:
1. Increase max_replicas: 10 → 15
2. Decrease min_replicas: 2 → 1 (save resources)
3. Add custom metric for request queue length

Would you like me to generate the updated HPA manifest?
```

### Example 2: DLQ Analysis
```
User: Why are actions failing and ending up in DLQ?

Claude:
I'll analyze the DLQ to identify failure patterns.

[Queries DLQ API]

DLQ Health Score: 42/100 (Poor)

Top Failure Reasons:
1. alert_webhook - 65 failures (ENDPOINT_UNREACHABLE)
2. autonomous_scale - 15 failures (RBAC_DENY)
3. autonomous_restart - 10 failures (POD_NOT_FOUND)

Root Causes:
- Webhook endpoint is down or misconfigured (71% of alert_webhook calls fail)
- Service account lacks scale permissions
- Pod restart failures due to missing pods

Recommended Actions:
1. Fix webhook endpoint configuration or implement fallback
2. Add RBAC permissions for ai-prod-operator service account
3. Investigate why pods are going missing before restart

I can generate the fix commands if needed.
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-22 | Initial skill definition |

---

## Dependencies

### Required Tools
- `kubectl` - For HPA and deployment queries

### Python Libraries
```python
import requests
from datetime import datetime, timedelta
from typing import Dict, List
```

---

## Related Skills

- **`observability`** - For metrics that feed into reliability analysis
- **`k8s`** - For Kubernetes HPA and deployment management
- **`perf`** - For performance-related reliability issues

---

**Skill Type**: Analysis/Reporting
**Confidence**: High
**Production Ready**: Yes
