# DevOps AI Agentics 2026 - Requirements Document

<div align="center">

**Version:** 1.0  
**Date:** 05/06/2026  
**Status:** Active Development

</div>

---

## 1. Tổng Quan (Overview)

### 1.1 Mục Tiêu Dự Án

**DevOps AI Agentics 2026** là một nền tảng giám sát DevOps thống nhất (unified monitoring platform) kết hợp:

- **DevOps Monitor** - Dashboard NOC-style tổng hợp Elasticsearch, APM, Prometheus & Kubernetes
- **AI Assistant** - Trợ lý monitoring Claude CLI cho truy vấn ngôn ngữ tự nhiên
- **AI Triage Cards** - Phân tích incident tự động bằng Claude API

### 1.2 Giá Trị Cốt Lõi (Value Proposition)

| Vấn đề hiện tại | Giải pháp của nền tảng |
|----------------|------------------------|
| Nhiều công cụ monitoring riêng lẻ | Một dashboard unified cho tất cả |
| Manual incident triage thời gian dài | AI-powered automated triage & recommendations |
| Khó phát hiện root cause | Correlation tự động across logs, metrics, traces |
| SLO tracking tách biệt | Centralized SLO management với error budget |
| Alert fatigue | Intelligent alerting với context-rich notifications |

### 1.3 Phạm Vi Dự Án (Scope)

**Included:**
- Integration với Elasticsearch, APM, Prometheus, Kubernetes
- Real-time dashboard với WebSocket updates
- AI-powered incident analysis (Triage Cards)
- Alerting engine với configurable rules
- SLO tracking & reporting
- Multi-project support
- CLI assistant cho natural language queries

**Out of Scope:**
- Data storage (platform aggregates, doesn't store)
- Agent deployment (uses existing infrastructure)
- Mobile application

---

## 2. Functional Requirements (Yêu Cầu Chức Năng)

### 2.1 Monitoring Dashboard

#### FR-1: Overview Dashboard
- **FR-1.1:** Hiển thị health status của tất cả systems trong single view
- **FR-1.2:** Color-coded status (Green/Yellow/Red) cho từng system
- **FR-1.3:** Real-time updates via WebSocket
- **FR-1.4:** Auto-refresh fallback (10s interval) khi WebSocket disconnect
- **FR-1.5:** Hiển thị active alerts count per system

#### FR-2: Log Management (Elasticsearch)
- **FR-2.1:** Full-text search across Elasticsearch logs
- **FR-2.2:** Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- **FR-2.3:** Filter by service name
- **FR-2.4:** Time range picker (Last 15m, 1h, 6h, 24h, 7d, custom)
- **FR-2.5:** Paginated results with configurable page size

#### FR-3: APM Monitoring
- **FR-3.1:** Transaction latency metrics (P50, P95, P99 percentiles)
- **FR-3.2:** Error tracking với automatic grouping
- **FR-3.3:** Service dependency map
- **FR-3.4:** Per-endpoint breakdown
- **FR-3.5:** Time series visualization

#### FR-4: Infrastructure Metrics (Prometheus)
- **FR-4.1:** Node-level CPU utilization
- **FR-4.2:** Node-level memory utilization
- **FR-4.3:** Disk usage per node
- **FR-4.4:** Network metrics (optional)
- **FR-4.5:** Custom query support for Prometheus queries

#### FR-5: Kubernetes Monitoring
- **FR-5.1:** Pod status across configured namespaces
- **FR-5.2:** Deployment health status
- **FR-5.3:** Cluster events viewing
- **FR-5.4:** Resource requests vs limits visualization
- **FR-5.5:** Multi-namespace support

### 2.2 AI-Powered Features

#### FR-6: AI Triage Cards
- **FR-6.1:** Generate triage card cho incident via REST API
- **FR-6.2:** Collect context từ logs, APM, metrics, K8s
- **FR-6.3:** Identify root causes với confidence scores
- **FR-6.4:** Provide prioritized recommendations
- **FR-6.5:** Support Vietnamese output
- **FR-6.6:** Structured JSON response format
- **FR-6.7:** Configurable time range cho analysis

#### FR-7: AI Assistant (CLI)
- **FR-7.1:** Natural language query interface
- **FR-7.2:** Query system health status
- **FR-7.3:** Query slow endpoints
- **FR-7.4:** Query infrastructure metrics
- **FR-7.5:** Per-project configuration support
- **FR-7.6:** Integration với Claude CLI

### 2.3 Alerting System

#### FR-8: Alert Engine
- **FR-8.1:** Background alert evaluation (asyncio task)
- **FR-8.2:** Configurable alert rules (threshold-based)
- **FR-8.3:** Multi-condition support per rule
- **FR-8.4:** Alert persistence (history tracking)
- **FR-8.5:** State management (last evaluation timestamp)
- **FR-8.6:** Default rules bundled với application

#### FR-9: Alert Notifications
- **FR-9.1:** Slack webhook notifications
- **FR-9.2:** Email notifications (SMTP)
- **FR-9.3:** Generic webhook support
- **FR-9.4:** Notification templating
- **FR-9.5:** Alert deduplication

#### FR-10: Alert Statistics
- **FR-10.1:** Prometheus alerts breakdown by namespace
- **FR-10.2:** Severity distribution (critical, warning, info)
- **FR-10.3:** Firing vs pending counts
- **FR-10.4:** Top alerts per namespace
- **FR-10.5:** Time-series alert trends (optional)

### 2.4 SLO Management

#### FR-11: SLO Configuration
- **FR-11.1:** Define availability SLOs per service (% target)
- **FR-11.2:** Define latency SLOs per service (threshold %)
- **FR-11.3:** Rolling window support (7d, 30d)
- **FR-11.4:** CRUD API cho SLO configs
- **FR-11.5:** Default configs bundled với application

#### FR-12: SLO Calculation & Reporting
- **FR-12.1:** Automatic error budget calculation
- **FR-12.2:** SLO dashboard overview
- **FR-12.3:** Per-service SLO detail view
- **FR-12.4:** Daily Slack SLO report
- **FR-12.5:** Slow APIs breakdown per service

### 2.5 Authentication & Authorization

#### FR-13: Authentication
- **FR-13.1:** HMAC-signed Bearer token authentication
- **FR-13.2:** API key authentication
- **FR-13.3:** Multiple API keys support
- **FR-13.4:** Token validation middleware

---

## 3. Non-Functional Requirements (Phi Chức Năng)

### 3.1 Performance

| NFR | Metric | Target |
|-----|--------|--------|
| NFR-P1 | Overview API response time | < 5 seconds (all services parallel) |
| NFR-P2 | Log search response time | < 3 seconds cho typical queries |
| NFR-P3 | WebSocket message latency | < 500ms |
| NFR-P4 | Dashboard initial load | < 2 seconds |
| NFR-P5 | Alert evaluation interval | 60 seconds (configurable) |

### 3.2 Scalability

| NFR | Requirement |
|-----|-------------|
| NFR-S1 | Horizontal scaling cho backend (stateless) |
| NFR-S2 | Frontend static assets served via CDN |
| NFR-S3 | WebSocket connection pooling |
| NFR-S4 | Lazy loading cho large datasets |

### 3.3 Availability

| NFR | Target |
|-----|--------|
| NFR-A1 | Platform uptime | 99.5% |
| NFR-A2 | Graceful degradation khi data source unavailable |
| NFR-A3 | Auto-reconnect WebSocket |
| NFR-A4 | Health check endpoint |

### 3.4 Security

| NFR | Implementation |
|-----|----------------|
| NFR-Sec1 | Authentication required cho tất cả endpoints |
| NFR-Sec2 | SSRF protection cho webhook calls |
| NFR-Sec3 | Rate limiting (60 req/min per IP) |
| NFR-Sec4 | Security headers (CSP, X-Frame-Options, etc.) |
| NFR-Sec5 | Secrets management via environment variables |
| NFR-Sec6 | Non-root container user |
| NFR-Sec7 | K8s security contexts |

### 3.5 Maintainability

| NFR | Requirement |
|-----|-------------|
| NFR-M1 | Config-driven architecture |
| NFR-M2 | Clear separation of concerns (services layer) |
| NFR-M3 | Type safety (TypeScript frontend, Pydantic backend) |
| NFR-M4 | Comprehensive logging |
| NFR-M5 | Health check diagnostics |

### 3.6 Usability

| NFR | Requirement |
|-----|-------------|
| NFR-U1 | Intuitive NOC-style dashboard |
| NFR-U2 | Responsive design (desktop, tablet) |
| NFR-U3 | Loading states cho async operations |
| NFR-U4 | Error messages với actionable guidance |
| NFR-U5 | Vietnamese language support |

---

## 4. Technical Requirements

### 4.1 Tech Stack

#### Backend
- **Framework:** FastAPI (Python 3.12+)
- **Validation:** Pydantic v2
- **Async:** asyncio, httpx
- **K8s Client:** Official Kubernetes Python client
- **LLM:** Anthropic Claude API

#### Frontend
- **Framework:** React 19
- **Language:** TypeScript
- **Build:** Vite 8
- **Styling:** Tailwind CSS 4
- **Charts:** Recharts
- **State:** TanStack Query
- **Routing:** React Router 7
- **HTTP:** Axios

#### Infrastructure
- **Containerization:** Docker
- **Orchestration:** Kubernetes
- **Ingress:** nginx

### 4.2 External Dependencies

| Service | Purpose | Required |
|---------|---------|----------|
| Elasticsearch | Logs & APM data storage | Yes |
| Prometheus | Metrics storage | Yes |
| Kubernetes cluster | Workloads to monitor | Yes |
| Anthropic API | AI Triage Cards | Optional |

### 4.3 Data Sources

| Data Source | Client | Query Method |
|-------------|--------|--------------|
| Elasticsearch logs | ElasticsearchClient | REST API |
| APM transactions | ApmClient | ES query on `apm-*-transaction*` |
| APM errors | ApmClient | ES query on `apm-*-error*` |
| Infrastructure metrics | PrometheusClient | HTTP API |
| K8s resources | KubernetesClient | Python client |

---

## 5. API Requirements

### 5.1 REST Endpoints

#### Overview
```
GET /api/v1/overview
```
- Returns: Health status của tất cả systems
- Timeout: 5s per service (parallel)

#### Logs
```
GET /api/v1/logs?query={query}&level={level}&service={service}&from={timestamp}&to={timestamp}
```

#### APM
```
GET /api/v1/apm/transactions?service={service}&from={timestamp}
GET /api/v1/apm/errors?service={service}&from={timestamp}
GET /api/v1/apm/summary
```

#### Infrastructure
```
GET /api/v1/infrastructure/metrics?from={timestamp}
```

#### Kubernetes
```
GET /api/v1/kubernetes/pods
GET /api/v1/kubernetes/deployments
```

#### AI Analysis
```
POST /api/v1/analyze
Body: {
  "project": string,
  "incident_id": string,
  "alert_message": string,
  "time_range_minutes": number,
  "include_recommendations": boolean
}
```

#### Alert Rules
```
GET /api/v1/alerts/rules
POST /api/v1/alerts/rules
PUT /api/v1/alerts/rules/{id}
DELETE /api/v1/alerts/rules/{id}
GET /api/v1/alerts/history
```

#### SLO
```
GET /api/v1/slo/dashboard
GET /api/v1/slo/service/{name}
GET /api/v1/slo/configs
POST /api/v1/slo/configs
PUT /api/v1/slo/configs/{id}
DELETE /api/v1/slo/configs/{id}
GET /api/v1/slo/service/{name}/slow-apis
```

### 5.2 WebSocket

```
Path: /ws/live
Events:
  - overview_updated
  - alert_fired
  - alert_resolved
```

---

## 6. Data Models

### 6.1 Triage Card (Response from AI)

```typescript
interface TriageCard {
  project: string;
  incident_id: string;
  summary: string;
  severity: "low" | "medium" | "high" | "critical";
  findings: Finding[];
  recommendations: Recommendation[];
  metadata: {
    generated_at: string;
    time_range_minutes: number;
    model: string;
  };
}

interface Finding {
  type: "root_cause" | "symptom" | "contributing_factor";
  title: string;
  description: string;
  severity: "info" | "warning" | "critical";
  confidence: number; // 0-1
  evidence?: string[];
}

interface Recommendation {
  priority: number; // 1=highest
  action: string;
  command?: string;
  expected_outcome?: string;
}
```

### 6.2 Alert Rule

```typescript
interface AlertRule {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  source: "elasticsearch" | "prometheus" | "kubernetes";
  conditions: Condition[];
  actions: Action[];
  severity: "info" | "warning" | "critical";
  cooldown_seconds: number;
}

interface Condition {
  type: string;
  field: string;
  operator: "gt" | "lt" | "eq" | "contains";
  threshold: number | string;
}

interface Action {
  type: "slack" | "email" | "webhook";
  config: Record<string, unknown>;
}
```

### 6.3 SLO Config

```typescript
interface SLOConfig {
  id: string;
  service_name: string;
  name: string;
  description: string;
  type: "availability" | "latency";
  target_percentage: number;
  window_days: 7 | 30;
  latency_threshold_ms?: number; // cho type=latency
  enabled: boolean;
}
```

---

## 7. Configuration

### 7.1 Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `ELASTICSEARCH_URL` | Elasticsearch endpoint | `http://es:9200` |
| `ELASTICSEARCH_USERNAME` | ES username | `elastic` |
| `ELASTICSEARCH_PASSWORD` | ES password | `changeme` |
| `PROMETHEUS_URL` | Prometheus endpoint | `http://prom:9090` |
| `AUTH_SECRET` | HMAC signing key | 64-char hex |
| `API_KEYS` | Valid API keys (JSON array) | `["key1", "key2"]` |

### 7.2 Optional Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Claude API key | — |
| `ANTHROPIC_MODEL` | LLM model | `claude-3-7-sonnet-20250214` |
| `KUBECONFIG_PATH` | Kubeconfig path (empty=in-cluster) | `""` |
| `K8S_NAMESPACES` | Namespaces to monitor (JSON) | `["default"]` |
| `SLACK_WEBHOOK_URL` | Slack webhook | — |
| `SLO_REPORT_ENABLED` | Enable daily SLO report | `false` |
| `SLO_REPORT_HOUR` | SLO report hour (0-23) | `9` |
| `SLO_REPORT_TIMEZONE` | Report timezone | `Asia/Ho_Chi_Minh` |

---

## 8. Constraints & Assumptions

### 8.1 Constraints

| Type | Description |
|------|-------------|
| Technical | Platform aggregates data, không store original data |
| Technical | Không có database (state minimal) |
| Technical | Depends on existing ELK, Prometheus, K8s setup |
| Security | Requires secure communication (HTTPS in production) |
| Resource | Minimum 1 CPU + 1 GB RAM |

### 8.2 Assumptions

| Area | Assumption |
|------|------------|
| Infrastructure | Elasticsearch, Prometheus, K8s đang chạy |
| Network | Platform có network access đến tất cả data sources |
| User | Users có basic understanding của monitoring concepts |
| AI | Anthropic API available cho AI features |

---

## 9. Success Criteria

Tiêu chí thành công cho dự án:

1. **Functionality**
   - [ ] Overview dashboard hiển thị health của ≥4 data sources
   - [ ] AI Triage Cards generate actionable recommendations
   - [ ] Alert engine evaluation <60s interval
   - [ ] SLO calculation accurate với error budget

2. **Performance**
   - [ ] Overview API responds trong <5s
   - [ ] Dashboard loads trong <2s
   - [ ] WebSocket latency <500ms

3. **Reliability**
   - [ ] Graceful degradation khi data source down
   - [ ] Auto-reconnect WebSocket
   - [ ] Platform uptime ≥99.5%

4. **Security**
   - [ ] Tất cả endpoints authenticated
   - [ ] SSRF protection active
   - [ ] Rate limiting enforced

5. **Usability**
   - [ ] Intuitive NOC-style interface
   - [ ] Vietnamese language support
   - [ ] Clear error messages

---

## 10. Roadmap Phases

### Phase 1: Foundation (Completed)
- ✅ Core integration (ES, Prometheus, K8s)
- ✅ Overview dashboard
- ✅ Basic alerting engine

### Phase 2: AI Features (Current)
- 🔄 AI Triage Cards
- 🔄 Enhanced alert correlation
- 🔄 SLO management

### Phase 3: Enhancement (Planned)
- ⏳ ML-based anomaly detection
- ⏳ Predictive alerting
- ⏳ Runbook automation

### Phase 4: Scale (Future)
- ⏳ Multi-cluster support
- ⏳ Advanced analytics
- ⏳ Incident workflow management

---

## 11. Appendix

### 11.1 Definitions

| Term | Definition |
|------|------------|
| SLO | Service Level Objective - mục tiêu performance cho service |
| Error Budget | Số lượng "errors" được phép trước khi violate SLO |
| Triage Card | AI-generated incident analysis với root cause & recommendations |
| NOC | Network Operations Center - centralized monitoring location |

### 11.2 References

- [Elasticsearch API Documentation](https://www.elastic.co/guide/en/elasticsearch/reference/current/index.html)
- [Prometheus HTTP API](https://prometheus.io/docs/prometheus/latest/querying/api/)
- [Kubernetes API](https://kubernetes.io/docs/reference/kubernetes-api/)
- [Anthropic Claude API](https://docs.anthropic.com/claude/reference/)
- [CLAUDE.md](../CLAUDE.md) - Project architecture details
- [DEPLOY.md](../DEPLOY.md) - Deployment guide

---

<div align="center">

**Document Owner:** DevOps Team  
**Last Updated:** 05/06/2026

</div>
