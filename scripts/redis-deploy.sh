#!/bin/bash
# Phase 7 - Sprint 0 - Day 1
# Redis Infrastructure Deployment Script
# Deploy Redis to all environments: dev, staging, production

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# Check if kubectl is available
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl not found. Please install kubectl first."
        exit 1
    fi
    print_success "kubectl found"
}

# Check if cluster is accessible
check_cluster() {
    if ! kubectl cluster-info &> /dev/null; then
        print_error "Cannot access Kubernetes cluster"
        exit 1
    fi
    print_success "Kubernetes cluster accessible"
}

# Create namespaces
create_namespaces() {
    print_info "Creating namespaces..."

    kubectl create namespace development --dry-run=client -o yaml | kubectl apply -f -
    kubectl create namespace staging --dry-run=client -o yaml | kubectl apply -f -
    kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

    print_success "Namespaces created"
}

# Deploy to development
deploy_dev() {
    print_info "Deploying Redis to Development environment..."

    kubectl apply -f k8s/monitoring/redis-dev.yaml

    # Wait for deployment
    kubectl rollout status deployment/redis -n development --timeout=2m

    print_success "Development Redis deployed"
}

# Deploy to staging
deploy_staging() {
    print_info "Deploying Redis to Staging environment..."

    kubectl apply -f k8s/monitoring/redis-staging.yaml

    # Wait for statefulset
    kubectl rollout status statefulset/redis -n staging --timeout=3m

    print_success "Staging Redis deployed"
}

# Deploy to production
deploy_prod() {
    print_info "Deploying Redis to Production environment..."

    kubectl apply -f k8s/monitoring/redis-cluster.yaml
    kubectl apply -f k8s/monitoring/redis-security.yaml

    # Wait for statefulset
    kubectl rollout status statefulset/redis -n monitoring --timeout=5m

    print_success "Production Redis deployed"
}

# Validate deployment
validate_deployment() {
    print_info "Validating Redis deployments..."

    echo ""
    echo "=== Development ==="
    kubectl get pods -n development -l app=redis
    kubectl get svc -n development -l app=redis

    echo ""
    echo "=== Staging ==="
    kubectl get pods -n staging -l app=redis
    kubectl get svc -n staging -l app=redis

    echo ""
    echo "=== Production ==="
    kubectl get pods -n monitoring -l app=redis
    kubectl get svc -n monitoring -l app=redis

    # Check if all pods are running
    DEV_RUNNING=$(kubectl get pods -n development -l app=redis -o jsonpath='{.items[*].status.phase}')
    STAGING_RUNNING=$(kubectl get pods -n staging -l app=redis -o jsonpath='{.items[*].status.phase}')
    PROD_RUNNING=$(kubectl get pods -n monitoring -l app=redis -o jsonpath='{.items[*].status.phase}')

    if [[ "$DEV_RUNNING" == *"Running"* ]] && [[ "$STAGING_RUNNING" == *"Running"* ]] && [[ "$PROD_RUNNING" == *"Running"* ]]; then
        print_success "All Redis pods are running"
        return 0
    else
        print_error "Some Redis pods are not running"
        return 1
    fi
}

# Test connectivity
test_connectivity() {
    print_info "Testing Redis connectivity..."

    # Test Dev
    echo "Testing Development Redis..."
    kubectl run redis-test-dev -n development --rm -it --restart=Never \
        --image=redis:7.2-alpine --command -- redis-cli -h redis -a dev_redis_password ping || true

    # Test Staging
    echo "Testing Staging Redis..."
    kubectl run redis-test-staging -n staging --rm -it --restart=Never \
        --image=redis:7.2-alpine --command -- redis-cli -h redis -a staging_redis_change_me ping || true

    # Test Prod
    echo "Testing Production Redis..."
    kubectl run redis-test-prod -n monitoring --rm -it --restart=Never \
        --image=redis:7.2-alpine --command -- redis-cli -h redis-0.redis -a CHANGE_ME_IN_PRODUCTION ping || true
}

# Get connection strings
get_connection_strings() {
    print_info "Redis Connection Strings:"

    echo ""
    echo "=== Development ==="
    echo "Host: redis.development.svc.cluster.local:6379"
    echo "Password: dev_redis_password"
    echo "NodePort (for local): <NODE_IP>:30379"

    echo ""
    echo "=== Staging ==="
    echo "Host: redis.staging.svc.cluster.local:6379"
    echo "Password: staging_redis_change_me"

    echo ""
    echo "=== Production ==="
    echo "Host: redis.monitoring.svc.cluster.local:6379"
    echo "Password: CHANGE_ME_IN_PRODUCTION (Please change this!)"
    echo "Sentinel: redis.monitoring.svc.cluster.local:26379"
}

# Main execution
main() {
    echo "=========================================="
    echo "Phase 7 - Sprint 0 - Day 1"
    echo "Redis Infrastructure Deployment"
    echo "=========================================="
    echo ""

    check_kubectl
    check_cluster
    create_namespaces

    # Ask which environment to deploy
    echo ""
    read -p "Deploy to all environments? (y/n/all/dev/staging/prod): " choice

    case $choice in
        y|all)
            deploy_dev
            deploy_staging
            deploy_prod
            ;;
        dev)
            deploy_dev
            ;;
        staging)
            deploy_staging
            ;;
        prod)
            deploy_prod
            ;;
        n)
            print_info "Skipping deployment"
            exit 0
            ;;
        *)
            print_error "Invalid choice"
            exit 1
            ;;
    esac

    validate_deployment
    get_connection_strings

    echo ""
    print_success "Redis infrastructure deployment completed!"
    echo ""
    echo "Next steps:"
    echo "1. Update Redis passwords in production"
    echo "2. Run connectivity tests: ./scripts/redis-test.sh"
    echo "3. Configure backend to use Redis"
    echo "4. Proceed to Day 2: GitOps & PostgreSQL setup"
}

# Run main function
main "$@"
