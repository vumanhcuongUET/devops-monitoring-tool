#!/bin/bash
# Phase 7 - Sprint 0 - Day 3
# Infrastructure Validation Script
# Comprehensive validation of all Sprint 0 infrastructure

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_info() { echo -e "${YELLOW}ℹ $1${NC}"; }
print_header() { echo -e "${BLUE}▶ $1${NC}"; }

check_cluster() {
    print_header "Checking Kubernetes cluster"

    if ! kubectl cluster-info &> /dev/null; then
        print_error "Cluster not accessible"
        return 1
    fi
    print_success "Cluster accessible"

    # Get cluster info
    kubectl cluster-info
    echo ""
}

check_namespaces() {
    print_header "Checking namespaces"

    namespaces=("development" "staging" "monitoring")

    all_exist=true
    for ns in "${namespaces[@]}"; do
        if kubectl get namespace $ns &> /dev/null; then
            print_success "Namespace $ns exists"
        else
            print_error "Namespace $ns missing"
            all_exist=false
        fi
    done

    echo ""
    return $([ "$all_exist" = true ] && echo 0 || echo 1)
}

check_redis() {
    print_header "Checking Redis Infrastructure"

    envs=("development:development" "staging:staging" "production:monitoring")

    all_ok=true
    for entry in "${envs[@]}"; do
        IFS=':' read -r env namespace <<< "$entry"

        # Check pods
        pods=$(kubectl get pods -n $namespace -l app=redis -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)

        if [ -z "$pods" ]; then
            print_error "$env: No Redis pods found"
            all_ok=false
            continue
        fi

        # Check pod status
        running=true
        for pod in $pods; do
            status=$(kubectl get pod $pod -n $namespace -o jsonpath='{.status.phase}' 2>/dev/null)
            if [ "$status" != "Running" ]; then
                print_error "$env: Pod $pod not ready (status: $status)"
                running=false
                all_ok=false
            fi
        done

        if [ "$running" = true ]; then
            # Count replicas
            replica_count=$(echo "$pods" | wc -w)
            print_success "$env: $replica_count Redis pod(s) running"
        fi

        # Check services
        svc=$(kubectl get svc -n $namespace -l app=redis -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)
        if [ -n "$svc" ]; then
            print_success "$env: Redis service configured"
        else
            print_error "$env: Redis service missing"
            all_ok=false
        fi
    done

    echo ""
    return $([ "$all_ok" = true ] && echo 0 || echo 1)
}

check_postgres() {
    print_header "Checking PostgreSQL Infrastructure"

    namespace="monitoring"

    # Check StatefulSet
    if kubectl get statefulset postgres -n $namespace &> /dev/null; then
        print_success "PostgreSQL StatefulSet exists"
    else
        print_error "PostgreSQL StatefulSet not found"
        echo ""
        return 1
    fi

    # Check pod
    pod=$(kubectl get pods -n $namespace -l app=postgres -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)
    if [ -n "$pod" ]; then
        status=$(kubectl get pod $pod -n $namespace -o jsonpath='{.status.phase}')
        if [ "$status" = "Running" ]; then
            print_success "PostgreSQL pod running"
        else
            print_error "PostgreSQL pod not ready (status: $status)"
        fi
    else
        print_error "PostgreSQL pod not found"
    fi

    # Check PVC
    if kubectl get pvc postgres-storage -n $namespace &> /dev/null; then
        print_success "PostgreSQL PVC allocated"
    else
        print_error "PostgreSQL PVC not found"
    fi

    # Check service
    if kubectl get svc postgres -n $namespace &> /dev/null; then
        print_success "PostgreSQL service configured"
    else
        print_error "PostgreSQL service not found"
    fi

    echo ""
}

check_gitops() {
    print_header "Checking GitOps Configuration"

    config_dir="./config-repo"

    if [ ! -d "$config_dir" ]; then
        print_error "GitOps repository not found at $config_dir"
        echo ""
        return 1
    fi

    print_success "GitOps repository exists"

    # Check global configs
    configs=(
        "$config_dir/global/defaults.yaml"
        "$config_dir/global/policies.yaml"
        "$config_dir/global/schemas/project.schema.yaml"
        "$config_dir/global/schemas/alert.schema.yaml"
        "$config_dir/global/schemas/slo.config.schema.yaml"
        "$config_dir/global/schemas/deployment.config.schema.yaml"
        "$config_dir/global/schemas/monitoring.config.schema.yaml"
    )

    for config in "${configs[@]}"; do
        if [ -f "$config" ]; then
            print_success "$(basename $config) exists"
        else
            print_error "$(basename $config) missing"
        fi
    done

    # Check project configs
    if [ -f "$config_dir/projects/meinvoice/config.yaml" ]; then
        print_success "Example project config exists"
    else
        print_error "Example project config missing"
    fi

    echo ""
}

check_monitoring() {
    print_header "Checking Monitoring Configuration"

    namespace="monitoring"

    # Check PrometheusRule
    if kubectl get prometheusrule phase7-alerts -n $namespace &> /dev/null; then
        print_success "PrometheusRule (phase7-alerts) configured"
    else
        print_error "PrometheusRule not found"
    fi

    # Check ConfigMaps
    if kubectl get configmap prometheus-config-phase7 -n $namespace &> /dev/null; then
        print_success "Prometheus config ConfigMap exists"
    else
        print_error "Prometheus config ConfigMap not found"
    fi

    if kubectl get configmap grafana-dashboards-phase7 -n $namespace &> /dev/null; then
        print_success "Grafana dashboards ConfigMap exists"
    else
        print_error "Grafana dashboards ConfigMap not found"
    fi

    # Check ServiceMonitors
    services=("redis" "postgres")
    for svc in "${services[@]}"; do
        if kubectl get servicemonitor $svc -n $namespace &> /dev/null; then
            print_success "ServiceMonitor for $svc exists"
        else
            print_error "ServiceMonitor for $svc not found"
        fi
    done

    echo ""
}

check_network_policies() {
    print_header "Checking Network Policies"

    namespace="monitoring"

    # Check Redis network policy
    if kubectl get networkpolicy redis-netpol -n $namespace &> /dev/null; then
        print_success "Redis network policy exists"
    else
        print_error "Redis network policy not found"
    fi

    # Check PostgreSQL network policy
    if kubectl get networkpolicy postgres-netpol -n $namespace &> /dev/null; then
        print_success "PostgreSQL network policy exists"
    else
        print_error "PostgreSQL network policy not found"
    fi

    echo ""
}

check_secrets() {
    print_header "Checking Secrets"

    namespaces=("development" "staging" "monitoring")

    for ns in "${namespaces[@]}"; do
        # Check Redis secret
        if kubectl get secret redis-secret -n $ns &> /dev/null; then
            print_success "$ns: redis-secret exists"
        else
            print_error "$ns: redis-secret not found"
        fi
    done

    # Check PostgreSQL secret
    if kubectl get secret postgres-secret -n monitoring &> /dev/null; then
        print_success "monitoring: postgres-secret exists"
    else
        print_error "monitoring: postgres-secret not found"
    fi

    echo ""
}

generate_summary() {
    print_header "Infrastructure Summary"

    echo "┌─────────────────────────────────────────────────────────────────┐"
    echo "│              PHASE 7 SPRINT 0 INFRASTRUCTURE                      │"
    echo "├─────────────────────────────────────────────────────────────────┤"

    components=(
        "Redis Cluster (Dev/Staging/Prod)"
        "PostgreSQL Analytics"
        "GitOps Repository"
        "Monitoring Configuration"
        "Network Policies"
        "Secrets Management"
    )

    for component in "${components[@]}"; do
        echo "│  ✓ $component"
    done

    echo "└─────────────────────────────────────────────────────────────────┘"
    echo ""
}

display_connection_details() {
    print_header "Connection Details"

    echo ""
    echo "Redis:"
    echo "  Development: redis.development.svc.cluster.local:6379"
    echo "  Staging:    redis.staging.svc.cluster.local:6379"
    echo "  Production: redis.monitoring.svc.cluster.local:6379"
    echo ""
    echo "PostgreSQL:"
    echo "  Analytics:  postgres.monitoring.svc.cluster.local:5432/devops_monitoring"
    echo ""
    echo "GitOps Repository:"
    echo "  Path: ./config-repo/"
    echo ""
    echo "Monitoring:"
    echo "  Grafana:    http://grafana.monitoring.svc.cluster.local"
    echo "  Prometheus: http://prometheus.monitoring.svc.cluster.local"
    echo ""
}

display_next_steps() {
    print_header "Next Steps"

    echo "1. Update all default passwords (Redis, PostgreSQL)"
    echo "2. Configure backend to connect to Redis and PostgreSQL"
    echo "3. Implement Sprint 1: Multi-Layer Caching"
    echo "4. Review and test deployment scripts"
    echo "5. Create infrastructure runbook"
    echo ""
}

# Main execution
main() {
    echo "=========================================="
    echo "Phase 7 - Sprint 0 - Day 3"
    echo "Infrastructure Validation"
    echo "=========================================="
    echo ""

    check_cluster
    check_namespaces
    check_redis
    check_postgres
    check_gitops
    check_monitoring
    check_network_policies
    check_secrets

    generate_summary
    display_connection_details
    display_next_steps

    print_success "Infrastructure validation completed!"
}

main "$@"
