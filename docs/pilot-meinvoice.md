# Giai đoạn 1: Pilot MeInvoice

## Overview

Document này hướng dẫn chạy pilot Giai đoạn 1 cho project **meinvoice** theo chiến lược [docs/chien_luoc_tong_the.md](../docs/chien_luoc_tong_the.md).

## Mục tiêu Pilot

- ✅ Chứng minh giá trị (Proof of Value) bằng cách giảm MTTI (Mean Time To Investigate)
- ✅ Tích hợp Claude API vào backend để generate Triage Card
- ✅ Test với real alert từ meinvoice

## Cài đặt

### 1. Backend Setup

```bash
cd backend

# Install dependencies (bao gồm Anthropic SDK)
pip install -r requirements.txt

# Configure .env
cp ../.env.example .env
```

### 2. Cấu hình Environment Variables

Thêm các biến sau vào `.env`:

```bash
# AI / LLM (Claude API)
ANTHROPIC_API_KEY=sk-ant-api03-...  # Get từ https://console.anthropic.com/
ANTHROPIC_MODEL=claude-sonnet-4-20250514
AI_MAX_TOKENS=4096

# Elasticsearch (meinvoice endpoints)
ELASTICSEARCH_URL=https://elkerror-elastic.misaonline.vpnlocal
ELASTICSEARCH_USERNAME=elastic
ELASTICSEARCH_PASSWORD=your_password

# Prometheus (meinvoice K8s)
PROMETHEUS_URL=https://k8smonitor-prometheus.misaonline.vpnlocal/k8s-mon-mei/

# Kubernetes
KUBECONFIG_PATH=/path/to/kubeconfig  # Hoặc để trống nếu in-cluster
K8S_NAMESPACES=["meinvoice"]

# Authentication
AUTH_SECRET=<generate-with: python3 -c "import secrets; print(secrets.token_hex(32))">
API_KEYS=["<generate-with: python3 -c \"import secrets; print(secrets.token_hex(32))\">"]
```

### 3. Khởi động Backend

```bash
# Development
uvicorn app.main:app --reload --port 8000

# Production via Docker
docker compose up -d
```

## Test API

### Health Check

```bash
curl http://localhost:8000/api/v1/analyze/health
```

Expected response:
```json
{
  "status": "healthy",
  "model": "claude-sonnet-4-20250514"
}
```

### Generate Triage Card

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "project": "meinvoice",
    "incident_id": "incident-001",
    "alert_message": "High error rate detected in meinvoice production API",
    "time_range_minutes": 60,
    "include_recommendations": true,
    "severity_threshold": "medium"
  }'
```

Hoặc sử dụng test script:

```bash
cd backend
API_KEY=your_api_key python test_analyze_api.py
```

## Triage Card Output Format

```json
{
  "success": true,
  "triage_card": {
    "generated_at": "2026-06-05T14:30:00Z",
    "project": "meinvoice",
    "incident_id": "incident-001",
    "summary": "MeInvoice API experiencing elevated error rate (~2.5%) primarily in checkout service. Root cause appears to be database connection timeout. 3 pods restarted in last hour.",
    "severity": "high",
    "status": "investigating",
    "time_window_start": "2026-06-05T13:30:00Z",
    "time_window_end": "2026-06-05T14:30:00Z",
    "findings": [
      {
        "type": "root_cause",
        "title": "Database connection timeout",
        "description": "APM shows 85% of errors have 'connection timeout' in payment service",
        "severity": "critical",
        "source": "apm",
        "evidence": "Error grouping: 'SqlException: Connection timeout' - 234 occurrences",
        "confidence": 0.9
      },
      {
        "type": "symptom",
        "title": "Pod restarts",
        "description": "3 pods in payment-service deployment restarted due to liveness probe failures",
        "severity": "high",
        "source": "kubernetes",
        "evidence": "Pods: payment-service-7d9f8c-5x2z, -7p4k, -9m8n all restarted within last hour",
        "confidence": 1.0
      }
    ],
    "recommendations": [
      {
        "priority": 1,
        "action": "Check database connectivity from payment-service pods",
        "command": "kubectl exec -n meinvoice deployment/payment-service -- pg_isopen -h db.meinvoice.svc",
        "reason": "Verify if database is reachable from affected pods",
        "risk": "low",
        "estimated_impact": "Diagnostic only"
      },
      {
        "priority": 2,
        "action": "Restart payment-service pods to clear any stuck connections",
        "command": "kubectl rollout restart deployment/payment-service -n meinvoice",
        "reason": "Fresh pods may establish healthy DB connections",
        "risk": "medium",
        "estimated_impact": "Brief service interruption (~10s)"
      }
    ],
    "model_used": "claude-sonnet-4-20250514",
    "tokens_used": 2847
  }
}
```

## Workflow SRE khi có Alert

### Trước (không có AI):
1. Nhận alert qua Slack/Email
2. Login vào Kibana → check logs
3. Login vào Prometheus → check metrics
4. Login vào K8s dashboard → check pods
5. Login vào APM → check traces
6. Nghiên cứu và phân tích
7. Đề xuất action (manual)
8. **Thời gian: 15-30 phút**

### Sau (với AI):
1. Nhận alert qua Slack/Email
2. Gọi `/api/v1/analyze` với alert context
3. Nhận Triage Card với:
   - Executive summary
   - Root cause analysis
   - Prioritized recommendations
4. Review và execute recommended actions
5. **Thời gian: 3-5 phút**

## Kết quả Mong đợi

| Metric | Trước | Sau (Target) |
|--------|-------|--------------|
| MTTI (Mean Time To Investigate) | 15-30 phút | 3-5 phút |
| MTTR (Mean Time To Resolve) | 30-60 phút | 15-20 phút |
| Số nguồn data cần check | 4-5 tools | 1 API call |
| Consistency | Phụ thuộc skill | Standardized |

## Next Steps (Giai đoạn 2)

Sau khi pilot thành công:
1. ✅ Tích hợp Approval Workflow
2. ✅ Build Action Engine (thực thi commands)
3. ✅ Human-in-the-loop (approve trước khi execute)
4. ✅ Audit Logging (ghi lại mọi action)

## Troubleshooting

### Lỗi "LLM service not configured"
→ Kiểm tra `ANTHROPIC_API_KEY` trong `.env`

### Lỗi "Failed to collect context data"
→ Kiểm tra kết nối đến Elasticsearch, Prometheus

### Lỗi "unauthorized"
→ Kiểm tra `API_KEYS` trong `.env` hoặc header `X-API-Key`

### Response trống/không có findings
→ Tăng `time_range_minutes` hoặc kiểm tra data availability

## Contact

- Team SRE: #sre-team
- Questions: Create ticket in Jira project DEVOPS-AI
