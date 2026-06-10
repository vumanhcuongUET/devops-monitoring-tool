# DevOps AI Agentics 2026 - Context

This document captures the domain language and core concepts of the DevOps AI Agentics platform. When working with this codebase, use these terms consistently.

---

## Domain Language

### Core Systems & Data Sources

#### Elasticsearch (ES)
- **Purpose**: Log storage and search engine
- **Cluster Health**: `green` (healthy), `yellow` (degraded), `red` (down)
- **Indices**: `apm-*-transaction*` (APM data), `apm-*-error*` (error tracking), log indices
- **Processor Events**: `transaction` (APM performance data), `error` (error occurrences)

#### APM (Application Performance Monitoring)
- **Transactions**: Individual API calls/endpoints with timing metrics
- **Transaction Name**: Identifier for an endpoint (e.g., `GET /api/users`)
- **Error Groups**: Categorized errors grouped by `grouping_key`
- **Latency Percentiles**: P50, P95, P99 response times
- **Throughput**: Request count per time period

#### Prometheus
- **Purpose**: Metrics and monitoring system
- **Metrics**: CPU, memory, disk utilization percentages
- **Time Series Data**: Collected at regular intervals
- **Query Language**: PromQL for metric queries

#### Kubernetes (K8s)
- **Pods**: Individual containers with status (`Running`, `Pending`, `Failed`, `Unknown`)
- **Deployments**: Application deployments with replica counts and availability
- **Nodes**: Worker nodes with status (`Ready`, `NotReady`)
- **Namespaces**: Logical clusters within the physical cluster

### Monitoring Concepts

#### Health Status Hierarchy
- **HEALTHY**: System operating normally, all checks passing
- **DEGRADED**: Issues detected but system remains functional
- **DOWN**: Critical failures, system unavailable

#### APM Data Models
- **Service**: A monitored application (e.g., `meinvoice-api`, `payment-service`)
- **Transaction Name**: Specific endpoint within a service
- **Duration**: Request processing time in milliseconds
- **Result**: `success` or `error` outcome

#### K8s Resource Models
- **Pod Status**: `Running`, `Pending`, `Failed`, `Unknown`
- **Deployment Ready Replicas**: Current available replicas vs desired replicas
- **Node Conditions**: Ready status based on conditions

### Alerting System

#### Alert Rules
- **Source**: Which system to query (`elasticsearch`, `apm`, `prometheus`, `kubernetes`)
- **Conditions**: Evaluation criteria with operators (`gt`, `gte`, `lt`, `lte`, `eq`)
- **Duration**: Minimum time threshold must be sustained before alert fires
- **Severity**: `info`, `warning`, `critical`
- **Cooldown**: Minimum time between consecutive alerts for the same rule

#### Alert Events
- **States**:
  - `firing`: Alert condition is actively met
  - `pending`: Condition met but duration threshold not yet reached
  - `inactive`: Alert not firing
- **Properties**: ID, rule name, current value, threshold, timestamp

#### Alert Notifications
- **Channels**: Slack webhook, Email (SMTP), Generic webhook
- **Notification Types**: Alert fired, alert resolved

#### Alert Statistics (Prometheus)
- **Breakdown by Namespace**: Grouping alerts by K8s namespace
- **Severity Distribution**: Count of alerts by severity level
- **Firing vs Pending**: Distinction between active and threshold-not-met alerts

### SLO (Service Level Objectives) System

#### SLO Configuration
- **Service Name**: The monitored service identifier
- **Types**:
  - `availability`: Uptime percentage (e.g., 99.9%)
  - `latency`: Performance threshold percentage (e.g., 95% of requests under 200ms)
- **Target**: The percentage goal (e.g., 99.9, 95.0)
- **Window**: Rolling time period (`7d` or `30d`)
- **Latency Threshold (ms)**: For latency SLOs, the millisecond threshold

#### SLO Calculations
- **Availability SLO**: `(good requests / total requests) * 100`
  - Good requests = total - errors
- **Latency SLO**: `(requests under threshold / total requests) * 100`
- **Error Budget**: Total acceptable errors before SLO is violated
- **Error Budget Consumed**: Percentage of budget already used
- **Error Budget Remaining**: Percentage of budget still available

#### SLO Status Levels
- **HEALTHY**: SLO is meeting target with comfortable margin
- **WARNING**: Approaching SLO violation threshold
- **CRITICAL**: At risk of violating SLO
- **BREACHED**: SLO target has been violated

#### SLO Reporting
- **Daily Slack Report**: Automated Block Kit message with:
  - All SLO statuses
  - Error budget remaining
  - Top slow APIs (for latency SLOs)

### Triage Cards (AI-Generated Incident Analysis)

#### Triage Card Structure
- **Project**: Which service/project is being analyzed
- **Incident ID**: Unique identifier for the incident
- **Summary**: AI-generated executive summary of the incident
- **Severity**: `critical`, `high`, `medium`, `low`, `info`

#### Findings
- **Types**:
  - `root_cause`: Primary cause of the incident
  - `symptom`: Observable effect
  - `contributing_factor`: Secondary causes
  - `anomaly`: Unusual patterns detected
  - `configuration_issue`: Misconfiguration identified
  - `dependency_issue`: Upstream/downstream problems
- **Confidence Score**: 0-1 probability that the finding is correct
- **Evidence**: Supporting data from logs, metrics, traces

#### Recommendations
- **Priority**: 1 (highest) to N (lowest)
- **Action**: Specific remediation step
- **Command**: CLI command to execute (kubectl, argocd, etc.)
- **Expected Outcome**: What should happen after action
- **Risk**: Potential side effects

#### Triage Card Generation
- **Input**: Alert message, time range, project context
- **Data Sources**: Logs (ES), APM data, Metrics (Prometheus), K8s state
- **Output**: Structured JSON with findings and recommendations

---

## Architecture Overview

### Data Flow

```
Frontend (React)
    │
    ├─ REST API ─────┐
    │                │
    └─ WebSocket ────┤
                     │
              Backend (FastAPI)
                     │
        ┌────────────┼────────────┐
        │            │            │
   Elasticsearch  Prometheus  Kubernetes
        │            │            │
    APM Client   Prom Client   K8s Client
```

### Client Architecture

Each data source has a dedicated client in `backend/app/services/`:
- **ElasticsearchClient**: Handles both logs and APM queries
- **ApmClient**: Queries `apm-*-transaction*` and `apm-*-error*` indices
- **PrometheusClient**: Fetches infrastructure metrics via HTTP API
- **KubernetesClient**: Manages K8s resources via Python client
- **LlmClient**: Integrates with Claude API for Triage Card generation
- **SloClient**: Calculates SLO metrics from APM data

### Background Processing

- **Alert Engine**: Runs as `asyncio` background task in FastAPI lifespan
  - Evaluates alert rules every 60 seconds (configurable)
  - Dispatches notifications via multiple channels
  - Persists state to `data/alert_rules.json` and `data/alert_state.json`

- **SLO Reporter**: Daily background task
  - Generates Slack SLO report at configured hour
  - Includes error budget status and slow APIs

### Real-time Communication

- **WebSocket** at `/ws/live` broadcasts:
  - Overview updates (when any system status changes)
  - Alert events (firing, resolved)

- **Fallback REST Polling**:
  - 10-second interval when WebSocket disconnects
  - Automatic reconnection with exponential backoff

---

## Key Patterns

### Multi-Source Aggregation
- **Overview Endpoint** (`GET /api/v1/overview`):
  - Queries all data sources in parallel via `asyncio.gather`
  - 5-second timeout per source (one source down doesn't block others)
  - Derives overall health from individual system statuses

### Error Handling
- **Graceful Degradation**: Each client handles failures independently
- **Timeout Protection**: All external calls have configurable timeouts
- **Partial Results**: UI shows available data even when some sources are down

### Configuration-Driven Architecture
- **Global Config** (`ai_assistant/config/global.yaml`): Default settings
- **Project Config** (`ai_assistant/projects/<project>/config.yaml`): Per-project overrides
- **Alert Rules** (`backend/app/alerting/default_rules.yaml`): Bundled default rules
- **SLO Configs** (`backend/app/alerting/default_slo_configs.yaml`): Bundled default SLOs
- **Custom Persistence**: User modifications saved to `data/` directory

### Authentication & Security
- **HMAC-signed Bearer tokens**: Primary auth mechanism
- **API Key fallback**: Alternative auth method
- **SSRF Protection**: Blocks internal IP access in webhook calls
- **Rate Limiting**: 60 requests/minute per IP with burst protection
- **Security Headers**: CSP, X-Frame-Options, etc.

### Project Isolation (Multi-Project Support)
- **Namespace-based**: Each project has its K8s namespace
- **Source Filtering**: Project-specific ELK/Prometheus endpoints
- **Query Inheritance**: Projects can override or inherit global queries
- **Section Skipping**: Projects can exclude irrelevant monitoring sections

---

## API Conventions

### Response Patterns
- **Health Status**: Always return `health_status`, `message`, `timestamp`
- **Array Responses**: Include `total` count for pagination
- **Error Responses**: Include `detail` field with error description

### Endpoint Naming
- `/api/v1/overview` — System-wide summary
- `/api/v1/<resource>/` — Resource-specific endpoints
- `/api/v1/<resource>/<id>` — Individual resource operations

### Time Parameters
- `from` / `to`: Unix timestamps or ISO 8601 strings
- `time_range_minutes`: Alternative for relative time ranges
- Default: `now-1h` (last hour)

---

## AI Assistant (CLI) Concepts

### Query Structure
- **Project Extraction**: Parse project name from natural language
- **Time Range Override**: Extract duration from query ("30 phút qua")
- **Section Selection**: Limit to specific monitoring sections

### Report Generation
- **Template-Based**: Uses YAML templates for report structure
- **Parallel Execution**: Runs multiple queries concurrently
- **Vietnamese Output**: Results formatted for Vietnamese users

### Configuration Hierarchy
1. Project-specific query (`projects/<project>/queries/<section>.yaml`)
2. Global fallback query (`queries/common/<section>.yaml`)
3. Project config overrides global sources
4. Global config provides defaults

---

## File Locations Reference

| Concept | Location |
|---------|----------|
| API Routes | `backend/app/api/v1/` |
| Data Models | `backend/app/models/` |
| Service Clients | `backend/app/services/` |
| Alert Engine | `backend/app/alerting/` |
| Configuration | `backend/app/config.py` |
| Frontend Pages | `frontend/src/pages/` |
| Frontend Components | `frontend/src/components/` |
| AI Assistant Queries | `ai_assistant/queries/` |
| AI Assistant Projects | `ai_assistant/projects/` |
| ADRs | `docs/adr/` |
| Strategy Docs | `docs/` |

---

## Related Files

- **CLAUDE.md**: Detailed project architecture and setup
- **README.md**: Quick start and feature overview
- **DEPLOY.md**: Deployment instructions
- **docs/requirement.md**: Functional and non-functional requirements
- **docs/chien_luoc_tong_the.md**: 4-phase strategic roadmap (Vietnamese)
