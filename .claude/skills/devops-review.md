# DevOps Best Practices Review Skill

Review code for DevOps best practices, reliability, and operational excellence.

## What to Check

### 1. Error Handling & Resilience

**Missing Timeout**
```python
# ❌ BAD - No timeout, can hang indefinitely
response = requests.get("https://api.example.com/data")

# ✅ GOOD - Timeout with fallback
try:
    response = requests.get("https://api.example.com/data", timeout=5.0)
except requests.Timeout:
    logger.warning("API timeout, using fallback")
    return get_fallback_data()
```

**No Retry Logic**
```python
# ❌ BAD - Single attempt, fails on transient errors
response = requests.post(url, data=payload)

# ✅ GOOD - Retry with exponential backoff
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def call_api_with_retry():
    return requests.post(url, data=payload)
```

**Missing Circuit Breaker**
```python
# ❌ BAD - No circuit breaker, cascades failures
for service in services:
    response = requests.get(service.url)

# ✅ GOOD - Circuit breaker pattern
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=60)
def call_service(service):
    return requests.get(service.url)
```

### 2. Resource Management

**Resource Leaks**
```python
# ❌ BAD - Connection not closed
connection = get_db_connection()
connection.execute(query)

# ✅ GOOD - Proper cleanup with context manager
with get_db_connection() as connection:
    connection.execute(query)
# Connection automatically closed
```

**Unclosed File Handles**
```python
# ❌ BAD - File may not be closed on error
f = open('data.json', 'r')
data = json.load(f)
process(data)
f.close()

# ✅ GOOD - Context manager ensures cleanup
with open('data.json', 'r') as f:
    data = json.load(f)
    process(data)
```

### 3. Configuration Management

**Hardcoded Configuration**
```python
# ❌ BAD - Hardcoded values
API_ENDPOINT = "https://api.example.com"
MAX_RETRIES = 3

# ✅ GOOD - Configurable
API_ENDPOINT = os.getenv("API_ENDPOINT", "https://api.example.com")
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
```

**Missing Environment-Specific Config**
```python
# ❌ BAD - Same config for all environments
DEBUG = True
DATABASE_URL = "localhost:5432"

# ✅ GOOD - Environment-aware
DEBUG = os.getenv("ENVIRONMENT") == "development"
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL required")
```

### 4. Observability

**Missing Structured Logging**
```python
# ❌ BAD - Unstructured logs
print("Processing request")
print(f"Error: {error}")

# ✅ GOOD - Structured logging
logger.info("Processing request", extra={
    "request_id": request_id,
    "user_id": user_id,
    "endpoint": endpoint
})
logger.error("Processing failed", extra={
    "request_id": request_id,
    "error": str(error),
    "error_type": type(error).__name__
})
```

**No Metrics**
```python
# ❌ BAD - No metrics
def process_order(order):
    # Process order
    pass

# ✅ GOOD - With metrics
from prometheus_client import Counter, Histogram

orders_processed = Counter('orders_processed_total', 'Total orders processed')
processing_time = Histogram('order_processing_seconds', 'Order processing time')

def process_order(order):
    with processing_time.time():
        # Process order
        pass
    orders_processed.inc()
```

**No Distributed Tracing**
```python
# ✅ GOOD - Add tracing context
import opentelemetry.trace as trace
tracer = trace.get_tracer(__name__)

def process_order(order):
    with tracer.start_as_current_span("process_order"):
        # Process order
        pass
```

### 5. Health Checks

**Missing Health Endpoint**
```python
# ✅ GOOD - Health check endpoint
@app.get("/health")
async def health_check():
    checks = {
        "database": await check_database(),
        "redis": await check_redis(),
        "external_api": await check_external_api(),
    }
    healthy = all(checks.values())
    status_code = 200 if healthy else 503
    return JSONResponse(
        content={"status": "healthy" if healthy else "unhealthy", "checks": checks},
        status_code=status_code
    )
```

**No Readiness/Liveness Probes**
```yaml
# ✅ GOOD - Kubernetes probes
livenessProbe:
  httpGet:
    path: /health/live
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
```

### 6. Graceful Degradation

**No Fallback**
```python
# ❌ BAD - No fallback, complete failure
def get_user_data(user_id):
    response = requests.get(f"{USER_SERVICE_URL}/{user_id}")
    return response.json()

# ✅ GOOD - Fallback mechanism
def get_user_data(user_id):
    try:
        response = requests.get(f"{USER_SERVICE_URL}/{user_id}", timeout=3)
        return response.json()
    except (requests.Timeout, requests.ConnectionError) as e:
        logger.warning(f"User service unavailable: {e}")
        return get_cached_user_data(user_id) or get_default_user_data()
```

### 7. Rate Limiting & Throttling

**No Rate Limiting**
```python
# ❌ BAD - No rate limit
@app.post("/api/expensive-operation")
async def expensive_operation():
    # Expensive operation without rate limiting
    pass

# ✅ GOOD - Rate limiting
from slowapi import Limiter
limiter = Limiter(key_func=get_remote_address)

@app.post("/api/expensive-operation")
@limiter.limit("10/minute")
async def expensive_operation():
    # Expensive operation with rate limit
    pass
```

### 8. Graceful Shutdown

**No Graceful Shutdown**
```python
# ❌ BAD - abrupt shutdown, loses in-flight requests
# Server just kills connections

# ✅ GOOD - Graceful shutdown
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down gracefully...")
    # Wait for in-flight requests to complete (max 30s)
    await wait_for_requests_to_complete(timeout=30)
    # Close database connections
    await db.close()
    # Flush logs
    await logging.shutdown()
    logger.info("Shutdown complete")
```

### 9. Deployment Safety

**No Database Migration Safety**
```bash
# ❌ BAD - Unsafe migration
kubectl apply -f migration.yaml

# ✅ GOOD - Safe rollout
kubectl apply -f migration.yaml
# Wait for migration to complete
kubectl wait --for=condition=complete job/migration
# Then deploy new version
kubectl rollout restart deployment/app
```

**No Blue-Green Deployment**
```yaml
# ✅ GOOD - Blue-green deployment strategy
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 100%  # Create full new deployment
      maxUnavailable: 0  # Keep old deployment fully available
```

### 10. Monitoring & Alerting

**Missing SLO/SLI**
```python
# ✅ GOOD - SLO tracking
slo_tracker = SLOTracker(
    service_name="user-service",
    slo_target=0.99,  # 99% success rate
    window=timedelta(days=7)
)

@slo_tracker.track
def handle_user_request():
    # Handle request
    pass
```

## Review Checklist

For each code change, check:

- [ ] All external calls have appropriate timeouts
- [ ] Retry logic for transient failures
- [ ] Circuit breaker for downstream services
- [ ] Resources properly cleaned up (connections, files, etc.)
- [ ] Configuration is externalized, not hardcoded
- [ ] Environment-specific configuration is supported
- [ ] Structured logging with context
- [ ] Metrics for key operations
- [ ] Distributed tracing for request flows
- [ ] Health check endpoints implemented
- [ ] Graceful degradation with fallbacks
- [ ] Rate limiting for expensive operations
- [ ] Graceful shutdown handling
- [ ] Safe deployment strategies
- [ ] SLO/SLI tracking and alerting

## Output Format

```markdown
## DevOps Review: [file_name]

### Critical
- [Issue] - [Impact] - [Recommendation]

### High
- [Issue] - [Impact] - [Recommendation]

### Medium
- [Issue] - [Impact] - [Recommendation]

### Low
- [Issue] - [Impact] - [Recommendation]

### Positive Patterns
+ [Good practice found]
```
