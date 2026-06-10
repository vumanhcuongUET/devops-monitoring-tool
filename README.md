<div align="center">

# DevOps AI Agentics 2026

**Unified DevOps monitoring platform with AI-powered observability**

Aggregating Elasticsearch, APM, Prometheus & Kubernetes with AI-powered incident analysis.

[![Backend](https://img.shields.io/badge/Backend-Python%20FastAPI-3776AB?logo=python&logoColor=white)](https://fastapi.tiangolo.com)
[![Frontend](https://img.shields.io/badge/Frontend-React%2019%20%2B%20TypeScript-3178C6?logo=typescript&logoColor=white)](https://react.dev)
[![AI](https://img.shields.io/badge/AI-Anthropic%20Claude-7B4AE2?logo=anthropic&logoColor=white)](https://claude.ai)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[Features](#-features) · [Quick Start](#-quick-start) · [API Docs](#-api-endpoints) · [Deploy](#-deploy) · [Strategy](#-strategy)

</div>

---

## Overview

**DevOps AI Agentics 2026** is a comprehensive monitoring platform that unifies multiple observability tools with AI-powered incident analysis.

### Components

1. **DevOps Monitor** — Unified NOC-style dashboard aggregating Elasticsearch, APM, Prometheus & Kubernetes
2. **AI Assistant** — Claude CLI-powered copilot for natural language monitoring queries
3. **AI Triage Cards** — Claude API integration for automated incident analysis and recommendations

### Why This Platform?

You already have Elasticsearch, Prometheus, and Kubernetes — each with its own UI. This platform **unifies them** into a single dashboard AND adds AI-powered insights:

- **One dashboard** — K8s, logs, APM, SLOs, infrastructure metrics all in one place
- **AI Triage Cards** — Automated incident analysis with root cause identification and recommendations
- **Real-time** — WebSocket push for overview updates and alert events
- **Alert Statistics** — Prometheus alerts breakdown by namespace
- **Unified alerting** — Rules across all data sources, notify via Webhook/Email
- **SLO tracking** — Availability & latency SLOs with error budget tracking
- **Lightweight** — No database, no agent. Just aggregates data from your existing tools
- **Secure** — Auth, SSRF protection, rate limiting, security headers out of the box

See [docs/chien_luoc_tong_the.md](docs/chien_luoc_tong_the.md) for the complete 4-phase strategic roadmap.

---

## 📋 Features

### Monitoring Dashboard

**Overview Dashboard** — Single NOC-style view showing health status of all systems with active alerts and auto-updates via WebSocket.

**Log Management** — Full-text search across Elasticsearch logs with filtering by level, service, and time range.

**APM Monitoring** — Transaction latency breakdown (P50/P95/P99), error tracking with automatic grouping.

**SLO Management** — Define availability and latency SLOs per service with automatic error budget calculation.

**Kubernetes Monitoring** — Pod status, deployment health, and cluster events across multiple namespaces.

**Infrastructure Metrics** — Node-level CPU, memory, and disk utilization from Prometheus.

**Alerting Engine** — Background alert evaluation across all data sources with configurable rules and multi-channel notifications.

### AI-Powered Features

**Triage Card Generation** (`POST /api/v1/analyze`) — AI-powered incident analysis:
- Collects context from logs, APM, metrics, K8s
- Identifies root causes with confidence scores
- Provides prioritized recommendations
- Returns structured JSON with findings and actions

**Prompt Engineering** — Config-driven system prompt optimized for DevOps incident analysis with Vietnamese output support.

**Proactive Insights** — Ask natural language questions and get instant analysis:
```
"Tình trạng hệ thống meinvoice"
"Top slow endpoints meinvoice 30 phút qua"
"Disk usage trên các server meinvoice"
```

### Alert Statistics

**Prometheus Alerts** — Query and analyze alerts from Prometheus:
- Breakdown by namespace
- Severity distribution (critical, warning, info)
- Firing vs pending counts
- Top alerts per namespace

---

## 🏗️ Tech Stack

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
│  │ ES Client    │ │ APM Client   │ │ LLM Client        │ │
│  └──────┬───────┘ └──────┬───────┘ └────────┬─────────┘ │
│  ┌──────┴───────────┴───────────┴────────┴─────────┐     │
│  │ Prom Client  │ K8s Client  │ SLO Client      │     │
│  └──────┬─────────┴────────────┴────────────────┘     │
│         │ Alert Engine                                   │
└─────────┴───────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼─────┐    ┌──────▼──────┐   ┌──────▼──────┐
   │ Elastic  │    │  Prometheus │   │ Kubernetes  │
   │ search   │    │             │   │  API Server │
   └──────────┘    └─────────────┘   └─────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose
- Running instances of: **Elasticsearch**, **Prometheus**, **Kubernetes cluster**
- [Anthropic API key](https://console.anthropic.com/) for AI features

### 1. Clone & Configure

```bash
git clone https://github.com/your-org/devops-ai-agentics-2026.git
cd devops_ai_agentics_2026
cp .env.example .env
```

### 2. Edit `.env`

```bash
# Infrastructure endpoints
ELASTICSEARCH_URL=http://your-es:9200
ELASTICSEARCH_USERNAME=elastic
ELASTICSEARCH_PASSWORD=your_password
PROMETHEUS_URL=http://your-prometheus:9090

# Kubernetes namespaces to monitor
K8S_NAMESPACES=["default","production","staging"]

# Authentication (generate secrets)
AUTH_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
API_KEYS=["$(python3 -c "import secrets; print(secrets.token_hex(32))")"]

# AI / LLM (optional, for Triage Cards)
ANTHROPIC_API_KEY=sk-ant-api03-...
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

---

## 🔌 API Endpoints

### Monitoring Data

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/overview` | System health overview (all systems) |
| `GET` | `/api/v1/logs` | Search Elasticsearch logs |
| `GET` | `/api/v1/apm/transactions` | APM transaction metrics |
| `GET` | `/api/v1/apm/errors` | APM error tracking |
| `GET` | `/api/v1/apm/summary` | APM summary (latency, error rate) |
| `GET` | `/api/v1/kubernetes/pods` | K8s pod status |
| `GET` | `/api/v1/kubernetes/deployments` | K8s deployment status |
| `GET` | `/api/v1/infrastructure/metrics` | Node metrics from Prometheus |

### AI-Powered Analysis

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/analyze` | Generate AI Triage Card for incident analysis |
| `GET` | `/api/v1/analyze/health` | Check LLM service availability |

### Alert Statistics (NEW)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/alerts/prometheus/stats` | Alert statistics by namespace |
| `GET` | `/api/v1/alerts/prometheus/namespace/{ns}` | Detailed stats for one namespace |

### SLO Management

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/slo/dashboard` | SLO overview with budgets |
| `GET` | `/api/v1/slo/service/{name}` | Per-service SLO |
| `GET/POST/PUT/DELETE` | `/api/v1/slo/configs` | SLO configuration CRUD |

### Alert Rules

| Method | Path | Description |
|--------|------|-------------|
| `GET/POST/PUT/DELETE` | `/api/v1/alerts/rules` | Alert rule CRUD |
| `GET` | `/api/v1/alerts/history` | Alert event history |

### WebSocket

| Path | Description |
|------|-------------|
| `/ws/live` | Real-time updates (overview, alerts) |

---

## 💡 Usage Examples

### Generate AI Triage Card

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "project": "meinvoice",
    "incident_id": "incident-001",
    "alert_message": "High error rate detected in production",
    "time_range_minutes": 60,
    "include_recommendations": true
  }'
```

**Response:**
```json
{
  "success": true,
  "triage_card": {
    "project": "meinvoice",
    "summary": "Payment service experiencing elevated error rate (~2.5%) due to database connection timeouts.",
    "severity": "high",
    "findings": [
      {
        "type": "root_cause",
        "title": "Database connection timeout",
        "severity": "critical",
        "confidence": 0.9
      }
    ],
    "recommendations": [
      {
        "priority": 1,
        "action": "Check database connectivity",
        "command": "kubectl exec -n meinvoice -- pg_isopen ..."
      }
    ]
  }
}
```

### Query Alert Statistics

```bash
# All namespaces
curl http://localhost:8000/api/v1/alerts/prometheus/stats

# Specific namespace
curl http://localhost:8000/api/v1/alerts/prometheus/namespace/meinvoice

# Filter namespaces
curl "http://localhost:8000/api/v1/alerts/prometheus/stats?namespaces=meinvoice,production"
```

---

## Configuration

All configuration is via environment variables (`.env` file or K8s ConfigMap/Secret).

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `ELASTICSEARCH_URL` | Elasticsearch endpoint | `http://es:9200` |
| `PROMETHEUS_URL` | Prometheus endpoint | `http://prom:9090` |
| `AUTH_SECRET` | HMAC signing key | 64-char hex |
| `API_KEYS` | List of valid API keys | `["abc..."]` |

### Optional (AI Features)

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Claude API key for Triage Cards | — |
| `ANTHROPIC_MODEL` | Model to use | `claude-sonnet-4-20250514` |
| `AI_MAX_TOKENS` | Max tokens for LLM response | `4096` |

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
| `ALERT_EMAIL_FROM` / `ALERT_EMAIL_TO` | Email addresses |
| `ALERT_WEBHOOK_URL` | Generic webhook URL |

---

## Deploy

### Docker Compose

```bash
docker compose up -d
```

### Kubernetes

```bash
# Build & push images
docker build -t your-registry/devops-ai-backend:latest ./backend
docker build -t your-registry/devops-ai-frontend:latest --target prod ./frontend
docker push your-registry/devops-ai-backend:latest
docker push your-registry/devops-ai-frontend:latest

# Deploy
kubectl apply -f k8s/
```

See [DEPLOY.md](DEPLOY.md) for complete guide.

---

## Security

| Feature | Implementation |
|---------|---------------|
| **Authentication** | HMAC-signed Bearer tokens + API key |
| **SSRF Protection** | Blocks internal IPs for webhooks |
| **Rate Limiting** | 60 req/min per IP, burst protection |
| **Container Security** | Non-root user, K8s security contexts |

---

## Resource Usage

| Component | CPU | RAM |
|-----------|-----|-----|
| Backend | 50-100m idle | 80-150 MB |
| Frontend | 10-20m | 15-30 MB |

**Minimum:** 1 CPU + 1 GB RAM

---

## Project Structure

```
devops_ai_agentics_2026/
├── ai_assistant/          # Claude CLI monitoring assistant
├── backend/
│   ├── app/
│   │   ├── api/v1/       # REST endpoints
│   │   ├── services/     # Data source clients
│   │   ├── models/       # Pydantic models (Triage Card, Alerts)
│   │   ├── alerting/     # Alert engine + SLO reporter
│   │   └── config.py     # Environment configuration
│   └── requirements.txt
├── frontend/              # React dashboard UI
├── k8s/                   # Kubernetes manifests
├── docs/                  # Strategy & pilot guides
├── docker-compose.yml
└── .env.example
```

---

## License

MIT License — see [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built with FastAPI · React · Elasticsearch · Prometheus · Kubernetes · Anthropic Claude**

</div>
