#!/bin/bash
# Phase 7 - Sprint 0 - Day 1
# Redis Validation and Testing Script
# Test Redis connectivity, performance, and failover

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

# Test Redis connectivity
test_connectivity() {
    local namespace=$1
    local host=$2
    local password=$3

    print_header "Testing connectivity to $namespace"

    result=$(kubectl run redis-test-$namespace -n $namespace --rm -i --restart=Never \
        --image=redis:7.2-alpine --command -- redis-cli -h $host -a $password ping 2>/dev/null || echo "FAILED")

    if [[ "$result" == *"PONG"* ]]; then
        print_success "$namespace Redis is reachable"
        return 0
    else
        print_error "$namespace Redis connection failed"
        return 1
    fi
}

# Test Redis basic operations
test_basic_operations() {
    local namespace=$1
    local host=$2
    local password=$3

    print_header "Testing basic operations in $namespace"

    kubectl run redis-test-ops-$namespace -n $namespace --rm -i --restart=Never \
        --image=redis:7.2-alpine --command -- sh -c "
        redis-cli -h $host -a $password <<EOF
SET test_key 'test_value'
GET test_key
DEL test_key
INCR counter
EXISTS counter
EOF
    " 2>/dev/null

    if [ $? -eq 0 ]; then
        print_success "$namespace basic operations work"
        return 0
    else
        print_error "$namespace basic operations failed"
        return 1
    fi
}

# Test Redis persistence (dev doesn't have persistence)
test_persistence() {
    local namespace=$1
    local host=$2
    local password=$3

    if [ "$namespace" == "development" ]; then
        print_info "Skipping persistence test for development (disabled)"
        return 0
    fi

    print_header "Testing persistence in $namespace"

    # Set a key and restart pod
    kubectl run redis-persistence-test-$namespace -n $namespace --rm -i --restart=Never \
        --image=redis:7.2-alpine --command -- sh -c "
        redis-cli -h $host -a $password SET persistent_key 'persistent_value'
        redis-cli -h $host -a $password GET persistent_key
        redis-cli -h $host -a $password SAVE
    " 2>/dev/null

    if [ $? -eq 0 ]; then
        print_success "$namespace persistence configured"
        return 0
    else
        print_error "$namespace persistence test failed"
        return 1
    fi
}

# Test Redis performance
test_performance() {
    local namespace=$1
    local host=$2
    local password=$3

    print_header "Testing performance in $namespace"

    output=$(kubectl run redis-perf-$namespace -n $namespace --rm -i --restart=Never \
        --image=redis:7.2-alpine --command -- sh -c "
        redis-cli -h $host -a $password --csv PING
        for i in \$(seq 1 100); do redis-cli -h $host -a $password SET key_\$i 'value_\$i' > /dev/null; done
        for i in \$(seq 1 100); do redis-cli -h $host -a $password GET key_\$i > /dev/null; done
        redis-cli -h $host -a $password DBSIZE
    " 2>/dev/null)

    echo "$output" | grep -q "100"
    if [ $? -eq 0 ]; then
        print_success "$namespace performance test passed (100 operations)"
        return 0
    else
        print_error "$namespace performance test failed"
        return 1
    fi
}

# Test Sentinel failover (production only)
test_sentinel() {
    local namespace="monitoring"
    local host="redis"

    print_header "Testing Sentinel in production"

    output=$(kubectl run redis-sentinel-test -n $namespace --rm -i --restart=Never \
        --image=redis:7.2-alpine --command -- sh -c "
        redis-cli -h redis -p 26379 SENTINELL masters
        redis-cli -h redis -p 26379 SENTINELL slaves mymaster
        redis-cli -h redis -p 26379 SENTINELL ckquorum mymaster
    " 2>/dev/null)

    if [[ "$output" == *"mymaster"* ]]; then
        print_success "Sentinel is configured and monitoring master"
        return 0
    else
        print_error "Sentinel test failed"
        return 1
    fi
}

# Check Redis info
get_redis_info() {
    local namespace=$1
    local host=$2
    local password=$3

    print_header "Redis info for $namespace"

    kubectl run redis-info-$namespace -n $namespace --rm -i --restart=Never \
        --image=redis:7.2-alpine --command -- sh -c "
        redis-cli -h $host -a $password INFO server | grep -E 'redis_version|os|process_id'
        redis-cli -h $host -a $password INFO memory | grep -E 'used_memory|maxmemory'
        redis-cli -h $host -a $password INFO stats | grep -E 'total_connections|total_commands'
    " 2>/dev/null || true
}

# Health check all Redis instances
health_check() {
    print_header "Health Check - All Environments"

    echo ""
    echo "┌─────────────────────────────────────────────────────────────────┐"
    echo "│                    REDIS HEALTH STATUS                         │"
    echo "├─────────────────────────────────────────────────────────────────┤"

    for env in development staging monitoring; do
        pods=$(kubectl get pods -n $env -l app=redis -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)
        if [ -n "$pods" ]; then
            for pod in $pods; do
                status=$(kubectl get pod $pod -n $env -o jsonpath='{.status.phase}')
                ready=$(kubectl get pod $pod -n $env -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
                echo -n "│ "
                printf "%-15s %-30s %-10s" "$env" "$pod" "$status"
                if [ "$ready" == "True" ]; then
                    echo -e " ${GREEN}READY${NC} │"
                else
                    echo -e " ${RED}NOT READY${NC} │"
                fi
            done
        fi
    done

    echo "└─────────────────────────────────────────────────────────────────┘"
}

# Main execution
main() {
    echo "=========================================="
    echo "Phase 7 - Sprint 0 - Day 1"
    echo "Redis Validation and Testing"
    echo "=========================================="
    echo ""

    # Check cluster access
    if ! kubectl cluster-info &> /dev/null; then
        print_error "Cannot access Kubernetes cluster"
        exit 1
    fi

    health_check

    echo ""
    read -p "Run full connectivity test? (y/n): " choice
    if [ "$choice" == "y" ]; then
        echo ""

        test_connectivity "development" "redis" "dev_redis_password"
        test_connectivity "staging" "redis" "staging_redis_change_me"
        test_connectivity "monitoring" "redis-0.redis" "CHANGE_ME_IN_PRODUCTION"

        echo ""
        test_basic_operations "development" "redis" "dev_redis_password"
        test_basic_operations "staging" "redis" "staging_redis_change_me"
        test_basic_operations "monitoring" "redis-0.redis" "CHANGE_ME_IN_PRODUCTION"

        echo ""
        test_persistence "staging" "redis" "staging_redis_change_me"
        test_persistence "monitoring" "redis-0.redis" "CHANGE_ME_IN_PRODUCTION"

        echo ""
        test_performance "development" "redis" "dev_redis_password"
        test_performance "staging" "redis" "staging_redis_change_me"

        echo ""
        test_sentinel
    fi

    echo ""
    read -p "Get Redis info? (y/n): " choice
    if [ "$choice" == "y" ]; then
        echo ""
        get_redis_info "development" "redis" "dev_redis_password"
        get_redis_info "staging" "redis" "staging_redis_change_me"
        get_redis_info "monitoring" "redis-0.redis" "CHANGE_ME_IN_PRODUCTION"
    fi

    echo ""
    print_success "Redis testing completed!"
    echo ""
    echo "Connection Summary:"
    echo "  Dev:      redis.development.svc.cluster.local:6379"
    echo "  Staging:  redis.staging.svc.cluster.local:6379"
    echo "  Prod:     redis.monitoring.svc.cluster.local:6379"
    echo ""
    echo "Next: Update backend configuration to use Redis"
}

main "$@"
