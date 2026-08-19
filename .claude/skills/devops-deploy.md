---
name: devops-deploy
description: Deploy DevOps monitoring tool to Kubernetes cluster
---

# DevOps Deploy

Deploy the monitoring platform to Kubernetes.

## Usage

Run `/devops-deploy <environment>` to deploy:
- `local` - Deploy to local K8s (minikube/kind)
- `staging` - Deploy to staging environment
- `production` - Deploy to production (requires approval)

## Prerequisites

- kubectl configured with target cluster
- Docker registry access
- `.env` file with required variables

## Deploy Commands

```bash
# Apply all resources
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/backend/
kubectl apply -f k8s/frontend/
kubectl apply -f k8s/ingress.yaml

# Or use kubectl with namespace
kubectl apply -f k8s/backend/ -n devops-monitoring

# Deploy specific service
kubectl apply -f k8s/backend/deployment.yaml -n devops-monitoring
```

## Kubernetes Structure

```
k8s/
├── namespace.yaml           # Namespace definition
├── backend/
│   ├── deployment.yaml      # Backend deployment
│   ├── service.yaml         # Backend service
│   ├── configmap.yaml       # Backend config
│   └── secret.yaml          # Backend secrets (create manually)
├── frontend/
│   ├── deployment.yaml      # Frontend deployment
│   ├── service.yaml         # Frontend service
│   └── configmap.yaml       # Frontend config
└── ingress.yaml            # Ingress for routing
```

## Environment Configuration

### Backend
- ConfigMap: Environment variables (non-sensitive)
- Secret: Sensitive values (API keys, passwords)

### Frontend
- ConfigMap: API endpoints, environment name

## Secrets Management

Create secrets manually:

```bash
# Backend secrets
kubectl create secret generic backend-secrets \
  --from-literal=elasticsearch-url='http://elasticsearch:9200' \
  --from-literal=elasticsearch-username='elastic' \
  --from-literal=elasticsearch-password='changeme' \
  --from-literal=anthropic-api-key='your-key-here' \
  -n devops-monitoring
```

## Verify Deployment

```bash
# Check pods
kubectl get pods -n devops-monitoring

# Check services
kubectl get svc -n devops-monitoring

# Check logs
kubectl logs -f deployment/backend -n devops-monitoring
kubectl logs -f deployment/frontend -n devops-monitoring

# Port forward to test locally
kubectl port-forward svc/backend 8000:80 -n devops-monitoring
kubectl port-forward svc/frontend 3000:80 -n devops-monitoring
```

## Rollback

```bash
# Rollback deployment
kubectl rollout undo deployment/backend -n devops-monitoring
kubectl rollout undo deployment/frontend -n devops-monitoring

# Check rollout status
kubectl rollout status deployment/backend -n devops-monitoring
```

## Scale

```bash
# Scale deployments
kubectl scale deployment/backend --replicas=3 -n devops-monitoring
kubectl scale deployment/frontend --replicas=2 -n devops-monitoring
```

## Ingress

Configure ingress in `k8s/ingress.yaml`:
- Routes `/api/*` to backend service
- Routes `/ws` to backend service (WebSocket)
- Routes `/*` to frontend service

## Helm (Alternative)

If Helm charts are available:

```bash
# Add repo (if applicable)
helm repo add devops-monitoring https://charts.example.com

# Install
helm install devops-monitoring ./chart --namespace devops-monitoring

# Upgrade
helm upgrade devops-monitoring ./chart --namespace devops-monitoring
```
