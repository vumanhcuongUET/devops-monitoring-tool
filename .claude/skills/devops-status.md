---
name: devops-status
description: Check status of Kubernetes deployments, pods, and services
---

# DevOps Status

Check the status of DevOps monitoring tool deployments in Kubernetes.

## Usage

Run `/devops-status` to check overall status, or specify:
- `pods` - Check pod status
- `services` - Check service status
- `deployments` - Check deployment status
- `all` - Check everything

## Commands

```bash
# Overall status
kubectl get all -n devops-monitoring

# Pod status
kubectl get pods -n devops-monitoring

# Service status
kubectl get svc -n devops-monitoring

# Deployment status
kubectl get deployments -n devops-monitoring

# Detailed pod info
kubectl describe pods -n devops-monitoring

# Pod logs
kubectl logs -f deployment/backend -n devops-monitoring
kubectl logs -f deployment/frontend -n devops-monitoring
```

## Health Checks

### Backend Health
```bash
# Port forward and check
kubectl port-forward svc/backend 8000:80 -n devops-monitoring
curl http://localhost:8000/api/v1/overview
```

### Frontend Health
```bash
# Port forward and check
kubectl port-forward svc/frontend 3000:80 -n devops-monitoring
curl http://localhost:3000
```

## Troubleshooting

### Pods not starting
```bash
# Check pod events
kubectl describe pod <pod-name> -n devops-monitoring

# Check pod logs
kubectl logs <pod-name> -n devops-monitoring

# Check previous container logs (if crashed)
kubectl logs <pod-name> --previous -n devops-monitoring
```

### Service connectivity
```bash
# Test service endpoint
kubectl run test-pod --image=nicolaka/netshoot -it --rm --restart=Never -n devops-monitoring
curl http://backend/api/v1/overview
```

### Common Issues

**CrashLoopBackOff:**
- Check logs for errors
- Verify environment variables in ConfigMap/Secret
- Check resource limits

**ImagePullBackOff:**
- Verify image name and tag
- Check image pull secrets if using private registry

**Pending:**
- Check scheduler events
- Verify resource requests vs cluster capacity
