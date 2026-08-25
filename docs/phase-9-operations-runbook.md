# Phase 9 Operations Runbook

## Distributed State Management

### Redis Operations

#### Check Redis Status
```bash
# Check Redis is running in Kubernetes
kubectl exec -n devops-monitoring deploy/redis -- redis-cli PING

# Check Redis info
kubectl exec -n devops-monitoring deploy/redis -- redis-cli INFO
```

#### View Alert State
```bash
# View all alert state keys
kubectl exec -n devops-monitoring deploy/redis -- redis-cli KEYS "alert:*"

# View specific alert state
kubectl exec -n devops-monitoring deploy/redis -- redis-cli GET "alert:state:alert-123"
```

#### View Approval State
```bash
# View all approval keys
kubectl exec -n devops-monitoring deploy/redis -- redis-cli KEYS "approval:*"

# View specific approval
kubectl exec -n devops-monitoring deploy/redis -- redis-cli GET "approval:approval-456"
```

#### Clear Rate Limits (Emergency)
```bash
# Clear all rate limits
kubectl exec -n devops-monitoring deploy/redis -- redis-cli FLUSHDB

# Clear specific rate limit key
kubectl exec -n devops-monitoring deploy/redis -- redis-cli DEL "ratelimit:user:123"
```

### Connection Pool Monitoring

#### Check Connection Pool Stats
```bash
# Via API endpoint
curl http://localhost:8000/api/v1/health/connection-pools | jq '.'

# Expected output:
# {
#   "elasticsearch": {
#     "active": 5,
#     "idle": 15,
#     "max": 20
#   },
#   ...
# }
```

### LLM Streaming

#### Verify Streaming Endpoint
```bash
# Test streaming endpoint
curl -X POST http://localhost:8000/api/v1/analyze/simple-stream \
  -H "Content-Type: application/json" \
  -d '{"project": "meinvoice", "question": "Tình trạng hệ thống?"}'
```

## Incident Response

### High Redis Memory

**Symptoms**: Redis OOM, alerts not persisting

**Mitigation**:
1. Check memory usage:
```bash
kubectl exec -n devops-monitoring deploy/redis -- redis-cli INFO memory
```

2. Review TTL settings in code

3. Increase Redis memory limit:
```bash
kubectl set resources deployment/redis \
  --limits=memory=2Gi \
  -n devops-monitoring
```

### Rate Limit Issues

**Symptoms**: Legitimate requests blocked

**Mitigation**:
1. Check rate limit state:
```bash
kubectl exec -n devops-monitoring deploy/redis -- redis-cli KEYS "ratelimit:*"
```

2. Temporarily increase limits via environment variables

3. Whitelist IP if needed:
```bash
kubectl exec -n devops-monitoring deploy/backend -- \
  redis-cli SADD "ratelimit:whitelist:10.0.0.1" 1
```

### Slow Overview Endpoint

**Symptoms**: Overview endpoint takes > 5 seconds

**Diagnosis**:
1. Check each service client individually
2. Review connection pool stats
3. Check Elasticsearch cluster health

**Mitigation**:
1. Verify Elasticsearch is not under load
2. Check connection pool settings
3. Enable request batching if not already active

## Monitoring

### Key Metrics

| Metric | Description | Threshold |
|--------|-------------|-----------|
| `overview_latency` | Overview endpoint response time | < 5s |
| `es_query_latency` | Elasticsearch query time | < 2s |
| `connection_pool_active` | Active connections | < max_connections |
| `redis_memory_used` | Redis memory usage | < 80% |
| `llm_first_token_time` | Time to first LLM token | < 1s |

### Dashboards

Configure these Grafana dashboards:

1. **Overview Performance**: Latency, error rate, throughput
2. **Connection Pools**: Active/idle connections per service
3. **Redis Metrics**: Memory, keys, operations/sec
4. **LLM Performance**: Token generation rate, latency

## Troubleshooting

### Common Issues

#### Issue: "Connection pool exhausted"
**Cause**: Too many concurrent requests
**Fix**: Increase `ES_MAX_CONNECTIONS` or enable request batching

#### Issue: "Redis connection refused"
**Cause**: Redis not running or wrong host/port
**Fix**: Check `REDIS_HOST` and `REDIS_PORT` settings

#### Issue: "LLM streaming timeout"
**Cause**: API key invalid or network issue
**Fix**: Verify `ANTHROPIC_API_KEY` and check firewall rules

## Backup & Recovery

### Redis Backup
```bash
# Trigger Redis BGSAVE
kubectl exec -n devops-monitoring deploy/redis -- redis-cli BGSAVE

# Copy RDB file
kubectl cp devops-monitoring/redis:/data/dump.rdb ./backup/redis/
```

### Restore Redis
```bash
# Copy RDB file back
kubectl cp ./backup/redis/dump.rdb devops-monitoring/redis:/data/dump.rdb

# Restart Redis pod
kubectl rollout restart deployment/redis -n devops-monitoring
```
