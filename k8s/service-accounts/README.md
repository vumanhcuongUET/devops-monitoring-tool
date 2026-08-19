# AI Agent Service Accounts

This directory contains Kubernetes service account manifests for AI agents with RBAC configuration.

## Service Accounts

### Production - Read Only (`prod-viewer.yaml`)
- **Purpose:** Production monitoring and analysis
- **Permissions:** View-only (get, list, watch)
- **Constraints:** No modify, no delete, no create
- **Use Case:** Triage cards, overview generation, SLO tracking

### Staging - Operator (`staging-operator.yaml`)
- **Purpose:** Staging environment operations
- **Permissions:** Edit (get, list, watch, create, update, patch)
- **Constraints:** No delete PVC, no delete namespace
- **Use Case:** Action execution in staging, testing workflows

### Development - Admin (`dev-admin.yaml`)
- **Purpose:** Development environment full access
- **Permissions:** Admin (all permissions)
- **Constraints:** None
- **Use Case:** Development, testing, skill development

## Deployment

### Apply Service Accounts

```bash
# Production (read-only)
kubectl apply -f k8s/service-accounts/prod-viewer.yaml

# Staging (operator)
kubectl apply -f k8s/service-accounts/staging-operator.yaml

# Development (admin)
kubectl apply -f k8s/service-accounts/dev-admin.yaml
```

### Verify

```bash
# Verify service accounts
kubectl get sa -n ai-agents

# Verify roles
kubectl get roles -n ai-agents

# Verify role bindings
kubectl get rolebindings -n ai-agents
```

## Integration

The Action Engine uses these service accounts for command execution:

```python
from app.governance.service_accounts import get_service_account_config

sa_config = get_service_account_config("meinvoice")
# Returns: {
#     "service_account": "ai-agent-prod-viewer",
#     "namespace": "ai-agents",
#     "environment": "production"
# }
```

## Security

- Service accounts use least privilege principle
- Credentials are short-lived (1 hour TTL)
- All SA usage is logged to audit trail
- SA rotation happens quarterly
