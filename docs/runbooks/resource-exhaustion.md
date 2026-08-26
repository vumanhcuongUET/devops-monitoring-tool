# Runbook: Resource Exhaustion

## Alert
- **Name**: `HighMemoryUsage`, `DiskSpaceLow`
- **Severity**: High/Critical
- **Condition**:
  - Memory usage > 90% for 5+ minutes
  - Disk space < 20% for 10+ minutes

## Detection
```
# Memory
container_memory_usage_bytes / container_spec_memory_limit_bytes > 0.9

# Disk
node_filesystem_avail_bytes / node_filesystem_size_bytes < 0.2
```

## Initial Assessment (5 min)

1. **Identify affected resource**
   ```bash
   # Check memory usage
   kubectl top pods -n devops-monitor --sort-by=memory

   # Check disk usage
   kubectl exec -n devops-monitor postgres-0 -- df -h
   ```

2. **Determine severity**
   - Critical: > 95% memory, < 10% disk
   - High: > 90% memory, < 20% disk

3. **Check trend**
   ```bash
   # Is usage increasing?
   kubectl exec -n devops-monitor postgres-0 -- \
     watch -n 10 'df -h | grep -v tmpfs'
   ```

## Investigation (10 min)

1. **Memory investigation**
   ```bash
   # Check for memory leaks
   kubectl exec -n devops-monitor deployment/backend -- \
     cat /proc/meminfo | grep -E 'MemTotal|MemFree|MemAvailable|Shmem|Slab'

   # Check container restarts
   kubectl get pods -n devops-monitor -o=jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.containerStatuses[0].restartCount}{"\n"}{end}'
   ```

2. **Disk investigation**
   ```bash
   # Find large files
   kubectl exec -n devops-monitor postgres-0 -- \
     find /var/lib/postgresql -size +100M -exec ls -lh {} \;

   # Check WAL retention
   kubectl exec -n devops-monitor postgres-0 -- \
     du -sh /var/lib/postgresql/pgdata/pg_wal
   ```

3. **Check logs size**
   ```bash
   # Check log rotation
   kubectl exec -n devops-monitor -l app=backend -- \
     du -sh /var/log/*
   ```

## Resolution Steps

### Memory Exhaustion

#### Immediate Actions
```bash
# 1. Identify high-memory consumers
kubectl top pods -n devops-monitor --sort-by=memory | head -5

# 2. Scale horizontally if possible
kubectl scale deployment backend -n devops-monitor --replicas=4

# 3. Restart pods with high memory
kubectl delete pod <high-memory-pod> -n devops-monitor
```

#### Longer-term Fixes
```bash
# 1. Increase memory limits
kubectl patch deployment backend -n devops-monitor --type=json \
  -p='[{"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/memory", "value": "2Gi"}]'

# 2. Enable memory profiling
kubectl set env deployment/backend -n devops-monitor \
  MALLOC_STATS=1

# 3. Investigate memory leak
# - Take heap dump
# - Analyze with memory profiler
```

### Disk Exhaustion

#### Immediate Actions
```bash
# 1. Clean up old logs (older than 7 days)
kubectl exec -n devops-monitor postgres-0 -- \
   find /var/log/postgresql -mtime +7 -delete

# 2. Vacuum PostgreSQL to reclaim space
kubectl exec -n devops-monitor postgres-0 -- \
   psql -U postgres -c "VACUUM FULL;"

# 3. Clean old WAL files
kubectl exec -n devops-monitor postgres-0 -- \
   psql -U postgres -c "SELECT pg_switch_wal();"
kubectl exec -n devops-monitor postgres-0 -- \
   psql -U postgres -c "SELECT pg_archivecleanup((SELECT current_setting('archive_command')), '000000010000000000000003');"
```

#### For Specific Scenarios
```bash
# Pod disk usage
kubectl exec -n devops-monitor <pod> -- df -h

# If /var/lib/docker is full
# 1. Clean up unused Docker resources
kubectl delete pod <pod> -n devops-monitor  # Force recreation

# 2. Clean old container images
docker system prune -a
```

## Verification

1. **Resource usage decreasing**
   ```bash
   # Monitor memory
   kubectl top pods -n devops-monitor --sort-by=memory

   # Monitor disk
   kubectl exec -n devops-monitor postgres-0 -- df -h
   ```

2. **No pod restarts**
   ```bash
   kubectl get pods -n devops-monitor | grep -v Running
   ```

3. **All services healthy**
   ```bash
   curl http://localhost:8000/api/v1/health
   ```

## Post-Incident

1. **Root cause analysis**
   - Memory leak?
   - Disk space not monitored?
   - Log retention policy needed?

2. **Prevention measures**
   - Set up automated log rotation
   - Configure WAL archiving
   - Add disk space monitoring

3. **Capacity planning**
   - Review growth trends
   - Plan for capacity increase
   - Update resource limits

## Related Runbooks
- [High Latency](./high-latency.md) - Often related to resource pressure
- [Database Issues](./database-issues.md) - Disk space impacts DB

## Prevention Checklist

- [ ] Automated log rotation configured
- [ ] WAL archiving enabled
- [ ] Regular VACUUM scheduled
- [ ] Disk space alerts configured (< 30%)
- [ ] Memory alerts configured (> 80%)
- [ ] Resource limits appropriate
