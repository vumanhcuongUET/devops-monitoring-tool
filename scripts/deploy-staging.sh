#!/bin/bash
# Staging Deployment Script for Phase 8
# This script deploys the platform to staging environment with Phase 8 features

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="devops-monitor-staging"
# Image paths must match what CI builds/pushes (ghcr.io/<repo>/backend,
# ghcr.io/<repo>/frontend) and what k8s/staging/*.yaml reference — the old
# "$REGISTRY/devops-monitor-backend" names never matched either.
REGISTRY="${REGISTRY:-ghcr.io/vumanhcuonguet/devops-monitoring-tool}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || true)}"
if [ -z "${IMAGE_TAG}" ]; then
    echo -e "${RED}[✗]${NC} Cannot determine IMAGE_TAG (git unavailable). Set IMAGE_TAG explicitly." >&2
    exit 1
fi
BACKEND_IMAGE="${REGISTRY}/backend:${IMAGE_TAG}"
FRONTEND_IMAGE="${REGISTRY}/frontend:${IMAGE_TAG}"

echo -e "${GREEN}=== Phase 8 Staging Deployment ===${NC}"
echo ""

# Function to print status
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Check prerequisites
echo "Checking prerequisites..."
command -v kubectl >/dev/null 2>&1 || { print_error "kubectl not found. Exiting."; exit 1; }
print_status "kubectl found"
[ -n "$REGISTRY" ] || { print_error "REGISTRY env var not set. Exiting (was hardcoded placeholder before)."; exit 1; }

# 1. Create namespace
echo ""
echo "Creating namespace..."
kubectl apply -f k8s/staging/namespace.yaml
print_status "Namespace created"

# 2. Create secrets
echo ""
echo "Creating secrets..."
if [ -f "$HOME/.staging-secrets" ]; then
    # shellcheck disable=SC1090
    source "$HOME/.staging-secrets"
    kubectl create secret generic backend-secrets-staging \
        --from-literal=database-url="$DATABASE_URL" \
        --from-literal=elasticsearch-url="$ELASTICSEARCH_URL" \
        --from-literal=elasticsearch-username="$ELASTICSEARCH_USERNAME" \
        --from-literal=elasticsearch-password="$ELASTICSEARCH_PASSWORD" \
        --from-literal=prometheus-url="$PROMETHEUS_URL" \
        --from-literal=prometheus-auth="$PROMETHEUS_AUTH" \
        --namespace=$NAMESPACE \
        --dry-run=client -o yaml | kubectl apply -f -
    print_status "Secrets created"
else
    print_error "Secrets file $HOME/.staging-secrets not found. Refusing to deploy."
    print_error "Applying the committed secret template would create empty/placeholder credentials."
    print_error "Create the file with real values (see k8s/templates/staging-secrets-template.yaml), then re-run."
    exit 1
fi

# 3. Create RBAC
echo ""
echo "Creating RBAC..."
kubectl apply -f k8s/staging/rbac.yaml
print_status "RBAC created"

# 4. Deploy backend
echo ""
echo "Deploying backend..."
# Build and push image (if needed)
if [ "$SKIP_BUILD" != "true" ]; then
    echo "Building backend image..."
    docker build -t $BACKEND_IMAGE backend/
    docker push $BACKEND_IMAGE
    print_status "Backend image built and pushed"
fi

kubectl apply -f k8s/staging/deployment.yaml
# The checked-in manifest carries a placeholder tag; point the rollout at the
# image THIS run built and pushed.
kubectl set image deployment/backend-staging "backend=${BACKEND_IMAGE}" -n $NAMESPACE
print_status "Backend deployed"

# 5. Deploy frontend
echo ""
echo "Deploying frontend..."
if [ "$SKIP_BUILD" != "true" ]; then
    echo "Building frontend image..."
    docker build -t $FRONTEND_IMAGE frontend/
    docker push $FRONTEND_IMAGE
    print_status "Frontend image built and pushed"
fi

kubectl apply -f k8s/staging/frontend-deployment.yaml
kubectl set image deployment/frontend-staging "frontend=${FRONTEND_IMAGE}" -n $NAMESPACE
print_status "Frontend deployed"

# 6. Wait for deployments to be ready
echo ""
echo "Waiting for deployments to be ready..."
kubectl wait --for=condition=available \
    deployment/backend-staging \
    -n $NAMESPACE \
    --timeout=300s || print_warning "Backend deployment timeout"

kubectl wait --for=condition=available \
    deployment/frontend-staging \
    -n $NAMESPACE \
    --timeout=300s || print_warning "Frontend deployment timeout"

print_status "Deployments ready"

# 7. Run smoke tests
echo ""
echo "Running smoke tests..."
if kubectl get svc backend-staging -n $NAMESPACE >/dev/null 2>&1; then
    # Port-forward to run tests
    echo "Setting up port-forward..."
    kubectl port-forward -n $NAMESPACE svc/backend-staging 8000:8000 &
    PF_PID=$!

    sleep 5

    echo "Running smoke tests..."
    if python backend/tests/smoke/test_sprint3_staging_smoke.py http://localhost:8000; then
        print_status "Smoke tests passed"
    else
        print_error "Smoke tests failed. Rolling back backend deployment."
        kill "$PF_PID" 2>/dev/null || true
        kubectl rollout undo deployment/backend-staging -n $NAMESPACE || true
        kubectl rollout status deployment/backend-staging -n $NAMESPACE --timeout=180s || true
        exit 1
    fi

    kill "$PF_PID" 2>/dev/null || true
else
    print_warning "Backend service not found. Skipping smoke tests."
fi

# 8. Show status
echo ""
echo "Deployment Status:"
echo "=================="
kubectl get deployments -n $NAMESPACE
echo ""
kubectl get pods -n $NAMESPACE
echo ""
kubectl get services -n $NAMESPACE

# 9. Show logs
echo ""
echo "Recent Backend Logs:"
kubectl logs -n $NAMESPACE -l app=backend,environment=staging --tail=20

echo ""
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo ""
echo "To access the staging environment:"
echo "  kubectl port-forward -n $NAMESPACE svc/frontend-staging 3000:3000"
echo ""
echo "To access backend API:"
echo "  kubectl port-forward -n $NAMESPACE svc/backend-staging 8000:8000"
echo ""
echo "To view logs:"
echo "  kubectl logs -n $NAMESPACE -l app=backend,environment=staging -f"
echo ""
