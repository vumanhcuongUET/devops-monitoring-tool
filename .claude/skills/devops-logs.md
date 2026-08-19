---
name: devops-logs
description: View and stream logs from backend and frontend deployments
---

# DevOps Logs

View logs from the DevOps monitoring tool deployments.

## Usage

Run `/devops-logs` to view logs, or specify:
- `backend` - Backend logs
- `frontend` - Frontend logs
- `all` - Both services

## Local Development Logs

```bash
# Backend (running with uvicorn)
cd backend
# Logs output to terminal when running: uvicorn app.main:app --reload

# Frontend (running with npm run dev)
cd frontend
# Logs output to terminal when running: npm run dev
```

## Kubernetes Logs

```bash
# Backend logs
kubectl logs -f deployment/backend -n devops-monitoring

# Frontend logs
kubectl logs -f deployment/frontend -n devops-monitoring

# All pods
kubectl logs -f -l app=devops-monitoring -n devops-monitoring

# Previous container logs (if crashed)
kubectl logs deployment/backend --previous -n devops-monitoring
```

## Docker Logs

```bash
# Backend container
docker logs -f devops-monitoring-backend

# Frontend container
docker logs -f devops-monitoring-frontend

# All services
docker compose logs -f
```

## Log Levels

Configure log levels in `.env`:
```
LOG_LEVEL=debug    # Development
LOG_LEVEL=info     # Production
```

## Structured Logs

Backend uses Python logging with structured output:
- Timestamp
- Level (DEBUG, INFO, WARNING, ERROR)
- Module
- Message
- Extra context (when applicable)

## Troubleshooting via Logs

### Backend Issues
```bash
# Check for startup errors
kubectl logs deployment/backend -n devops-monitoring | grep -i error

# Check for database/connection issues
kubectl logs deployment/backend -n devops-monitoring | grep -i "connection\|database"

# Check for LLM API issues
kubectl logs deployment/backend -n devops-monitoring | grep -i "anthropic\|claude"
```

### Frontend Issues
```bash
# Check for build errors
kubectl logs deployment/frontend -n devops-monitoring | grep -i error

# Check for API errors
kubectl logs deployment/frontend -n devops-monitoring | grep -i "fetch\|api"
```

## Log Aggregation

If using centralized logging (ELK):
- Backend logs: `index: devops-monitoring-backend-*`
- Frontend logs: `index: devops-monitoring-frontend-*`
