# Runbook: SLO Violation

## Alert
- **Name**: `SLOViolation`
- **Severity**: Critical
- **Condition**: SLO budget remaining < 0%

## Detection
```
slo_budget_remaining < 0
```

## Initial Assessment (5 min)

1. **Identify violated SLO**
   ```bash
   # Check all SLO statuses
   curl http://localhost:8000/api/v1/slo/all/status
   ```

2. **Check SLO details**
   ```bash
   # Get specific SLO information
   curl http://localhost:8000/api/v1/slo/service/{service_name}/status
   ```

3. **Identify violation window**
   - Check SLO window (7d, 30d)
   - Calculate error budget burn rate
   - Determine time to full exhaustion

## Investigation (10 min)

1. **Analyze slow APIs**
   ```bash
   # Get slow API breakdown
   curl http://localhost:8000/api/v1/slo/service/{service_name}/slow-apis
   ```

2. **Review error budget consumption**
   ```bash
   # Get budget consumption rate
   curl http://localhost:8000/api/v1/slo/service/{service_name}/budget
   ```

3. **Identify contributing factors**
   - High error rate?
   - High latency (for latency SLOs)?
   - Specific time patterns?

4. **Check SLO configuration**
   ```bash
   # Verify SLO targets are realistic
   kubectl get configmap slo-configs -n devops-monitor -o yaml
   ```

## Resolution Steps

### Phase 1: Stabilize (Immediate)

1. **If error rate is high**
   - Follow [High Error Rate](./high-error-rate.md) runbook
   - Implement emergency fixes

2. **If latency is high**
   - Follow [High Latency](./high-latency.md) runbook
   - Scale horizontally

3. **Enable degraded mode**
   ```bash
   # Enable feature flags to reduce load
   curl -X POST http://localhost:8000/api/v1/features/disable-critical-path

   # Enable caching
   curl -X POST http://localhost:8000/api/v1/cache/enable-aggressive
   ```

### Phase 2: Recover Budget

1. **Calculate recovery time**
   ```bash
   # Estimate time to recover budget
   curl http://localhost:8000/api/v1/slo/service/{service_name}/recovery-estimate
   ```

2. **Implement improvements**
   - Optimize slow queries
   - Add caching layers
   - Fix bugs causing errors

3. **Monitor budget recovery**
   ```bash
   # Watch budget percentage
   watch -n 60 'curl -s http://localhost:8000/api/v1/slo/service/{service_name}/budget'
   ```

### Phase 3: Prevent Recurrence

1. **Review SLO targets**
   - Are targets realistic?
   - Should targets be adjusted?

2. **Improve engineering practices**
   - Add performance tests
   - Implement canary deployments
   - Add more monitoring

3. **Update SLO documentation**
   - Document SLO rationale
   - Update runbooks

## Verification

1. **SLO status improves**
   ```bash
   curl http://localhost:8000/api/v1/slo/service/{service_name}/status
   ```

2. **Budget no longer negative**
   ```bash
   curl http://localhost:8000/api/v1/slo/service/{service_name}/budget
   ```

3. **Trend is positive**
   - Budget is increasing over time
   - Error rate is decreasing

## Post-Incident

1. **Postmortem**
   - Why was SLO violated?
   - Was it a configuration issue?
   - Are SLO targets appropriate?

2. **Documentation updates**
   - Update SLO targets if needed
   - Document lessons learned
   - Update runbooks

3. **Process improvements**
   - Implement automated SLO monitoring
   - Add SLO checks to CI/CD
   - Schedule regular SLO reviews

## Related Runbooks
- [High Error Rate](./high-error-rate.md)
- [High Latency](./high-latency.md)
- [SLO at Risk](./slo-at-risk.md) (warning level)

## SLA Implications

- **Check SLA terms** - May have financial penalties
- **Notify stakeholders** - Proactive communication
- **Document outage** - For SLA reporting
