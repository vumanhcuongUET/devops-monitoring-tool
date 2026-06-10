# DevOps AI Agentics 2026 - Thiết Lập Đầu Vào

## 📋 Tổng Quan

Để vận hành hệ thống DevOps AI Agentics 2026, bạn cần cấu hình các thông số kết nối đến các nguồn dữ liệu (Elasticsearch, Prometheus, Kubernetes) và API key cho các tính năng AI.

---

## 🔗 Kết Nguồn Dữ Liệu (Bắt Buộc)

### 1. Elasticsearch / ELK

Dùng cho: Log search, APM data, SLO calculations

| Thông số | Mô tả | Ví dụ | Lấy ở đâu? |
|----------|--------|-------|-------------|
| `ELASTICSEARCH_URL` | Endpoint URL của Elasticsearch | `http://10.0.0.10:9200` hoặc `https://elkerror-elastic.misaonline.vpnlocal` | Admin ELK |
| `ELASTICSEARCH_USERNAME` | Username authentication | `elastic` | Admin ELK |
| `ELASTICSEARCH_PASSWORD` | Password authentication | `your_password` | Admin ELK |
| `ELASTICSEARCH_INDEX_PATTERN` | Pattern index cho logs | `logs-*` hoặc `logstash-meinvoice*` | Admin ELK |

**Kiểm tra kết nối:**
```bash
curl -u elastic:password http://your-es:9200/_cluster/health
```

---

### 2. Prometheus

Dùng cho: Infrastructure metrics, Alert statistics

| Thông số | Mô tả | Ví dụ | Lấy ở đâu? |
|----------|--------|-------|-------------|
| `PROMETHEUS_URL` | Endpoint URL của Prometheus | `http://10.0.0.11:9090` hoặc `https://k8smonitor-prometheus.misaonline.vpnlocal/k8s-mon-mei/` | Admin Prometheus |
| **Note:** | URL cần trỏ đến Prometheus đang chứa alerts của namespace cần monitor | — | Admin K8s/Prometheus |

**Kiểm tra kết nối:**
```bash
curl http://your-prometheus:9090/api/v1/query?query=up
```

**Kiểm tra alerts:**
```bash
curl http://your-prometheus:9090/api/v1/alerts
```

---

### 3. Kubernetes

Dùng cho: Pod status, deployment health, cluster events

| Thông số | Mô tả | Ví dụ | Lấy ở đâu? |
|----------|--------|-------|-------------|
| `KUBECONFIG_PATH` | Đường dẫn đến kubeconfig file | `/path/to/kubeconfig` hoặc `""` (in-cluster) | `~/.kube/config` |
| `K8S_NAMESPACES` | Danh sách namespaces cần monitor | `["default", "production", "staging"]` hoặc `["meinvoice"]` | Project requirement |

**Lưu ý:**
- Nếu chạy trong cluster (K8s): để `KUBECONFIG_PATH=""`
- Nếu chạy local: set đường dẫn đầy đủ đến kubeconfig

**Kiểm tra kết nối:**
```bash
export KUBECONFIG=/path/to/kubeconfig
kubectl get pods -n meinvoice
```

---

## 🔑 Authentication (Bắt Buộc)

### HMAC Secret & API Keys

Dùng cho: Bảo vệ API endpoints

| Thông số | Mô tả | Cách sinh | Ví dụ |
|----------|--------|-----------|-------|
| `AUTH_SECRET` | HMAC signing key (64-char hex) | `python3 -c "import secrets; print(secrets.token_hex(32))"` | `abc123...` |
| `API_KEYS` | List API keys cho client | `python3 -c "import secrets; print(secrets.token_hex(32))"` | `["xyz789..."]` |

**Sinh secrets:**
```bash
# AUTH_SECRET
AUTH_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
echo "AUTH_SECRET=$AUTH_SECRET"

# API_KEY
API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
echo "API_KEYS=[\"$API_KEY\"]"
```

---

## 🤖 AI / LLM (Tùy Chọn)

Dùng cho: Triage Card generation, AI-powered incident analysis

| Thông số | Mô tả | Ví dụ | Lấy ở đâu? |
|----------|--------|-------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key | `sk-ant-api03-...` | https://console.anthropic.com/ |
| `ANTHROPIC_MODEL` | Model sử dụng | `claude-sonnet-4-20250514` | — |
| `AI_MAX_TOKENS` | Max tokens cho LLM response | `4096` | — |

**Cách lấy API key:**
1. Truy cập https://console.anthropic.com/
2. Login hoặc tạo account
3. Click **Get API Keys**
4. Copy key

**Kiểm tra:**
```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"claude-3-haiku-20240307","max_tokens":10,"messages":[{"role":"user","content":"Hi"}]}'
```

---

## 📢 Notifications (Tùy Chọn)

### Slack Webhook

Dùng cho: Alert notifications qua Slack

| Thông số | Mô tả | Ví dụ | Lấy ở đâu? |
|----------|--------|-------|-------------|
| `SLACK_WEBHOOK_URL` | Incoming webhook URL | `https://hooks.slack.com/services/...` | Slack App settings |

**Cách tạo webhook:**
1. Vào Slack workspace → Apps
2. Tìm hoặc tạo app Incoming Webhooks
3. Click **Add New Webhook to Workspace**
4. Copy webhook URL

---

### Email Notifications

Dùng cho: Alert notifications qua email

| Thông số | Mô tả | Ví dụ |
|----------|--------|-------|
| `SMTP_HOST` | SMTP server address | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP port | `587` |
| `SMTP_USER` | SMTP username | `your-email@gmail.com` |
| `SMTP_PASSWORD` | SMTP password hoặc App Password | `your-app-password` |
| `ALERT_EMAIL_FROM` | From address | `noreply@company.com` |
| `ALERT_EMAIL_TO` | To addresses (JSON array) | `["team@company.com"]` |

---

### Generic Webhook

| Thông số | Mô tả | Ví dụ |
|----------|--------|-------|
| `ALERT_WEBHOOK_URL` | Custom webhook URL | `https://your-webhook.com/alerts` |

---

## ⚙️ Cấu Hình Khác (Optional)

### CORS

| Thông số | Mô tả | Default |
|----------|--------|---------|
| `CORS_ORIGINS` | Allowed origins (JSON array) | `["http://localhost:3000"]` |

### Rate Limiting

| Thông số | Mô tả | Default |
|----------|--------|---------|
| `POLL_INTERVAL_SECONDS` | Frontend poll interval | `10` |
| `REQUEST_TIMEOUT_SECONDS` | API client timeout | `5` |
| `ALERT_CHECK_INTERVAL_SECONDS` | Alert evaluation cycle | `30` |

### SLO Reporting

| Thông số | Mô tả | Default |
|----------|--------|---------|
| `SLO_REPORT_ENABLED` | Enable daily SLO report | `true` |
| `SLO_REPORT_HOUR` | Hour to send report (24h) | `9` |
| `SLO_REPORT_TIMEZONE` | Timezone | `Asia/Ho_Chi_Minh` |

---

## 📝 File .env Hoàn Chỉ

```bash
# ============================================
# NGUỒN DỮ LIỆU (BẮT BUỘC)
# ============================================

# Elasticsearch
ELASTICSEARCH_URL=https://elkerror-elastic.misaonline.vpnlocal
ELASTICSEARCH_USERNAME=elastic
ELASTICSEARCH_PASSWORD=your_elk_password_here
ELASTICSEARCH_INDEX_PATTERN=logstash-meinvoice*

# APM (trên ES)
APM_INDEX_PATTERN=trace-apm-default

# Prometheus
PROMETHEUS_URL=https://k8smonitor-prometheus.misaonline.vpnlocal/k8s-mon-mei/

# Kubernetes
KUBECONFIG_PATH=/path/to/kubeconfig  # Hoặc để trống nếu in-cluster
K8S_NAMESPACES=["meinvoice", "production", "staging"]

# ============================================
# AUTHENTICATION (BẮT BUỘC)
# ============================================

# Generate bằng: python3 -c "import secrets; print(secrets.token_hex(32))"
AUTH_SECRET=your_auth_secret_here_64_chars_hex
API_KEYS=["your_api_key_here_64_chars_hex"]

# ============================================
# AI / LLM (TÙY CHỌN - CẦN CHO TRIAGE CARDS)
# ============================================

# Lấy từ: https://console.anthropic.com/
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
ANTHROPIC_MODEL=claude-sonnet-4-20250514
AI_MAX_TOKENS=4096

# ============================================
# NOTIFICATIONS (TÙY CHỌN)
# ============================================

# Slack Webhook
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your_app_password_here
ALERT_EMAIL_FROM=noreply@company.com
ALERT_EMAIL_TO=["team@company.com"]

# Generic Webhook
ALERT_WEBHOOK_URL=https://your-webhook.com/alerts

# ============================================
# OTHER CONFIG
# ============================================

# CORS
CORS_ORIGINS=["http://localhost:3000", "https://your-domain.com"]

# Timeouts & Intervals
POLL_INTERVAL_SECONDS=10
REQUEST_TIMEOUT_SECONDS=5
ALERT_CHECK_INTERVAL_SECONDS=30

# SLO Reporting
SLO_REPORT_ENABLED=true
SLO_REPORT_HOUR=9
SLO_REPORT_TIMEZONE=Asia/Ho_Chi_Minh
```

---

## ✅ Checklist Trước Khi Chạy

### Phần 1: Kết Nguồn Dữ Liệu

- [ ] Elasticsearch URL, username, password đã có và test OK
- [ ] Prometheus URL đã có và test OK
- [ ] Kubernetes kubeconfig đã set up (hoặc để trống cho in-cluster)
- [ ] Danh sách namespaces cần monitor đã xác định

### Phần 2: Authentication

- [ ] AUTH_SECRET đã sinh (64-char hex)
- [ ] API keys đã sinh (ít nhất 1 key)
- [ ] Secrets và keys đã lưu vào `.env`

### Phần 3: AI Features (nếu dùng)

- [ ] Anthropic API key đã lấy
- [ ] Test gọi Claude API thành công
- [ ] `ANTHROPIC_MODEL` đã set

### Phần 4: Notifications (nếu dùng)

- [ ] Slack webhook URL đã có (nếu dùng Slack)
- [ ] SMTP credentials đã có (nếu dùng Email)
- [ ] Webhook URL đã có (nếu dùng custom webhook)

---

## 🧪 Testing Commands

### Test Elasticsearch
```bash
curl -u elastic:password http://your-es:9200/_cluster/health
```

### Test Prometheus
```bash
curl http://your-prometheus:9090/api/v1/query?query=up
curl http://your-prometheus:9090/api/v1/alerts
```

### Test Kubernetes
```bash
export KUBECONFIG=/path/to/kubeconfig
kubectl get pods -A
```

### Test Claude API
```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-3-haiku-20240307","max_tokens":10,"messages":[{"role":"user","content":"Hello"}]}'
```

### Test Backend API (sau khi start)
```bash
# Health check
curl http://localhost:8000/health

# Get token
curl -X POST http://localhost:8000/auth/token \
  -H "X-API-Key: your_api_key"

# Test overview
curl http://localhost:8000/api/v1/overview \
  -H "Authorization: Bearer your_token"

# Test alert stats
curl http://localhost:8000/api/v1/alerts/prometheus/stats \
  -H "Authorization: Bearer your_token"
```

---

## 🚀 Bắt Dầu

Sau khi cấu hình xong:

```bash
# 1. Copy file cấu hình
cp .env.example .env

# 2. Edit .env với các thông số trên
nano .env

# 3. Kiểm tra tất cả kết nối
# (Chạy các test commands ở trên)

# 4. Start hệ thống
docker compose up -d

# 5. Kiểm tra dashboard
open http://localhost:3000
```

---

## 📞 Support

Nếu gặp vấn đề:
1. Kiểm tra log backend: `docker compose logs backend`
2. Kiểm tra log frontend: `docker compose logs frontend`
3. Verify kết nối đến từng nguồn dữ liệu
4. Contact: #sre-team

---

*Document version: 1.0*
*Last updated: 2026-06-05*
