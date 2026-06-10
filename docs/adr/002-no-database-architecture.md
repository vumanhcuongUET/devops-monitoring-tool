# ADR-002: No Database Architecture

**Status**: Accepted
**Date**: 2025-06-10
**Context**: DevOps AI Agentics 2026 Platform

## Context

Most monitoring platforms store historical data in a database for querying and analysis. We need to decide whether to implement a data storage layer.

## Decision

We chose a **state minimal design** where the platform does NOT store monitoring data - it only stores configuration and state metadata.

### What We Store

**Configuration (YAML files + JSON persistence):**
- Alert rules: `backend/app/alerting/default_rules.yaml` + `data/alert_rules.json`
- SLO configs: `backend/app/alerting/default_slo_configs.yaml` + `data/slo_configs.json`
- Alert state: `data/alert_state.json` (last evaluation timestamps)

**What We Don't Store:**
- Logs (kept in Elasticsearch)
- Metrics (kept in Prometheus)
- APM data (kept in Elasticsearch)
- K8s state (queried live from API)

### Architecture

```
┌─────────────────────────────────────────────┐
│         DevOps AI Agentics Platform          │
│  (No database for metrics/logs/traces)       │
└───────────────┬─────────────────────────────┘
                │
    ┌───────────┼───────────┐
    │           │           │
    ▼           ▼           ▼
┌────────┐ ┌────────┐ ┌──────────┐
│   ES   │ │  Prom  │ │  K8s     │
│ (logs) │ │(metrics)│ │ (state)  │
└────────┘ └────────┘ └──────────┘
```

## Rationale

### Pros
1. **Simplicity**: No database to manage, backup, or scale
2. **Cost**: No additional storage costs
3. **Freshness**: Always showing latest data from source systems
4. **Consistency**: Single source of truth for each data type
5. **Deployment**: Smaller resource footprint

### Cons
1. **Dependency**: Platform is unavailable if source systems are down
2. **Performance**: Cannot optimize queries with indexes
3. **Historical Analysis**: Limited by source system retention policies
4. **Cross-Source Correlation**: More complex queries across systems

## Graceful Degradation

When a data source is unavailable:
- Show degraded status for that component
- Display available data from other sources
- Show error message indicating which system is down
- Continue functioning for unaffected features

## When This Will Change

We may introduce a database if:
1. We need long-term historical analysis beyond source retention
2. Query performance becomes unacceptable
3. We need complex cross-source correlations
4. We implement ML-based anomaly detection requiring historical data

## Related Decisions

- [ADR-001: Architecture Overview](./001-architecture-overview.md)
- [ADR-004: Real-time Communication](./004-real-time-communication.md)
