# Alert Statistics - Hướng dẫn sử dụng

## Tổng quan

**Alert Statistics** module cho phép truy vấn và phân tích alerts từ Prometheus theo nhiều chiều:
- Phân tích theo namespace
- Phân bố theo severity (critical, warning, info)
- Top alerts theo từng namespace
- Tổng quan toàn cluster

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Frontend Dashboard                       │
│  • Alert statistics card on overview                       │
│  • Namespace breakdown page                                │
│  • Top alerts visualization                                 │
└──────────────────────────┬───────────────────────────────┘
                           │ REST API
                           ▼
┌──────────────────────────────────────────────────────────┐
│                   Backend FastAPI                          │
│  GET /api/v1/alerts/prometheus/stats                       │
│  GET /api/v1/alerts/namespace/{ns}                         │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│                   PrometheusClient                         │
│  Query alerts from Prometheus HTTP API                     │
│  Parse, group, calculate statistics                       │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│                   Prometheus Server                       │
│  /api/v1/alerts endpoint                                   │
└──────────────────────────────────────────────────────────┘
```

## API Endpoints

### 1. Cluster Alert Statistics

**GET** `/api/v1/alerts/prometheus/stats`

Lấy thống kê alerts cho toàn cluster hoặc nhiều namespace.

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `namespaces` | string | No | All configured | Comma-separated namespace list |
| `include_pending` | boolean | No | `true` | Include pending alerts in counts |
| `top_n` | integer | No | `5` | Number of top alerts per namespace |

#### Example Request

```bash
# All namespaces
curl http://localhost:8000/api/v1/alerts/prometheus/stats

# Specific namespaces
curl "http://localhost:8000/api/v1/alerts/prometheus/stats?namespaces=meinvoice,production"

# Customize top alerts and exclude pending
curl "http://localhost:8000/api/v1/alerts/prometheus/stats?top_n=10&include_pending=false"
```

#### Response (200 OK)

```json
{
  "timestamp": "2026-08-16T10:30:00Z",
  "total_namespaces": 3,
  "total_alerts": 47,
  "total_firing": 23,
  "namespaces": [
    {
      "namespace": "meinvoice",
      "total_alerts": 18,
      "firing": 12,
      "pending": 6,
      "by_severity": {
        "critical": 3,
        "warning": 7,
        "info": 8
      },
      "top_alerts": [
        {
          "name": "HighErrorRate",
          "severity": "critical",
          "state": "firing",
          "summary": "Error rate exceeded 5% threshold"
        },
        {
          "name": "PodCrashLooping",
          "severity": "warning",
          "state": "firing",
          "summary": "Pod payment-api-7f8d9 is crash looping"
        }
      ]
    },
    {
      "namespace": "production",
      "total_alerts": 15,
      "firing": 8,
      "pending": 7,
      "by_severity": {
        "critical": 2,
        "warning": 5,
        "info": 8
      },
      "top_alerts": [...]
    }
  ],
  "top_namespaces": [
    {"namespace": "meinvoice", "firing": 12, "total": 18},
    {"namespace": "production", "firing": 8, "total": 15},
    {"namespace": "staging", "firing": 3, "total": 14}
  ]
}
```

### 2. Namespace Alert Statistics

**GET** `/api/v1/alerts/prometheus/namespace/{namespace}`

Lấy thống kê chi tiết cho một namespace cụ thể.

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `namespace` | string | Yes | Kubernetes namespace name |

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `include_pending` | boolean | No | `true` | Include pending alerts |
| `top_n` | integer | No | `10` | Number of top alerts |

#### Example Request

```bash
curl http://localhost:8000/api/v1/alerts/prometheus/namespace/meinvoice

curl "http://localhost:8000/api/v1/alerts/prometheus/namespace/production?top_n=20"
```

#### Response (200 OK)

```json
{
  "namespace": "meinvoice",
  "total_alerts": 18,
  "firing": 12,
  "pending": 6,
  "by_severity": {
    "critical": 3,
    "warning": 7,
    "info": 8
  },
  "top_alerts": [
    {
      "name": "HighErrorRate",
      "severity": "critical",
      "state": "firing",
      "summary": "Error rate exceeded 5% threshold",
      "labels": {
        "namespace": "meinvoice",
        "service": "payment-api",
        "severity": "critical"
      }
    },
    {
      "name": "PodCrashLooping",
      "severity": "warning",
      "state": "firing",
      "summary": "Pod payment-api-7f8d9 is crash looping",
      "labels": {
        "namespace": "meinvoice",
        "pod": "payment-api-7f8d9",
        "severity": "warning"
      }
    }
  ]
}
```

#### Error Response (404)

```json
{
  "detail": "Namespace 'unknown' not found or has no alerts"
}
```

## Pydantic Models

```python
from pydantic import BaseModel
from typing import Optional

class AlertStats(BaseModel):
    """Alert statistics for a single namespace."""
    critical: int
    warning: int
    info: int

class TopAlert(BaseModel):
    """Top alert information."""
    name: str
    severity: str
    state: str
    summary: str
    labels: dict[str, str] = {}

class NamespaceAlertStats(BaseModel):
    """Alert statistics for one namespace."""
    namespace: str
    total_alerts: int
    firing: int
    pending: int
    by_severity: AlertStats
    top_alerts: list[TopAlert]

class ClusterAlertStats(BaseModel):
    """Cluster-wide alert statistics."""
    timestamp: str
    total_namespaces: int
    total_alerts: int
    total_firing: int
    namespaces: list[NamespaceAlertStats]
    top_namespaces: list[dict]
```

## Cấu hình Prometheus Client

### Environment Variables

```bash
# .env
PROMETHEUS_URL=http://prometheus.monitoring.svc:9090

# Optional: Query timeout (seconds)
PROMETHEUS_TIMEOUT=30
```

### Alert Detection Rules

Prometheus detect alerts by severity label:

```yaml
# Example Prometheus alert rule
groups:
  - name: payment_api
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
          namespace: meinvoice
        annotations:
          summary: "Error rate exceeded 5%"

      - alert: PodCrashLooping
        expr: rate(kube_pod_container_status_restarts_total[1h]) > 0
        for: 10m
        labels:
          severity: warning
          namespace: meinvoice
        annotations:
          summary: "Pod {{ $labels.pod }} is crash looping"
```

## Frontend Integration

### React Component Example

```typescript
// AlertStatsCard.tsx
import { useEffect, useState } from 'react';
import api from '@/services/api';

interface AlertStats {
  total_alerts: number;
  total_firing: number;
  by_severity: {
    critical: number;
    warning: number;
    info: number;
  };
}

export function AlertStatsCard() {
  const [stats, setStats] = useState<AlertStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/api/v1/alerts/prometheus/stats')
      .then(res => {
        // Sum across all namespaces
        const total = res.data.namespaces.reduce((acc: any, ns: any) => ({
          total_alerts: acc.total_alerts + ns.total_alerts,
          total_firing: acc.total_firing + ns.firing,
          by_severity: {
            critical: acc.by_severity.critical + ns.by_severity.critical,
            warning: acc.by_severity.warning + ns.by_severity.warning,
            info: acc.by_severity.info + ns.by_severity.info,
          }
        }), { total_alerts: 0, total_firing: 0, by_severity: { critical: 0, warning: 0, info: 0 } });
        setStats(total);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div>Loading...</div>;

  return (
    <div className="alert-stats-card">
      <h3>Alert Statistics</h3>
      <div className="stat-row">
        <span className="label">Total Alerts:</span>
        <span className="value">{stats?.total_alerts}</span>
      </div>
      <div className="stat-row critical">
        <span className="label">Critical:</span>
        <span className="value">{stats?.by_severity.critical}</span>
      </div>
      <div className="stat-row warning">
        <span className="label">Warning:</span>
        <span className="value">{stats?.by_severity.warning}</span>
      </div>
      <div className="stat-row info">
        <span className="label">Info:</span>
        <span className="value">{stats?.by_severity.info}</span>
      </div>
    </div>
  );
}
```

### TanStack Query Hook

```typescript
// hooks/useAlertStats.ts
import { useQuery } from '@tanstack/react-query';
import api from '@/services/api';

export function useAlertStats(namespaces?: string[]) {
  return useQuery({
    queryKey: ['alertStats', namespaces],
    queryFn: () => api.get('/api/v1/alerts/prometheus/stats', {
      params: namespaces ? { namespaces: namespaces.join(',') } : {}
    }),
    refetchInterval: 30000, // Poll every 30s
  });
}

// Usage
function Dashboard() {
  const { data: alertStats, isLoading } = useAlertStats(['meinvoice', 'production']);

  return <AlertVisualization data={alertStats?.data} />;
}
```

## Ví dụ sử dụng

### cURL Examples

```bash
# Get all alert stats
curl http://localhost:8000/api/v1/alerts/prometheus/stats

# Filter namespaces
curl "http://localhost:8000/api/v1/alerts/prometheus/stats?namespaces=meinvoice,production"

# Get specific namespace
curl http://localhost:8000/api/v1/alerts/prometheus/namespace/meinvoice

# Exclude pending alerts
curl "http://localhost:8000/api/v1/alerts/prometheus/stats?include_pending=false"

# Get more top alerts
curl "http://localhost:8000/api/v1/alerts/prometheus/namespace/production?top_n=20"
```

### Python Examples

```python
import requests

BASE_URL = "http://localhost:8000"

# Get cluster stats
response = requests.get(f"{BASE_URL}/api/v1/alerts/prometheus/stats")
stats = response.json()

print(f"Total namespaces: {stats['total_namespaces']}")
print(f"Total firing: {stats['total_firing']}")

# Get specific namespace
ns_response = requests.get(
    f"{BASE_URL}/api/v1/alerts/prometheus/namespace/meinvoice"
)
ns_stats = ns_response.json()

print(f"\nNamespace: {ns_stats['namespace']}")
print(f"Firing alerts: {ns_stats['firing']}")
print(f"Severity breakdown: {ns_stats['by_severity']}")

# Print top alerts
for alert in ns_stats['top_alerts']:
    print(f"- [{alert['severity']}] {alert['name']}: {alert['summary']}")
```

### Monitoring Alert Statistics

```python
# Example: Monitor alert stats and send notification
import requests
import time

def check_alert_health(threshold=10):
    """Check if firing alerts exceed threshold."""
    response = requests.get(
        "http://localhost:8000/api/v1/alerts/prometheus/stats"
    )
    stats = response.json()

    if stats['total_firing'] > threshold:
        print(f"⚠️ HIGH ALERT COUNT: {stats['total_firing']} firing")

        # Print worst namespaces
        for ns in stats['top_namespaces'][:3]:
            print(f"  - {ns['namespace']}: {ns['firing']} firing")

        return False
    return True

# Run check every 5 minutes
while True:
    check_alert_health(threshold=15)
    time.sleep(300)
```

## Xử lý sự cố

### Lỗi "Cannot connect to Prometheus"

**Nguyên nhân:**
- `PROMETHEUS_URL` sai
- Prometheus không accessible từ backend

**Giải pháp:**
```bash
# Test connectivity
curl $PROMETHEUS_URL/api/v1/alerts

# Check .env
grep PROMETHEUS_URL .env

# Verify from within pod
kubectl exec -it deployment/monitor-backend -- \
  curl -s http://prometheus.monitoring.svc:9090/api/v1/alerts
```

### Lỗi "Namespace not found"

**Nguyên nhân:**
- Namespace không có alerts
- Namespace không tồn tại

**Giải pháp:**
- Query tất cả namespaces trước để xem danh sách
- Check spelling
- Verify namespace exists in cluster

### Dữ liệu không update

**Nguyên nhân:**
- Prometheus stale data
- Caching issue

**Giải pháp:**
```bash
# Force Prometheus scrape
curl -X POST http://prometheus:9090/api/v1/admin/tsdb/snapshot

# Add cache-busting parameter
curl "http://localhost:8000/api/v1/alerts/prometheus/stats?_t=$(date +%s)"
```

## Best Practices

### 1. Alert Naming Convention

Dùng naming convention nhất quán để dễ phân tích:

```
{Service}{Metric}{Condition}
Examples:
- PaymentAPIHighErrorRate
- DatabaseCPUHigh
- PodNotReady
- DiskSpaceLow
```

### 2. Severity Label Standards

| Severity | Use case | Color (UI) |
|----------|----------|------------|
| `critical` | Service down, data loss | Red |
| `warning` | Degraded performance, high resource | Orange |
| `info` | Informational, upcoming maintenance | Blue |

### 3. Alert Annotation Standards

Luôn có summary annotation:

```yaml
annotations:
  summary: "Clear, human-readable description"
  description: "Optional: more detailed info"
  runbook_url: "Link to runbook"
```

### 4. Polling Strategy

Frontend nên poll ở mức hợp lý:
- Overview page: 30s
- Alert detail page: 10s
- Background: 60s

Dùng WebSocket (`/ws/live`) cho real-time updates thay vì poll.

## Tích hợp với Triage Cards

Kết hợp Alert Statistics với AI Triage Cards:

```python
# Auto-generate triage card for critical alerts
import requests

def auto_triage_critical_alerts():
    response = requests.get(
        "http://localhost:8000/api/v1/alerts/prometheus/stats"
    )
    stats = response.json()

    for ns in stats['namespaces']:
        critical = ns['by_severity']['critical']
        if critical > 0:
            # Generate triage card for this namespace
            triage = requests.post(
                "http://localhost:8000/api/v1/analyze",
                json={
                    "project": ns['namespace'],
                    "incident_id": f"critical-alerts-{ns['namespace']}",
                    "alert_message": f"{critical} critical alerts firing",
                    "severity_threshold": "critical"
                }
            )
            print(f"Triage generated for {ns['namespace']}")
```

## References

- Prometheus Alerting: https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
- Prometheus API: https://prometheus.io/docs/prometheus/latest/querying/api/
- Related docs:
  - [docs/ai-triage-cards.md](ai-triage-cards.md) - AI-powered incident analysis
  - [docs/chien_luoc_tong_the.md](chien_luoc_tong_the.md) - Strategic roadmap
