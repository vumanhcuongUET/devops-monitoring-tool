# DevOps AI Agentics 2026 - Deployment Guide

**Version**: 1.0
**Last Updated**: 2026-08-25
**Status**: ✅ Production Ready (Phase 9) | 📋 Enhanced (Phase 10)

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Architecture Overview](#2-architecture-overview)
3. [Component Specifications](#3-component-specifications)
4. [Resource Requirements](#4-resource-requirements)
5. [Deployment Steps](#5-deployment-steps)
6. [Post-Deployment Validation](#6-post-deployment-validation)
7. [Operations & Maintenance](#7-operations--maintenance)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Prerequisites

### 1.1 Infrastructure Requirements

| Component | Minimum Version | Notes |
|-----------|-----------------|-------|
| **Kubernetes** | 1.25+ | For production deployment |
| **Docker** | 20.x+ | For local development |
| **Helm** | 3.x+ | Optional (for package management) |
| **PostgreSQL** | 16+ | Phase 10 requirement |
| **Redis** | 7.x+ | For distributed state |
| **Elasticsearch** | 7.x+ | For logs and APM data |
| **Prometheus** | 2.45+ | For metrics |
| **Nginx Ingress** | 1.x+ | For routing |

### 1.2 External Services (Required)

| Service | Purpose | Example Endpoint |
|---------|---------|------------------|
| **Elasticsearch** | Log & APM storage | `http://elasticsearch:9200` |
| **Prometheus** | Metrics collection | `http://prometheus:9090` |
| **S3/MinIO** | Backup storage | `s3://backups` |
| **Slack** | Alert notifications | `https://hooks.slack.com/...` |
| **Anthropic Claude** | AI features | `https://api.anthropic.com` |

### 1.3 Software Requirements

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.12+ | Backend development |
| Node.js | 20.x+ | Frontend development |
| kubectl | 1.25+ | K8s operations |
| aws-cli | 2.x+ | S3 backup operations |

---

## 2. Architecture Overview

### 2.1 System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User Access Layer                            │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────┐ │
│  │  Web Browser     │────│  Nginx Ingress   │────│  API Gateway  │ │
│  └──────────────────┘    └──────────────────┘    └──────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────────────┐
│                         Application Layer                            │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────┐ │
│  │  Frontend (React)│────│  Backend (FastAPI)│───│  WebSocket   │ │
│  │  - 2 replicas    │    │  - 2 replicas     │    │  - Live updates│ │
│  └──────────────────┘    └──────────────────┘    └──────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────────────┐
│                          Service Layer                               │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐│
│  │   ES    │ │  Prom   │ │  K8s    │ │  Redis  │ │  PostgreSQL  ││
│  │ Client  │ │  Client │ │  Client │ │  Store  │ │  (Phase 10) ││
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────────────┐
│                          Data Layer                                  │
│  ┌─────────────────┐ ┌─────────────┐ ┌─────────┐ ┌──────────────┐│
│  │  Elasticsearch  │ │  Prometheus │ │  Redis  │ │  PostgreSQL   ││
│  │  - APM data     │ │  - Metrics  │ │ - State │ │  - Audit log  ││
│  │  - Logs         │ │             │ │         │ │  - Approvals  ││
│  └─────────────────┘ └─────────────┘ └─────────┘ └──────────────┘│
└─────────────────────────────────────────────────────────────────────┘

                                │
┌─────────────────────────────────────────────────────────────────────┐
│                       Observability Layer                            │
│  ┌──────────────┐ ┌──────────────┐ ┌─────────────┐ ┌────────────┐ │
│  │ OpenTelemetry│ │    Jaeger    │ │   Grafana   │ │ Alertmanager│ │
│  │  - Tracing   │ │  - Trace UI  │ │ - Dashboards│ │ - Alerts   │ │
│  └──────────────┘ └──────────────┘ └─────────────┘ └────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Network Architecture

```
Internet
    │
    ▼
┌───────────────────────────────────────────────┐
│  Load Balancer / Nginx Ingress                │
│  - TLS termination                            │
│  - WebSocket support                          │
│  - Rate limiting                              │
└───────────────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────────────┐
│  Frontend (React)                              │
│  - 2 replicas (HPA: 2-10)                     │
│  - Service: frontend:80                        │
└───────────────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────────────┐
│  Backend (FastAPI)                             │
│  - 2 replicas (HPA: 2-10)                     │
│  - Service: backend:8000                      │
└───────────────────────────────────────────────┘
    │
    ├─────────────────────────────────────────────┐
    │                                             │
    ▼                                             ▼
┌──────────────────┐                    ┌──────────────────┐
│  Service Network │                    │  Data Network    │
│  - Elasticsearch │                    │  - PostgreSQL    │
│  - Prometheus    │                    │  - Redis         │
│  - Kubernetes    │                    │  - Backup Store  │
└──────────────────┘                    └──────────────────┘
```

---

## 3. Component Specifications

### 3.1 Backend Service

```yaml
# k8s/backend/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: monitor-backend
  namespace: devops-monitor
spec:
  replicas: 2
  selector:
    matchLabels:
      app: monitor-backend
  template:
    metadata:
      labels:
        app: monitor-backend
        version: v1.0.0
    spec:
      serviceAccountName: monitor-backend
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
        seccompProfile:
          type: RuntimeDefault
      containers:
      - name: backend
        image: your-registry/devops-monitor-backend:v1.0.0
        ports:
        - containerPort: 8000
          name: http
          protocol: TCP
        envFrom:
        - configMapRef:
            name: monitor-backend-config
        - secretRef:
            name: monitor-backend-secrets
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 1Gi
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop:
            - ALL
        startupProbe:
          httpGet:
            path: /health
            port: http
          initialDelaySeconds: 30
          periodSeconds: 5
          failureThreshold: 30
        livenessProbe:
          httpGet:
            path: /health
            port: http
          initialDelaySeconds: 30
          periodSeconds: 30
          timeoutSeconds: 5
        readinessProbe:
          httpGet:
            path: /health
            port: http
          initialDelaySeconds: 10
          periodSeconds: 10
          timeoutSeconds: 3
        volumeMounts:
        - name: tmp
          mountPath: /tmp
      volumes:
      - name: tmp
        emptyDir: {}
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: monitor-backend-hpa
  namespace: devops-monitor
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: monitor-backend
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 100
        periodSeconds: 30
```

### 3.2 Frontend Service

```yaml
# k8s/frontend/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: monitor-frontend
  namespace: devops-monitor
spec:
  replicas: 2
  selector:
    matchLabels:
      app: monitor-frontend
  template:
    metadata:
      labels:
        app: monitor-frontend
        version: v1.0.0
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
      - name: frontend
        image: your-registry/devops-monitor-frontend:v1.0.0
        ports:
        - containerPort: 80
          name: http
        env:
        - name: VITE_API_URL
          value: "https://monitoring.yourdomain.com"
        resources:
          requests:
            cpu: 50m
            memory: 64Mi
          limits:
            cpu: 500m
            memory: 256Mi
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop:
            - ALL
        livenessProbe:
          httpGet:
            path: /
            port: http
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /
            port: http
          initialDelaySeconds: 10
          periodSeconds: 10
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: monitor-frontend-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: monitor-frontend
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

### 3.3 PostgreSQL (Phase 10)

```yaml
# k8s/postgresql/deployment.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: devops-monitor
spec:
  serviceName: postgres
  replicas: 2
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:16-alpine
        ports:
        - containerPort: 5432
        env:
        - name: POSTGRES_DB
          value: devops_monitor
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: postgres-secrets
              key: username
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-secrets
              key: password
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
        volumeMounts:
        - name: postgres-data
          mountPath: /var/lib/postgresql/data
        resources:
          requests:
            cpu: 200m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 2Gi
        livenessProbe:
          exec:
            command:
            - pg_isready
            - -U
            - $(POSTGRES_USER)
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          exec:
            command:
            - pg_isready
            - -U
            - $(POSTGRES_USER)
          initialDelaySeconds: 10
          periodSeconds: 5
  volumeClaimTemplates:
  - metadata:
      name: postgres-data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: fast-ssd
      resources:
        requests:
          storage: 20Gi
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: devops-monitor
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
  clusterIP: None
```

### 3.4 Redis Cluster

```yaml
# k8s/monitoring/redis-cluster.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis
  namespace: devops-monitor
spec:
  serviceName: redis
  replicas: 6
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        command:
        - redis-server
        - /redis-config/redis.conf
        ports:
        - containerPort: 6379
        - containerPort: 16379
        volumeMounts:
        - name: redis-config
          mountPath: /redis-config
        - name: redis-data
          mountPath: /data
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 1Gi
      volumes:
      - name: redis-config
        configMap:
          name: redis-config
  volumeClaimTemplates:
  - metadata:
      name: redis-data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: fast-ssd
      resources:
        requests:
          storage: 5Gi
```

---

## 4. Resource Requirements

### 4.1 Development Environment (Docker Compose)

| Component | CPU | Memory | Disk | Notes |
|-----------|-----|--------|------|-------|
| Backend | 1 core | 512Mi | 1Gi | Single replica |
| Frontend | 0.5 core | 256Mi | 500Mi | Nginx |
| **Total** | **1.5 cores** | **768Mi** | **1.5Gi** | Min requirements |

### 4.2 Production Environment (Kubernetes)

#### Small Deployment (< 50 projects)

| Component | CPU (request) | Memory (request) | CPU (limit) | Memory (limit) | Replicas | Storage |
|-----------|---------------|------------------|-------------|----------------|----------|---------|
| **Frontend** | 50m | 64Mi | 500m | 256Mi | 2-10 (HPA) | - |
| **Backend** | 100m | 256Mi | 1000m | 1Gi | 2-10 (HPA) | 1Gi PVC |
| **PostgreSQL** | 200m | 512Mi | 1000m | 2Gi | 2 (HA) | 20Gi SSD |
| **Redis** | 100m | 256Mi | 500m | 1Gi | 6 (Cluster) | 5Gi × 6 |
| **OTel Collector** | 50m | 64Mi | 200m | 256Mi | 2 | - |
| **ArgoCD** | 100m | 128Mi | 500m | 512Mi | 1 | - |
| **Monitoring** | 200m | 256Mi | 1000m | 2Gi | - | 20Gi |
| **Total (min)** | **~800m** | **~1.5Gi** | **~3.7Gi** | **~6Gi** | **14 pods** | **~70Gi** |

#### Medium Deployment (50-200 projects)

| Component | CPU (request) | Memory (request) | CPU (limit) | Memory (limit) | Replicas | Storage |
|-----------|---------------|------------------|-------------|----------------|----------|---------|
| **Frontend** | 100m | 128Mi | 1000m | 512Mi | 4-20 (HPA) | - |
| **Backend** | 200m | 512Mi | 2000m | 2Gi | 4-20 (HPA) | 2Gi PVC |
| **PostgreSQL** | 500m | 1Gi | 2000m | 4Gi | 3 (HA) | 50Gi SSD |
| **Redis** | 200m | 512Mi | 1000m | 2Gi | 6 (Cluster) | 10Gi × 6 |
| **OTel Collector** | 100m | 128Mi | 500m | 512Mi | 2 | - |
| **ArgoCD** | 200m | 256Mi | 1000m | 1Gi | 2 (HA) | - |
| **Monitoring** | 500m | 1Gi | 2000m | 4Gi | - | 50Gi |
| **Total (min)** | **~1.8 cores** | **~3.5Gi** | **~9.5 cores** | **~12.5Gi** | **20+ pods** | **~160Gi** |

### 4.3 Cloud Provider Estimate

#### AWS Estimate (Medium Deployment)

| Service | Component | Monthly Cost (USD) |
|---------|-----------|-------------------|
| **EKS** | Cluster | $72/month |
| **EC2** | Worker nodes (3 × t3.large) | $105/month |
| **EBS** | Storage (160Gi) | $16/month |
| **ELB** | Application LB | $20/month |
| **RDS** | PostgreSQL (db.t3.large) | $95/month |
| **ElastiCache** | Redis (cache.t3.medium) | $55/month |
| **S3** | Backup storage (100Gi) | $2.30/month |
| **CloudWatch** | Logs & metrics | $15/month |
| **Total** | | **~$380/month** |

#### GCP Estimate (Medium Deployment)

| Service | Component | Monthly Cost (USD) |
|---------|-----------|-------------------|
| **GKE** | Cluster | $0 (free tier) |
| **Compute** | Nodes (3 × e2-medium) | $70/month |
| **Disk** | Persistent Disk (160Gi) | $20/month |
| **LB** | Load Balancer | $25/month |
| **Cloud SQL** | PostgreSQL (db-n1-standard-1) | $100/month |
| **Memorystore** | Redis (1.5Gi) | $55/month |
| **Cloud Storage** | Backups (100Gi) | $2/month |
| **Monitoring** | Cloud Operations | $10/month |
| **Total** | | **~$282/month** |

### 4.4 Network Requirements

| Environment | Bandwidth | Connections | Notes |
|-------------|-----------|-------------|-------|
| Dev | 10 Mbps | 100 concurrent | Development |
| Production (Small) | 100 Mbps | 500 concurrent | < 50 projects |
| Production (Medium) | 500 Mbps | 2000 concurrent | 50-200 projects |
| Production (Large) | 1+ Gbps | 5000+ concurrent | 200+ projects |

---

## 5. Deployment Steps

### 5.1 Prerequisites Checklist

```bash
#!/bin/bash
# scripts/prerequisites-check.sh

echo "🔍 Checking prerequisites..."

# Check kubectl
if command -v kubectl &> /dev/null; then
    echo "✅ kubectl: $(kubectl version --client --short 2>/dev/null)"
else
    echo "❌ kubectl not found"
    exit 1
fi

# Check cluster access
if kubectl cluster-info &> /dev/null; then
    echo "✅ Kubernetes cluster accessible"
else
    echo "❌ Cannot access Kubernetes cluster"
    exit 1
fi

# Check Nginx Ingress
if kubectl get pods -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx &> /dev/null; then
    echo "✅ Nginx Ingress installed"
else
    echo "⚠️  Nginx Ingress not found. Install with:"
    echo "   kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.1/deploy/static/provider/cloud/deploy.yaml"
fi

# Check cert-manager
if kubectl get pods -n cert-manager &> /dev/null; then
    echo "✅ cert-manager installed"
else
    echo "⚠️  cert-manager not found. Install with:"
    echo "   kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml"
fi

# Check storage class
if kubectl get storageclass | grep -q "fast-ssd\|ssd\|gp3"; then
    echo "✅ SSD storage class available"
else
    echo "⚠️  No SSD storage class found. Create one manually."
fi

echo "✅ Prerequisites check complete!"
```

### 5.2 Build and Push Images

```bash
#!/bin/bash
# scripts/build-push.sh

REGISTRY="your-registry.com"
VERSION="v1.0.0"

echo "🔨 Building images..."

# Build backend
docker build -t ${REGISTRY}/devops-monitor-backend:${VERSION} ./backend
docker push ${REGISTRY}/devops-monitor-backend:${VERSION}

# Build frontend
docker build -t ${REGISTRY}/devops-monitor-frontend:${VERSION} --target prod ./frontend
docker push ${REGISTRY}/devops-monitor-frontend:${VERSION}

echo "✅ Images built and pushed!"
```

### 5.3 Deploy to Kubernetes

```bash
#!/bin/bash
# scripts/deploy-production.sh

set -e

NAMESPACE="devops-monitor"
REGISTRY="your-registry.com"
VERSION="v1.0.0"

echo "🚀 Deploying to production..."

# Step 1: Create namespace
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# Step 2: Apply RBAC
kubectl apply -f k8s/backend/rbac.yaml

# Step 3: Create ConfigMap
cat k8s/backend/configmap.yaml | \
  sed "s|your-registry|${REGISTRY}|g" | \
  sed "s|VERSION: latest|VERSION: ${VERSION}|g" | \
  kubectl apply -f -

# Step 4: Create Secrets (you need to create these first)
# kubectl apply -f k8s/backend/secret.yaml

# Step 5: Deploy PostgreSQL (Phase 10)
kubectl apply -f k8s/postgresql/

# Step 6: Deploy Redis
kubectl apply -f k8s/monitoring/redis-cluster.yaml

# Step 7: Deploy backend
kubectl apply -f k8s/backend/deployment.yaml

# Step 8: Deploy frontend
kubectl apply -f k8s/frontend/deployment.yaml

# Step 9: Deploy ingress
kubectl apply -f k8s/ingress.yaml

# Step 10: Wait for rollout
kubectl rollout status deployment/monitor-backend -n ${NAMESPACE} --timeout=5m
kubectl rollout status deployment/monitor-frontend -n ${NAMESPACE} --timeout=5m

echo "✅ Deployment complete!"
echo "🌐 Application available at: https://monitoring.yourdomain.com"
```

### 5.4 Create Secrets

```bash
#!/bin/bash
# scripts/create-secrets.sh

NAMESPACE="devops-monitor"

echo "🔐 Creating secrets..."

# Generate secrets
AUTH_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
REDIS_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

# Create backend secrets
kubectl create secret generic monitor-backend-secrets -n ${NAMESPACE} \
  --from-literal=AUTH_SECRET="${AUTH_SECRET}" \
  --from-literal=API_KEYS=["${API_KEY}"] \
  --from-literal=ELASTICSEARCH_USERNAME="elastic" \
  --from-literal=ELASTICSEARCH_PASSWORD="${ES_PASSWORD}" \
  --from-literal=ANTHROPIC_API_KEY="${ANTHROPIC_KEY}" \
  --dry-run=client -o yaml | kubectl apply -f -

# Create PostgreSQL secrets
kubectl create secret generic postgres-secrets -n ${NAMESPACE} \
  --from-literal=username="devops_monitor" \
  --from-literal=password="${DB_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

# Create Redis secrets
kubectl create secret generic redis-secrets -n ${NAMESPACE} \
  --from-literal=password="${REDIS_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "✅ Secrets created!"
echo "⚠️  Save these values securely:"
echo "   AUTH_SECRET=${AUTH_SECRET}"
echo "   API_KEY=${API_KEY}"
```

---

## 6. Post-Deployment Validation

### 6.1 Health Checks

```bash
#!/bin/bash
# scripts/validate-deployment.sh

NAMESPACE="devops-monitor"

echo "🔍 Validating deployment..."

# Check all pods running
kubectl get pods -n ${NAMESPACE}

# Check services
kubectl get svc -n ${NAMESPACE}

# Check ingress
kubectl get ingress -n ${NAMESPACE}

# Test health endpoint
kubectl run health-test --image=curlimages/curl:latest --rm -i --restart=Never \
  -- curl -f http://monitor-backend.${NAMESPACE}.svc.cluster.local:8000/health

echo "✅ Validation complete!"
```

### 6.2 Smoke Tests

```bash
#!/bin/bash
# scripts/smoke-tests.sh

API_URL="https://monitoring.yourdomain.com"
API_KEY="your-api-key"

echo "🧪 Running smoke tests..."

# Test 1: Health check
echo "Test 1: Health check..."
curl -f ${API_URL}/health || exit 1

# Test 2: Get token
echo "Test 2: Authentication..."
TOKEN=$(curl -s -X POST ${API_URL}/auth/token \
  -H "X-API-Key: ${API_KEY}" | jq -r '.access_token')

# Test 3: Overview endpoint
echo "Test 3: Overview endpoint..."
curl -f ${API_URL}/api/v1/overview \
  -H "Authorization: Bearer ${TOKEN}" || exit 1

# Test 4: WebSocket connection
echo "Test 4: WebSocket..."
# (requires websocat or similar tool)

echo "✅ All smoke tests passed!"
```

### 6.3 Performance Tests

```bash
#!/bin/bash
# scripts/run-performance-tests.sh

echo "⚡ Running performance tests..."

# Run K6 load tests
k6 run tests/load/overview_load_test.k6.js
k6 run tests/load/alert_load_test.k6.js

echo "✅ Performance tests complete!"
```

---

## 7. Operations & Maintenance

### 7.1 Daily Operations

| Task | Command | Frequency |
|------|---------|-----------|
| **Check pod status** | `kubectl get pods -n devops-monitor` | Hourly |
| **Check resource usage** | `kubectl top pods -n devops-monitor` | Hourly |
| **Check logs** | `kubectl logs -f deployment/monitor-backend -n devops-monitor` | As needed |
| **Review alerts** | Grafana dashboards | Daily |
| **Check backups** | `aws s3 ls s3://backups/postgresql/` | Daily |

### 7.2 Weekly Tasks

| Task | Description |
|------|-------------|
| **Review audit logs** | Check for unusual activity |
| **Review performance** | Check latency, error rates |
| **Capacity planning** | Review resource trends |
| **Security updates** | Check for CVEs in dependencies |

### 7.3 Monthly Tasks

| Task | Description |
|------|-------------|
| **Backup restoration test** | Restore random backup to test environment |
| **DR test** | If quarterly, test full DR procedure |
| **Cost review** | Review AWS/GCP billing |
| **Patch management** | Apply security patches |

### 7.4 Maintenance Windows

| Task | Frequency | Duration |
|------|-----------|----------|
| **Kubernetes upgrades** | Quarterly | 2 hours |
| **Database maintenance** | Monthly | 1 hour |
| **Redis upgrades** | As needed | 30 min |
| **Application updates** | Weekly | 15 min |

---

## 8. Troubleshooting

### 8.1 Common Issues

#### Issue: Pods not starting

```bash
# Check pod status
kubectl get pods -n devops-monitor

# Describe pod for events
kubectl describe pod <pod-name> -n devops-monitor

# Check logs
kubectl logs <pod-name> -n devops-monitor

# Common causes:
# - Image pull errors → Check registry access
# - ConfigMap missing → Check configmap.yaml
# - Secret missing → Check secrets
# - Resource limits → Check resources
```

#### Issue: High memory usage

```bash
# Check memory usage
kubectl top pods -n devops-monitor

# Check pod limits
kubectl get pod <pod-name> -n devops-monitor -o yaml | grep -A 5 resources

# Solution: Increase limits or investigate memory leak
kubectl set resources deployment/monitor-backend \
  --limits=memory=2Gi -n devops-monitor
```

#### Issue: Database connection failures

```bash
# Check PostgreSQL pods
kubectl get pods -n devops-monitor -l app=postgres

# Check PostgreSQL logs
kubectl logs postgres-0 -n devops-monitor

# Test connection
kubectl exec -it postgres-0 -n devops-monitor -- psql -U devops_monitor

# Common causes:
# - Wrong password → Update secret
# - Pod not ready → Wait for startup
# - Network policy → Check network policies
```

#### Issue: Redis connection failures

```bash
# Check Redis pods
kubectl get pods -n devops-monitor -l app=redis

# Check Redis logs
kubectl logs redis-0 -n devops-monitor

# Test connection
kubectl exec -it redis-0 -n devops-monitor -- redis-cli ping

# Common causes:
# - Wrong password → Update secret
# - Cluster not formed → Check cluster status
# - Memory limit reached → Check Redis memory
```

### 8.2 Emergency Procedures

#### Emergency: Rollback Deployment

```bash
# Rollback to previous version
kubectl rollout undo deployment/monitor-backend -n devops-monitor

# Check rollback status
kubectl rollout status deployment/monitor-backend -n devops-monitor
```

#### Emergency: Scale to Zero

```bash
# Scale all deployments to zero
kubectl scale deployment --all --replicas=0 -n devops-monitor

# Scale back up
kubectl scale deployment/monitor-backend --replicas=2 -n devops-monitor
kubectl scale deployment/monitor-frontend --replicas=2 -n devops-monitor
```

#### Emergency: Restore Backup

```bash
# Download backup from S3
aws s3 cp s3://backups/postgresql/latest.dump /tmp/latest.dump

# Restore to PostgreSQL
kubectl exec -it postgres-0 -n devops-monitor -- \
  psql -U devops_monitor -d devops_monitor < /tmp/latest.dump
```

---

## Appendix

### A. Environment Variables

See `.env.example` for complete list.

### B. K8s Manifests Reference

All manifests located in `k8s/` directory.

### C. API Documentation

Available at `https://monitoring.yourdomain.com/docs` (Swagger)

### D. Monitoring Dashboards

- Grafana: `https://grafana.yourdomain.com`
- Jaeger: `https://jaeger.yourdomain.com`

---

**Document Version**: 1.0
**Created**: 2026-08-25
**Maintained by**: DevOps AI Agentics Team
