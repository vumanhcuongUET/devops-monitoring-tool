# API Documentation

## Core Adapters

The AI Assistant provides service adapters for integrating with backend services. All adapters implement a consistent interface.

### ElasticsearchAdapter

```python
from services.elasticsearch_adapter import ElasticsearchAdapter

adapter = ElasticsearchAdapter(
    fallback_enabled=True  # Fall back to direct HTTP if backend unavailable
)

# Check availability
if adapter.available:
    # Search Elasticsearch
    result = adapter.search(
        index="logs-*",
        body={"query": {"match_all": {}}},
        size=10
    )
```

**Methods:**

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `search()` | `index`, `body`, `size=10` | dict | Execute Elasticsearch search query |
| `count()` | `index`, `body` | dict | Count documents matching query |
| `aggregate()` | `index`, `body` | dict | Execute aggregation query |

**Returns:**
- On success: `{"status": "ok", "data": <elasticsearch_response>}`
- On error: `{"status": "error", "error": <message>}`

### PrometheusAdapter

```python
from services.prometheus_adapter import PrometheusAdapter

adapter = PrometheusAdapter(
    fallback_enabled=True
)

# Check availability
if adapter.available:
    # Execute PromQL query
    result = adapter.query(
        promql='rate(http_requests_total[5m])'
    )
```

**Methods:**

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `query()` | `promql`, `params={}` | dict | Execute PromQL instant query |
| `query_range()` | `promql`, `start`, `end`, `step` | dict | Execute PromQL range query |

**Returns:**
- On success: `{"status": "ok", "data": <prometheus_response>}`
- On error: `{"status": "error", "error": <message>}`

### ApmAdapter

```python
from services.apm_adapter import ApmAdapter

adapter = ApmAdapter(fallback_enabled=True)

if adapter.available:
    # Get error transactions
    result = adapter.search_errors(
        service_name="meinvoice",
        time_range="now-1h"
    )
```

**Methods:**

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `search_errors()` | `service_name`, `time_range` | dict | Search APM error transactions |
| `get_service_stats()` | `service_name`, `time_range` | dict | Get service statistics |

### KubernetesAdapter

```python
from services.kubernetes_adapter import KubernetesAdapter

adapter = KubernetesAdapter(fallback_enabled=True)

if adapter.available:
    # Get pod status
    result = adapter.get_pod_status(
        namespace="production",
        label_selector="app=api"
    )
```

**Methods:**

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `get_pod_status()` | `namespace`, `label_selector` | dict | Get pod status by namespace |
| `get_deployment_status()` | `namespace`, `name` | dict | Get deployment status |
| `get_events()` | `namespace`, `field_selector` | dict | Get Kubernetes events |

## Core Utilities

### Cache Layer

```python
from core.cache import get_cache

# Get cache instance (default: in-memory SimpleCache)
cache = get_cache()

# Set value
cache.set("key", {"data": "value"}, ttl=60)

# Get value
value = cache.get("key")

# Delete value
cache.delete("key")

# Clear all
cache.clear()
```

**Cache Types:**
- `SimpleCache` - In-memory cache (default)
- `RedisCache` - Distributed Redis cache (if enabled)

### Single Flight (Query Deduplication)

```python
from core.single_flight import single_flight

@single_flight
def expensive_query(param):
    # This will only execute once per unique param
    # concurrent calls with same param will wait for first result
    return perform_query(param)
```

### Retry with Circuit Breaker

```python
from core.retry import with_retry, CircuitBreaker

@with_retry(max_attempts=3, backoff_base=2)
def flaky_api_call():
    # Will retry up to 3 times with exponential backoff
    return make_request()

# Or use circuit breaker
breaker = CircuitBreaker(failure_threshold=5, timeout=60)

@breaker
def protected_call():
    # Circuit opens after 5 failures, stays open for 60s
    return make_request()
```

### Security Functions

```python
from core.security import (
    InputValidator,
    check_rate_limit,
    log_event
)

# Validate inputs
is_valid, error = InputValidator.validate_project_name("my-project")
is_valid, error = InputValidator.validate_url("https://api.example.com")
is_valid, error = InputValidator.validate_promql('up{job="prometheus"}')

# Check rate limits
result = check_rate_limit(
    identifier="user123",
    rate=10.0,  # 10 requests per second
    capacity=100  # Allow bursts up to 100
)

# Log audit event
log_event(
    event_type="query",
    actor="user123",
    action="run_query",
    resource="meinvoice",
    status="success"
)
```

### Audit Logging

```python
from core.audit import get_audit_logger, AuditLogEntry

# Get logger instance
logger = get_audit_logger()

# Create and log entry
entry = AuditLogEntry(
    event_type="action",
    actor="user123",
    action="scale_deployment",
    resource="production/api",
    details={"replicas": 5}
)
logger.log(entry)

# Query audit logs
results = logger.query(
    actor="user123",
    start_time=start_timestamp,
    limit=100
)

# Verify integrity
verification = logger.verify_integrity()
if not verification["valid"]:
    # Logs have been tampered with
    handle_security_incident()
```

## Configuration

### Feature Flags

```python
from core.config_loader import is_feature_enabled

# Check if backend integration is enabled
if is_feature_enabled("backend_integration.enabled"):
    # Use backend adapters
    pass

# Check if optimization is enabled
if is_feature_enabled("optimization.cache_enabled"):
    # Use caching
    pass
```

### Loading Configuration

```python
from core.config_loader import load_config, load_query_def

# Load project configuration
config = load_config("meinvoice")

# Load query definition
qdef = load_query_def("meinvoice", "errors")
```

## Error Handling

All adapters and utilities follow consistent error handling:

```python
# Adapter errors return error dict
result = adapter.search(index="logs-*", body={...})
if result.get("status") == "error":
    print(f"Error: {result.get('error')}")
    # Handle error

# Utility errors raise exceptions
try:
    value = cache.get("key")
except CacheError as e:
    print(f"Cache error: {e}")
    # Handle error
```

## Thread Safety

- **Cache**: Thread-safe for get/set/delete operations
- **Single Flight**: Thread-safe with locking per key
- **Rate Limiter**: Thread-safe with internal locking
- **Audit Logger**: Thread-safe with file-level locking

## Performance Considerations

1. **Cache TTL**: Set appropriate TTL values to balance freshness and performance
2. **Rate Limits**: Configure rate limits based on backend capacity
3. **Single Flight**: Use for expensive, read-only operations
4. **Circuit Breakers**: Prevent cascading failures in dependent services

---

**API Version**: 2.0  
**Last Updated**: 2026-08-24  
**Maintained by**: DevOps AI Agentics Team
