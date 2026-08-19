# Open Policy Agent (OPA) Deployment

This directory contains Kubernetes manifests for deploying OPA server for policy evaluation.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Policy Enforcement                     │
│                                                              │
│  Action Request ──► OPA Server ──► Allow/Deny + Reasons     │
│                      │                                     │
│                      ├─── Rego Policies                    │
│                      └─── Data (external)                  │
└─────────────────────────────────────────────────────────────┘
```

## Deployment

### Deploy OPA Server

```bash
# Create namespace
kubectl create namespace opa

# Deploy OPA server
kubectl apply -f k8s/opa/

# Verify deployment
kubectl get pods -n opa
```

### Load Policies

```bash
# Load policies from bundle
kubectl exec -n opa deployment/opa -- \
  opa policy load policies/opa/

# Or use the REST API
curl -X POST http://opa.opa.svc:8181/v1/policies \
  -H "Content-Type: text/plain" \
  --data-binary @policies/opa/actions.rego
```

## Testing

### Test Policy Evaluation

```bash
curl -X POST http://opa.opa.svc:8181/v1/data/devops/actions/allow \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "action": {"command": "kubectl delete pod"},
      "project": "meinvoice",
      "environment": "production",
      "user": "john.doe"
    }
  }'
```

### Using the API

```bash
curl -X POST http://backend/api/v1/governance/policies/validate \
  -H "X-API-Key: <key>" \
  -H "Content-Type: application/json" \
  -d '{
    "action": {"command": "kubectl delete pod"},
    "project": "meinvoice"
  }'
```

## Troubleshooting

### Check OPA Logs

```bash
kubectl logs -n opa deployment/opa --tail=100 -f
```

### View Active Policies

```bash
kubectl exec -n opa deployment/opa -- \
  curl http://localhost:8181/v1/policies
```
