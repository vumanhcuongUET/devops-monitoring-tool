# DevOps Monitor - Hướng dẫn triển khai

## 1. Yêu cầu hạ tầng

### Các hệ thống cần có sẵn (tool không tự cài)

| Hệ thống | Mục đích | Cần có trước? |
|----------|----------|---------------|
| **Elasticsearch** (7.x+) | Logs + APM data | Có |
| **Elastic APM Server** | APM agents gửi data → ES | Có (APM data nằm trong ES) |
| **Prometheus** | Infrastructure metrics | Có |
| **Kubernetes cluster** | Pod/deployment/event data | Có |

### Tài nguyên tối thiểu

| Môi trường | CPU | RAM | Disk |
|------------|-----|-----|------|
| Dev (Docker Compose) | 1 core | 1 GB | 1 GB |
| Prod (K8s, 2 replicas) | 1 core | 1 GB | 1 GB PVC |

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
cd devops-monitor-tools
cp .env.example .env
```

### Bước 3: Chỉnh sửa .env

```bash
# ===== BẮT BUỘC =====

# Elasticsearch
ELASTICSEARCH_URL=http://10.0.0.10:9200          # Địa chỉ ES của bạn
ELASTICSEARCH_USERNAME=elastic
ELASTICSEARCH_PASSWORD=your_strong_password

# Prometheus
PROMETHEUS_URL=http://10.0.0.11:9090              # Địa chỉ Prometheus của bạn

# Kubernetes (khi chạy ngoài cluster)
KUBECONFIG_PATH=/home/user/.kube/config            # Đường dẫn kubeconfig

# Hoặc nhiều namespace
K8S_NAMESPACES=["default","production","staging"]

# Auth
AUTH_ENABLED=true
AUTH_SECRET=                                        # Chạy lệnh dưới để generate
API_KEYS=[]                                         # Chạy lệnh dưới để generate
```

Generate auth keys:

```bash
# Generate AUTH_SECRET
python3 -c "import secrets; print('AUTH_SECRET=' + secrets.token_hex(32))"

# Generate API_KEY
python3 -c "import secrets; print('API_KEY=' + secrets.token_hex(32))"
```

Kết quả ví dụ:
```
AUTH_SECRET=a1b2c3d4e5f6...64chars
API_KEYS=["f6e5d4c3b2a1...64chars"]
```

Điền vào `.env`:

```bash
AUTH_SECRET=a1b2c3d4e5f6...64chars
API_KEYS=["f6e5d4c3b2a1...64chars"]
```

### Bước 4: Chạy

```bash
docker compose up -d
```

### Bước 5: Lấy token để truy cập

```bash
# Dùng API key để lấy Bearer token
curl -X POST http://localhost:8000/auth/token \
  -H "X-API-Key: your_api_key_here"
```

Response:
```json
{"access_token": "eyJ...", "token_type": "bearer"}
```

### Bước 6: Truy cập

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- Token tự động lưu vào localStorage khi frontend gửi request

### Bước 7: Dừng

```bash
docker compose down          # Dừng, giữ data
docker compose down -v       # Dừng, xóa hết data
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

### Backend không kết nối được Elasticsearch

```bash
# Kiểm tra kết nối từ trong pod
kubectl exec -it deployment/monitor-backend -n devops-monitor -- \
  curl -s http://elasticsearch:9200/_cluster/health

# Nếu lỗi, kiểm tra ES URL trong configmap
kubectl get configmap monitor-backend-config -n devops-monitor -o yaml
```

### Frontend không gọi được API

```bash
# Kiểm tra ingress
kubectl describe ingress devops-monitor -n devops-monitor

# Kiểm tra CORS_ORIGINS trong configmap có đúng domain frontend không
```

### Auth không hoạt động

```bash
# Kiểm tra logs
kubectl logs deployment/monitor-backend -n devops-monitor | grep -i auth

# Đảm bảo AUTH_SECRET và API_KEYS không rỗng trong secret
kubectl get secret monitor-backend-secrets -n devops-monitor -o yaml
```

### WebSocket không hoạt động qua Ingress

Đảm bảo ingress có annotation:
```yaml
nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
```
(V đã có sẵn trong ingress.yaml)

### Nhiều namespace không hiển thị

Kiểm tra K8S_NAMESPACES trong ConfigMap là JSON array hợp lệ:
```bash
# Đúng
K8S_NAMESPACES: '["default","production","staging"]'

# Sai (thiếu ngoặc hoặc dấu nháy)
K8S_NAMESPACES: default,production
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
