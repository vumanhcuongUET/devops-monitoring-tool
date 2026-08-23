# GitOps Configuration Repository

This repository contains all configuration for the DevOps Monitoring Platform using GitOps methodology.

## 📁 Repository Structure

```
config-repo/
├── global/              # Global configurations and defaults
│   ├── defaults.yaml    # Default values for all projects
│   ├── policies.yaml    # Global policies (validation, security, RBAC)
│   └── schemas/         # Configuration validation schemas
│       ├── project.schema.yaml
│       ├── alert.schema.yaml
│       ├── slo.config.schema.yaml
│       ├── deployment.config.schema.yaml
│       └── monitoring.config.schema.yaml
├── projects/            # Project-specific configurations
│   ├── meinvoice/
│   │   ├── config.yaml       # Main project config
│   │   ├── alerts.yaml       # Alert rules (optional)
│   │   ├── slos.yaml         # SLO configs (optional)
│   │   └── priorities.yaml   # Priority overrides (optional)
│   └── [other projects]/
└── versions/            # Versioned configurations (for rollback)
    └── v1.0.0/
```

## 🌳 Branch Strategy

| Branch | Environment | Purpose |
|--------|-------------|---------|
| `main` | Production | Production configurations (requires approval) |
| `develop` | Staging | Staging configurations |
| `feature/*` | Development | Feature branches and project configs |

## 📝 Configuration Types

### Project Configuration
Defines monitoring, caching, and SLO settings for a project.

**File**: `projects/{project}/config.yaml`
**Schema**: `global/schemas/project.schema.yaml`

### Alert Configuration
Defines alert rules and notification settings.

**File**: `projects/{project}/alerts.yaml`
**Schema**: `global/schemas/alert.schema.yaml`

### SLO Configuration
Defines Service Level Objectives and error budgets.

**File**: `projects/{project}/slos.yaml`
**Schema**: `global/schemas/slo.config.schema.yaml`

## 🔄 GitOps Workflow

### Making Configuration Changes

1. **Create feature branch** (for development/testing):
   ```bash
   git checkout -b config/meinvoice/new-feature
   ```

2. **Edit configuration files**:
   ```bash
   vim projects/meinvoice/config.yaml
   ```

3. **Validate configuration**:
   ```bash
   python scripts/validate-config.py projects/meinvoice/config.yaml
   ```

4. **Commit changes**:
   ```bash
   git add projects/meinvoice/config.yaml
   git commit -m "Update meinvoice SLO targets"
   ```

5. **Push and create PR** (for production):
   ```bash
   git push origin config/meinvoice/new-feature
   # Create PR to main branch
   ```

6. **Merge and auto-sync**:
   - Backend automatically syncs changes
   - Validates against schemas
   - Applies to target environment

### Emergency Rollback

```bash
# List versions
./scripts/config-cli.py list-versions meinvoice

# Rollback to specific version
./scripts/config-cli.py rollback meinvoice v1.0.0 --reason "Emergency rollback"
```

## ✅ Validation

All configurations are validated against schemas before being applied:

- **Schema validation**: Ensures required fields and correct types
- **Business logic validation**: Custom validation rules
- **Policy compliance**: Checks against global policies

Failed validations prevent changes from being applied.

## 🔐 Security

- **Secrets**: Never store secrets in this repository
- **Secret references**: Use `password_ref: "secret/name"` format
- **Encryption**: Sensitive configs encrypted at rest
- **Audit logging**: All changes logged with author and timestamp

## 📊 Monitoring

Configuration changes trigger:

- **Validation events**: Logged to audit log
- **Sync events**: Tracked in Prometheus
- **Change notifications**: Sent to Slack on production changes

## 🛠️ Useful Commands

```bash
# Validate all configs
./scripts/validate-all-configs.sh

# Sync changes to backend
./scripts/sync-configs.sh

# List project versions
./scripts/config-cli.py list-versions {project}

# Diff versions
./scripts/config-cli.py diff {project} v1.0.0 v1.1.0

# Export config for environment
./scripts/export-config.sh staging
```

## 📚 Related Documentation

- [Phase 7 Plan](../../docs/phase-7-production-hardening.md)
- [Configuration Management](../../docs/phase-7-production-hardening.md#sprint-4-configuration-management)
- [Schema Documentation](../../docs/config-schemas.md)

## 🆘 Support

For configuration issues:
1. Check validation output: `./scripts/validate-config.py`
2. Review schema definitions in `global/schemas/`
3. Contact: platform-team@example.com
