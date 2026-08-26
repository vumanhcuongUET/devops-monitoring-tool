# Runbook: Database Issues

## Alert
- **Name**: `PostgreSQLDown`, `PostgreSQLSlowQueries`, `PostgreSQLConnectionPoolExhausted`
- **Severity**: Critical/High
- **Condition**: Database down, slow queries, connection pool issues

## Detection
```
# Database down
pg_up == 0

# Slow queries
rate(pg_stat_database_calls_total[5m]) / rate(...) > 0.05

# Connection pool
pg_stat_activity_count / pg_settings_max_connections > 0.9
```

## Initial Assessment (5 min)

1. **Check PostgreSQL status**
   ```bash
   # Check pod status
   kubectl get pods -n devops-monitor -l app=postgresql

   # Check if PostgreSQL is running
   kubectl exec -n devops-monitor postgres-0 -- pg_isready
   ```

2. **Check replication status (if HA)**
   ```bash
   # Check replication lag
   kubectl exec -n devops-monitor postgres-1 -- \
     psql -U postgres -c "SELECT now() - pg_last_xact_replay_timestamp() AS lag;"
   ```

3. **Identify issue type**
   - Database completely down?
   - Slow queries?
   - Connection issues?

## Investigation (10 min)

1. **If database is down**
   ```bash
   # Check pod logs
   kubectl logs -n devops-monitor postgres-0 --tail=100

   # Check pod events
   kubectl describe pod postgres-0 -n devops-monitor
   ```

2. **If slow queries**
   ```bash
   # Enable slow query log
   kubectl exec -n devops-monitor postgres-0 -- \
     psql -U postgres -c "ALTER SYSTEM SET log_min_duration_statement = 1000;"
   kubectl exec -n devops-monitor postgres-0 -- \
     psql -U postgres -c "SELECT pg_reload();"

   # Check for long-running queries
   kubectl exec -n devops-monitor postgres-0 -- \
     psql -U postgres -c "SELECT pid, now() - pg_stat_activity.query_start AS duration, query FROM pg_stat_activity WHERE state = 'active' ORDER BY duration DESC;"
   ```

3. **If connection issues**
   ```bash
   # Check active connections
   kubectl exec -n devops-monitor postgres-0 -- \
     psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"

   # Check max connections
   kubectl exec -n devops-monitor postgres-0 -- \
     psql -U postgres -c "SHOW max_connections;"
   ```

## Resolution Steps

### Database Down

#### If pod is not running
```bash
# 1. Check PVC status
kubectl get pvc -n devops-monitor postgres-data

# 2. Recreate pod
kubectl delete pod postgres-0 -n devops-monitor

# 3. Monitor startup
kubectl logs -n devops-monitor postgres-0 -f
```

#### If data corruption suspected
```bash
# 1. Restore from backup
./scripts/restore-postgresql.sh <backup_file> devops-monitor

# 2. Verify restore
kubectl exec -n devos-monitor postgres-0 -- \
  psql -U postgres -c "SELECT COUNT(*) FROM audit_log;"
```

### Slow Queries

#### Immediate Actions
```bash
# 1. Kill long-running queries
kubectl exec -n devops-monitor postgres-0 -- \
  psql -U postgres -c "SELECT pg_cancel_backend(<pid>);"

# 2. If necessary, terminate
kubectl exec -n devops-monitor postgres-0 -- \
  psql -U postgres -c "SELECT pg_terminate_backend(<pid>);"
```

#### Longer-term Fixes
```bash
# 1. Analyze query plan
kubectl exec -n devops-monitor postgres-0 -- \
  psql -U postgres -c "EXPLAIN ANALYZE <your-query>;"

# 2. Add missing indexes
kubectl exec -n devos-monitor postgres-0 -- \
  psql -U postgres -c "CREATE INDEX CONCURRENTLY idx_name ON table(column);"

# 3. Update statistics
kubectl exec -n devos-monitor postgres-0 -- \
  psql -U postgres -c "ANALYZE table_name;"
```

### Connection Pool Exhausted

#### Immediate Actions
```bash
# 1. Check for idle connections
kubectl exec -n devos-monitor postgres-0 -- \
  psql -U postgres -c "SELECT * FROM pg_stat_activity WHERE state = 'idle';"

# 2. Kill idle connections
kubectl exec -n devos-monitor postgres-0 -- \
  psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND state_change < now() - interval '10 minutes';"
```

#### Longer-term Fixes
```bash
# 1. Increase max_connections
kubectl edit configmap postgres-config -n devops-monitor
# Update: max_connections = 200

# 2. Configure PgBouncer for connection pooling
kubectl apply -f k8s/postgresql/pgbouncer.yaml
```

## Verification

1. **Database is healthy**
   ```bash
   kubectl exec -n devos-monitor postgres-0 -- pg_isready
   ```

2. **No long-running queries**
   ```bash
   kubectl exec -n devos-monitor postgres-0 -- \
     psql -U postgres -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active' AND now() - query_start > interval '5 minutes';"
   ```

3. **Application can connect**
   ```bash
   curl http://localhost:8000/api/v1/health/db
   ```

## Post-Incident

1. **Analyze root cause**
   - Hardware issue?
   - Missing index?
   - Application not closing connections?

2. **Prevention measures**
   - Set up connection pooling
   - Add query performance monitoring
   - Implement connection limits per application

3. **Update runbook**
   - Document new patterns discovered
   - Add troubleshooting steps

## Related Runbooks
- [High Error Rate](./high-error-rate.md)
- [High Latency](./high-latency.md)
- [Resource Exhaustion](./resource-exhaustion.md)

## Maintenance Commands

```bash
# Manual VACUUM
kubectl exec -n devos-monitor postgres-0 -- \
  psql -U postgres -c "VACUUM ANALYZE;"

# Check database size
kubectl exec -n devos-monitor postgres-0 -- \
  psql -U postgres -c "SELECT pg_database.datname, pg_size_pretty(pg_database_size(pg_database.datname)) FROM pg_database;"

# Check table sizes
kubectl exec -n devos-monitor postgres-0 -- \
  psql -U postgres -c "SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC;"
```
