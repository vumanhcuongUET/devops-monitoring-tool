# Runbook: High Error Rate

## Alert
- **Name**: `HighErrorRate`
- **Severity**: High
- **Condition**: Error rate > 5% for 5+ minutes

## Detection
```
rate(http_requests_total{status=~"5.."}[5m])
/
rate(http_requests_total[5m])
> 0.05
```

## Initial Assessment (5 min)

1. **Identify scope**
   ```bash
   # Check which service is affected
   kubectl get pods -n devops-monitor -l app=backend
   ```

2. **Check Grafana dashboard**
   - Navigate to Service Overview dashboard
   - Look for error spike timestamp
   - Identify affected endpoints

3. **Check recent deployments**
   ```bash
   kubectl rollout history deployment/backend -n devops-monitor
   ```

## Investigation (10 min)

1. **Check logs for error patterns**
   ```bash
   # Get logs from affected pods
   kubectl logs -n devops-monitor -l app=backend --tail=1000 | grep ERROR
   ```

2. **Verify database connectivity**
   ```bash
   # Check PostgreSQL connection
   kubectl exec -n devops-monitor postgres-0 -- \
     psql -U postgres -c "SELECT 1;"
   ```

3. **Check external dependencies**
   - Elasticsearch status
   - Prometheus connectivity
   - Redis connection

4. **Analyze error distribution**
   ```bash
   # Get breakdown by error code
   kubectl logs -n devops-monitor -l app=backend --tail=1000 | \
     grep -oP 'status=\d{3}' | sort | uniq -c
   ```

## Resolution Steps

### If recent deployment
```bash
# Rollback to previous version
kubectl rollout undo deployment/backend -n devops-monitor

# Verify rollback
kubectl rollout status deployment/backend -n devops-monitor
```

### If database issue
```bash
# Check PostgreSQL pod status
kubectl get pods -n devops-monitor -l app=postgresql

# If PostgreSQL is down, trigger failover
kubectl apply -f k8s/postgresql/failover.yaml
```

### If external dependency
```bash
# Check circuit breaker status
curl http://localhost:8000/api/v1/circuit-breakers

# If tripped, reset after dependency is healthy
curl -X POST http://localhost:8000/api/v1/circuit-breakers/reset
```

### If code bug
1. Identify root cause from logs
2. Create hotfix branch
3. Deploy hotfix to staging first
4. Test in staging
5. Deploy to production

## Verification

1. **Error rate returns to baseline**
   ```bash
   # Check current error rate
   curl http://localhost:8000/api/v1/metrics/error-rate
   ```

2. **No new errors in 10 minutes**
   ```bash
   # Monitor logs
   kubectl logs -n devops-monitor -l app=backend --tail=100 -f
   ```

3. **All services healthy**
   ```bash
   kubectl get pods -n devops-monitor
   ```

## Post-Incident

1. **Document root cause**
   - Create incident report
   - Update this runbook if needed

2. **Create prevention task**
   - Add test case for regression
   - Consider additional monitoring

3. **Team debrief**
   - Schedule postmortem within 48 hours
   - Discuss what went well/what could be improved

## Related Runbooks
- [High Latency](./high-latency.md)
- [SLO Violation](./slo-violation.md)
- [Database Issues](./database-issues.md)
