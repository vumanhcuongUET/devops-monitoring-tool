# Kubernetes Manifests Review Skill

Review Kubernetes manifests for security, reliability, and best practices.

## What to Check

### 1. Resource Management

**Missing Resource Limits**
```yaml
# ❌ VULNERABLE - No limits, can consume all node resources
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: app
    image: myapp:latest

# ✅ SECURE - Resource requests and limits
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: app
    image: myapp:latest
    resources:
      requests:
        memory: "128Mi"
        cpu: "100m"
      limits:
        memory: "256Mi"
        cpu: "500m"
```

**Excessive Resources**
```yaml
# ❌ BAD - Wasteful resource allocation
resources:
  limits:
    memory: "8Gi"  # Too high for most workloads
    cpu: "4"

# ✅ GOOD - Reasonable limits based on usage
resources:
  limits:
    memory: "512Mi"  # Based on actual usage monitoring
    cpu: "500m"
```

### 2. Security Context

**Running as Root**
```yaml
# ❌ VULNERABLE - Running as root user
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: app
    image: myapp:latest
    securityContext:
      runAsUser: 0  # Root

# ✅ SECURE - Non-root user
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: app
    image: myapp:latest
    securityContext:
      runAsUser: 1000
      runAsGroup: 1000
      runAsNonRoot: true
      fsGroup: 1000
      readOnlyRootFilesystem: true
      allowPrivilegeEscalation: false
```

**Privileged Containers**
```yaml
# ❌ VULNERABLE - Privileged container
spec:
  containers:
  - name: app
    securityContext:
      privileged: true

# ✅ SECURE - No privileges
spec:
  containers:
  - name: app
    securityContext:
      privileged: false
      allowPrivilegeEscalation: false
      capabilities:
        drop:
        - ALL
```

### 3. Host Access

**Host Network/PID**
```yaml
# ❌ VULNERABLE - Host access
spec:
  hostNetwork: true
  hostPID: true
  hostIPC: true

# ✅ SECURE - No host access
spec:
  hostNetwork: false
  hostPID: false
  hostIPC: false
```

**Host Path Volumes**
```yaml
# ❌ VULNERABLE - Host path mount
spec:
  volumes:
  - name: host-root
    hostPath:
      path: /  # Entire host filesystem!

# ✅ SECURE - Avoid hostPath or use specific paths
spec:
  volumes:
  - name: config
    configMap:
      name: app-config
```

### 4. Secrets Management

**Secrets as Environment Variables**
```yaml
# ❌ VULNERABLE - Secrets in environment (visible in logs, etc.)
spec:
  containers:
  - name: app
    env:
    - name: API_KEY
      valueFrom:
        secretKeyRef:
          name: api-secret
          key: api-key

# ✅ SECURE - Mount as file (more secure)
spec:
  containers:
  - name: app
    volumeMounts:
    - name: secrets
      mountPath: /etc/secrets
      readOnly: true
  volumes:
  - name: secrets
    secret:
      secretName: api-secret
      defaultMode: 0400
```

**Hardcoded Secrets**
```yaml
# ❌ VULNERABLE - Secret in manifest
spec:
  containers:
  - name: app
    env:
    - name: PASSWORD
      value: "hardcoded-password"

# ✅ SECURE - Reference Secret
spec:
  containers:
  - name: app
    env:
    - name: PASSWORD
      valueFrom:
        secretKeyRef:
          name: db-secret
          key: password
```

### 5. Network Security

**Missing NetworkPolicy**
```yaml
# ❌ INSECURE - All pods can communicate
# No NetworkPolicy defined

# ✅ SECURE - Network isolation
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: app-network-policy
spec:
  podSelector:
    matchLabels:
      app: myapp
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: frontend
    ports:
    - protocol: TCP
      port: 8080
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: database
    ports:
    - protocol: TCP
      port: 5432
```

**Exposing Services Directly**
```yaml
# ❌ BAD - Service exposed without restrictions
apiVersion: v1
kind: Service
spec:
  type: LoadBalancer  # Publicly accessible!

# ✅ GOOD - Use Ingress with authentication
apiVersion: v1
kind: Service
spec:
  type: ClusterIP  # Internal only
---
apiVersion: networking.k8s.io/v1
kind: Ingress
spec:
  tls:
  - hosts:
    - api.example.com
    secretName: tls-cert
  rules:
  - host: api.example.com
    http:
      paths:
      - path: /
        backend:
          service:
            name: app
```

### 6. Health Checks

**Missing Liveness Probe**
```yaml
# ❌ BAD - No liveness probe, dead pods not restarted
spec:
  containers:
  - name: app
    image: myapp:latest

# ✅ GOOD - Liveness and readiness probes
spec:
  containers:
  - name: app
    image: myapp:latest
    livenessProbe:
      httpGet:
        path: /health/live
        port: 8080
      initialDelaySeconds: 30
      periodSeconds: 10
      timeoutSeconds: 5
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /health/ready
        port: 8080
      initialDelaySeconds: 5
      periodSeconds: 5
      timeoutSeconds: 3
      failureThreshold: 2
    startupProbe:
      httpGet:
        path: /health/startup
        port: 8080
      initialDelaySeconds: 0
      periodSeconds: 5
      failureThreshold: 12  # 60s total (5s * 12)
```

### 7. Image Security

**Using `latest` Tag**
```yaml
# ❌ BAD - Unpredictable, cannot rollback
spec:
  containers:
  - name: app
    image: myapp:latest  # What version is this?

# ✅ GOOD - Pinned version
spec:
  containers:
  - name: app
    image: myapp:v1.2.3  # Pinned version
    imagePullPolicy: IfNotPresent
```

**Untrusted Images**
```yaml
# ❌ BAD - Using random image from Docker Hub
image: randomuser/unverified-app:latest

# ✅ GOOD - Verified images
image: registry.company.com/myapp:v1.2.3  # Internal registry
```

### 8. Pod Disruption Budget

**Missing PDB**
```yaml
# ❌ BAD - No disruption budget, can lose all pods during updates

# ✅ GOOD - Pod Disruption Budget ensures availability
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: app-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: myapp
```

### 9. RBAC

**Overly Permissive RBAC**
```yaml
# ❌ VULNERABLE - Cluster admin for service account
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: app-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin  # Too powerful!
subjects:
- kind: ServiceAccount
  name: app-sa

# ✅ SECURE - Least privilege
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  namespace: production
  name: app-role
rules:
- apiGroups: [""]
  resources: ["configmaps"]
  verbs: ["get", "list"]  # Only what's needed
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  namespace: production
  name: app-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: app-role
subjects:
- kind: ServiceAccount
  name: app-sa
  namespace: production
```

### 10. Deployment Safety

**Unsafe Rolling Update**
```yaml
# ❌ BAD - Can cause downtime
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 0
      maxUnavailable: 50%  # Half the pods down!

# ✅ GOOD - Zero downtime
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 25%        # Create new pods first
      maxUnavailable: 0     # No downtime
```

**No Revision History Limit**
```yaml
# ❌ BAD - Unlimited history, consumes etcd space
spec:
  revisionHistoryLimit: 0  # Cannot rollback!
# Or no limit (old deployments accumulate)

# ✅ GOOD - Limited history
spec:
  revisionHistoryLimit: 10  # Keep last 10 for rollback
```

## Review Checklist

For each Kubernetes manifest, check:

- [ ] Resource requests and limits are set
- [ ] Containers run as non-root user
- [ ] No privileged containers
- [ ] No hostNetwork, hostPID, hostIPC
- [ ] HostPath volumes minimized and justified
- [ ] Secrets mounted as files, not env vars
- [ ] No hardcoded secrets in manifests
- [ ] Network policies define pod-to-pod communication
- [ ] Liveness, readiness, and startup probes configured
- [ ] Images use pinned versions (not `latest`)
- [ ] Images from trusted registries
- [ ] Pod Disruption Budget configured for availability
- [ ] RBAC follows least privilege principle
- [ ] Rolling update config ensures zero downtime
- [ ] Revision history limit configured

## Output Format

```markdown
## Kubernetes Review: [file_name]

### Critical
- [Issue] - [Security impact] - [Recommendation]

### High
- [Issue] - [Impact] - [Recommendation]

### Medium
- [Issue] - [Impact] - [Recommendation]

### Low
- [Issue] - [Impact] - [Recommendation]

### Positive Patterns
+ [Good practice found]
```
