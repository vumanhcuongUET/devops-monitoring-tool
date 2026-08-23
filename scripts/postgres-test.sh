#!/bin/bash
# Phase 7 - Sprint 0 - Day 2
# PostgreSQL Validation and Testing Script

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

test_connection() {
    print_header "Testing PostgreSQL connection"

    result=$(kubectl run pg-test-conn -n monitoring --rm -i --restart=Never \
        --image=postgres:15-alpine --command -- sh -c "
        pg_isready -h postgres -U postgres -d devops_monitoring
    " 2>/dev/null || echo "FAILED")

    if [[ "$result" == *"accepting connections"* ]]; then
        print_success "PostgreSQL is accepting connections"
        return 0
    else
        print_error "PostgreSQL connection failed"
        return 1
    fi
}

test_database_exists() {
    print_header "Checking database and schema"

    kubectl run pg-test-db -n monitoring --rm -i --restart=Never \
        --image=postgres:15-alpine --command -- psql \
        -h postgres -U postgres -d devops_monitoring -c "
        SELECT schema_name FROM information_schema.schemata
        WHERE schema_name = 'analytics';
    " 2>/dev/null | grep -q "analytics"

    if [ $? -eq 0 ]; then
        print_success "Analytics schema exists"
    else
        print_error "Analytics schema not found"
    fi
}

test_tables_exist() {
    print_header "Checking analytics tables"

    tables=("metrics" "cost_tracking" "performance_baselines" "cache_stats" "realtime_analytics" "config_audit_log")

    all_exist=true
    for table in "${tables[@]}"; do
        result=$(kubectl run pg-test-table -n monitoring --rm -i --restart=Never \
            --image=postgres:15-alpine --command -- psql \
            -h postgres -U postgres -d devops_monitoring -t -c "
            SELECT COUNT(*) FROM analytics.$table;
        " 2>/dev/null || echo "0")

        if [[ "$result" =~ [0-9]+ ]]; then
            print_success "Table $table exists"
        else
            print_error "Table $table missing"
            all_exist=false
        fi
    done

    if [ "$all_exist" = true ]; then
        return 0
    else
        return 1
    fi
}

test_write_operations() {
    print_header "Testing write operations"

    kubectl run pg-test-write -n monitoring --rm -i --restart=Never \
        --image=postgres:15-alpine --command -- psql \
        -h postgres -U postgres -d devops_monitoring -c "
        INSERT INTO analytics.metrics
        (project, metric_name, metric_type, timestamp, value, labels)
        VALUES
        ('test-project', 'test_metric', 'counter', NOW(), 100, '{\"test\": \"value\"}');
    " 2>/dev/null

    if [ $? -eq 0 ]; then
        print_success "Write operation successful"
        return 0
    else
        print_error "Write operation failed"
        return 1
    fi
}

test_read_operations() {
    print_header "Testing read operations"

    result=$(kubectl run pg-test-read -n monitoring --rm -i --restart=Never \
        --image=postgres:15-alpine --command -- psql \
        -h postgres -U postgres -d devops_monitoring -t -c "
        SELECT COUNT(*) FROM analytics.metrics WHERE project = 'test-project';
    " 2>/dev/null | tr -d ' ')

    if [ "$result" -gt 0 ]; then
        print_success "Read operation successful (found $result records)"
        return 0
    else
        print_error "Read operation failed"
        return 1
    fi
}

test_views() {
    print_header "Testing views"

    kubectl run pg-test-views -n monitoring --rm -i --restart=Never \
        --image=postgres:15-alpine --command -- psql \
        -h postgres -U postgres -d devops_monitoring -c "
        SELECT * FROM analytics.daily_cost_summary LIMIT 1;
    " 2>/dev/null

    if [ $? -eq 0 ]; then
        print_success "Views are accessible"
        return 0
    else
        print_error "Views not accessible"
        return 1
    fi
}

test_analytics_user() {
    print_header "Testing analytics_user permissions"

    kubectl run pg-test-analytics -n monitoring --rm -i --restart=Never \
        --image=postgres:15-alpine --env=PGPASSWORD=analytics_user --command -- psql \
        -h postgres -U analytics_user -d devops_monitoring -c "
        SELECT COUNT(*) FROM analytics.metrics;
    " 2>/dev/null

    if [ $? -eq 0 ]; then
        print_success "Analytics user can read analytics data"
        return 0
    else
        print_error "Analytics user permissions issue"
        return 1
    fi
}

get_performance_stats() {
    print_header "PostgreSQL Performance Stats"

    kubectl run pg-perf -n monitoring --rm -i --restart=Never \
        --image=postgres:15-alpine --command -- psql \
        -h postgres -U postgres -d devops_monitoring -c "
        SELECT
            schemaname,
            tablename,
            n_tup_ins as inserts,
            n_tup_upd as updates,
            n_tup_del as deletes,
            n_live_tup as live_rows,
            n_dead_tup as dead_rows
        FROM pg_stat_user_tables
        WHERE schemaname = 'analytics'
        ORDER BY tablename;
    " 2>/dev/null || true
}

get_storage_info() {
    print_header "Storage Information"

    kubectl run pg-storage -n monitoring --rm -i --restart=Never \
        --image=postgres:15-alpine --command -- psql \
        -h postgres -U postgres -d devops_monitoring -c "
        SELECT
            pg_database.datname,
            pg_size_pretty(pg_database_size(pg_database.datname)) as size
        FROM pg_database
        WHERE datname = 'devops_monitoring';
    " 2>/dev/null || true

    kubectl get pvc -n monitoring postgres-storage -o jsonpath='{.status.capacity.storage}'
}

health_check() {
    print_header "PostgreSQL Health Check"

    echo ""
    echo "┌─────────────────────────────────────────────────────────────────┐"
    echo "│                  POSTGRESQL HEALTH STATUS                        │"
    echo "├─────────────────────────────────────────────────────────────────┤"

    pod=$(kubectl get pods -n monitoring -l app=postgres -o jsonpath='{.items[0].metadata.name}')
    if [ -n "$pod" ]; then
        status=$(kubectl get pod $pod -n monitoring -o jsonpath='{.status.phase}')
        ready=$(kubectl get pod $pod -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
        restarts=$(kubectl get pod $pod -n monitoring -o jsonpath='{.status.containerStatuses[0].restartCount}')

        echo -n "│ "
        printf "%-15s %-30s %-10s" "PostgreSQL" "$pod" "$status"
        if [ "$ready" == "True" ]; then
            echo -e " ${GREEN}READY${NC} │"
        else
            echo -e " ${RED}NOT READY${NC} │"
        fi
        echo -n "│ "
        printf "%-15s %-30s %-10s" "" "Restarts: $restarts" ""
        echo "         │"
    fi

    pvc=$(kubectl get pvc -n monitoring postgres-storage -o jsonpath='{.status.phase}')
    echo -n "│ "
    printf "%-15s %-30s %-10s" "Storage" "postgres-storage" "$pvc"
    echo "         │"

    echo "└─────────────────────────────────────────────────────────────────┘"
}

# Main execution
main() {
    echo "=========================================="
    echo "Phase 7 - Sprint 0 - Day 2"
    echo "PostgreSQL Validation and Testing"
    echo "=========================================="
    echo ""

    if ! kubectl cluster-info &> /dev/null; then
        print_error "Cannot access Kubernetes cluster"
        exit 1
    fi

    health_check

    echo ""
    read -p "Run full test suite? (y/n): " choice
    if [ "$choice" == "y" ]; then
        echo ""

        test_connection
        test_database_exists
        test_tables_exist
        test_write_operations
        test_read_operations
        test_views
        test_analytics_user

        echo ""
        get_performance_stats
        get_storage_info
    fi

    echo ""
    print_success "PostgreSQL testing completed!"
    echo ""
    echo "Connection Summary:"
    echo "  Host: postgres.monitoring.svc.cluster.local:5432"
    echo "  Database: devops_monitoring"
    echo "  Primary User: postgres"
    echo "  Analytics User: analytics_user"
    echo ""
    echo "Schema: analytics"
    echo "Tables: metrics, cost_tracking, performance_baselines, cache_stats, realtime_analytics, config_audit_log"
}

main "$@"
