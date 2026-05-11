<div align="center">

# DevOps Monitor

**Unified NOC-style monitoring dashboard for modern infrastructure**

Aggregating Elasticsearch, Elastic APM, Prometheus & Kubernetes into one real-time interface.

[![Backend](https://img.shields.io/badge/Backend-Python%20FastAPI-3776AB?logo=python&logoColor=white)](https://fastapi.tiangolo.com)
[![Frontend](https://img.shields.io/badge/Frontend-React%2019%20%2B%20TypeScript-3178C6?logo=typescript&logoColor=white)](https://react.dev)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[Features](#-features) · [Tech Stack](#-tech-stack) · [Quick Start](#-quick-start) · [Configuration](#-configuration) · [Deploy](#-deploy) · [Security](#-security)

</div>

---

## Why DevOps Monitor?

You already have Elasticsearch, Prometheus, and Kubernetes — each with its own UI. **DevOps Monitor unifies them** into a single dashboard so your team can see system health at a glance, without switching between 5 tabs.

- **One dashboard** — K8s, logs, APM, SLOs, infrastructure metrics all in one place
- **Real-time** — WebSocket push for overview updates and alert events
- **Unified alerting** — Rules across all data sources, notify via Slack/Email/Webhook
- **SLO tracking** — Availability & latency SLOs with error budget tracking + daily Slack reports
- **Lightweight** — No database, no agent. Just aggregates data from your existing tools
- **Secure** — Auth, SSRF protection, rate limiting, security headers out of the box

---

## Features

### Overview Dashboard
Single NOC-style view showing health status of all systems — Kubernetes, Elasticsearch, APM, and Infrastructure — with active alerts and recent events. Auto-updates via WebSocket.

### Log Management
Full-text search across Elasticsearch logs with filtering by level, service, and time range. Paginated results with configurable page size.

### APM Monitoring
Transaction latency breakdown (P50/P95/P99), error tracking with automatic grouping, and per-service filtering. Data sourced directly from Elastic APM indices.

### SLO Management
Define availability and latency SLOs per service with 7-day or 30-day rolling windows. Automatic error budget calculation, slow API detection, and daily Slack report.

### Kubernetes Monitoring
Pod status, deployment health, and cluster events across multiple namespaces. Filter by namespace from the frontend.

### Infrastructure Metrics
Node-level CPU, memory, and disk utilization from Prometheus with sparkline history charts.

### Alerting Engine
Background alert evaluation across all data sources (ES, APM, Prometheus, K8s) with configurable rules, severity levels, duration thresholds, and multi-channel notifications.

### Security
HMAC-signed Bearer tokens + API key authentication, SSRF protection, input validation, rate limiting, non-root containers, K8s security contexts, and full nginx security headers.

---

## Tech Stack

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (React 19)                    │
│  TypeScript · Vite 8 · Tailwind CSS 4 · Recharts ·      │
│  TanStack Query · React Router 7 · Axios                 │
└──────────────────────────┬──────────────────────────────┘
                           │ REST / WebSocket
┌──────────────────────────▼──────────────────────────────┐
│                   Backend (FastAPI)                       │
│  Python 3.12 · Pydantic v2 · async/await · httpx        │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐ │
│  │ ES Client    │ │ APM Client   │ │ SLO Client       │ │
│  └──────┬───────┘ └──────┬───────┘ └────────┬─────────┘ │
│  ┌──────┴───────┐ ┌──────┴───────┐ ┌────────┴─────────┐ │
│  │ Prom Client  │ │  K8s Client  │ │  Alert Engine    │ │
│  └──────────────┘ └──────────────┘ └──────────────────┘ │
└──────────────────────────┬──────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼─────┐    ┌──────▼──────┐   ┌──────▼──────┐
   │ Elastic  │    │  Prometheus │   │ Kubernetes  │
   │ search   │    │             │   │  API Server │
   └──────────┘    └─────────────┘   └─────────────┘
```

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose
- Running instances of: **Elasticsearch**, **Prometheus**, **Kubernetes cluster**

### 1. Clone & Configure

```bash
git clone https://github.com/your-org/devops-monitor-tools.git
cd devops-monitor-tools
cp .env.example .env
```

### 2. Edit `.env`

```bash
# Required — point to your infrastructure
ELASTICSEARCH_URL=http://10.0.0.10:9200
ELASTICSEARCH_PASSWORD=your_password
PROMETHEUS_URL=http://10.0.0.11:9090

# Multiple K8s namespaces
K8S_NAMESPACES=["default","production","staging"]

# Generate auth credentials
AUTH_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
API_KEYS=["$(python3 -c "import secrets; print(secrets.token_hex(32))")"]
```

### 3. Launch

```bash
docker compose up -d
```

### 4. Access

| URL | Description |
|-----|-------------|
| `http://localhost:3000` | Dashboard |
| `http://localhost:8000/docs` | API Documentation (Swagger) |

### 5. Authenticate

```bash
# Get Bearer token using your API key
curl -X POST http://localhost:8000/auth/token \
  -H "X-API-Key: your_api_key"
```

The frontend automatically uses the API key from `VITE_API_KEY` env var and manages tokens.

---

## Dashboard Preview

```
┌────────────────────────────────────────────────────────────────┐
│  DevOps Monitor                                    🔴 3 alerts │
├──────────┬──────────┬──────────┬──────────────────────────────┤
│  K8s     │  Elastic │   APM    │  Infrastructure              │
│  ● OK    │  ● OK    │  ⚠ WARN │  ● OK                        │
│  12 pods │  0 err/h │ 45ms    │  CPU 32%  MEM 61%            │
│  3 deploys│  green  │  2.1% err│  4 nodes  4 healthy          │
├──────────┴──────────┴──────────┴──────────────────────────────┤
│  Recent Alerts                                                 │
│  🔴 CRITICAL  High Error Rate   production-api   5m ago       │
│  🟡 WARNING   Memory Usage      node-worker-02   12m ago      │
│  🟢 RESOLVED  Pod Restarts      staging-backend  1h ago       │
└────────────────────────────────────────────────────────────────┘
```

---

## Configuration

All configuration is via environment variables (`.env` file or K8s ConfigMap/Secret).

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `ELASTICSEARCH_URL` | Elasticsearch endpoint | `http://es:9200` |
| `ELASTICSEARCH_PASSWORD` | ES password | — |
| `PROMETHEUS_URL` | Prometheus endpoint | `http://prom:9090` |
| `AUTH_SECRET` | HMAC signing key (generate randomly) | 64-char hex |
| `API_KEYS` | List of valid API keys | `["abc..."]` |

### Kubernetes

| Variable | Description | Default |
|----------|-------------|---------|
| `KUBECONFIG_PATH` | Leave empty for in-cluster | `""` |
| `K8S_NAMESPACES` | JSON array of namespaces | `["default"]` |

### Notifications

| Variable | Description |
|----------|-------------|
| `SLACK_WEBHOOK_URL` | Slack incoming webhook |
| `SMTP_HOST` / `SMTP_PORT` | Email server |
| `SMTP_USER` / `SMTP_PASSWORD` | Email credentials |
| `ALERT_EMAIL_FROM` / `ALERT_EMAIL_TO` | Email addresses |
| `ALERT_WEBHOOK_URL` | Generic webhook URL |

### SLO Reporting

| Variable | Description | Default |
|----------|-------------|---------|
| `SLO_REPORT_ENABLED` | Enable daily report | `true` |
| `SLO_REPORT_HOUR` | Hour to send (24h) | `9` |
| `SLO_REPORT_TIMEZONE` | Timezone | `Asia/Ho_Chi_Minh` |

### Tuning

| Variable | Description | Default |
|----------|-------------|---------|
| `ALERT_CHECK_INTERVAL_SECONDS` | Alert evaluation cycle | `30` |
| `POLL_INTERVAL_SECONDS` | Frontend polling interval | `10` |
| `REQUEST_TIMEOUT_SECONDS` | API client timeout | `5` |
| `CORS_ORIGINS` | Allowed origins (JSON array) | `["http://localhost:3000"]` |

---

## Deploy

### Docker Compose (Dev/Staging)

```bash
docker compose up -d
```

Resource limits pre-configured: Backend (512MB, 1 CPU), Frontend (256MB, 0.5 CPU).

### Kubernetes (Production)

```bash
# Build & push images
docker build -t your-registry/devops-monitor-backend:latest ./backend
docker build -t your-registry/devops-monitor-frontend:latest --target prod ./frontend
docker push your-registry/devops-monitor-backend:latest
docker push your-registry/devops-monitor-frontend:latest

# Update image references in k8s manifests, then deploy
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/backend/
kubectl apply -f k8s/frontend/
kubectl apply -f k8s/ingress.yaml
```

Production manifests include:
- 2 replicas per service (high availability)
- Pod security contexts (non-root, drop capabilities)
- RBAC with read-only ClusterRole
- Persistent volume for alert data
- Health probes (liveness + readiness)
- Resource requests & limits

See [DEPLOY.md](DEPLOY.md) for the complete step-by-step guide.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/overview` | System health overview (all 4 systems) |
| `GET` | `/api/v1/logs` | Search Elasticsearch logs |
| `GET` | `/api/v1/apm/transactions` | APM transaction metrics |
| `GET` | `/api/v1/apm/errors` | APM error tracking |
| `GET` | `/api/v1/apm/summary` | APM summary (latency, error rate) |
| `GET` | `/api/v1/kubernetes/pods` | K8s pod status |
| `GET` | `/api/v1/kubernetes/deployments` | K8s deployment status |
| `GET` | `/api/v1/kubernetes/events` | K8s events |
| `GET` | `/api/v1/infrastructure/metrics` | Node metrics from Prometheus |
| `GET` | `/api/v1/slo/dashboard` | SLO overview with budgets |
| `GET` | `/api/v1/slo/service/{name}` | Per-service SLO |
| `GET` | `/api/v1/slo/service/{name}/slow-apis` | APIs not meeting SLO |
| `GET/POST/PUT/DELETE` | `/api/v1/slo/configs` | SLO configuration CRUD |
| `GET/POST/PUT/DELETE` | `/api/v1/alerts/rules` | Alert rule CRUD |
| `GET` | `/api/v1/alerts/history` | Alert event history |
| `POST` | `/auth/token` | Generate Bearer token |
| `WS` | `/ws/live` | Real-time updates |

Interactive docs available at `/docs` (Swagger UI).

---

## Security

| Feature | Implementation |
|---------|---------------|
| **Authentication** | HMAC-signed Bearer tokens + API key (`X-API-Key` header) |
| **Authorization** | All endpoints protected except `/health` and `/docs` |
| **SSRF Protection** | Blocks internal IPs for webhook URLs (127.x, 10.x, 172.16-31, 192.168.x, 169.254.x) |
| **Input Validation** | Identifier validation, ES query sanitization, max length constraints |
| **Rate Limiting** | 60 req/min per IP, burst protection (20 req/2s) |
| **CORS** | Configurable origins, restricted headers |
| **Container Security** | Non-root user in Docker, K8s security contexts (runAsNonRoot, drop ALL capabilities) |
| **Security Headers** | CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy |

---

## Resource Usage

DevOps Monitor is designed to be **lightweight** — it does not store data or run agents.

| Component | CPU | RAM | Notes |
|-----------|-----|-----|-------|
| Backend | 50-100m idle | 80-150 MB | Single async process |
| Frontend | 10-20m | 15-30 MB | Static files via nginx |
| Disk | — | 1 GB PVC | JSON state files only |

Minimum requirement: **1 CPU + 1 GB RAM** for the entire stack.

---

## Project Structure

```
devops-monitor-tools/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI entry point
│   │   ├── config.py               # Environment configuration
│   │   ├── auth.py                 # Authentication (HMAC + API key)
│   │   ├── security.py             # SSRF protection + input validation
│   │   ├── rate_limit.py           # In-memory rate limiter
│   │   ├── api/
│   │   │   ├── v1/                 # REST endpoints
│   │   │   │   ├── overview.py
│   │   │   │   ├── logs.py
│   │   │   │   ├── apm.py
│   │   │   │   ├── kubernetes.py
│   │   │   │   ├── alerts.py
│   │   │   │   ├── slo.py
│   │   │   │   └── infrastructure.py
│   │   │   └── ws/
│   │   │       └── live.py         # WebSocket endpoint
│   │   ├── services/               # Data source clients
│   │   │   ├── elasticsearch_client.py
│   │   │   ├── apm_client.py
│   │   │   ├── prometheus_client.py
│   │   │   ├── kubernetes_client.py
│   │   │   └── slo_client.py
│   │   ├── alerting/               # Alert engine + SLO reporting
│   │   │   ├── engine.py
│   │   │   ├── rules.py
│   │   │   ├── state.py
│   │   │   ├── notifiers.py
│   │   │   └── slo_reporter.py
│   │   └── models/                 # Pydantic data models
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/                  # Dashboard pages
│   │   ├── components/             # Reusable UI components
│   │   ├── hooks/                  # React hooks (WebSocket, polling, auth)
│   │   ├── api/                    # API client modules
│   │   ├── types/                  # TypeScript type definitions
│   │   └── utils/                  # Helpers & constants
│   ├── nginx.conf                  # Production server config
│   ├── Dockerfile
│   └── package.json
├── k8s/                            # Kubernetes manifests
│   ├── namespace.yaml
│   ├── backend/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml
│   │   ├── secret.yaml
│   │   └── rbac.yaml
│   ├── frontend/
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   └── ingress.yaml
├── docker-compose.yml
├── .env.example
├── DEPLOY.md
└── CLAUDE.md
```

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built with FastAPI · React · Elasticsearch · Prometheus · Kubernetes**

</div>
