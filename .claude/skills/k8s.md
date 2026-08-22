# Claude Code Skill: k8s - Kubernetes & GitOps Operations

## Overview

**Skill Name**: `k8s`
**Purpose**: Kubernetes and GitOps operations assistant
**Trigger**: User requests related to Kubernetes, K8s manifests, HPA, ServiceMonitor, deployments
**Version**: 1.0

---

## Skill Definition

```yaml
name: k8s
description: Kubernetes and GitOps operations assistant for manifest generation, validation, and analysis
triggers:
  - "kubectl"
  - "kubernetes"
  - "k8s"
  - "deployment"
  - "service"
  - "configmap"
  - "secret"
  - "hpa"
  - "servicemonitor"
  - "networkpolicy"
  - "pod"
  - "helm"
  - "argocd"
  - "gitops"
examples:
  - "Create HPA for backend deployment"
  - "Review ServiceMonitor config"
  - "Validate k8s manifests"
  - "Generate NetworkPolicy"
  - "Analyze pod resource usage"
```

---

## Capabilities

### 1. Manifest Generation

#### HPA (Horizontal Pod Autoscaler)
```yaml
# Input: Deployment name, scaling parameters
command: "Create HPA for backend with min 2 max 10 replicas"

output:
  apiVersion: autoscaling/v2
  kind: HorizontalPodAutoscaler
  metadata:
    name: backend-hpa
  spec:
    scaleTargetRef:
      apiVersion: apps/v1
      kind: Deployment
      name: backend
    minReplicas: 2
    maxReplicas: 10
    metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

#### ServiceMonitor (Prometheus Operator)
```yaml
# Input: Service name, port, labels
command: "Create ServiceMonitor for backend service on port 8000"

output:
  apiVersion: monitoring.coreos.com/v1
  kind: ServiceMonitor
  metadata:
    name: backend
    labels:
      app: backend
  spec:
    selector:
      matchLabels:
        app: backend
    endpoints:
    - port: http
      path: /metrics
      interval: 30s
```

#### NetworkPolicy
```yaml
# Input: Namespace, pod selector, ingress/egress rules
command: "Create NetworkPolicy allowing ingress from frontend to backend"

output:
  apiVersion: networking.k8s.io/v1
  kind: NetworkPolicy
  metadata:
    name: backend-policy
  spec:
    podSelector:
      matchLabels:
        app: backend
    policyTypes:
    - Ingress
    ingress:
    - from:
      - podSelector:
          matchLabels:
            app: frontend
      ports:
      - protocol: TCP
        port: 8000
```

---

### 2. Manifest Validation

#### Syntax Validation
```bash
# Commands generated:
kubectl apply --dry-run=client -f <manifest>
kubectl apply --validate=server -f <manifest>
kubeval <manifest>
```

#### Best Practices Check
```yaml
checks:
  - Resource requests/limits present
  - Security context configured (non-root, read-only FS)
  - Probes configured (liveness, readiness, startup)
  - Labels/annotations standards
  - Image tags (not :latest)
  - Replica count appropriate
  
output_format:
  - ✅ PASS: [check name]
  - ❌ FAIL: [check name] - [recommendation]
  - ⚠️  WARN: [check name] - [suggestion]
```

---

### 3. Resource Analysis

#### Pod Resource Usage
```yaml
# Input: Namespace, deployment
command: "Analyze resource usage for backend pods"

queries:
  - kubectl top pods -n <namespace> -l app=<app>
  - kubectl get pods -n <namespace> -o json
  - Prometheus query for resource utilization

output:
  Pod: backend-abc123
    CPU: 450m / 2 requests (22%)
    Memory: 256Mi / 512Mi limits (50%)
    Status: Under-provisioned (can reduce requests)
  Pod: backend-xyz789
    CPU: 1800m / 2 requests (90%)
    Memory: 480Mi / 512Mi limits (94%)
    Status: Over-provisioned (increase limits needed)
```

#### HPA Effectiveness
```yaml
# Input: HPA name
command: "Analyze HPA effectiveness for backend-hpa"

metrics:
  - Current replicas: 5
  - Min/Max: 2-10
  - Scaling events last 24h: 12
  - Average time to scale: 45s
  - Time at max replicas: 2h 30m
  
recommendations:
  - Consider increasing max replicas (hit max 23% of time)
  - Decrease min replicas (at min for 78% of time)
  - Add custom metric (memory) for better scaling
```

---

### 4. Configuration Analysis

#### ConfigMap/Secret Review
```yaml
# Input: Namespace
command: "Review ConfigMaps and Secrets in production namespace"

analysis:
  configmaps:
    total: 15
    with_env_vars: 12
    with_multipart_data: 3
    recommendations:
      - Migrate app-config to ConfigMap (currently hardcoded)
      
  secrets:
    total: 8
    with_ttl: 0
    recommendations:
      - Consider External Secrets Operator for rotation
      - Add annotations for secret types
```

#### Security Context Audit
```yaml
# Input: Deployment/StatefulSet/DaemonSet
command: "Audit security context for all deployments"

checks:
  - Run as non-root: ✅
  - Read-only root filesystem: ✅
  - Drop capabilities: ✅
  - Privileged mode: ✅
  - HostNetwork: ✅
  - HostPID: ✅
  
findings:
  FAIL: frontend-deployment
    - runAsUser: 0 (running as root)
    - readOnlyRootFilesystem: false
    recommendations: Add securityContext to container spec
```

---

### 5. Deployment Assistance

#### Rollout Status
```bash
# Generated commands:
kubectl rollout status deployment/<name>
kubectl rollout history deployment/<name>
kubectl get replicaset -l app=<app>
```

#### Rollback Guidance
```yaml
# Input: Deployment name
command: "Rollback backend to previous version"

steps:
  1. Check current version:
     kubectl get deployment backend -o yaml
  
  2. View rollout history:
     kubectl rollout history deployment/backend
  
  3. Perform rollback:
     kubectl rollout undo deployment/backend
  
  4. Verify rollback:
     kubectl rollout status deployment/backend
```

#### Helm Operations
```bash
# Generated commands:
helm list -n <namespace>
helm status <release> -n <namespace>
helm upgrade <release> <chart> -n <namespace> --values values.yaml
helm rollback <release> -n <namespace>
```

---

### 6. ArgoCD Operations

#### Application Sync
```yaml
# Input: ArgoCD application name
command: "Sync ArgoCD application backend-prod"

operations:
  - Check sync status:
      argocd app get backend-prod
  
  - View out-of-sync resources:
      argocd app diff backend-prod
  
  - Trigger sync:
      argocd app sync backend-prod
  
  - Verify sync:
      argocd app get backend-prod
```

#### Application Health
```yaml
# Input: Application or project
command: "Check ArgoCD application health"

health_checks:
  - Application sync status
  - Resource health
  - Operation progress
  - Recent sync failures
  
output:
  Application: backend-prod
    Sync Status: Synced
    Health: Healthy
    Operation State: Succeeded
    Recent Events: None
```

---

## Integration with Claude Code

### File Context Awareness

The skill should:
1. **Read existing K8s manifests** in the workspace
2. **Understand project structure** (k8s/ directory layout)
3. **Reference existing patterns** (consistency with current manifests)
4. **Validate against cluster** if kubeconfig available

### Tool Usage

```python
# Tools the skill should use:
- Bash: kubectl, helm, argocd commands
- Read: Manifest files, kubeconfig
- Write: Generate new manifests
- WebFetch: K8s API documentation if needed
```

---

## Safety Considerations

### Read-First Approach
- All `kubectl delete` commands require confirmation
- All `helm uninstall` commands require confirmation
- Dry-run mode by default for destructive operations

### Validation
- Validate manifests against cluster schema if available
- Check resource quotas before generating deployments
- Validate image pull secrets exist

### Namespace Safety
- Default to non-production namespaces
- Explicit confirmation for production namespace operations
- Warn before affecting system namespaces

---

## Error Handling

### Common Errors
```yaml
kubectl_not_found:
  message: "kubectl not found in PATH"
  solution: "Install kubectl or provide path"

cluster_unreachable:
  message: "Cannot connect to cluster"
  solution: "Check kubeconfig context and credentials"

namespace_not_found:
  message: "Namespace {namespace} does not exist"
  solution: "Create namespace or use existing namespace"

resource_quota_exceeded:
  message: "Creating resource would exceed quota"
  solution: "Check resource limits and quotas"
```

---

## Examples

### Example 1: Generate HPA
```
User: Create an HPA for the backend deployment with min 3 max 12 replicas

Claude:
I'll create a HorizontalPodAutoscaler for your backend deployment.

[Generates HPA manifest]
- Min replicas: 3
- Max replicas: 12
- Target CPU: 70%
- Target memory: 80%

Would you like me to apply this to your cluster?
```

### Example 2: Validate Manifests
```
User: Check if all manifests in k8s/backend/ are valid

Claude:
I'll validate all Kubernetes manifests in k8s/backend/.

[Runs kubeval]
✅ deployment.yaml - Valid
❌ service.yaml - Invalid: port name must be numeric
❌ hpa.yaml - Warning: using :latest image tag

Would you like me to fix the issues?
```

### Example 3: Analyze Resources
```
User: Show me resource usage for all deployments in production

Claude:
I'll analyze resource usage for all production deployments.

[Queries Prometheus and kubectl]

Deployments in production namespace:
1. backend - CPU: 85%, Memory: 92% ⚠️ 
2. frontend - CPU: 45%, Memory: 67%
3. worker - CPU: 78%, Memory: 71%

Recommendation: Consider scaling backend or increasing resource limits.
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-22 | Initial skill definition |

---

## Dependencies

### Required Tools
- `kubectl` - Kubernetes CLI
- `helm` - Helm package manager (optional)
- `argocd` - ArgoCD CLI (optional)
- `kubeval` - K8s manifest validation (optional)

### Python Libraries (if implementing as tool)
```python
import yaml
import json
import subprocess
from pathlib import Path
```

---

## Related Skills

- **`perf`** - For analyzing performance metrics from Kubernetes
- **`infra`** - For infrastructure-level Kubernetes configurations
- **`ci-cd`** - For CI/CD pipelines with Kubernetes deployments

---

**Skill Type**: Assistant/Guide
**Confidence**: High
**Production Ready**: Yes
