# Migration Guide: run_query.py → run_query_v2.py

## Overview

`run_query.py` (v1) was removed on **2026-08-30**. Use `run_query_v2.py`.

This guide helps you migrate to `run_query_v2.py`, which includes significant enhancements:

| Feature | v1 (run_query.py) | v2 (run_query_v2.py) |
|---------|-------------------|---------------------|
| Backend Integration | None | ✅ Full adapter support with fallback |
| Feature Flags | Hardcoded | ✅ Dynamic via `features.yaml` |
| Retry Logic | None | ✅ Exponential backoff |
| Circuit Breaker | None | ✅ Failing service protection |
| Structured Logging | Basic print | ✅ JSON with credential sanitization |
| Metrics | None | ✅ Comprehensive instrumentation |
| Cache | None | ✅ TTL-based result caching |
| Query Deduplication | None | ✅ Single-flight pattern |

---

## Quick Migration

### Command Line Changes

**v1 Command:**
```bash
python tools/run_query.py --project meinvoice --section errors --time-range now-30m
```

**v2 Command:**
```bash
python tools/run_query_v2.py --project meinvoice --section errors --time-range now-30m
```

That's it! All existing arguments work identically.

---

## Compatibility

### Query Definitions (YAML)

All your existing query YAML files work unchanged:

- `projects/<name>/queries/*.yaml`
- `queries/common/*.yaml`
- Project configs and global configs

**No changes required.**

### Environment Variables

All existing environment variables continue to work:

- `ELK_AUTH`
- `ELK_PROJECT_AUTH`
- `PROM_AUTH`

---

## New Features in v2

### 1. Backend Service Integration

When the backend is available, v2 uses connection-pooled service clients:

```yaml
# config/features.yaml
backend_integration:
  enabled: true  # Set to true when backend is available
  fallback_on_error: true  # Falls back to HTTP if backend fails
```

### 2. Feature Flags

Runtime behavior controlled via `config/features.yaml`:

```yaml
optimization:
  cache_enabled: true
  deduplication_enabled: true
  parallel_queries: true

retry:
  enabled: true
  max_attempts: 3
  circuit_breaker_enabled: true
```

### 3. Distributed Caching (Optional)

Enable Redis-based distributed caching:

```yaml
optimization:
  redis_cache:
    enabled: true
    url: "redis://localhost:6379/0"
    ttl_seconds: 60
```

### 4. Structured JSON Logging

v2 outputs structured logs with credential sanitization:

```json
{
  "timestamp": "2026-08-23T12:00:00Z",
  "level": "INFO",
  "message": "Query executed",
  "request_id": "abc123",
  "project": "meinvoice",
  "section": "errors"
}
```

---

## Migration Steps

### Phase 1: Test v2 in Development (Week 1)

1. **Test with your existing queries:**
   ```bash
   python tools/run_query_v2.py --project <your-project> --section <query>
   ```

2. **Compare outputs with v1:**
   ```bash
   # Run both and compare
   python tools/run_query.py --project meinvoice --section errors > v1_output.json
   python tools/run_query_v2.py --project meinvoice --section errors > v2_output.json
   diff v1_output.json v2_output.json
   ```

3. **Verify all critical queries work correctly**

### Phase 2: Update CI/CD (Week 2)

Update any scripts or CI/CD pipelines:

```bash
# Before
python tools/run_query.py --project $PROJECT --section $SECTION

# After
python tools/run_query_v2.py --project $PROJECT --section $SECTION
```

### Phase 3: Configure Feature Flags (Week 3)

Copy and customize `config/features.yaml`:

```bash
cp config/features.yaml config/features.local.yaml
# Edit features.local.yaml for your environment
```

### Phase 4: Deploy to Production (Week 4)

1. Deploy v2 alongside v1
2. Monitor for any issues
3. Switch traffic to v2
4. Keep v1 as fallback for 1 week

### Phase 5: Remove v1 (Week 5+)

After successful production run:

```bash
# Remove v1 (after v1.1.0 release)
rm tools/run_query.py
```

---

## Timeline

| Milestone | Date | Action |
|-----------|------|--------|
| Deprecation Notice | 2026-08-23 | v1 marked deprecated |
| v1.1.0 Release | ~2026-11-23 | v1 removed (90 days) |
| End of Support | 2026-12-31 | No further bug fixes |

---

## Troubleshooting

### Issue: "Backend unavailable" messages

**Cause:** Backend integration is enabled but backend service is not running.

**Solution:** Either:
- Start the backend service, or
- Disable backend integration in `features.yaml`:
  ```yaml
  backend_integration:
    enabled: false
  ```

### Issue: Different output format

**Cause:** v2 uses structured JSON logging by default.

**Solution:** Disable structured output in `features.yaml`:
```yaml
output:
  use_emoji: false
  use_colors: false
```

### Issue: Performance slower than v1

**Cause:** v2 has additional overhead for metrics, logging, caching.

**Solution:** Disable features you don't need in `features.yaml`:
```yaml
monitoring:
  track_metrics: false
optimization:
  cache_enabled: false
  deduplication_enabled: false
```

---

## Need Help?

- **Documentation**: See `README.md` and `CLAUDE.md`
- **Issues**: Report at https://github.com/vumanhcuongUET/devops-monitoring-tool/issues
- **Questions**: Contact the DevOps team
