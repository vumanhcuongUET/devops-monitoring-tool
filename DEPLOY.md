# DevOps Monitor - Hướng dẫn triển khai

## 1. Yêu cầu hạ tầng

### Các hệ thống cần có sẵn (tool không tự cài)

| Hệ thống | Mục đích | Cần có trước? | Endpoint ví dụ |
|----------|----------|---------------|----------------|
| **Elasticsearch** (7.x+) | Logs + APM data | Có | `http://elasticsearch:9200` |
| **Elastic APM Server** | APM agents gửi data → ES | Có (APM data nằm trong ES) | `http://apm-server:8200` |
| **Prometheus** | Infrastructure metrics | Có | `http://prometheus:9090` |
| **Kubernetes cluster** | Pod/deployment/event data | Có | — |
| **Anthropic Claude API** | AI Triage Cards | Có (optional - cho AI features) | `https://api.anthropic.com` |

### Tài nguyên tối thiểu

| Môi trường | CPU | RAM | Disk | Note |
|------------|-----|-----|------|------|
| Dev (Docker Compose) | 1 core | 1 GB | 1 GB | Single replica |
| Prod (K8s, 2 replicas) | 1 core | 1 GB | 1 GB PVC | HorizontalPodAutoscaler 推荐 |

### Phần mềm cần cài đặt

| Phần mềm | Version mín | Mục đích |
|----------|-------------|----------|
| Docker | 20.x+ | Build và chạy containers |
| Docker Compose | 2.x+ | Dev deployment |
| kubectl | 1.25+ | K8s operations |
| Python | 3.12+ | Backend development |
| Node.js | 20.x+ | Frontend development |
| npm/pnpm | 9.x+/8.x+ | Frontend dependencies |

---

## 1.1 Kiểm tra prerequisites (Pre-flight Check)

```bash
#!/bin/bash
# preflight-check.sh

echo "🔍 Checking prerequisites..."

# Docker
if command -v docker &> /dev/null; then
    echo "✅ Docker: $(docker --version)"
else
    echo "❌ Docker not found"
    exit 1
fi

# Docker Compose
if docker compose version &> /dev/null; then
    echo "✅ Docker Compose: $(docker compose version)"
else
    echo "❌ Docker Compose not found"
    exit 1
fi

# Python
if command -v python3 &> /dev/null; then
    echo "✅ Python: $(python3 --version)"
else
    echo "❌ Python not found"
    exit 1
fi

# Node.js
if command -v node &> /dev/null; then
    echo "✅ Node.js: $(node --version)"
else
    echo "❌ Node.js not found"
    exit 1
fi

echo "✅ All prerequisites met!"
```

Chạy script:
```bash
chmod +x preflight-check.sh
./preflight-check.sh
```

---

## 2. Triển khai Dev (Docker Compose)

### Bước 1: Cài đặt prerequisites

```bash
# Cần có Docker + Docker Compose
docker --version
docker compose version
```

### Bước 2: Clone project và tạo .env

```bash
cd devops-monitor-tool
cp .env.example .env
```

### Bước 3: Chỉnh sửa .env

#### 3.1. BẮT BUỘC - Infrastructure endpoints

```bash
# ===== ELASTICSEARCH =====
ELASTICSEARCH_URL=http://10.0.0.10:9200          # Địa chỉ ES của bạn
ELASTICSEARCH_USERNAME=elastic
ELASTICSEARCH_PASSWORD=your_strong_password

# ===== PROMETHEUS =====
PROMETHEUS_URL=http://10.0.0.11:9090              # Địa chỉ Prometheus của bạn

# ===== KUBERNETES =====
# Chạy ngoài cluster (dev)
KUBECONFIG_PATH=/home/user/.kube/config

# Hoặc nhiều namespace (JSON array)
K8S_NAMESPACES=["default","production","staging"]
```

**Tips:**
- Test kết nối ES: `curl -u elastic:password http://your-es:9200/_cluster/health`
- Test kết nối Prometheus: `curl http://your-prom:9090/api/v1/query?query=up`
- Test K8s: `kubectl get pods`

#### 3.2. BẮT BUỘC - Authentication

```bash
# ===== AUTH =====
AUTH_ENABLED=true
AUTH_SECRET=                                        # Chạy lệnh dưới để generate
API_KEYS=[]                                         # Chạy lệnh dưới để generate
```

Generate auth keys:

```bash
# Generate AUTH_SECRET (64 hex chars)
python3 -c "import secrets; print('AUTH_SECRET=' + secrets.token_hex(32))"

# Generate API_KEY (64 hex chars)
python3 -c "import secrets; print('API_KEY=' + secrets.token_hex(32))"
```

Kết quả ví dụ:
```
AUTH_SECRET=a1b2c3d4e5f6...64chars
API_KEY=["f6e5d4c3b2a1...64chars"]
```

**QUAN TRỌNG:** Copy chính xác vào `.env`:
```bash
AUTH_SECRET=a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d
API_KEYS=["f6e5d4c3b2a10987654321fedcba09876543210abcdef1234567890abcdef12"]
```

#### 3.3. OPTIONAL - AI Features (Triage Cards)

```bash
# ===== AI / LLM =====
# Get API key from https://console.anthropic.com/
ANTHROPIC_API_KEY=sk-ant-api03-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514
AI_MAX_TOKENS=4096
```

**Note:** Nếu không set `ANTHROPIC_API_KEY`, AI features sẽ disabled nhưng core monitoring vẫn hoạt động.

#### 3.4. OPTIONAL - Notifications

```bash
# ===== NOTIFICATIONS =====
# Slack
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ALERT_EMAIL_FROM=monitoring@yourdomain.com
ALERT_EMAIL_TO=oncall@yourdomain.com

# Generic webhook
ALERT_WEBHOOK_URL=https://your-webhook-endpoint.com
```

#### 3.5. OPTIONAL - SLO Reporting

```bash
# ===== SLO DAILY REPORT =====
SLO_REPORT_ENABLED=true
SLO_REPORT_HOUR=9                                  # 9 AM
SLO_REPORT_TIMEZONE=Asia/Ho_Chi_Minh
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...  # Required for SLO report
```

### Bước 4: Chạy

```bash
# Xây dựng và khởi động
docker compose up -d

# Xem logs
docker compose logs -f

# Kiểm tra containers
docker compose ps
```

**Expected output:**
```
NAME                    STATUS         PORTS
devops-monitor-backend  running        0.0.0.0:8000->8000
devops-monitor-frontend running        0.0.0.0:3000->3000
```

### Bước 5: Lấy token để truy cập

```bash
# Dùng API key từ .env để lấy Bearer token
curl -X POST http://localhost:8000/auth/token \
  -H "X-API-Key: f6e5d4c3b2a1...64chars"
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### Bước 6: Truy cập

| URL | Mô tả |
|-----|-------|
| http://localhost:3000 | Frontend Dashboard |
| http://localhost:8000/docs | API Documentation (Swagger) |
| http://localhost:8000/redoc | Alternative API docs |

**Frontend tự động:**
- Gửi API key qua header `X-API-Key`
- Lưu Bearer token vào `localStorage`
- Tự động refresh token khi hết hạn

### Bước 7: Verify deployment

```bash
# Test overview endpoint (cần token)
TOKEN="your_token_here"
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/overview

# Test AI triage (optional, cần ANTHROPIC_API_KEY)
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project":"test","incident_id":"test-1","alert_message":"test"}'

# Test health check
curl http://localhost:8000/health
```

### Bước 8: Dừng

```bash
docker compose down          # Dừng, giữ data volumes
docker compose down -v       # Dừng, xóa data volumes

# Xem logs cho troubleshooting
docker compose logs backend
docker compose logs frontend
```

---

## 3. Triển khai Production (Kubernetes)

### Bước 1: Chuẩn bị

```bash
# Cần có kubectl truy cập vào cluster
kubectl cluster-info

# Cần có container registry (Docker Hub, ECR, GCR, Harbor...)
# Cần có nginx ingress controller đã cài trong cluster
```

### Bước 2: Build và push images

```bash
# Đổi YOUR_REGISTRY thành registry của bạn
export REGISTRY=your-registry.com/devops-monitor

# Build backend
docker build -t ${REGISTRY}-backend:latest ./backend
docker push ${REGISTRY}-backend:latest

# Build frontend (production stage)
docker build -t ${REGISTRY}-frontend:latest --target prod ./frontend
docker push ${REGISTRY}-frontend:latest
```

### Bước 3: Cập nhật image trong K8s manifests

Sửa `k8s/backend/deployment.yaml`:
```yaml
image: your-registry.com/devops-monitor-backend:latest
```

Sửa `k8s/frontend/deployment.yaml`:
```yaml
image: your-registry.com/devops-monitor-frontend:latest
```

### Bước 4: Cập nhật ConfigMap

Sửa `k8s/backend/configmap.yaml`:
```yaml
data:
  ELASTICSEARCH_URL: "http://elasticsearch.elasticsearch.svc:9200"
  ELASTICSEARCH_INDEX_PATTERN: "logs-*"
  APM_INDEX_PATTERN: "apm-*"
  PROMETHEUS_URL: "http://prometheus.monitoring.svc:9090"
  K8S_NAMESPACES: '["default","production","staging"]'
  ALERT_CHECK_INTERVAL_SECONDS: "30"
  CORS_ORIGINS: '["https://monitor.yourdomain.com"]'
  POLL_INTERVAL_SECONDS: "10"
  REQUEST_TIMEOUT_SECONDS: "5"
  AUTH_ENABLED: "true"
```

### Bước 5: Cập nhật Secret

```bash
# Generate secrets
export ES_PASS=$(python3 -c "import secrets; print(secrets.token_hex(16))")
export AUTH_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
export API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

Sửa `k8s/backend/secret.yaml`:
```yaml
stringData:
  ELASTICSEARCH_USERNAME: "elastic"
  ELASTICSEARCH_PASSWORD: "your_real_es_password"
  AUTH_SECRET: "generated_secret_here"
  API_KEYS: "generated_api_key_here"
```

Hoặc dùng sealed-secrets/external-secrets cho production.

### Bước 6: Cập nhật Ingress domain

Sửa `k8s/ingress.yaml`:
```yaml
spec:
  rules:
    - host: monitor.yourdomain.com    # Đổi thành domain của bạn
```

### Bước 7: Deploy

```bash
# Tạo namespace
kubectl apply -f k8s/namespace.yaml

# Deploy backend
kubectl apply -f k8s/backend/rbac.yaml
kubectl apply -f k8s/backend/configmap.yaml
kubectl apply -f k8s/backend/secret.yaml
kubectl apply -f k8s/backend/service.yaml
kubectl apply -f k8s/backend/deployment.yaml

# Deploy frontend
kubectl apply -f k8s/frontend/service.yaml
kubectl apply -f k8s/frontend/deployment.yaml

# Deploy ingress
kubectl apply -f k8s/ingress.yaml
```

### Bước 8: Verify

```bash
# Kiểm tra pods đang chạy
kubectl get pods -n devops-monitor

# Kiểm tra services
kubectl get svc -n devops-monitor

# Kiểm tra ingress
kubectl get ingress -n devops-monitor

# Xem logs
kubectl logs -f deployment/monitor-backend -n devops-monitor
```

### Bước 9: Lấy token và truy cập

```bash
# Port-forward để test
kubectl port-forward svc/monitor-backend 8000:8000 -n devops-monitor

# Lấy token
curl -X POST http://localhost:8000/auth/token \
  -H "X-API-Key: your_api_key"
```

Truy cập: https://monitor.yourdomain.com

---

## 4. Xử lý sự cố thường gặp

### 4.1 Backend không start

**Symptoms:** Container restart loop, backend logs showing errors.

**Diagnosis:**
```bash
# Check logs
docker compose logs backend
kubectl logs deployment/monitor-backend -n devops-monitor --tail=100 -f

# Common issues in logs:
# - "Cannot connect to Elasticsearch" → Check ES URL
# - "AUTH_SECRET not set" → Generate and set in .env/Secret
# - "Invalid K8S_NAMESPACES format" → Must be JSON array
```

**Fix:** Đảm bảo tất cả required env vars được set đúng format.

---

### 4.2 Backend không kết nối được Elasticsearch

**Symptoms:** `Overview` page không hiện logs data.

**Diagnosis:**
```bash
# Test từ local
curl -u elastic:password http://your-es:9200/_cluster/health

# Test từ trong container
docker compose exec backend curl -s http://elasticsearch:9200/_cluster/health
kubectl exec -it deployment/monitor-backend -n devops-monitor -- \
  curl -s http://elasticsearch.elasticsearch.svc:9200/_cluster/health
```

**Fix:**
1. Verify `ELASTICSEARCH_URL` trong `.env` hoặc ConfigMap
2. Check username/password
3. Verify network connectivity (same cluster VPC)
4. Check Elasticsearch health status: `curl http://es:9200/_cluster/health?pretty`

---

### 4.3 Prometheus metrics không hiển thị

**Symptoms:** Infrastructure metrics không có data.

**Diagnosis:**
```bash
# Test Prometheus API
curl http://prometheus:9090/api/v1/query?query=up

# Test từ container
docker compose exec backend curl -s http://prometheus:9090/api/v1/query?query=up
```

**Fix:**
1. Verify `PROMETHEUS_URL` trong config
2. Check Prometheus is actually running
3. Verify network reachability

---

### 4.4 Kubernetes data không hiển thị

**Symptoms:** Pod/Deployment sections empty.

**Diagnosis:**
```bash
# Check kubeconfig path (dev)
echo $KUBECONFIG_PATH
cat $KUBECONFIG_PATH

# Test kubectl access
kubectl get pods --all-namespaces

# From container (prod)
kubectl auth can-i list pods --all-namespaces \
  --as=system:serviceaccount:devops-monitor:monitor-backend
```

**Fix:**
1. **Dev (Docker Compose):** Mount kubeconfig volume:
   ```yaml
   # docker-compose.yml
   volumes:
     - ~/.kube/config:/root/.kube/config:ro
   ```
2. **Prod (K8s):** Verify RBAC permissions:
   ```bash
   kubectl get clusterrole monitor-backend -o yaml
   kubectl get clusterrolebinding monitor-backend -o yaml
   ```

---

### 4.5 Frontend không gọi được API

**Symptoms:** Browser console shows CORS errors, API calls fail.

**Diagnosis:**
```bash
# Check CORS origin
grep CORS_ORIGINS .env
kubectl get cm monitor-backend-config -n devops-monitor -o yaml | grep CORS
```

**Fix:** Update `CORS_ORIGINS` với chính xác frontend URL:
```bash
# Dev
CORS_ORIGINS='["http://localhost:3000"]'

# Prod
CORS_ORIGINS='["https://monitor.yourdomain.com"]'
```

---

### 4.6 Auth không hoạt động

**Symptoms:** 401 Unauthorized errors.

**Diagnosis:**
```bash
# Check logs for auth errors
docker compose logs backend | grep -i auth
kubectl logs deployment/monitor-backend -n devops-monitor | grep -i auth

# Verify secrets not empty
grep AUTH_SECRET .env
kubectl get secret monitor-backend-secrets -n devops-monitor -o yaml
```

**Fix:** Ensure AUTH_SECRET và API_KEYS được generated và set:
```bash
# Re-generate if needed
AUTH_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

---

### 4.7 WebSocket không hoạt động qua Ingress

**Symptoms:** Real-time updates không work, browser falls back to polling.

**Diagnosis:** Check browser console for WebSocket connection errors.

**Fix:** Ensure ingress has required annotations:
```yaml
nginx.ingress.kubernetes.io/websocket-services: "monitor-backend"
nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
```

(Đã có sẵn trong `k8s/ingress.yaml`)

---

### 4.8 AI Triage Cards không work

**Symptoms:** `POST /api/v1/analyze` returns "LLM service not configured".

**Diagnosis:**
```bash
# Check API key is set
grep ANTHROPIC_API_KEY .env

# Test health endpoint
curl http://localhost:8000/api/v1/analyze/health
```

**Fix:**
1. Get API key from https://console.anthropic.com/
2. Set in `.env`: `ANTHROPIC_API_KEY=sk-ant-api03-...`
3. Restart backend: `docker compose restart backend`

---

### 4.9 Nhiều namespace không hiển thị

**Symptoms:** Chỉ thấy 1 namespace hoặc không thấy namespace nào.

**Diagnosis:**
```bash
# Check format
grep K8S_NAMESPACES .env
kubectl get cm monitor-backend-config -n devops-monitor -o yaml | grep K8S_NAMESPACES
```

**Fix:** Ensure valid JSON array format:
```bash
# Đúng
K8S_NAMESPACES='["default","production","staging"]'

# Sai (thiếu ngoặc hoặc dấu nháy)
K8S_NAMESPACES=default,production
K8S_NAMESPACES=["default","production"]  # Sai khi ở trong YAML mà không quote lại
```

---

### 4.10 High memory usage

**Symptoms:** Pods getting OOMKilled.

**Diagnosis:**
```bash
# Check memory usage
docker stats
kubectl top pod -n devops-monitor

# Check limits
kubectl get deployment monitor-backend -n devops-monitor -o yaml | grep -A 5 resources
```

**Fix:** Increase memory limits:
```yaml
# k8s/backend/deployment.yaml
resources:
  requests:
    memory: "256Mi"
  limits:
    memory: "512Mi"
```

---

## 5. Checklist triển khai Production

- [ ] Đổi tất cả mật khẩu trong Secret (không dùng giá trị mẫu)
- [ ] Generate AUTH_SECRET ngẫu nhiên
- [ ] Generate API_KEYS ngẫu nhiên
- [ ] Đổi domain trong Ingress
- [ ] Đổi CORS_ORIGINS thành domain thật
- [ ] Đổi image thành registry của bạn
- [ ] Kiểm tra ES/Prometheus URL đúng service name trong cluster
- [ ] Cấu hình TLS certificate (cert-manager hoặc manual)
- [ ] Kiểm tra RBAC quyền đọc pods/deployments/events
- [ ] Test alert notification (Slack/Email)
