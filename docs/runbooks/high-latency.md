# Runbook: High Latency

## Alert
- **Name**: `HighLatency`
- **Severity**: High
- **Condition**: P95 latency > 2s for 10+ minutes

## Detection
```
histogram_quantile(0.95,
  rate(http_request_duration_seconds_bucket[5m])
) > 2
```

## Initial Assessment (5 min)

1. **Identify affected service**
   ```bash
   # Check which service has high latency
   curl http://localhost:8000/api/v1/metrics/latency/by-service
   ```

2. **Check latency breakdown**
   ```bash
   # View P50, P95, P99 latencies
   curl http://localhost:8000/api/v1/metrics/latency/percentiles
   ```

3. **Identify slow endpoints**
   ```bash
   # Get slowest endpoints
   curl http://localhost:8000/api/v1/slo/service/all/slow-apis
   ```

## Investigation (10 min)

1. **Check database query performance**
   ```bash
   # Enable slow query log
   kubectl exec -n devops-monitor postgres-0 -- \
     psql -U postgres -c "ALTER SYSTEM SET log_min_duration_statement = 1000;"

   # Check for slow queries
   kubectl logs -n devops-monitor postgres-0 --tail=100 | grep "duration:"
   ```

2. **Check external service calls**
   ```bash
   # View Elasticsearch query times
   kubectl logs -n devops-monitor -l app=backend --tail=1000 | \
     grep "elasticsearch" | grep "duration"
   ```

3. **Check resource usage**
   ```bash
   # Check CPU throttling
   kubectl top pods -n devops-monitor -l app=backend

   # Check memory pressure
   kubectl exec -n devops-monitor -c backend -- \
     cat /sys/fs/cgroup/memory/memory.stat | grep pgmajfault
   ```

4. **Analyze distributed tracing**
   - Navigate to Jaeger UI
   - Search traces with duration > 2s
   - Identify slow spans

## Resolution Steps

### If database queries are slow
```bash
# 1. Check for missing indexes
kubectl exec -n devops-monitor postgres-0 -- \
  psql -U postgres -c "SELECT * FROM pg_stat_user_tables;"

# 2. Add missing indexes
kubectl exec -n devops-monitor postgres-0 -- \
  psql -U postgres -c "CREATE INDEX CONCURRENTLY idx_name ON table(column);"

# 3. Update statistics
kubectl exec -n devops-monitor postgres-0 -- \
  psql -U postgres -c "ANALYZE table_name;"
```

### If external API calls are slow
```bash
# 1. Check circuit breaker status
curl http://localhost:8000/api/v1/circuit-breakers

# 2. Increase timeout if needed
kubectl edit configmap backend-config -n devops-monitor

# 3. Restart to apply
kubectl rollout restart deployment/backend -n devops-monitor
```

### If resource constrained
```bash
# 1. Check current limits
kubectl get deployment backend -n devops-monitor -o json | jq '.spec.template.spec.containers[0].resources'

# 2. Increase limits
kubectl patch deployment backend -n devops-monitor --type=json \
  -p='[{"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/cpu", "value": "2000m"}]'

# 3. Scale horizontally if needed
kubectl scale deployment backend -n devops-monitor --replicas=4
```

### If cache misses
```bash
# 1. Check Redis hit rate
kubectl exec -n devops-monitor redis-0 -- redis-cli INFO stats | grep keyspace

# 2. Warm up cache
curl -X POST http://localhost:8000/api/v1/cache/warm

# 3. Consider increasing cache size
kubectl edit configmap redis-config -n devops-monitor
```

## Verification

1. **Latency returns to baseline**
   ```bash
   # Monitor P95 latency
   watch -n 10 'curl -s http://localhost:8000/api/v1/metrics/latency/p95'
   ```

2. **No slow endpoints**
   ```bash
   curl http://localhost:8000/api/v1/slo/service/all/slow-apis
   ```

3. **SLO compliance restored**
   ```bash
   curl http://localhost:8000/api/v1/slo/service/all/status
   ```

## Post-Incident

1. **Document findings**
   - Which component was slow?
   - What was the root cause?
   - What was the resolution?

2. **Update runbook**
   - Add new pattern if discovered
   - Update troubleshooting steps

3. **Prevention measures**
   - Add performance tests
   - Set up synthetic monitoring
   - Consider pre-warming caches

## Related Runbooks
- [High Error Rate](./high-error-rate.md)
- [Resource Exhaustion](./resource-exhaustion.md)
- [Database Issues](./database-issues.md)
