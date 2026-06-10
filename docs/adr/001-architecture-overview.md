# ADR-001: Architecture Overview

**Status**: Accepted
**Date**: 2025-06-10
**Context**: DevOps AI Agentics 2026 Platform

## Context

We need a unified monitoring platform that aggregates data from multiple observability tools (Elasticsearch, APM, Prometheus, Kubernetes) and provides AI-powered incident analysis.

## Decision

### Unified Dashboard Architecture

We chose a **unified dashboard approach** where a single platform aggregates data from all monitoring tools, rather than using separate tools for each system.

**Rationale:**
- Reduces context switching during incident response
- Enables correlation across different data sources
- Provides a single pane of glass for NOC-style monitoring
- Allows AI to reason about holistic system state

### Technology Stack

**Backend: Python FastAPI**
- Async/await support for concurrent data source queries
- Pydantic for type-safe data validation
- Built-in OpenAPI documentation
- Easy async WebSocket support

**Frontend: React 19 + TypeScript**
- Strong typing for data models
- Modern reactive patterns with hooks
- Vite for fast development and optimized builds
- TanStack Query for server state management

**Rationale for Stack:**
- Python aligns with DevOps/SRE skill sets
- FastAPI's async model fits the I/O-bound monitoring workload
- TypeScript ensures type safety across the full stack
- React ecosystem provides mature visualization libraries

### Multi-Source Aggregation Pattern

We implement **parallel aggregation** where all data sources are queried concurrently:

```python
results = await asyncio.gather(
    elasticsearch_client.get_health(),
    prometheus_client.get_metrics(),
    kubernetes_client.get_pod_status(),
    return_exceptions=True
)
```

**Timeout per source:** 5 seconds
**Behavior:** One source being down doesn't block others

## Consequences

### Positive
- Fast response times despite querying multiple systems
- Resilient to partial outages
- Clear separation of concerns (one client per source)
- Easy to add new data sources

### Negative
- More complex deployment (must connect to multiple external systems)
- Network dependency on all data sources
- Authentication must be managed for each source

### Trade-offs
- **Chose**: State minimal design (no database)
- **Rejected**: Full data warehousing approach
- **Reason**: Platform aggregates, doesn't store - keeps it lightweight

## Related Decisions

- [ADR-002: No Database Architecture](./002-no-database-architecture.md)
- [ADR-003: AI Integration Strategy](./003-ai-integration-strategy.md)
- [ADR-004: Real-time Communication](./004-real-time-communication.md)
