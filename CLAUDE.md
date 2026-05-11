# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Unified DevOps monitoring dashboard aggregating data from Elasticsearch/ELK, Elastic APM (.NET apps), Prometheus/Grafana, and Kubernetes into a single NOC-style interface with unified alerting.

**Stack**: Backend Python (FastAPI) + Frontend Node.js (React + TypeScript + Vite + Tailwind)

## Commands

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
FastAPI serves interactive Swagger docs at `http://localhost:8000/docs`.

### Frontend
```bash
cd frontend
npm install
npm run dev          # Dev server at :3000 with API proxy to :8000
npm run build        # TypeScript check (tsc -b) + Vite build
npm run lint         # ESLint
```

### Docker
```bash
cp .env.example .env  # Then edit .env with your endpoints
docker compose up
```

### Deploy to K8s
```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/backend/
kubectl apply -f k8s/frontend/
kubectl apply -f k8s/ingress.yaml
```

## Architecture

```
Frontend (React)  ──REST/WebSocket──>  Backend (FastAPI)
                                           ├── ElasticsearchClient  → Elasticsearch REST API
                                           ├── ApmClient            → ES on apm-* indices
                                           ├── SloClient            → ES on apm-* indices (SLO calculations)
                                           ├── PrometheusClient     → Prometheus HTTP API
                                           ├── KubernetesClient     → K8s Python client
                                           ├── AlertEngine          → Background asyncio task
                                           └── SloReporter          → Daily Slack SLO report
```

- **APM data is stored in Elasticsearch** — `ApmClient` queries `apm-*-transaction*` and `apm-*-error*` indices directly via the ES client, not through a separate API.
- **Alert engine** runs as a background `asyncio` task inside FastAPI (no external process). Default rules come from `backend/app/alerting/default_rules.yaml`. Custom rules persist to `data/alert_rules.json`, state to `data/alert_state.json`. The `data/` directory is a Docker volume for persistence across restarts.
- **WebSocket** at `/ws/live` broadcasts overview updates and alert events. Frontend falls back to REST polling (10s interval) if WS disconnects.
- **Overview endpoint** (`GET /api/v1/overview`) calls all four service clients via `asyncio.gather` with 5s timeouts — one system being down doesn't block others.
- **K8s client** supports both in-cluster config (prod) and kubeconfig (dev), controlled by `KUBECONFIG_PATH` env var.
- **Frontend routing**: Vite dev server proxies `/api` and `/ws` to backend (see `vite.config.ts`). In production, `nginx.conf` handles the same proxying. Both are configured so the frontend only needs a single origin.

## Key Files

- `backend/app/config.py` — All env var configuration (Pydantic Settings)
- `backend/app/main.py` — FastAPI entry, lifespan (client init + alert engine start)
- `backend/app/api/v1/overview.py` — Core NOC endpoint with health derivation logic
- `backend/app/alerting/engine.py` — Alert evaluation loop, notification dispatch
- `backend/app/services/elasticsearch_client.py` — Most complex client (handles both logs and APM queries)
- `frontend/src/pages/OverviewPage.tsx` — Main dashboard page
- `frontend/src/hooks/useWebSocket.ts` — WebSocket with auto-reconnect + REST fallback

## Environment Variables

All config is in `.env` (see `.env.example`). Critical ones:
- `ELASTICSEARCH_URL`, `ELASTICSEARCH_USERNAME`, `ELASTICSEARCH_PASSWORD`
- `PROMETHEUS_URL`
- `KUBECONFIG_PATH` (empty = in-cluster)
- `K8S_NAMESPACES` (JSON array)
- `SLACK_WEBHOOK_URL`, `SMTP_*` for alert notifications
- `SLO_REPORT_ENABLED`, `SLO_REPORT_HOUR`, `SLO_REPORT_TIMEZONE` for daily SLO Slack report

## SLO System

- **SLO configs** define per-service targets (availability %, latency threshold %) with 7d or 30d rolling windows. Defaults in `backend/app/alerting/default_slo_configs.yaml`, custom configs persist to `data/slo_configs.json`.
- **SloClient** (`services/slo_client.py`) calculates SLO by querying `apm-*-transaction*` indices: counts total vs errors (availability) or total vs slow requests (latency), then derives error budget consumed/remaining.
- **Slow APIs** — `GET /api/v1/slo/service/{name}/slow-apis` returns per-transaction breakdown showing which specific APIs are not meeting SLO.
- **Daily Slack report** — `SloReporter` background task sends a Block Kit message with all SLO statuses, budget remaining, and top slow APIs. Triggered at `SLO_REPORT_HOUR` (default 9 AM) in `SLO_REPORT_TIMEZONE`.
