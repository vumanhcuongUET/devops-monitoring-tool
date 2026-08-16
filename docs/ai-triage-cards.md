# AI Triage Cards - Hướng dẫn chi tiết

## Tổng quan

**AI Triage Cards** là tính năng cốt lõi của Phase 1 trong chiến lược DevOps AI Agentics 2026. Nó sử dụng Claude API để phân tích sự cố và đưa ra khuyến nghị dựa trên dữ liệu từ nhiều nguồn monitoring.

### Cách hoạt động

```
┌─────────────────────────────────────────────────────────────┐
│                     1. Incident Detected                     │
│                  (Alert/Notification)                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              2. POST /api/v1/analyze                         │
│  Collect context from:                                       │
│  • Elasticsearch (logs + alerts)                              │
│  • APM (transactions + errors)                               │
│  • Prometheus (infrastructure metrics)                       │
│  • Kubernetes (pods + deployments)                           │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 3. Claude LLM Analysis                        │
│  • Identify root causes with confidence scores                │
│  • Generate prioritized recommendations                      │
│  • Output structured Triage Card (JSON)                      │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                4. Triage Card Response                        │
│  • Summary of incident                                        │
│  • Findings (root cause, affected services)                  │
│  • Recommendations (with commands/PRs)                       │
│  • Severity level                                             │
└─────────────────────────────────────────────────────────────┘
```

## API Endpoint

### Generate Triage Card

**POST** `/api/v1/analyze`

#### Request Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | Bearer token (from `/auth/token`) |
| `Content-Type` | Yes | `application/json` |

#### Request Body

```json
{
  "project": "meinvoice",
  "incident_id": "alert-123",
  "alert_message": "High error rate detected in production API",
  "time_range_minutes": 60,
  "include_recommendations": true,
  "severity_threshold": "medium"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `project` | string | Yes | Project/service name |
| `incident_id` | string | Yes | Unique incident identifier |
| `alert_message` | string | Yes | Alert message or description |
| `time_range_minutes` | integer | No | Time range for context collection (default: 60) |
| `include_recommendations` | boolean | No | Include action recommendations (default: true) |
| `severity_threshold` | string | No | Min severity: `low`, `medium`, `high`, `critical` |

#### Response

**Success** (200 OK):
```json
{
  "success": true,
  "triage_card": {
    "project": "meinvoice",
    "incident_id": "alert-123",
    "generated_at": "2026-08-16T10:30:00Z",
    "summary": "Payment service experiencing elevated error rate (~2.5%) due to database connection timeouts.",
    "severity": "high",
    "findings": [
      {
        "type": "root_cause",
        "title": "Database connection timeout",
        "description": "Payment API experiencing connection timeouts to PostgreSQL database. Connection pool exhaustion detected.",
        "severity": "critical",
        "confidence": 0.9,
        "evidence": {
          "error_rate": "2.5%",
          "affected_transactions": "payment-process, payment-callback",
          "correlation_id": "txn-abc123"
        }
      },
      {
        "type": "affected_service",
        "title": "Payment API degradation",
        "description": "Payment processing endpoint showing 95th percentile latency of 2.3s (baseline: 400ms).",
        "severity": "high",
        "confidence": 0.85,
        "evidence": {
          "p95_latency_ms": 2300,
          "baseline_p95_ms": 400,
          "error_count": 127
        }
      }
    ],
    "recommendations": [
      {
        "priority": 1,
        "action": "Check database connectivity",
        "command": "kubectl exec -n meinvoice deployment/payment-api -- pg_isopen -h postgres.default.svc.cluster.local",
        "expected_outcome": "Verify database connectivity from payment pods"
      },
      {
        "priority": 2,
        "action": "Increase connection pool size",
        "command": "kubectl set env deployment/payment-api DB_POOL_SIZE=50 -n meinvoice",
        "expected_outcome": "Reduce connection timeout errors"
      },
      {
        "priority": 3,
        "action": "Check database resource limits",
        "command": "kubectl top pod -n meinvoice -l app=postgres",
        "expected_outcome": "Verify database has sufficient CPU/memory"
      }
    ],
    "context_summary": {
      "data_sources": ["logs", "apm", "metrics", "kubernetes", "alerts"],
      "time_range_analyzed": "60 minutes",
      "total_logs_analyzed": 127,
      "apm_errors_found": 45
    }
  },
  "error": null
}
```

**Error** (400/500):
```json
{
  "success": false,
  "error": "LLM service not configured: ANTHROPIC_API_KEY not set",
  "triage_card": null,
  "debug_info": {
    "context_sources": ["logs", "apm", "metrics"]
  }
}
```

## Cấu hình

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | — | Claude API key |
| `ANTHROPIC_MODEL` | No | `claude-sonnet-4-20250514` | Model to use |
| `AI_MAX_TOKENS` | No | `4096` | Max response tokens |

### Lấy ANTHROPIC_API_KEY

1. Truy cập https://console.anthropic.com/
2. Đăng nhập hoặc tạo tài khoản
3. Vào API Keys section
4. Create new API key
5. Copy và thêm vào `.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-api03-...
```

## Ví dụ sử dụng

### cURL

```bash
# 1. Get auth token
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "X-API-Key: your_api_key" | jq -r '.access_token')

# 2. Generate triage card
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "project": "meinvoice",
    "incident_id": "high-error-rate",
    "alert_message": "Error rate exceeded 5% threshold in production",
    "time_range_minutes": 30,
    "severity_threshold": "high"
  }'
```

### Python

```python
import requests

BASE_URL = "http://localhost:8000"
API_KEY = "your_api_key"

# Get token
token_response = requests.post(
    f"{BASE_URL}/auth/token",
    headers={"X-API-Key": API_KEY}
)
token = token_response.json()["access_token"]

# Generate triage card
response = requests.post(
    f"{BASE_URL}/api/v1/analyze",
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    },
    json={
        "project": "meinvoice",
        "incident_id": "incident-001",
        "alert_message": "High latency detected",
        "time_range_minutes": 60
    }
)

triage_card = response.json()
print(f"Summary: {triage_card['triage_card']['summary']}")
print(f"Severity: {triage_card['triage_card']['severity']}")
```

### JavaScript/TypeScript

```typescript
const BASE_URL = 'http://localhost:8000';
const API_KEY = 'your_api_key';

async function generateTriageCard() {
  // Get token
  const tokenRes = await fetch(`${BASE_URL}/auth/token`, {
    method: 'POST',
    headers: { 'X-API-Key': API_KEY }
  });
  const { access_token } = await tokenRes.json();

  // Generate triage card
  const response = await fetch(`${BASE_URL}/api/v1/analyze`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${access_token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      project: 'meinvoice',
      incident_id: 'incident-001',
      alert_message: 'Pod crash loop detected',
      time_range_minutes: 30
    })
  });

  const result = await response.json();
  console.log('Summary:', result.triage_card.summary);
  return result;
}
```

## Health Check

**GET** `/api/v1/analyze/health`

Kiểm tra xem LLM service có sẵn sàng không:

```bash
curl http://localhost:8000/api/v1/analyze/health
```

Response:
```json
{
  "status": "healthy",
  "model": "claude-sonnet-4-20250514"
}
```

## Xử lý sự cố

### Lỗi "LLM service not configured"

**Nguyên nhân:** `ANTHROPIC_API_KEY` không được set hoặc không hợp lệ.

**Giải pháp:**
1. Kiểm tra `.env` file có `ANTHROPIC_API_KEY`
2. Verify API key tại https://console.anthropic.com/
3. Restart backend sau khi cập nhật `.env`

### Lỗi "Failed to collect context data"

**Nguyên nhân:** Một hoặc nhiều data sources không khả dụng.

**Giải pháp:**
1. Kiểm tra Elasticsearch connection
2. Kiểm tra Prometheus connection
3. Kiểm tra K8s connection/kubeconfig
4. Xem debug_info trong response để biết nguồn nào lỗi

### Response quá chậm

**Nguyên nhân:** time_range_minutes quá lớn hoặc quá nhiều data.

**Giải pháp:**
1. Giảm `time_range_minutes` (từ 60 xuống 30)
2. Chỉnh `AI_MAX_TOKENS` nhỏ hơn nếu response quá dài
3. Kiểm tra latency kết nối đến các data sources

## Best Practices

### 1. Incident ID Naming Convention

Sử dụng naming convention nhất quán:

```
alert-{alert_name}
incident-{timestamp}
{project}-{service}-{issue_type}
```

Ví dụ:
- `meinvoice-payment-db-timeout`
- `incident-20260816-1030`
- `frontend-api-high-latency`

### 2. Alert Message Writing

Viết alert message rõ ràng để AI phân tích tốt hơn:

**Bad:**
```
Something wrong
```

**Good:**
```
High error rate detected in payment processing API.
Error rate exceeded 5% threshold in last 5 minutes.
Affected endpoints: /api/payment/process, /api/payment/callback
```

### 3. Time Range Selection

Chọn time_range phù hợp với incident:

| Loại incident | Khuyến nghị time_range |
|--------------|----------------------|
| Spike đột ngột | 15-30 phút |
| Degradation từ từ | 2-4 giờ |
| Issue theo mùa | 24 giờ |
| Root cause analysis | 1-2 giờ |

### 4. Severity Threshold

Sử dụng severity threshold để lọc noise:

```
medium  — Default, balance signal/noise
high    — Chỉ alerts quan trọng
critical — Chỉ emergencies
```

## Tích hợp với Alerting

### Tự động tạo Triage Card khi có alert

```yaml
# Alert rule example
name: "High Error Rate - Auto Triage"
condition: "error_rate > 5%"
action:
  type: "webhook"
  url: "http://monitor-backend:8000/api/v1/analyze"
  headers:
    Authorization: "Bearer {{TOKEN}}"
  body:
    project: "meinvoice"
    incident_id: "{{ALERT_ID}}"
    alert_message: "{{ALERT_MESSAGE}}"
    time_range_minutes: 30
    severity_threshold: "high"
```

### Slack Bot Integration

```python
# Slack bot command handler
@app.command("/triage")
async def triage_command(ack, body, respond):
    await ack()
    
    # Parse incident from Slack command
    incident = parse_incident(body)
    
    # Call analyze API
    triage = await generate_triage_card(incident)
    
    # Format and send to Slack
    await respond(format_triage_slack(triage))
```

## Phase 2 Preview

Phase 1 (hiện tại) là **READ-ONLY** — AI chỉ phân tích và đề xuất.

Phase 2 (sắp tới) sẽ thêm **ACTION PROPOSAL**:
- Auto-generate kubectl commands
- Suggest PR diffs
- Approval workflow qua Slack/Teams
- Execution với confirm từ user

Xem [docs/chien_luoc_tong_the.md](chien_luoc_tong_the.md) để biết thêm chi tiết.
