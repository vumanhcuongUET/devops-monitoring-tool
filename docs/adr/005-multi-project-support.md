# ADR-005: Multi-Project Support

**Status**: Accepted
**Date**: 2025-06-10
**Context**: DevOps AI Agentics 2026 Platform

## Context

The platform needs to support multiple projects (e.g., `meinvoice`, other services). We need a strategy for project isolation and configuration.

## Decision

### Config-Driven Project Isolation

We use a **YAML-based configuration hierarchy** for multi-project support:

```
config/
  global.yaml              # Default settings
projects/
  _template/               # Project template
    config.yaml
  meinvoice/               # Project-specific config
    config.yaml
    queries/
      errors.yaml          # Override default queries
```

### Configuration Hierarchy

Settings are resolved in this order:

1. **Project-specific query** (`projects/<project>/queries/<section>.yaml`)
2. **Global fallback query** (`queries/common/<section>.yaml`)
3. **Project config** (`projects/<project>/config.yaml`)
4. **Global config** (`config/global.yaml`)

### Project Configuration Structure

```yaml
# projects/meinvoice/config.yaml
inherit: global  # Inherit from global config

sources:
  elk-app:
    url: "http://meinvoice-elk:9200"
  prometheus:
    url: "http://meinvoice-prom:9090"

filters:
  namespace: "meinvoice"
  app_id: "meinvoice"

skip_sections:
  - apm_errors
  - errors
```

### AI Assistant Project Support

**Natural Language Parsing:**
- Extract project name from user queries
- Example: `"Tình trạng hệ thống meinvoice"` → project = `meinvoice`

**Project Isolation:**
- Each project has its own K8s namespace
- Separate ELK/Prometheus endpoints per project
- Project-specific query overrides

### Backend Multi-Project Support

**Current Implementation:**
- `K8S_NAMESPACES` env var for list of namespaces
- Overview endpoint aggregates across all configured namespaces
- SLO configs are service-specific (not project-specific currently)

**Future Enhancement:**
- Per-project SLO configs
- Per-project alert rules
- Project-based access control

## Rationale

### Why Config-Driven?

1. **Self-Service**: DevOps teams can add their own projects
2. **No Code Changes**: New projects don't require backend changes
3. **Version Control**: Configs can be tracked in git
4. **Flexibility**: Easy to override defaults per project

### Why Not Database?

1. **Simplicity**: YAML files are easier to edit than DB entries
2. **Deployment**: Configs can be deployed with the application
3. **Transparency**: Configs visible in version control
4. **No Migration**: No schema changes needed

## Consequences

### Positive
- Easy to add new projects
- Clear configuration structure
- Template for new projects

### Negative
- Need to restart to load config changes (currently)
- YAML syntax errors can break things
- No UI for configuration (currently)

## Future Enhancements

1. **Hot Reload**: Watch config files for changes
2. **Validation**: Validate configs on load
3. **UI**: Web interface for project configuration
4. **RBAC**: Project-based access control
5. **Per-Project Alert Rules**: Separate alert rules per project

## Related Decisions

- [ADR-001: Architecture Overview](./001-architecture-overview.md)
- [ADR-003: AI Integration Strategy](./003-ai-integration-strategy.md)

## References

- `ai_assistant/config/global.yaml` - Global configuration
- `ai_assistant/projects/_template/` - Project template
- `ai_assistant/projects/meinvoice/` - Example project
