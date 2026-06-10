# ADR-003: AI Integration Strategy

**Status**: Accepted
**Date**: 2025-06-10
**Context**: DevOps AI Agentics 2026 Platform

## Context

We want to integrate AI capabilities for automated incident analysis and recommendations. We need to decide on the AI model, integration approach, and safety measures.

## Decision

### Model Choice: Anthropic Claude

We chose **Anthropic's Claude API** for AI-powered incident analysis.

**Rationale:**
- Strong performance on technical/analysis tasks
- Good at following structured output formats
- Supports long context windows for comprehensive incident data
- Reliable API with good uptime
- Built-in safety measures

### Triage Card Generation

**API Endpoint:** `POST /api/v1/analyze`

**Input:**
- Project name
- Incident ID
- Alert message
- Time range
- Whether to include recommendations

**Process:**
1. Collect context from multiple sources (logs, APM, metrics, K8s)
2. Build comprehensive prompt with system instructions
3. Call Claude API with structured output requirements
4. Parse response into Triage Card JSON

**Output Structure:**
```json
{
  "project": "meinvoice",
  "incident_id": "incident-001",
  "summary": "Payment service experiencing elevated error rate...",
  "severity": "high",
  "findings": [
    {
      "type": "root_cause",
      "title": "Database connection timeout",
      "confidence": 0.9
    }
  ],
  "recommendations": [
    {
      "priority": 1,
      "action": "Check database connectivity",
      "command": "kubectl exec ..."
    }
  ]
}
```

### Config-Driven System Prompts

We use **YAML-based configuration** for system prompts:

- Default DevOps expert prompt in `backend/app/services/llm_client.py`
- Project-specific overrides possible (future)
- Prompt includes: role definition, output format requirements, safety guidelines

### Human-in-the-Loop Principle

Following the strategic vision from `docs/chien_luoc_tong_the.md`:

**Current Phase (Phase 1-2):**
- AI provides analysis and recommendations
- Human must approve before any actions are taken
- AI output is advisory only

**Future Phases (Phase 3-4):**
- May progress to autonomous actions for low-risk tasks
- Always maintain audit trail
- RBAC to control what AI can do

### Safety Measures

1. **Output Validation**: Parse and validate AI response against schema
2. **Command Sanitization**: Validate any generated CLI commands
3. **Confidence Thresholds**: Only show findings with sufficient confidence
4. **Evidence Requirements**: AI must provide evidence for claims

### Language Support

The platform supports **Vietnamese output** for:
- AI Assistant (CLI) responses
- Triage Card summaries and recommendations

This aligns with the Vietnamese development team's workflow.

## Related Decisions

- [ADR-001: Architecture Overview](./001-architecture-overview.md)
- [ADR-005: Multi-Project Support](./005-multi-project-support.md)

## References

- `docs/chien_luoc_tong_the.md` - Strategic roadmap with 4 phases
- `docs/requirement.md` - Functional requirements for AI features
