# Hướng dẫn triển khai — Kubernetes & Docker Swarm

Hướng dẫn triển khai **DevOps AI Agentics 2026** (backend FastAPI + frontend React + Redis + PostgreSQL/TimescaleDB) lên **Kubernetes** (khuyến nghị cho production, manifests sẵn trong `k8s/`) hoặc **Docker Swarm** (môi trường đơn giản hơn, dùng `docker-stack.yml` ở thư mục gốc).

> **Scale backend — đã hỗ trợ ≥2 replica (cập nhật H1, 2026-08-30).**
> Trước đây AlertEngine chạy in-process và WebSocket broadcast là pod-local, nên ≥2 replica **nhân đôi alert và mất realtime event** (review H1, 2026-08-29). Giờ đã có 2 cơ chế flag-gated (mặc định **tắt**, cần Redis):
> - `ALERT_ENGINE_LEADER_LOCK=true` — bầu 1 leader qua Redis lock cho AlertEngine + SloReporter (không còn alert/report nhân bản; leader chết thì lock TTL 30s hết hạn, pod khác tự nhận vai).
> - `WS_FANOUT_USE_REDIS=true` — fanout broadcast `/ws/live` qua Redis pub/sub đến mọi pod (không còn mất realtime event).
> Khi scale: bật cả 2 flag (`k8s/backend/configmap.yaml` hoặc biến env của `docker-stack.yml`). Lưu ý: volume `data/` là **ReadWriteOnce** — nếu cần endpoint sửa alert rule/SLO config hoạt động trên mọi pod, đổi sang RWX; nếu không, chỉ leader ghi state nên an toàn, còn rule edit nên thực hiện khi 1 replica hoặc dùng RWX. Frontend thì thoải mái scale.

## Tài khoản người dùng (Phase 13)

Frontend đăng nhập bằng username/password (`POST /auth/login`), token có `sub=<username>` và RBAC role (`admin`/`operator`/`viewer`). Người dùng lưu ở `data/users.json` (scrypt). Tạo user đầu tiên:

```bash
cd backend && python -m app.users create <name> --role admin
```

API key (`X-API-Key`) vẫn dùng cho automation — token mint qua `/auth/token` mang `sub="service"`, RBAC environment-keyed như cũ. `VITE_API_KEY` đã bỏ khỏi frontend bundle.

## Kiến trúc & phụ thuộc

| Thành phần | Image | Ghi chú |
|---|---|---|
| Backend | `${REGISTRY}/devops-monitor-backend` | FastAPI, port 8000, `/health`, non-root, đọc/ghi `data/` (alert rules/state, SLO configs) |
| Frontend | `${REGISTRY}/devops-monitor-frontend` | nginx (stage `prod` của `frontend/Dockerfile`), port 80, proxy `/api` + `/ws` → backend |
| Redis | `redis:7.2-alpine` | Alert state, approvals, rate limit, L2 cache — bật qua flag `*_USE_REDIS` |
| PostgreSQL | `timescale/timescaledb:2-pg16` | Bất bắt buộc — mirror audit/approval + analytics; migration 002 cần TimescaleDB extension |
| Ngoài hệ thống | — | Elasticsearch (logs + `apm-*`), Prometheus, K8s API (optional), Anthropic API (Triage Cards) |

Frontend không gọi backend trực tiếp qua URL tuyệt đối — nginx.conf proxy `monitor-backend:8000`, nên **tên service backend bắt buộc là `monitor-backend`** trên cả 2 nền tảng (đã đúng sẵn trong `k8s/` và `docker-stack.yml`).

---

## Phần A — Kubernetes

### A.1. Yêu cầu

- Cluster K8s 1.28+ (manifests dùng `networking.k8s.io/v1`, `apps/v1`)
- `ingress-nginx` đã cài (Ingress class `nginx`)
- StorageClass mặc định có khả năng cấp PVC (backend cần 1Gi `alert-data-pvc`)
- Optional: `cert-manager` cho TLS tự động, `metrics-server`
- Registry accessible từ cluster (ACR/GCR/ECR/Harbor/self-hosted)

### A.2. Build & push images

```bash
# Tag theo registry của bạn
export REGISTRY=your-registry.example.com/devops-monitor
export TAG=v1.0.0   # dùng tag immutable, tránh :latest

docker build -t $REGISTRY/devops-monitor-backend:$TAG ./backend
docker build -t $REGISTRY/devops-monitor-frontend:$TAG --target prod ./frontend
docker push $REGISTRY/devops-monitor-backend:$TAG
docker push $REGISTRY/devops-monitor-frontend:$TAG
```

Sửa `image:` trong `k8s/backend/deployment.yaml`, `k8s/frontend/deployment.yaml` theo `$REGISTRY/...:$TAG`.

### A.3. Tạo secrets

Secrets trong repo là **template** — không commit giá trị thật (xem `docs/security-review-2026-08-20.md`). Prod nên dùng external-secrets/sealed-secrets (manifests sẵn ở `k8s/external-secrets/`), còn cách nhanh:

```bash
# Sinh giá trị
python3 -c "import secrets; print(secrets.token_hex(32))"   # AUTH_SECRET
python3 -c "import secrets; print(secrets.token_hex(32))"   # mỗi API key

# Điền vào k8s/backend/secret.yaml (stringData) rồi apply,
# hoặc tạo trực tiếp không qua file:
kubectl create secret generic monitor-backend-secrets -n devops-monitor \
  --from-literal=ELASTICSEARCH_USERNAME=elastic \
  --from-literal=ELASTICSEARCH_PASSWORD='<mật-khẩu-es>' \
  --from-literal=AUTH_SECRET='<token_hex_32>' \
  --from-literal=API_KEYS='<key1>,<key2>' \
  --from-literal=SLACK_WEBHOOK_URL='' \
  --from-literal=SMTP_HOST='' --from-literal=SMTP_PORT='587' \
  --from-literal=SMTP_USER='' --from-literal=SMTP_PASSWORD='' \
  --from-literal=ALERT_EMAIL_FROM='' --from-literal=ALERT_WEBHOOK_URL=''
```

`API_KEYS` là danh sách phân tách bằng dấu phẩy — frontend/auth client cần 1 key này. Nếu ứng client thật, điền thêm `ANTHROPIC_API_KEY` (Triage Cards) và `TEAMS_WEBHOOK_SECRET`, `SLACK_SIGNING_SECRET` nếu dùng approvals qua chat (Phase 13: HMAC key của Teams là `TEAMS_WEBHOOK_SECRET`, không phải webhook URL).

### A.4. Deploy theo thứ tự

```bash
# 1) Namespace chính
kubectl apply -f k8s/namespace.yaml

# 2) PostgreSQL (namespace 'postgres') — optional, chỉ cần khi bật DATABASE_ENABLED
kubectl apply -f k8s/postgresql/namespace.yaml
tạo Secret postgres-credentials out-of-band (template: k8s/templates/postgres-credentials-template.yaml)
kubectl apply -f k8s/postgresql/configmap.yaml
kubectl apply -f k8s/postgresql/deployment.yaml
kubectl apply -f k8s/postgresql/service.yaml
kubectl apply -f k8s/postgresql/pdb.yaml

# 3) Redis (manifest mẫu ở ns 'development'; service DNS sẽ là
#    redis.development.svc.cluster.local — hoặc sửa metadata.namespace thành devops-monitor)
kubectl apply -f k8s/monitoring/redis-dev.yaml

# 4) Backend — RBAC, ConfigMap, Secret, PVC, Deployment, Service, NetworkPolicy, PDB
kubectl apply -f k8s/backend/

# 5) Frontend
kubectl apply -f k8s/frontend/

# 6) Ingress + TLS (sửa host monitor.yourdomain.com; secret devops-monitor-tls
#    do cert-manager tạo, hoặc tự cấp: kubectl create secret tls ...)
kubectl apply -f k8s/ingress.yaml
```

Trước bước 4, chỉnh `k8s/backend/configmap.yaml` cho đúng môi trường:

- `ELASTICSEARCH_URL`, `PROMETHEUS_URL` — endpoint thật của ELK/Prometheus
- `K8S_NAMESPACES` — JSON array namespace cần giám sát
- `CORS_ORIGINS` — origin của frontend prod
- Nếu dùng Redis/Postgres trong cluster, thêm flag bật state phân tán (xem A.6)

### A.5. Bật Redis / PostgreSQL state

Mặc định (an toàn nhất khi mới lên): alert/approval state lưu file trong PVC `alert-data-pvc`. Bật dần:

```bash
# Redis state (điểm cộng: không mất state khi pod restart nếu PVC nhỏ)
kubectl -n devops-monitor set env deploy/monitor-backend \
  REDIS_HOST=redis.development.svc.cluster.local \
  ALERT_STATE_USE_REDIS=true \
  APPROVAL_STATE_USE_REDIS=true \
  RATE_LIMIT_USE_REDIS=true

# PostgreSQL mirror (audit + approval events)
kubectl -n devops-monitor set env deploy/monitor-backend \
  DATABASE_ENABLED=true \
  DATABASE_HOST=postgres.postgres.svc.cluster.local \
  DATABASE_NAME=devops_monitor DATABASE_USER=devops
# DATABASE_PASSWORD set qua secret monitor-backend-secrets (A.3)
```

`set env` trigger rollout mới — đợi `rollout status` xanh trước bước tiếp.

### A.6. Migration database

Backend **không** tự chạy migration khi start (3 migration: `001_initial_schema`, `002_timescaledb_metrics` — cần TimescaleDB, `003_approval_events`). Chạy sau khi A.5 rollout xong và postgres healthy:

```bash
kubectl -n devops-monitor exec deploy/monitor-backend -- alembic upgrade head
```

Lệnh đọc `DATABASE_*` từ env của pod (đã trỏ vào `postgres.postgres.svc.cluster.local` ở A.5). Kiểm tra: `kubectl -n devops-monitor exec deploy/monitor-backend -- alembic current`.

### A.7. Kiểm tra sau triển khai

```bash
kubectl -n devops-monitor get pods,svc,ingress
kubectl -n devops-monitor rollout status deploy/monitor-backend
curl -f https://monitor.yourdomain.com/health          # qua ingress
curl -f https://monitor.yourdomain.com/api/v1/overview # cần API key
kubectl -n devops-monitor logs deploy/monitor-backend --tail=100
```

Đủ điều kiện: pod backend `1/1 Running`, probe `/health` pass, frontend trả UI, WS `/ws` kết nối (mở dashboard, thấy live updates), alert engine khởi động trong log.

### A.8. Vận hành

```bash
# Update version
kubectl -n devops-monitor set image deploy/monitor-backend backend=$REGISTRY/devops-monitor-backend:$TAG
kubectl -n devops-monitor set image deploy/monitor-frontend frontend=$REGISTRY/devops-monitor-frontend:$TAG

# Rollback
kubectl -n devops-monitor rollout undo deploy/monitor-backend

# Scale — CHỈ frontend
kubectl -n devops-monitor scale deploy/monitor-frontend --replicas=4
# KHÔNG scale monitor-backend (xem cảnh báo đầu tài liệu)
```

### A.9. Tùy chọn

- **Monitoring stack**: `k8s/monitoring/` — Prometheus (scrape `/metrics` của backend, alert rules đã fix A1), Alertmanager, Grafana dashboards
- **Staging**: `k8s/staging/` (namespace + deployment + RBAC riêng; secret template ở `k8s/templates/`)
- **GitOps**: `k8s/applications/` + `k8s/argocd/` — ArgoCD Application trỏ về repo này
- **Secrets operator**: `k8s/external-secrets/`, Vault HA ở `k8s/secrets/`
- **Backup**: `k8s/postgresql/backup-cronjob.yaml`, `k8s/redis/backup-cronjob.yaml`; runbook khôi phục ở `docs/disaster-recovery-runbook.md`

---

## Phần B — Docker Swarm

Dành cho môi trường 1–3 node không có K8s. Dùng **`docker-stack.yml`** ở thư mục gốc (backend + frontend + redis + postgres/TimescaleDB, overlay network, healthchecks, resource limits).

Khác biệt cần biết trước khi chọn Swarm:

- **Secrets**: config pydantic đọc env trực tiếp, không có cơ chế `_FILE`, nên không dùng `docker secret` nguyên bản — giá trị được thay vào service spec lúc deploy (xem được qua `docker service inspect`). Chấp nhận được cho lab/staging nội bộ; production nhạy cảm thì dùng K8s + external-secrets.
- **Volume local**: Swarm không tự di chuyển volume giữa node. Toàn bộ service có state (backend, redis, postgres) bị **pin vào 1 node qua label**.
- **TLS**: không có Ingress + cert-manager. Publish 80 và đặt một reverse proxy (nginx host / Traefik / LB công ty) phía trước cho HTTPS, hoặc dùng backend LB có TLS.

### B.1. Khởi tạo cluster + label node chứa data

```bash
# Trên node manager
docker swarm init --advertise-addr <IP-manager>

# Trên các node worker
docker swarm join --token <token> <IP-manager>:2377

# Chọn 1 node chạy các service có state, gắn label
docker node update --label-add devops-monitor.data=true <tên-node>

# (Tuỳ chọn) Kubeconfig nếu muốn backend nói chuyện với K8s API:
#   mkdir -p /opt/devops-monitor && cp ~/.kube/config /opt/devops-monitor/kubeconfig
#   rồi bỏ comment volume kubeconfig trong docker-stack.yml
```

### B.2. .env trên manager

Tạo `/opt/devops-monitor/.env` (chmod 600, không commit). Copy từ `.env.example`, bắt buộc có:

```bash
REGISTRY=your-registry.example.com/devops-monitor
TAG=v1.0.0
ELASTICSEARCH_URL=http://your-es:9200
ELASTICSEARCH_USERNAME=elastic
ELASTICSEARCH_PASSWORD=...
PROMETHEUS_URL=http://your-prometheus:9090
AUTH_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
API_KEYS=key1,key2
REDIS_PASSWORD=$(python3 -c "import secrets; print(secrets.token_hex(16))")
DATABASE_PASSWORD=$(python3 -c "import secrets; print(secrets.token_hex(16))")
```

### B.3. Deploy stack

```bash
# Build & push images (giống A.2)
docker stack deploy -c docker-stack.yml monitor --with-registry-auth

# Theo dõi
docker stack services monitor
docker service ps monitor_monitor-backend
docker service logs -f monitor_monitor-backend
```

`--with-registry-auth` để worker pull image từ registry private. Stack **không** publish port 8000 — chỉ frontend 80; traffic `/api`, `/ws` đi qua nginx trong image frontend tới `monitor-backend` trên overlay network.

### B.4. Migration database

`docker-stack.yml` bật sẵn `DATABASE_ENABLED=true` + image TimescaleDB. Chạy 1 lần sau khi postgres healthy:

```bash
docker run --rm --network monitor_backend-net \
  -e DATABASE_URL="postgresql+asyncpg://devops:<mật-khẩu>@postgres:5432/devops_monitor" \
  $REGISTRY/devops-monitor-backend:$TAG alembic upgrade head
```

### B.5. TLS

Cách tối thiểu: nginx trên host manager (hoặc LB trước swarm) terminate HTTPS 443 → `proxy_pass http://127.0.0.1:80` (frontend đã proxy `/api`, `/ws`). Nhớ tăng `proxy_read_timeout` cho WebSocket (tương đương annotation `3600` trong `k8s/ingress.yaml`).

### B.6. Kiểm tra & vận hành

```bash
curl -f http://<manager>/health
docker service ls                                   # mọi service 1/1 (frontend 2/2)
docker service update --image $REGISTRY/devops-monitor-backend:$TAG monitor_monitor-backend
docker service rollback monitor_monitor-backend
docker service scale monitor_monitor-frontend=3     # CHỈ frontend
```

Update backend/redis/postgres dùng `docker service update` (rolling, giữ nguyên volume). Backup: `docker exec <postgres-container> pg_dump ...` — đối chiếu `docs/disaster-recovery-runbook.md`.

---

## Checklist sau triển khai (cả 2 nền tảng)

- [ ] `/health` trả 200 qua hostname public
- [ ] Dashboard load, `/ws` live updates chạy (không rơi về REST polling)
- [ ] Overview hiển thị dữ liệu thật từ ELK + Prometheus (không phải lỗi kết nối)
- [ ] Tạo 1 action test → approve → execute chạy trọn vòng (audit log ghi cả file/Redis + Postgres mirror)
- [ ] Alert engine log khởi động, test 1 rule ra Slack/email
- [ ] `AUTH_SECRET`, `API_KEYS` khác giá trị dev; CORS khớp domain prod
- [ ] Backup cron (Postgres/Redis) + PVC/volume đã tạo
- [ ] Backend đúng 1 replica trên cả 2 nền tảng
