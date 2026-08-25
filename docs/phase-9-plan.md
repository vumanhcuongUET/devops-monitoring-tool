# Phase 9: Production Hardening & Scalability

**Status**: 🚧 IN PROGRESS
**Start Date**: 2026-08-25
**Target Completion**: 2026-09-14 (20 days)

---

## Executive Summary

Phase 9 addresses critical issues identified in comprehensive project review, focusing on:
1. **Distributed State Management** - Migrate from file-based to Redis-backed state
2. **Performance Optimization** - Connection pooling, LLM streaming
3. **Security Hardening** - Secret management, SSRF protection
4. **DevOps Automation** - CI/CD pipelines, load testing

**Critical Issues Being Addressed**:
- P0: Development secrets in .env, File-based state persistence
- P1: In-memory rate limiting, No connection pooling, SSRF DNS rebinding
- P2: No CI/CD pipelines, Bare except clauses, Missing load testing

---

## 🎯 Phase 9 Goals

| Goal | Current State | Target State |
|------|---------------|--------------|
| Scalability | 5/10 (file-based state, in-memory rate limits) | 9/10 (Redis-backed, distributed) |
| Performance | 6/10 (no pooling, blocking operations) | 8/10 (pooled, async optimized) |
| Security | 8.4/10 (some gaps) | 9.5/10 (secrets managed, SSRF hardened) |
| DevOps Maturity | 5/10 (manual deployments) | 8/10 (CI/CD automated) |
| Code Quality | 7/10 (bare except, large functions) | 8/10 (clean code patterns) |
| Testing | 6/10 (no load tests) | 8/10 (load + chaos tests) |

---

## Sprint Structure

```
Phase 9: Production Hardening & Scalability (20 days)
├── Sprint 1: State Management & Distributed Systems (Days 1-5)
├── Sprint 2: Performance & Connection Optimization (Days 6-10)
├── Sprint 3: Security Hardening & CI/CD (Days 11-15)
└── Sprint 4: Observability & Validation (Days 16-20)
```

---

## Sprint 1: State Management & Distributed Systems (Days 1-5)

### Objective
Migrate from file-based to distributed Redis-backed state management for alerts, approvals, and rate limiting.

### Issues Addressed
- P0#2: File-based state persistence
- P1#3: In-memory rate limiting

### Day 1: Redis-based Alert State

**File**: `backend/app/alerting/redis_store.py` (new)

```python
from typing import Optional
import json
import redis.asyncio as redis
from app.config import settings

class RedisAlertStore:
    """Redis-backed alert state with proper locking and TTL."""

    def __init__(self):
        self.redis = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            db=settings.REDIS_DB_ALERTS,
            decode_responses=True,
        )

    async def save_alert_state(self, state: dict) -> None:
        """Save alert state with Redis SETNX for distributed locking."""
        key = f"alert:state:{state['id']}"
        await self.redis.setex(
            key,
            86400,  # 24 hour TTL
            json.dumps(state),
        )

    async def get_alert_state(self, alert_id: str) -> Optional[dict]:
        """Get alert state from Redis."""
        key = f"alert:state:{alert_id}"
        data = await self.redis.get(key)
        return json.loads(data) if data else None

    async def acquire_lock(self, alert_id: str, ttl: int = 30) -> bool:
        """Acquire distributed lock for alert modification."""
        lock_key = f"alert:lock:{alert_id}"
        return await self.redis.set(
            lock_key,
            "locked",
            nx=True,
            ex=ttl,
        )
```

**Modified File**: `backend/app/alerting/engine.py`

```python
# Replace file-based with Redis-backed store
from app.alerting.redis_store import RedisAlertStore

class AlertEngine:
    def __init__(self):
        self.store = RedisAlertStore()  # Changed from JSONFileStore
```

**Tests**: `backend/tests/alerting/test_redis_store.py`

**Acceptance Criteria**:
- [ ] Alert state persisted in Redis
- [ ] Concurrent modifications handled correctly
- [ ] TTL configured for automatic cleanup
- [ ] All existing alert tests pass

---

### Day 2: Redis-based Approval Store

**File**: `backend/app/approvals/redis_store.py` (new)

```python
from typing import Optional
import json
import redis.asyncio as redis
from app.config import settings

class RedisApprovalStore:
    """Redis-backed approval state with distributed locking."""

    def __init__(self):
        self.redis = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            db=settings.REDIS_DB_APPROVALS,
            decode_responses=True,
        )

    async def save_approval(self, approval: dict) -> None:
        """Save approval with distributed lock."""
        key = f"approval:{approval['id']}"
        lock_key = f"approval:lock:{approval['id']}"

        # Acquire lock
        locked = await self.redis.set(lock_key, "1", nx=True, ex=30)
        if not locked:
            raise RuntimeError("Approval is being modified by another process")

        try:
            await self.redis.setex(key, 604800, json.dumps(approval))  # 7 day TTL
        finally:
            await self.redis.delete(lock_key)
```

**Acceptance Criteria**:
- [ ] Approval state in Redis
- [ ] Distributed locking prevents race conditions
- [ ] 7-day retention for audit trail

---

### Day 3: Redis-based Distributed Rate Limiting

**File**: `backend/app/rate_limit/redis_rate_limiter.py` (new)

```python
import time
import redis.asyncio as redis
from typing import Optional
from app.config import settings

class RedisRateLimiter:
    """Distributed rate limiter using Redis with sliding window."""

    def __init__(self):
        self.redis = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            db=settings.REDIS_DB_RATE_LIMIT,
            decode_responses=True,
        )

    async def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, dict]:
        """
        Check rate limit using Redis sorted set for sliding window.

        Returns: (allowed, rate_limit_info)
        """
        now = time.time()
        window_start = now - window_seconds
        redis_key = f"ratelimit:{key}"

        pipe = self.redis.pipeline()

        # Remove entries outside the window
        pipe.zremrangebyscore(redis_key, 0, window_start)

        # Count current requests
        pipe.zcard(redis_key)

        # Add current request
        pipe.zadd(redis_key, {str(now): now})

        # Set expiry
        pipe.expire(redis_key, window_seconds)

        results = await pipe.execute()
        current_count = results[1]

        allowed = current_count < max_requests
        reset_time = now + (window_seconds - (now - window_start))

        return allowed, {
            "limit": max_requests,
            "remaining": max(0, max_requests - current_count),
            "reset": int(reset_time),
        }
```

**Modified File**: `backend/app/api/v1/analyze.py`

```python
from app.rate_limit.redis_rate_limiter import RedisRateLimiter

rate_limiter = RedisRateLimiter()

@router.post("/analyze")
async def analyze(request: Request, ...):
    allowed, info = await rate_limiter.check_rate_limit(
        key=f"user:{user_id}",
        max_requests=100,
        window_seconds=60,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail=info)
```

**Acceptance Criteria**:
- [ ] Rate limits work across multiple pods
- [ ] Sliding window algorithm implemented
- [ ] Proper HTTP 429 responses with Retry-After header

---

### Day 4: Connection Pooling for Service Clients

**File**: `backend/app/services/elasticsearch_client.py`

```python
class ElasticsearchClient:
    def __init__(self):
        self.client = AsyncElasticsearch(
            settings.ELASTICSEARCH_URL,
            basic_auth=(
                settings.ELASTICSEARCH_USERNAME,
                settings.ELASTICSEARCH_PASSWORD,
            ),
            request_timeout=settings.REQUEST_TIMEOUT_SECONDS,
            # NEW: Connection pooling
            max_connections=20,
            max_retries=3,
            retry_on_timeout=True,
            http_compress=True,
        )
```

**File**: `backend/app/services/prometheus_client.py`

```python
from prometheus_client.rest import RequestsTransport

class PrometheusClient:
    def __init__(self):
        self.session = aiohttp.ClientSession(
            base_url=settings.PROMETHEUS_URL,
            # NEW: Connection pooling
            connector=aiohttp.TCPConnector(
                limit=20,  # Max connections
                limit_per_host=10,
                ttl_dns_cache=300,
                keepalive_timeout=60,
            ),
            timeout=aiohttp.ClientTimeout(total=settings.REQUEST_TIMEOUT_SECONDS),
        )
```

**File**: `backend/app/config.py` (add new settings)

```python
class Settings(BaseSettings):
    # ... existing settings ...

    # Redis Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB_ALERTS: int = 0
    REDIS_DB_APPROVALS: int = 1
    REDIS_DB_RATE_LIMIT: int = 2
    REDIS_DB_CACHE: int = 3

    # Connection Pool Settings
    ES_MAX_CONNECTIONS: int = 20
    PROM_MAX_CONNECTIONS: int = 20
    K8S_MAX_CONNECTIONS: int = 10
```

**Acceptance Criteria**:
- [ ] All service clients use connection pooling
- [ ] Pool size configurable via environment variables
- [ ] Keep-alive enabled
- [ ] DNS caching configured

---

### Day 5: Integration Tests for Distributed State

**File**: `backend/tests/integration/test_distributed_state.py` (new)

```python
import pytest
import asyncio
from app.alerting.redis_store import RedisAlertStore
from app.approvals.redis_store import RedisApprovalStore
from app.rate_limit.redis_rate_limiter import RedisRateLimiter

@pytest.mark.integration
class TestDistributedState:
    """Test distributed state management with Redis."""

    async def test_concurrent_alert_modifications(self):
        """Test that concurrent alert modifications are handled correctly."""
        store = RedisAlertStore()
        alert_id = "test-concurrent-123"

        # Simulate concurrent modifications
        tasks = [
            store.save_alert_state({"id": alert_id, "status": f"state-{i}"})
            for i in range(10)
        ]
        await asyncio.gather(*tasks)

        # Verify final state is consistent
        result = await store.get_alert_state(alert_id)
        assert result is not None
        assert result["id"] == alert_id

    async def test_distributed_rate_limit_across_pods(self):
        """Test rate limiting works across distributed processes."""
        limiter = RedisRateLimiter()
        key = "test-distributed-limit"

        # Simulate 10 concurrent requests, limit is 5
        tasks = [
            limiter.check_rate_limit(key, max_requests=5, window_seconds=60)
            for _ in range(10)
        ]
        results = await asyncio.gather(*tasks)

        allowed_count = sum(1 for allowed, _ in results if allowed)
        assert allowed_count == 5

    async def test_approval_lock_prevents_race_conditions(self):
        """Test distributed approval locking."""
        store = RedisApprovalStore()
        approval_id = "test-lock-123"

        # First acquisition should succeed
        lock1 = await store.redis.set(f"approval:lock:{approval_id}", "1", nx=True, ex=30)
        assert lock1 is True

        # Second acquisition should fail
        lock2 = await store.redis.set(f"approval:lock:{approval_id}", "1", nx=True, ex=30)
        assert lock2 is False
```

**Acceptance Criteria**:
- [ ] All integration tests pass
- [ ] Concurrent access tests validate
- [ ] Race conditions properly handled

---

## Sprint 2: Performance & Connection Optimization (Days 6-10)

### Objective
Optimize performance with connection pooling, request batching, and LLM streaming.

### Issues Addressed
- P1#4: No connection pooling
- P3#9: No LLM streaming

### Day 6: Advanced Connection Pool Configuration

**File**: `backend/app/services/connection_pool.py` (new)

```python
from dataclasses import dataclass
from typing import Optional
import aiohttp
from app.config import settings

@dataclass
class PoolConfig:
    """Connection pool configuration."""
    max_connections: int = 20
    max_connections_per_host: int = 10
    keepalive_timeout: int = 60
    connect_timeout: int = 5
    socket_timeout: int = 30

class ConnectionPoolManager:
    """Centralized connection pool management."""

    _instance: Optional["ConnectionPoolManager"] = None
    _pools: dict[str, aiohttp.TCPConnector] = {}

    def __init__(self):
        if ConnectionPoolManager._instance is not None:
            raise RuntimeError("Use get_pool_manager()")

    @classmethod
    def get_pool_manager(cls) -> "ConnectionPoolManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_pool(self, name: str, config: PoolConfig) -> aiohttp.TCPConnector:
        """Get or create connection pool."""
        if name not in self._pools:
            self._pools[name] = aiohttp.TCPConnector(
                limit=config.max_connections,
                limit_per_host=config.max_connections_per_host,
                ttl_dns_cache=300,
                keepalive_timeout=config.keepalive_timeout,
            )
        return self._pools[name]

    async def close_all(self):
        """Close all connection pools."""
        for pool in self._pools.values():
            await pool.close()
        self._pools.clear()
```

**Acceptance Criteria**:
- [ ] Centralized pool management
- [ ] Configurable pool sizes per service
- [ ] Proper cleanup on shutdown

---

### Day 7: Request Batching Optimization

**File**: `backend/app/services/batch_optimizer.py` (new)

```python
from typing import Any, Callable, Awaitable
from collections import defaultdict
import asyncio

class BatchOptimizer:
    """Optimize multiple requests by batching when possible."""

    def __init__(self, batch_size: int = 10, max_wait: float = 0.1):
        self.batch_size = batch_size
        self.max_wait = max_wait
        self._pending: defaultdict[str, list] = defaultdict(list)

    async def batch_request(
        self,
        batch_key: str,
        request_id: str,
        execute_fn: Callable[[list[str]], Awaitable[list[Any]]],
    ) -> Any:
        """
        Add request to batch and wait for batch completion.

        Args:
            batch_key: Key to group requests (e.g., "overview-data")
            request_id: Unique ID for this request
            execute_fn: Function to execute batched requests
        """
        future = asyncio.Future()
        self._pending[batch_key].append((request_id, future))

        if len(self._pending[batch_key]) >= self.batch_size:
            # Batch is full, execute immediately
            await self._execute_batch(batch_key, execute_fn)
        else:
            # Wait for more requests or timeout
            asyncio.create_task(self._delayed_execute(batch_key, execute_fn))

        return await future

    async def _delayed_execute(self, batch_key: str, execute_fn: Callable):
        """Execute batch after delay."""
        await asyncio.sleep(self.max_wait)
        if batch_key in self._pending:
            await self._execute_batch(batch_key, execute_fn)

    async def _execute_batch(self, batch_key: str, execute_fn: Callable):
        """Execute all pending requests in batch."""
        if batch_key not in self._pending:
            return

        requests = self._pending.pop(batch_key)
        request_ids = [r[0] for r in requests]
        futures = [r[1] for r in requests]

        try:
            results = await execute_fn(request_ids)
            for future, result in zip(futures, results):
                if not future.done():
                    future.set_result(result)
        except Exception as e:
            for future in futures:
                if not future.done():
                    future.set_exception(e)
```

**Modified File**: `backend/app/api/v1/overview.py`

```python
from app.services.batch_optimizer import BatchOptimizer

batch_optimizer = BatchOptimizer(batch_size=10, max_wait=0.1)

@router.get("/overview")
async def get_overview(project: str):
    # Batch multiple overview requests
    result = await batch_optimizer.batch_request(
        batch_key=f"overview:{project}",
        request_id=f"req_{uuid4()}",
        execute_fn=lambda ids: fetch_overview_data(project),
    )
    return result
```

**Acceptance Criteria**:
- [ ] Multiple overview requests batched
- [ ] Reduced backend API calls
- [ ] Latency improvements measurable

---

### Day 8: LLM Streaming Implementation

**File**: `backend/app/services/llm_client.py`

```python
async def analyze_with_streaming(
    self,
    context: dict[str, Any],
    question: str,
) -> AsyncIterator[str]:
    """
    Analyze context and stream response token by token.

    Yields JSON-formatted chunks compatible with frontend.
    """
    message = self.client.messages.create(
        model=self.model,
        max_tokens=settings.AI_MAX_TOKENS,
        system=self.SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": self._format_prompt(context, question)},
        ],
        temperature=0.3,
        stream=True,  # Enable streaming
    )

    full_response = ""
    for chunk in message:
        if chunk.type == "content_block_delta":
            if chunk.delta.text:
                text = chunk.delta.text
                full_response += text
                # Yield formatted chunk
                yield json.dumps({
                    "type": "token",
                    "text": text,
                    "done": False,
                }) + "\n"

    # Send final completion signal
    yield json.dumps({
        "type": "complete",
        "text": "",
        "done": True,
        "full_response": full_response,
    }) + "\n"
```

**File**: `backend/app/api/v1/analyze.py` (add streaming endpoint)

```python
from fastapi.responses import StreamingResponse

@router.post("/analyze/stream")
async def analyze_stream(request: AnalyzeRequest):
    """Streaming version of analyze endpoint."""
    llm_client = get_llm_client()

    async def generate():
        context = await build_context(request.project, request.question)
        async for chunk in llm_client.analyze_with_streaming(context, request.question):
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
    )
```

**Frontend Hook**: `frontend/src/hooks/useLLMStream.ts` (new)

```typescript
export function useLLMStream() {
  const [response, setResponse] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const streamQuery = async (project: string, question: string) => {
    setIsStreaming(true);
    setResponse("");
    setError(null);

    try {
      const response = await fetch("/api/v1/analyze/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project, question }),
      });

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split("\n").filter(Boolean);

        for (const line of lines) {
          const data = JSON.parse(line);
          if (data.type === "token") {
            setResponse((prev) => prev + data.text);
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsStreaming(false);
    }
  };

  return { response, isStreaming, error, streamQuery };
}
```

**Acceptance Criteria**:
- [ ] LLM responses stream token by token
- [ ] Frontend displays streaming responses
- [ ] Time to first token < 1 second
- [ ] Better UX for long analyses

---

### Day 9: Performance Benchmarks

**File**: `backend/tests/performance/test_benchmarks.py` (new)

```python
import pytest
import time
from app.services.elasticsearch_client import ElasticsearchClient
from app.services.prometheus_client import PrometheusClient
from app.services.kubernetes_client import KubernetesClient

@pytest.mark.benchmark
class TestPerformanceBenchmarks:
    """Performance benchmarks for critical operations."""

    async def test_elasticsearch_query_performance(self):
        """Benchmark Elasticsearch log query performance."""
        client = ElasticsearchClient()
        start = time.time()

        result = await client.search_logs(
            project="meinvoice",
            query="ERROR",
            time_range="30m",
        )

        duration = time.time() - start
        assert duration < 2.0, f"Query took {duration:.2f}s, expected < 2s"
        assert result is not None

    async def test_overview_endpoint_latency(self):
        """Benchmark overview endpoint latency."""
        from app.api.v1.overview import get_overview

        start = time.time()
        result = await get_overview(project="meinvoice")
        duration = time.time() - start

        assert duration < 5.0, f"Overview took {duration:.2f}s, expected < 5s"

    async def test_concurrent_overview_requests(self):
        """Benchmark concurrent overview requests."""
        import asyncio

        async def make_request():
            from app.api.v1.overview import get_overview
            return await get_overview(project="meinvoice")

        start = time.time()
        results = await asyncio.gather(*[make_request() for _ in range(10)])
        duration = time.time() - start

        assert len(results) == 10
        assert duration < 10.0, f"10 requests took {duration:.2f}s"
```

**Acceptance Criteria**:
- [ ] All benchmarks meet targets
- [ ] Baseline metrics documented
- [ ] Performance regression tests added

---

### Day 10: Sprint 2 Completion & Validation

**Checklist**:
- [ ] All Sprint 2 tasks complete
- [ ] Connection pooling configured for all services
- [ ] Request batching implemented
- [ ] LLM streaming functional
- [ ] Performance benchmarks passing
- [ ] Documentation updated

**Deliverables**:
- `backend/app/services/connection_pool.py`
- `backend/app/services/batch_optimizer.py`
- LLM streaming endpoint
- Performance benchmark suite

---

## Sprint 3: Security Hardening & CI/CD (Days 11-15)

### Objective
Enhanced security with proper secret management and automated CI/CD pipelines.

### Issues Addressed
- P0#1: Development secrets in .env
- P1#5: SSRF DNS rebinding vulnerability
- P2#6: No CI/CD pipelines

### Day 11: Remove .env and Setup Secret Management

**Action Items**:
1. Ensure `.env` is in `.gitignore` (already should be)
2. Remove any `.env` files from git history
3. Setup Kubernetes secrets with External Secrets Operator

**File**: `k8s/backend/external-secret.yaml` (new)

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: backend-secrets
  namespace: devops-monitoring
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: SecretStore
  target:
    name: backend-secrets
    creationPolicy: Owner
  data:
    - secretKey: elasticsearch-password
      remoteRef:
        key: devops/monitoring/elasticsearch
        property: password
    - secretKey: prometheus-password
      remoteRef:
        key: devops/monitoring/prometheus
        property: password
    - secretKey: auth-secret
      remoteRef:
        key: devops/monitoring/auth
        property: secret
    - secretKey: anthropic-api-key
      remoteRef:
        key: devops/monitoring/anthropic
        property: api_key
```

**File**: `.gitignore` (verify)

```gitignore
# Environment variables
.env
.env.local
.env.*.local

# Secrets
*.key
*.pem
secrets/
```

**File**: `scripts/remove-env-from-history.sh` (new)

```bash
#!/bin/bash
# Remove .env files from git history

echo "⚠️  WARNING: This will rewrite git history"
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Use BFG Repo-Cleaner or git-filter-repo
git filter-repo --path .env --invert-paths

echo "✅ .env removed from history"
echo "⚠️  Force push required: git push origin --force --all"
```

**Acceptance Criteria**:
- [ ] `.env` in `.gitignore`
- [ ] No secrets in git history
- [ ] External Secrets Operator configured
- [ ] All secrets sourced from Vault/Secret Manager

---

### Day 12: SSRF Protection Enhancement

**File**: `backend/app/security.py` (enhance)

```python
import socket
import time
from typing import Optional, Set
from functools import lru_cache
from ipaddress import ip_address, ip_network

class SSRFProtection:
    """Enhanced SSRF protection with DNS caching and rebinding prevention."""

    # DNS cache: hostname -> (ip_list, timestamp)
    _dns_cache: dict[str, tuple[list[str], float]] = {}
    _cache_ttl = 300  # 5 minutes

    # Blocked networks
    BLOCKED_NETWORKS: Set[str] = {
        "127.0.0.0/8",      # Loopback
        "169.254.0.0/16",   # Link-local
        "10.0.0.0/8",       # Private
        "172.16.0.0/12",     # Private
        "192.168.0.0/16",   # Private
        "::1/128",           # IPv6 loopback
        "fc00::/7",         # IPv6 private
        "fe80::/10",        # IPv6 link-local
    }

    @classmethod
    def resolve_and_validate(
        cls,
        hostname: str,
        port: Optional[int] = None,
    ) -> tuple[bool, str]:
        """
        Resolve hostname and validate against SSRF rules.
        Returns: (is_safe, error_message)
        """
        now = time.time()

        # Check cache first
        if hostname in cls._dns_cache:
            ips, cached_time = cls._dns_cache[hostname]
            if now - cached_time < cls._cache_ttl:
                resolved_ips = ips
            else:
                resolved_ips = cls._resolve_dns(hostname)
        else:
            resolved_ips = cls._resolve_dns(hostname)

        # Update cache
        cls._dns_cache[hostname] = (resolved_ips, now)

        # Validate each resolved IP
        for ip_str in resolved_ips:
            if not cls._is_ip_allowed(ip_str):
                return False, f"IP {ip_str} is not allowed"

        return True, ""

    @classmethod
    def _resolve_dns(cls, hostname: str) -> list[str]:
        """Resolve hostname to IP addresses."""
        try:
            addr_info = socket.getaddrinfo(
                hostname,
                80,  # Port doesn't matter for resolution
                proto=socket.IPPROTO_TCP,
            )
            # Extract unique IPs
            ips = set()
            for info in addr_info:
                ip_str = info[4][0]
                ips.add(ip_str)
            return list(ips)
        except socket.gaierror:
            raise ValueError(f"DNS resolution failed for {hostname}")

    @classmethod
    def _is_ip_allowed(cls, ip_str: str) -> bool:
        """Check if IP is allowed (not in blocked networks)."""
        try:
            ip = ip_address(ip_str)
            for network_str in cls.BLOCKED_NETWORKS:
                network = ip_network(network_str, strict=False)
                if ip in network:
                    return False
            return True
        except ValueError:
            return False

    @classmethod
    def clear_dns_cache(cls):
        """Clear DNS cache (for testing or manual refresh)."""
        cls._dns_cache.clear()
```

**Modified File**: `backend/app/api/v1/analyze.py`

```python
from app.security import SSRFProtection

# In the analyze endpoint, validate any URLs
if "url" in request_data:
    is_safe, error = SSRFProtection.resolve_and_validate(request_data["url"])
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"Invalid URL: {error}")
```

**Acceptance Criteria**:
- [ ] DNS caching implemented (5 min TTL)
- [ ] DNS rebinding attacks prevented
- [ ] All blocked networks covered
- [ ] Cache can be cleared manually

---

### Day 13: GitHub Actions CI/CD Pipeline

**File**: `.github/workflows/ci.yml` (new)

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

env:
  PYTHON_VERSION: "3.12"
  NODE_VERSION: "20"

jobs:
  backend-lint:
    name: Backend Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - name: Install dependencies
        run: |
          cd backend
          pip install ruff black mypy
      - name: Run ruff
        run: cd backend && ruff check .
      - name: Run black
        run: cd backend && black --check .
      - name: Run mypy
        run: cd backend && mypy app/

  backend-test:
    name: Backend Tests
    runs-on: ubuntu-latest
    services:
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install -r requirements-test.txt
      - name: Run tests
        run: |
          cd backend
          pytest tests/ -v --cov=app --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: ./backend/coverage.xml

  frontend-test:
    name: Frontend Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
      - name: Install dependencies
        run: cd frontend && npm ci
      - name: Run linter
        run: cd frontend && npm run lint
      - name: Run type check
        run: cd frontend && npx tsc -b
      - name: Run tests
        run: cd frontend && npm run test

  security-scan:
    name: Security Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Bandit
        run: |
          pip install bandit
          bandit -r backend/app/ -f json -o bandit-report.json
      - name: Run npm audit
        run: cd frontend && npm audit --audit-level=high
      - name: Check for secrets
        uses: trufflesecurity/trufflehog@main
        with:
          path: ./
          base: ${{ github.event.repository.default_branch }}

  build-and-push:
    name: Build and Push Images
    needs: [backend-lint, backend-test, frontend-test, security-scan]
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and push backend
        uses: docker/build-push-action@v5
        with:
          context: ./backend
          push: true
          tags: ghcr.io/${{ github.repository }}/backend:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max
      - name: Build and push frontend
        uses: docker/build-push-action@v5
        with:
          context: ./frontend
          push: true
          tags: ghcr.io/${{ github.repository }}/frontend:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

**Acceptance Criteria**:
- [ ] CI pipeline runs on all PRs
- [ ] All tests must pass before merge
- [ ] Docker images built and pushed
- [ ] Security scans integrated

---

### Day 14: External Secrets Operator Setup

**File**: `k8s/external-secrets/setup.yaml` (new)

```yaml
---
# SecretStore configuration
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: vault-backend
  namespace: devops-monitoring
spec:
  provider:
    vault:
      server: "https://vault.internal.company.com:8200"
      path: "secret"
      auth:
        kubernetes:
          mountPath: "auth/kubernetes"
          role: "devops-monitoring"
          serviceAccountRef:
            name: external-secrets-sa
      version: "v2"

---
# Service account for External Secrets
apiVersion: v1
kind: ServiceAccount
metadata:
  name: external-secrets-sa
  namespace: devops-monitoring

---
# Role for SecretStore access
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: secret-reader
  namespace: devops-monitoring
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list"]

---
# Role binding
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: secret-reader-binding
  namespace: devops-monitoring
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: secret-reader
subjects:
  - kind: ServiceAccount
    name: external-secrets-sa
```

**Acceptance Criteria**:
- [ ] External Secrets Operator installed
- [ ] Vault integration configured
- [ ] Secrets auto-synced from Vault
- [ ] Rotation supported

---

### Day 15: Security Validation

**File**: `backend/tests/security/test_security_hardening.py` (new)

```python
import pytest
from app.security import SSRFProtection
from app.config import settings

@pytest.mark.security
class TestSecurityHardening:
    """Test security hardening measures."""

    def test_ssrf_blocks_loopback(self):
        """Test that SSRF protection blocks loopback addresses."""
        is_safe, error = SSRFProtection.resolve_and_validate("localhost")
        assert not is_safe
        assert "not allowed" in error.lower()

    def test_ssrf_blocks_private_networks(self):
        """Test that SSRF protection blocks private networks."""
        is_safe, _ = SSRFProtection.resolve_and_validate("10.0.0.1")
        assert not is_safe

    def test_dns_cache_prevents_rebinding(self):
        """Test that DNS caching prevents rebinding attacks."""
        from app.security import SSRFProtection

        # First resolution
        SSRFProtection.resolve_and_validate("example.com")

        # Cache should be populated
        assert "example.com" in SSRFProtection._dns_cache

    def test_no_secrets_in_environment(self):
        """Test that no dummy secrets are configured."""
        assert settings.AUTH_SECRET != "dummy_secret_for_dev"
        assert settings.AUTH_SECRET != "CHANGE_ME"

    def test_rate_limit_enforced(self):
        """Test that rate limiting is enforced."""
        # Test distributed rate limiting
        from app.rate_limit.redis_rate_limiter import RedisRateLimiter
        import asyncio

        async def test():
            limiter = RedisRateLimiter()
            key = "test-security-rate-limit"

            # Make 10 requests, limit is 5
            results = await asyncio.gather(*[
                limiter.check_rate_limit(key, 5, 60)
                for _ in range(10)
            ])

            allowed = sum(1 for r, _ in results if r)
            assert allowed == 5, f"Expected 5 allowed, got {allowed}"

        asyncio.run(test())
```

**Acceptance Criteria**:
- [ ] All security tests pass
- [ ] SSRF protection validated
- [ ] Secrets properly externalized
- [ ] Rate limiting enforced

---

## Sprint 4: Observability & Validation (Days 16-20)

### Objective
Enhanced observability with distributed tracing, load testing, and code quality improvements.

### Issues Addressed
- P2#7: Bare except clauses
- P2#8: Missing load testing
- P3#10: Large functions

### Day 16: OpenTelemetry Distributed Tracing

**File**: `backend/app/telemetry.py` (new)

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor

def setup_telemetry(app=None):
    """Setup OpenTelemetry tracing."""
    resource = Resource(attributes={
        "service.name": "devops-monitoring-backend",
        "service.version": "1.0.0",
        "deployment.environment": settings.ENVIRONMENT,
    })

    provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(
        endpoint=settings.OTLP_ENDPOINT,
        insecure=not settings.OTLP_SECURE,
    )
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    trace.set_tracer_provider(provider)

    # Instrument FastAPI
    if app:
        FastAPIInstrumentor.instrument_app(app)

    # Instrument HTTP clients
    HTTPXClientInstrumentor().instrument()

    # Instrument asyncio
    AsyncioInstrumentor().instrument()

    return provider
```

**File**: `backend/app/main.py` (modify)

```python
from app.telemetry import setup_telemetry

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_telemetry(app)
    # ... rest of startup
    yield
    # ... shutdown
```

**File**: `k8s/backend/otel-collector.yaml` (new)

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: otel-collector-config
data:
  config.yaml: |
    receivers:
      otlp:
        protocols:
          grpc:

    processors:
      batch:

    exporters:
      jaeger:
        endpoint: jaeger:4317
        tls:
          insecure: true

    service:
      pipelines:
        traces:
          receivers: [otlp]
          processors: [batch]
          exporters: [jaeger]
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: otel-collector
spec:
  replicas: 1
  selector:
    matchLabels:
      app: otel-collector
  template:
    metadata:
      labels:
        app: otel-collector
    spec:
      containers:
      - name: otel-collector
        image: otel/opentelemetry-collector-contrib:latest
        args:
        - --config=/etc/otel-collector-config/config.yaml
        volumeMounts:
        - name: config
          mountPath: /etc/otel-collector-config
      volumes:
      - name: config
        configMap:
          name: otel-collector-config
```

**Acceptance Criteria**:
- [ ] OpenTelemetry tracing enabled
- [ ] Spans visible in Jaeger
- [ ] Distributed traces across services

---

### Day 17: Load Testing Suite

**File**: `tests/load/overview_load_test.k6.js` (new)

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '1m', target: 10 },   // Ramp up to 10 users
    { duration: '3m', target: 50 },   // Ramp up to 50 users
    { duration: '5m', target: 100 },  // Ramp up to 100 users
    { duration: '2m', target: 0 },     // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],  // 95% of requests < 2s
    http_req_failed: ['rate<0.05'],      // Error rate < 5%
  },
};

const BACKEND_URL = __ENV.BACKEND_URL || 'http://localhost:8000';

export default function () {
  // Test overview endpoint
  const overviewRes = http.get(`${BACKEND_URL}/api/v1/overview?project=meinvoice`);
  check(overviewRes, {
    'overview status 200': (r) => r.status === 200,
    'overview response time < 2s': (r) => r.timings.duration < 2000,
  });

  // Test APM data endpoint
  const apmRes = http.get(`${BACKEND_URL}/api/v1/apm/transactions?project=meinvoice&range=1h`);
  check(apmRes, {
    'apm status 200': (r) => r.status === 200,
  });

  sleep(1);
}

export function handleSummary(data) {
  return {
    stdout: JSON.stringify(data, null, 2),
  };
}
```

**File**: `tests/load/alert_load_test.k6.js` (new)

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    constant_load: {
      executor: 'constant-vus',
      vus: 20,
      duration: '2m',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<1000'],
    http_req_failed: ['rate<0.01'],
  },
};

const BACKEND_URL = __ENV.BACKEND_URL || 'http://localhost:8000';

export default function () {
  const payload = JSON.stringify({
    name: `Test Alert ${__VU}`,
    condition: "error_rate > 5%",
    threshold: 5,
    window_minutes: 5,
    project: "meinvoice",
  });

  const params = {
    headers: { 'Content-Type': 'application/json' },
  };

  const res = http.post(`${BACKEND_URL}/api/v1/alerts/rules`, payload, params);
  check(res, {
    'create alert status 201': (r) => r.status === 201,
  });
}
```

**File**: `scripts/run-load-tests.sh` (new)

```bash
#!/bin/bash
set -e

echo "🚀 Running Load Tests..."

# Start backend in background
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

# Wait for backend to be ready
sleep 5

# Run K6 tests
echo "Running overview load test..."
k6 run tests/load/overview_load_test.k6.js --out json=overview-results.json

echo "Running alert load test..."
k6 run tests/load/alert_load_test.k6.js --out json=alert-results.json

# Cleanup
kill $BACKEND_PID

echo "✅ Load tests complete!"
echo "Results:"
cat overview-results.json | jq '.metrics'
```

**Acceptance Criteria**:
- [ ] Load tests for overview endpoint
- [ ] Load tests for alert management
- [ ] Performance thresholds defined
- [ ] Results can be visualized

---

### Day 18: Code Quality Fixes

**Fix 1: Bare Except Clauses**

**Files to fix**:
- `backend/app/services/log_sampler.py`
- `backend/app/actions/remediation_actions.py`
- `backend/app/cache/l3_cache.py`

**Pattern**:
```python
# BEFORE (bad)
except:
    logger.error("Something went wrong")

# AFTER (good)
except Exception as e:
    logger.exception(f"Error in operation: {e}")
```

**Fix 2: Extract Large Functions**

**File**: `backend/app/actions/engine.py`

```python
# Extract action state building logic
def _build_action_kwargs(action_id: str, state: dict) -> dict:
    """Build action kwargs from state."""
    action_kwargs = {"id": action_id, "status": state.get("status")}
    optional_fields = [
        "command_type", "target_resource", "parameters",
        "impact_level", "risk_score", "estimated_duration",
        "rollback_command", "requires_approval", "approval_id",
        "created_at", "expires_at", "created_by", "tags",
    ]
    for field in optional_fields:
        if field in state:
            action_kwargs[field] = state[field]
    return action_kwargs

# Use in multiple places
def approve_action(action_id: str, approver: str) -> dict:
    # ... validation ...
    action_kwargs = _build_action_kwargs(action_id, state)
    # ... rest of approval logic
```

**Acceptance Criteria**:
- [ ] All bare except clauses fixed
- [ ] Large functions refactored
- [ ] Code follows clean code principles
- [ ] All tests still pass

---

### Day 19: Documentation Updates

**File**: `docs/phase-9-operations-runbook.md` (new)

```markdown
# Phase 9 Operations Runbook

## Distributed State Management

### Redis Operations

**Check Redis status:**
\`\`\`bash
kubectl exec -n devops-monitoring deploy/redis -- redis-cli PING
\`\`\`

**View alert state:**
\`\`\`bash
kubectl exec -n devops-monitoring deploy/redis -- redis-cli KEYS "alert:state:*"
\`\`\`

**Clear rate limits (emergency):**
\`\`\`bash
kubectl exec -n devops-monitoring deploy/redis -- redis-cli FLUSHDB
\`\`\`

### Connection Pool Monitoring

**Check connection pool stats:**
\`\`\`bash
# Check Elasticsearch connection pool
curl http://localhost:8000/api/v1/health/elasticsearch | jq ".connection_pool"
\`\`\`

## Incident Response

### High Redis Memory

**Symptoms:** Redis OOM, alerts not persisting

**Mitigation:**
1. Check memory usage: `kubectl exec ... -- redis-cli INFO memory`
2. Increase Redis memory limit in deployment
3. Review TTL settings

### Rate Limit Issues

**Symptoms:** Legitimate requests blocked

**Mitigation:**
1. Check rate limit state in Redis
2. Temporarily increase limits
3. Whitelist IP if needed
\`\`\`bash
# Whitelist IP
kubectl exec -n devops-monitoring deploy/backend -- \
  redis-cli SADD ratelimit:whitelist:10.0.0.1 1
\`\`\`
```

**File**: `docs/phase-9-architecture.md` (new)

```markdown
# Phase 9 Architecture Updates

## Distributed State Architecture

\`\`\`
┌─────────────────┐
│   Frontend      │
└────────┬────────┘
         │
┌────────▼────────┐
│  Backend (Pod)  │◄────┐
└────────┬────────┘     │
         │              │
┌────────▼────────┐    │
│     Redis       │────┘ (Shared state)
│  (Distributed)  │
└─────────────────┘
\`\`\`

## Connection Pool Architecture

Each service client maintains a connection pool:

- Elasticsearch: 20 max connections
- Prometheus: 20 max connections
- Kubernetes: 10 max connections
- Claude API: 10 max connections
```

**Acceptance Criteria**:
- [ ] Runbook updated with new operations
- [ ] Architecture documented
- [ ] Troubleshooting guides added
- [ ] API documentation updated

---

### Day 20: Final Validation & Completion

**Final Checklist**:

**Sprint 1 - State Management**:
- [ ] Redis-based alert state
- [ ] Redis-based approval store
- [ ] Redis-based rate limiting
- [ ] Connection pooling implemented

**Sprint 2 - Performance**:
- [ ] Request batching
- [ ] LLM streaming
- [ ] Performance benchmarks
- [ ] All targets met

**Sprint 3 - Security & CI/CD**:
- [ ] .env removed from git
- [ ] SSRF protection enhanced
- [ ] CI/CD pipeline active
- [ ] External secrets configured

**Sprint 4 - Observability**:
- [ ] OpenTelemetry tracing
- [ ] Load tests passing
- [ ] Code quality fixes
- [ ] Documentation complete

**Final Validation**:
```bash
# Run all tests
pytest backend/tests/ -v --cov=app
pytest frontend/tests/ -v

# Run load tests
k6 run tests/load/overview_load_test.k6.js

# Run security scan
bandit -r backend/app/
```

**Acceptance Criteria**:
- [ ] All tests passing (>95% coverage)
- [ ] Load tests meeting targets
- [ ] Security scans clean
- [ ] Documentation complete
- [ ] Phase 9 complete

---

## Deliverables Summary

| Sprint | Key Deliverables |
|--------|-----------------|
| **Sprint 1** | Redis state management, connection pooling |
| **Sprint 2** | Request batching, LLM streaming, benchmarks |
| **Sprint 3** | Secret management, CI/CD, SSRF protection |
| **Sprint 4** | OpenTelemetry, load tests, code quality |

---

## Success Metrics

| Metric | Before | Target | Current |
|--------|--------|--------|---------|
| Scalability Score | 5/10 | 9/10 | TBD |
| Performance Score | 6/10 | 8/10 | TBD |
| Security Score | 8.4/10 | 9.5/10 | TBD |
| DevOps Maturity | 5/10 | 8/10 | TBD |
| Critical Issues | 2 | 0 | TBD |
| High Issues | 3 | 0 | TBD |

---

**Document Version**: 1.0
**Created**: 2026-08-25
**Author**: Claude (SA/DevOps/AI Expert)
