# GitOps Configuration Repository

This repository contains all configuration for the DevOps Monitoring Platform using GitOps methodology.

## Structure

```
configs/
├── global/
│   ├── defaults.yaml          # Global defaults
│   ├── policies.yaml          # Global policies
│   └── schemas/               # Configuration schemas
│       ├── project.schema.yaml
│       ├── alert.schema.yaml
│       ├── slo.config.schema.yaml
│       ├── deployment.config.schema.yaml
│       └── monitoring.config.schema.yaml
├── projects/                 # Project-specific configurations
│   └── meinvoice/
│       ├── config.yaml         # Project config
│       ├── alerts.yaml          # Alert rules
│       └── slos.yaml            # SLO configurations
└── versions/                  # Versioned configurations
    └── v1.0.0/
```

## Workflow

### Branch Strategy

- `main` - Production configuration (merged after approval)
- `develop` - Staging configuration (merged after review)
- `feature/*` - Feature branches for individual changes

### Change Process

1. Create feature branch from `develop`
2. Make configuration changes
3. Validate against schemas
4. Create pull request
5. Request review and approval
6. Merge to `develop`
7. After testing, promote to `main`

### Schema Validation

All configurations are validated against schemas before merge:

```bash
# Validate project config
python -m backend.app.config.validation \
  --config configs/projects/meinvoice/config.yaml \
  --schema project
```

## Configuration Types

### Project Configuration (`config.yaml`)

Main project configuration including:
- Project metadata
- Monitoring sources
- Alert channels
- Cache settings
- SLO targets

### Alert Configuration (`alerts.yaml`)

Alert rule definitions:
- Conditions and thresholds
- Actions and notifications
- Severity levels
- Cooldown periods

### SLO Configuration (`slos.yaml`)

Service Level Objectives:
- Availability targets
- Latency targets
- Error budgets
- SLI queries

## Best Practices

1. **Use Secrets References**: Never hardcode passwords, use `${VAR_NAME}` format
2. **Document Changes**: Add clear commit messages explaining what and why
3. **Validate Locally**: Always validate configs before committing
4. **Test in Staging**: Promote to production after staging validation
5. **Tag Releases**: Use semantic versioning for production releases

## Commands

```bash
# Validate all configurations
make validate-all

# Sync changes to production
make sync-production

# Rollback to previous version
make rollback VERSION=v1.2.3

# View diff between versions
make diff FROM=v1.2.3 TO=v1.2.4
```

## Support

For configuration issues, contact:
- Platform Team: platform@company.com
- Documentation: [Confluence Link]
