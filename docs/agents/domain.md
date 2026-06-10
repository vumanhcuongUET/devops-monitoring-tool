# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root — contains the project's domain language and key concepts
- **`docs/adr/`** — read ADRs that touch the area you're about to work in

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront.

## File structure

This is a **single-context repo**:

```
/
├── CONTEXT.md              ← Domain language for the entire platform
├── docs/
│   ├── adr/               ← Architecture Decision Records
│   │   ├── 001-architecture-overview.md
│   │   ├── 002-no-database-architecture.md
│   │   ├── 003-ai-integration-strategy.md
│   │   ├── 004-real-time-communication.md
│   │   └── 005-multi-project-support.md
│   ├── chien_luoc_tong_the.md  ← Strategic roadmap (Vietnamese)
│   └── requirement.md           ← Functional requirements
└── devops_ai_agentics_2026/
    ├── backend/            ← FastAPI backend
    ├── frontend/           ← React dashboard
    ├── ai_assistant/       ← Claude CLI monitoring assistant
    └── ...
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

Key domain terms include:
- **Health Status**: healthy, degraded, down
- **Data Sources**: Elasticsearch, APM, Prometheus, Kubernetes
- **Monitoring Concepts**: Transactions, Pods, Deployments, Nodes
- **Alerting**: Alert Rules, Alert Events, Severity (info/warning/critical)
- **SLO System**: Availability, Latency, Error Budget, Rolling Windows
- **Triage Cards**: AI-generated incident analysis

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for documentation).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-002 (no database architecture) — but worth reopening because…_

## Language Notes

- Most documentation is in English for compatibility with AI tools
- Strategic documents in `docs/` are in Vietnamese (`chien_luoc_tong_the.md`, `requirement.md`)
- The platform supports Vietnamese output for AI features (Triage Cards, AI Assistant)
