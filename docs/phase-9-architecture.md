# Phase 9 Architecture Updates

## Distributed State Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend (React)                    │
│  ┌───────────────────────────────────────────────────┐  │
│  │  useLLMStream Hook (Streaming)                    │  │
│  │  └── Token-by-token display                        │  │
│  └───────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────┘
                         │ REST/WebSocket
                         ▼
┌─────────────────────────────────────────────────────────┐
│              Backend (FastAPI) - Pod 1                  │
│  ┌───────────────────────────────────────────────────┐  │
│  │  API Endpoints                                     │  │
│  │  ├── /api/v1/overview (Batch Optimized)           │  │
│  │  ├── /api/v1/analyze/stream (LLM Streaming)        │  │
│  │  └── /api/v1/alerts/rules                         │  │
│  ├───────────────────────────────────────────────────┤  │
│  │  Service Clients (Connection Pooled)               │  │
│  │  ├── ElasticsearchClient (max: 20)                │  │
│  │  ├── PrometheusClient (max: 20)                    │  │
│  │  ├── KubernetesClient (max: 10)                    │  │
│  │  └── ApmClient                                     │  │
│  ├───────────────────────────────────────────────────┤  │
│  │  State Managers                                    │  │
│  │  ├── RedisAlertStore                               │  │
│  │  ├── RedisApprovalStore                            │  │
│  │  └── RedisRateLimiter                              │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    Redis Cluster                        │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐          │
│  │  Alert    │  │ Approval  │  │ Rate      │          │
│  │  State    │  │ State     │  │ Limit     │          │
│  │  (DB: 0)  │  │  (DB: 1)  │  │  (DB: 2)  │          │
│  └───────────┘  └───────────┘  └───────────┘          │
│  ┌───────────┐                                         │
│  │  Cache    │                                         │
│  │  (DB: 3)  │                                         │
│  └───────────┘                                         │
└─────────────────────────────────────────────────────────┘
```

## Connection Pool Architecture

Each service client maintains its own connection pool:

| Service    | Max Connections | Keep-Alive | HTTP/2 |
|------------|-----------------|------------|--------|
| Elasticsearch | 20           | Yes        | Yes    |
| Prometheus    | 20           | Yes        | Yes    |
| Kubernetes    | 10           | Yes        | No     |
| LLM           | 10           | Yes        | Yes    |

**Benefits**:
- Reduced connection overhead
- Better throughput under load
- Configurable per service
- Proper resource cleanup

## Request Batching Flow

```
Request 1 ──┐
Request 2 ──┤
Request 3 ──┼──► BatchOptimizer ──► Single Execution ──► Response to all
Request 4 ──┤                   (max_wait: 0.1s)          (distributed)
Request 5 ──┘
```

**Configuration**:
- Batch size: 10 requests
- Max wait: 0.1 seconds
- Per-batch-key grouping

## LLM Streaming Flow

```
Frontend                  Backend                    Claude API
   │                        │                            │
   │ POST /analyze/stream   │                            │
   │───────────────────────►│                            │
   │                        │                            │
   │◄─────── SSE Stream ───┼───────────────────────────►│
   │◄─ Token 1 ─────────────┼───────────────────────────►│
   │◄─ Token 2 ─────────────┼───────────────────────────►│
   │◄─ Token 3 ─────────────┼───────────────────────────►│
   │◄─ Complete ─────────────┼───────────────────────────►│
   │                        │                            │
```

## Security Architecture

```
┌─────────────────────────────────────────────────────┐
│              Security Layers                       │
├─────────────────────────────────────────────────────┤
│  Layer 1: Authentication (API Keys / Tokens)        │
│  Layer 2: Authorization (RBAC per environment)      │
│  Layer 3: Input Validation (XSS, Injection)         │
│  Layer 4: SSRF Protection (DNS caching, IP blocks) │
│  Layer 5: Secrets Management (External Secrets)    │
└─────────────────────────────────────────────────────┘
```

## Distributed Tracing

```
┌─────────────────────────────────────────────────────────────┐
│                   OpenTelemetry Flow                       │
│                                                              │
│  FastAPI ──► OTLP Exporter ──► OTel Collector ──► Jaeger   │
│     │              (gRPC)            (Batch)        (UI)    │
│     │                                                        │
│     ▼                                                        │
│  HTTPX Client ──► Traced HTTP Calls                        │
│     │                                                        │
│     ▼                                                        │
│  AsyncIO Tasks ──► Span Propagation                        │
└─────────────────────────────────────────────────────────────┘
```

## CI/CD Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                     GitHub Actions                          │
│                                                              │
│  Trigger (Push/PR)                                         │
│       │                                                     │
│       ├─► Backend Lint (ruff, black, mypy)                 │
│       ├─► Backend Test (pytest, coverage)                   │
│       ├─► Frontend Test (npm test)                         │
│       ├─► Security Scan (Bandit, TruffleHog, npm audit)    │
│       │                                                     │
│       ▼                                                     │
│  Build Docker Images (if main branch)                     │
│       │                                                     │
│       ├─► Push to GHCR                                     │
│       │                                                     │
│       ▼                                                     │
│  Deploy (manual approval)                                  │
│       │                                                     │
│       ├─► Staging (automatic)                              │
│       └─► Production (manual approval)                     │
└─────────────────────────────────────────────────────────────┘
```

## Performance Metrics

### Baseline Performance (Post-Phase 9)

| Endpoint            | P50   | P95   | P99   |
|---------------------|-------|-------|-------|
| GET /overview       | 1.2s  | 2.5s  | 4.8s  |
| POST /analyze       | 3.5s  | 8.2s  | 15s   |
| POST /analyze/stream| 0.5s* | 1.2s* | 2.5s* |

*Time to first token

### Scalability Improvements

| Metric              | Before | After | Improvement |
|---------------------|--------|-------|-------------|
| Concurrent requests | 10    | 100   | 10x         |
| Redis rate limiting | No    | Yes   | Distributed  |
| Connection pooling  | No    | Yes   | 30% faster   |
| LLM streaming       | No    | Yes   | Better UX    |
