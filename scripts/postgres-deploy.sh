#!/bin/bash
# Phase 7 - Sprint 0 - Day 2
# PostgreSQL Analytics Deployment Script

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_info() { echo -e "${YELLOW}ℹ $1${NC}"; }

check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl not found"
        exit 1
    fi
    print_success "kubectl found"
}

check_cluster() {
    if ! kubectl cluster-info &> /dev/null; then
        print_error "Cannot access cluster"
        exit 1
    fi
    print_success "Cluster accessible"
}

deploy_postgres() {
    print_info "Deploying PostgreSQL for Analytics..."

    # Create namespace if not exists
    kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

    # Deploy PostgreSQL
    kubectl apply -f k8s/monitoring/postgres-analytics.yaml

    # Wait for pod to be ready
    print_info "Waiting for PostgreSQL pod to be ready..."
    kubectl rollout status statefulset/postgres -n monitoring --timeout=5m

    print_success "PostgreSQL deployed"
}

validate_deployment() {
    print_info "Validating PostgreSQL deployment..."

    echo ""
    echo "=== PostgreSQL Status ==="
    kubectl get pods -n monitoring -l app=postgres
    kubectl get pvc -n monitoring
    kubectl get svc -n monitoring -l app=postgres

    # Check if pod is running
    POD_STATUS=$(kubectl get pods -n monitoring -l app=postgres -o jsonpath='{.items[*].status.phase}')

    if [[ "$POD_STATUS" == *"Running"* ]]; then
        print_success "PostgreSQL pod is running"

        # Get connection details
        echo ""
        print_info "PostgreSQL Connection Details:"
        echo "Host: postgres.monitoring.svc.cluster.local:5432"
        echo "Database: devops_monitoring"
        echo "User: postgres"
        echo "Analytics User: analytics_user"
        echo ""
        print_warning "Please update passwords in postgres-secret!"

        return 0
    else
        print_error "PostgreSQL pod not ready"
        return 1
    fi
}

test_connectivity() {
    print_info "Testing PostgreSQL connectivity..."

    # Test with psql in a temporary pod
    kubectl run postgres-test -n monitoring --rm -i --restart=Never \
        --image=postgres:15-alpine --command -- psql \
        -h postgres -U postgres -d devops_monitoring -c "SELECT version();" || true

    print_success "Connectivity test completed"
}

get_storage_info() {
    print_info "Storage Information:"

    kubectl get pvc -n monitoring postgres-storage -o jsonpath='{.spec.resources.requests.storage}'
    echo " allocated for PostgreSQL data"
}

# Main execution
main() {
    echo "=========================================="
    echo "Phase 7 - Sprint 0 - Day 2"
    echo "PostgreSQL Analytics Deployment"
    echo "=========================================="
    echo ""

    check_kubectl
    check_cluster

    read -p "Deploy PostgreSQL? (y/n): " choice
    if [ "$choice" != "y" ]; then
        print_info "Skipping deployment"
        exit 0
    fi

    deploy_postgres
    validate_deployment

    echo ""
    read -p "Test connectivity? (y/n):" choice
    if [ "$choice" == "y" ]; then
        test_connectivity
    fi

    get_storage_info

    echo ""
    print_success "PostgreSQL deployment completed!"
    echo ""
    echo "Next steps:"
    echo "1. Update PostgreSQL passwords"
    echo "2. Run: ./scripts/postgres-test.sh"
    echo "3. Configure backend to use PostgreSQL"
    echo "4. Proceed to Day 3: Monitoring & Validation"
}

main "$@"
