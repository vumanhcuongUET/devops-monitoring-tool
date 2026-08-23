# Phase 7: Production Hardening & Scalability Enhancement (REVISED)

**Document Version**: 2.0
**Author**: Solution Architect & SRE Team
**Status**: ✅ APPROVED FOR EXECUTION (Revised based on Sprint Review)
**Timeline**: 9 Weeks (Revised from 6 weeks based on gap analysis)
**Priority**: HIGH - Address critical architecture gaps
**Dependencies**: Phase 6 (Token Optimization) must be complete

---

## 📋 Revision History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-23 | Initial plan | SRE Team |
| 2.0 | 2026-08-23 | Revised based on Sprint Review - Extended timeline, added Sprint 0, addressed gaps | Solution Architecture Team |

---

## 📋 Executive Summary

### Business Problem

After completing Phase 6 (AI Input Optimization), critical architecture gaps remain that hinder production readiness at scale:

1. **Single Point of Failure**: Platform has 0% uptime when all data sources are down
2. **Performance Degradation**: No caching, average latency 1500-2000ms
3. **Scalability Limits**: No database architecture prevents query optimization
4. **Config Drift**: No version control or validation for project configs
5. **Cost Still High**: Even after Phase 6, $1,350/year for 1000 req/day

### Solution

Implement **Production Hardening & Scalability Enhancement** that:
1. **Adds multi-layer caching** for 30-40% additional cost savings
2. **Implements graceful degradation** for 99.9% uptime during outages
3. **Enhances DR capabilities** to meet RTO/RPO targets
4. **Adds intelligent caching** for performance optimization
5. **Implements config management** for GitOps workflow

### Expected ROI

| Metric | Before Phase 6 | After Phase 6 | After Phase 7 | Improvement |
|--------|---------------|---------------|---------------|-------------|
| Token usage | 5,000 | 2,000 | 800 | **84%** |
| Cost/year (1k req/day) | $5,400 | $1,800 | $720 | **87%** |
| Avg latency | 1500ms | 1500ms | 300ms | **80%** |
| Uptime during outage | 0% | 0% | 99.9% | **+99.9%** |
| P99 latency | 5000ms | 5000ms | 1000ms | **80%** |

---

## 🏗️ Technical Architecture

### Enhanced Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React + TypeScript)                     │
│  - Virtual Scrolling                                                   │
│  - Optimistic Updates                                                  │
│  - WebSocket Cache Invalidation                                       │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          FASTAPI BACKEND                                 │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    API LAYER (FastAPI routes)                      │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                   │                                      │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    CACHE LAYER (NEW - Phase 7)                     │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────────┐  │  │
│  │  │ L1: In-Memory│ │ L2: Redis   │ │ L3: Semantic Cache          │  │  │
│  │  │ (per-request)│ │ (5-15min)   │ │ (pattern-based) 1-24h       │  │  │
│  │  │ + Cache Warming│ │ + Redis Cluster│ │ + Redis Persistence       │  │  │
│  │  └─────────────┘ └─────────────┘ └─────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                   │                                      │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    GRACEFUL DEGRADATION (NEW)                     │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────────┐  │  │
│  │  │ Priority Q  │ │ Cached Data │ │ Fallback Mode               │  │
│  │  │ (P0→P1→P2→P3)│ │ (critical)  │ │ (degraded service)          │  │
│  │  │ + Hysteresis │ │ + Auto Refresh│ │ + On-call Integration      │  │
│  │  └─────────────┘ └─────────────┘ └─────────────────────────────┘  │
│  └───────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
         ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
         │ Elasticsearch│  │  Prometheus  │  │  Kubernetes  │
         │   (Logs/APM) │  │  (Metrics)   │  │   (State)    │
         └──────────────┘  └──────────────┘  └──────────────┘

                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
         ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
         │  REDIS CLUSTER│ │ CONFIG DB    │  │ ANALYTICS DB  │
         │ (HA + Sentinel)│ │ (GitOps + KMS)│ │ (PostgreSQL)  │
         └──────────────┘  └──────────────┘  └──────────────┘
```

---

## 👥 Resource Requirements (Revised)

### Team Composition

| Role | Original | Revised | Responsibility |
|------|----------|---------|---------------|
| Backend Lead | 1.0 FTE | **1.0 FTE** | Caching, DR, config management, architecture |
| Frontend Developer | — | **1.0 FTE** | Dashboards, virtualization, WebSocket |
| DevOps Engineer | 0.25 FTE | **1.0 FTE** | Redis, GitOps, deployment, monitoring |
| QA Engineer | 0.5 FTE | **1.0 FTE** | Integration tests, DR tests, load tests |
| **Total** | **1.75 FTE** | **4.0 FTE** | Gap: +2.25 FTE |

### Infrastructure Requirements (Revised)

| Component | Environment | Specs | Monthly Cost |
|-----------|-------------|-------|--------------|
| Redis Cluster | Production | 3 nodes, 2GB each, HA | $200 |
| Redis | Staging | 2 nodes, 1GB each | $80 |
| Redis | Dev | 1 node, 512MB | $20 |
| PostgreSQL (Analytics) | Production | db.t3.medium, 100GB | $50 |
| GitOps Repository | All | S3/Git hosting | $10 |
| Monitoring | All | Additional metrics storage | $50 |
| **Total** | | | **~$360/month** |
| **Annual** | | | **~$4,320/year** |

---

## 📅 Detailed Sprint Plan (Revised: 9 Weeks)

### Sprint 0: Infrastructure Setup (Week 1: Days 1-3)

**Objective**: Establish foundation infrastructure before development begins

#### Day 1: Redis Infrastructure

**Tasks**:
1. **Provision Redis Cluster** (4h)
   ```bash
   # Production - Redis Cluster with Sentinel
   aws elasticache create-replication-group \
     --replication-group-id devops-p7-prod \
     --replication-group-description "DevOps Phase 7 Production" \
     --num-cache-clusters 3 \
     --cache-node-type cache.t3.medium \
     --engine redis 7.x \
     --automatic-failover-enabled \
     --multi-az-zone-enabled

   # Staging - Redis Cluster (smaller)
   aws elasticache create-replication-group \
     --replication-group-id devops-p7-staging \
     --cache-node-type cache.t3.micro \
     --num-cache-clusters 2

   # Dev - Single instance
   aws elasticache create-cache-cluster \
     --cache-cluster-id devops-p7-dev \
     --cache-node-type cache.t3.micro \
     --num-cache-nodes 1
   ```

2. **Configure Redis Security** (4h)
   ```bash
   # Security groups
   # Redis AUTH
   # TLS encryption in transit
   # VPC endpoints
   ```

**Deliverables**:
- Redis cluster provisioned (prod, staging, dev)
- Security configured
- Connection strings documented

**Acceptance Criteria**:
- ✅ Redis cluster operational in all environments
- ✅ Security groups configured
- ✅ Connection tested from application

---

#### Day 2: GitOps & Configuration Infrastructure

**Tasks**:
1. **Setup GitOps Repository** (4h)
   ```bash
   # Create GitOps repository
   mkdir -p config-repo/{global,projects,versions}
   cd config-repo
   git init
   # Configure branch strategy
   git checkout -b main
   git checkout -b develop
   ```

2. **Setup PostgreSQL for Analytics** (4h)
   ```bash
   # Provision PostgreSQL
   aws rds create-db-instance \
     --db-instance-identifier devops-p7-analytics \
     --db-instance-class db.t3.medium \
     --engine postgres \
     --allocated-storage 100 \
     --master-username admin \
     --storage-encrypted
   ```

**Deliverables**:
- GitOps repository created
- Branch strategy configured
- PostgreSQL provisioned

**Acceptance Criteria**:
- ✅ Repository accessible
- ✅ Database operational
- ✅ Connection strings secured

---

#### Day 3: Monitoring & Validation

**Tasks**:
1. **Configure Monitoring** (4h)
   ```yaml
   # Add Redis metrics to Prometheus
   - Redis memory usage
   - Redis hit rate
   - Redis connection count
   - Redis eviction rate
   ```

2. **Infrastructure Validation** (4h)
   - Test Redis connectivity from all environments
   - Validate PostgreSQL connection
   - Test GitOps repository access
   - Verify security configurations

**Deliverables**:
- Monitoring configured
- Infrastructure validated
- Runbook created

**Acceptance Criteria**:
- ✅ All infrastructure components operational
- ✅ Monitoring collecting metrics
- ✅ Access documented

---

### Sprint 1: Multi-Layer Caching Implementation (Week 1-2: Days 4-10)

#### Day 4: L1 In-Memory Cache & Cache Warming

**Objective**: Implement L1 cache with warming strategy

**Tasks**:
1. **Implement L1 Cache with Warming** (`backend/app/cache/l1_cache.py`)
   ```python
   from functools import lru_cache
   from contextvars import ContextVar
   from typing import Dict, Any, Optional
   import hashlib
   import json

   # Context variable for request-scoped cache
   request_cache: ContextVar[Dict[str, Any]] = ContextVar('request_cache', default={})

   class L1Cache:
       """In-memory cache for deduplicating queries within a single request."""

       @staticmethod
       def _generate_key(source: str, params: Dict) -> str:
           """Generate cache key from source and parameters."""
           key_dict = {"source": source, **params}
           key_str = json.dumps(key_dict, sort_keys=True)
           return hashlib.sha256(key_str.encode()).hexdigest()

       async def get(self, source: str, params: Dict) -> Optional[Any]:
           """Get cached result for current request."""
           cache = request_cache.get()
           key = self._generate_key(source, params)
           return cache.get(key)

       async def set(self, source: str, params: Dict, value: Any) -> None:
           """Cache result for current request."""
           cache = request_cache.get()
           key = self._generate_key(source, params)
           cache[key] = value
           request_cache.set(cache)

       async def clear(self) -> None:
           """Clear cache for current request."""
           request_cache.set({})

       def get_stats(self) -> Dict[str, int]:
           """Get cache statistics for current request."""
           cache = request_cache.get()
           return {
               "hits": sum(1 for v in cache.values() if v is not None),
               "size": len(cache)
           }

   class CacheWarmer:
       """Background cache warmer to prevent cold starts."""

       def __init__(self, l2_cache: L2CacheManager):
           self.l2_cache = l2_cache
           self.warming_queue: asyncio.Queue = None

       async def warm_cache(self, project: str):
           """Warm cache for project with critical data."""
           # Pre-fetch health endpoints
           # Pre-fetch active alerts
           # Pre-fetch pod status
           pass

       async def start_warming_service(self):
           """Start background warming service."""
           while True:
               # Warm all active projects
               # Sleep for 5 minutes
               await asyncio.sleep(300)
   ```

2. **Single Flight Pattern** (Prevent cache stampede)
   ```python
   class SingleFlight:
       """Ensure only one request for in-flight data."""

       def __init__(self):
           self.in_flight: Dict[str, asyncio.Event] = {}

       async def execute(self, key: str, func: Callable) -> Any:
           """Execute with single flight guarantee."""
           if key in self.in_flight:
               await self.in_flight[key].wait()
               result = await self.cache.get(key)
               return result

           self.in_flight[key] = asyncio.Event()

           try:
               result = await func()
               await self.cache.set(key, result)
               return result
           finally:
               self.in_flight[key].set()
               del self.in_flight[key]
   ```

**Deliverables**:
- L1 cache implementation
- Cache warming service
- Single flight pattern
- Unit tests

**Acceptance Criteria**:
- ✅ L1 cache prevents duplicate queries
- ✅ Cache warming prevents cold starts
- ✅ Single flight prevents stampede
- ✅ Unit tests passing

---

#### Day 5: L2 Redis Cache with Enhanced Features

**Objective**: Implement L2 cache with improved features

**Tasks**:
1. **Enhanced L2 Cache Manager** (`backend/app/cache/l2_cache.py`)
   ```python
   from typing import Optional, Any, Dict, List
   from datetime import timedelta

   class L2CacheManager:
       """Redis-based cache manager with intelligent TTL."""

       TTL_CONFIG = {
           "health": 60,           # 1 minute for health checks
           "metrics": 300,         # 5 minutes for metrics
           "pod_status": 180,      # 3 minutes for pod status
           "alerts": 120,          # 2 minutes for alerts
           "overview": 300,        # 5 minutes for overview
           "triage_card": 600,     # 10 minutes for triage cards
           "semantic": 86400       # 24 hours for semantic cache
       }

       def __init__(self, redis_client: RedisCache):
           self.redis = redis_client
           self.stats = {"hits": 0, "misses": 0}

       def _get_key(self, prefix: str, identifier: Dict) -> str:
           """Generate Redis key with prefix and identifier."""
           parts = [prefix]
           for k, v in sorted(identifier.items()):
               parts.append(f"{k}:{v}")
           return ":".join(parts)

       async def get(
           self,
           data_type: str,
           identifier: Dict
       ) -> Optional[Any]:
           """Get cached data by type and identifier."""
           key = self._get_key(data_type, identifier)
           value = await self.redis.get(key)

           if value is not None:
               self.stats["hits"] += 1
               return value

           self.stats["misses"] += 1
           return None

       async def set(
           self,
           data_type: str,
           identifier: Dict,
           value: Any,
           ttl_override: Optional[int] = None
       ) -> bool:
           """Cache data with type-specific TTL."""
           key = self._get_key(data_type, identifier)
           ttl = ttl_override or self.TTL_CONFIG.get(data_type, 300)
           return await self.redis.set(key, value, ttl)

       async def invalidate(
           self,
           data_type: str,
           identifier: Optional[Dict] = None
       ) -> int:
           """Invalidate cache entries."""
           if identifier:
               key = self._get_key(data_type, identifier)
               return await self.redis.delete(key)
           else:
               pattern = self._get_key(data_type, {})
               return await self.redis.delete_pattern(f"{pattern}*")

       def get_hit_rate(self) -> float:
           """Calculate cache hit rate."""
           total = self.stats["hits"] + self.stats["misses"]
           return self.stats["hits"] / total if total > 0 else 0.0
   ```

2. **Redis Sentinel Integration**
   ```python
   class RedisSentinelManager:
       """Manage Redis Sentinel for high availability."""

       def __init__(self, sentinel_hosts: List[str]):
           self.sentinel_hosts = sentinel_hosts
           self.master = None

       async def get_master(self) -> str:
           """Get current master address."""
           # Query Sentinel for master
           # Return master address
           pass

       async def check_failover(self) -> bool:
           """Check if failover occurred."""
           # Query Sentinel for master status
           # Compare with known master
           pass
   ```

**Deliverables**:
- Enhanced L2 cache manager
- Redis Sentinel integration
- Connection pooling

**Acceptance Criteria**:
- ✅ Redis caching functional
- ✅ TTL configuration working
- ✅ Cache invalidation functional
- ✅ Hit rate tracking accurate
- ✅ Sentinel failover supported

---

#### Day 6: L3 Semantic Cache Implementation

**Objective**: Implement pattern-based semantic caching

**Tasks**:
1. **L3 Semantic Cache** (`backend/app/cache/l3_cache.py`)
   ```python
   from typing import Dict, Any, List, Optional
   from datetime import datetime, timedelta
   import hashlib
   import json

   class SemanticCache:
       """Pattern-based semantic caching for similar incidents."""

       def __init__(self, redis_client: RedisCache):
           self.redis = redis_client

       def _generate_semantic_key(
           self,
           incident_type: str,
           patterns: List[str]
       ) -> str:
           """Generate semantic key from incident type and patterns."""
           # Sort patterns for consistency
           patterns_sorted = sorted(patterns)

           # Create semantic signature
           signature = f"{incident_type}:{','.join(patterns_sorted)}"

           # Hash for key
           return f"semantic:{incident_type}:{hashlib.sha256(signature.encode()).hexdigest()[:16]}"

       async def get(
           self,
           incident_type: str,
       patterns: List[str]
       ) -> Optional[Dict[str, Any]]:
           """Get cached result for semantic pattern."""
           key = self._generate_semantic_key(incident_type, patterns)
           result = await self.redis.get(key)

           if result:
               # Check if patterns match sufficiently (>70%)
               cached_patterns = result.get("patterns", [])
               match_score = self._calculate_pattern_match(patterns, cached_patterns)

               if match_score > 0.7:
                   result["match_score"] = match_score
                   result["semantic_hit"] = True
                   return result

           return None

       async def set(
           self,
           incident_type: str,
           patterns: List[str],
           analysis: Dict[str, Any],
           ttl: int = 86400  # 24 hours
       ) -> bool:
           """Cache analysis with semantic patterns."""
           key = self._generate_semantic_key(incident_type, patterns)

           value = {
               "incident_type": incident_type,
               "patterns": patterns,
               "analysis": analysis,
               "cached_at": datetime.now().isoformat()
           }

           return await self.redis.set(key, value, ttl)

       def _calculate_pattern_match(
           self,
           patterns1: List[str],
           patterns2: List[str]
       ) -> float:
           """Calculate pattern match score (0-1)."""
           if not patterns1 or not patterns2:
               return 0.0

           # Convert to sets
           set1 = set(patterns1)
           set2 = set(patterns2)

           # Jaccard similarity
           intersection = len(set1.intersection(set2))
           union = len(set1.union(set2))

           return intersection / union if union > 0 else 0.0

       async def find_similar(
           self,
           incident_type: str,
       patterns: List[str],
           threshold: float = 0.5
       ) -> List[Dict[str, Any]]:
           """Find semantically similar cached incidents."""
           # Scan semantic keys for incident type
           pattern = f"semantic:{incident_type}:*"
           keys = await self.redis.keys(pattern)

           similar = []
           for key in keys:
               cached = await self.redis.get(key)
               if cached:
                   match_score = self._calculate_pattern_match(
                       patterns,
                       cached.get("patterns", [])
                   )

                   if match_score >= threshold:
                       cached["match_score"] = match_score
                       similar.append(cached)

           # Sort by match score
           similar.sort(key=lambda x: x["match_score"], reverse=True)

           return similar[:5]  # Return top 5
   ```

2. **Pattern Extraction**
   ```python
   class PatternExtractor:
       """Extract semantic patterns from incidents."""

       def extract_patterns(
           self,
           incident: Dict[str, Any]
       ) -> List[str]:
           """Extract key patterns from incident."""
           patterns = []

           # Extract from error messages
           if "error" in incident:
               patterns.extend(self._extract_error_patterns(incident["error"]))

           # Extract from affected services
           if "services" in incident:
               patterns.extend([f"service:{s}" for s in incident["services"]])

           # Extract from metrics
           if "metrics" in incident:
               patterns.extend(self._extract_metric_patterns(incident["metrics"]))

           # Extract from time patterns
           if "timestamp" in incident:
               patterns.append(self._extract_time_pattern(incident["timestamp"]))

           return list(set(patterns))  # Deduplicate
   ```

**Deliverables**:
- L3 semantic cache implementation
- Pattern extraction logic
- Similarity matching
- Unit tests

**Acceptance Criteria**:
- ✅ Semantic keys generated correctly
- ✅ Pattern matching functional (>70% threshold)
- ✅ Similar incidents found accurately
- ✅ TTL configurable (1-24 hours)

---

#### Day 7: Enhanced Cache Invalidation

**Objective**: Implement improved cache invalidation with Redis-backed tag index

**Tasks**:
1. **Enhanced Cache Invalidation** (`backend/app/cache/invalidation.py`)
   ```python
   from enum import Enum
   from typing import List, Dict
   import json

   class InvalidationStrategy(Enum):
       TIME_BASED = "time_based"           # TTL expiration
       EVENT_BASED = "event_based"        # On specific events
       TAG_BASED = "tag_based"            # Cache tagging (Redis-backed)
       SELECTIVE = "selective"            # Selective invalidation

   class CacheInvalidator:
       """Manage cache invalidation strategies with Redis backing."""

       TAG_INDEX_PREFIX = "tag_index"

       def __init__(self, redis_client: RedisCache):
           self.redis = redis_client

       async def set_with_tags(
           self,
           data_type: str,
           identifier: Dict,
           value: Any,
           tags: List[str],
           ttl: int
       ) -> bool:
           """Set cache with tags for group invalidation."""
           key = self.l2_cache._get_key(data_type, identifier)
           result = await self.l2_cache.set(data_type, identifier, value, ttl)

           # Index by tags in Redis (not in-memory)
           for tag in tags:
               tag_key = f"{self.TAG_INDEX_PREFIX}:{tag}"
               await self.redis.sadd(tag_key, key)
               # Set TTL on tag index
               await self.redis.expire(tag_key, ttl + 60)  # Keep longer than cache

           return result

       async def invalidate_by_tag(self, tag: str) -> int:
           """Invalidate all cache entries with a tag."""
           tag_key = f"{self.TAG_INDEX_PREFIX}:{tag}"

           # Get all keys for this tag
           keys = await self.redis.smembers(tag_key)

           if not keys:
               return 0

           # Delete all cached keys
           count = 0
           for key in keys:
               count += await self.redis.delete(key)

           # Clear tag index
           await self.redis.delete(tag_key)

           return count

       async def invalidate_on_deployment(
           self,
           project: str,
           service: str
       ) -> int:
           """Invalidate cache when deployment occurs."""
           tags = [f"project:{project}", f"service:{service}"]
           total = 0
           for tag in tags:
               total += await self.invalidate_by_tag(tag)
           return total

       async def invalidate_on_config_change(
           self,
           project: str,
           config_type: str
       ) -> int:
           """Invalidate cache when config changes."""
           return await self.invalidate_by_tag(f"config:{project}:{config_type}")

       async def get_tag_stats(self) -> Dict[str, int]:
           """Get statistics about tag index."""
           # Scan all tag index keys
           pattern = f"{self.TAG_INDEX_PREFIX}:*"
           tag_keys = await self.redis.keys(pattern)

           stats = {}
           for tag_key in tag_keys:
               tag_name = tag_key.split(":")[-1]
               member_count = await self.redis.scard(tag_key)
               stats[tag_name] = member_count

           return stats
   ```

2. **Webhook Integration with Retry**
   ```python
   # backend/app/api/v1/webhooks.py
   from fastapi import APIRouter, BackgroundTasks, HTTPException
   import asyncio

   @router.post("/webhooks/deployment")
   async def on_deployment(
       payload: DeploymentEvent,
       background_tasks: BackgroundTasks
   ):
       """Handle deployment webhook and invalidate relevant cache."""
       try:
           background_tasks.add_task(
               cache_invalidator.invalidate_on_deployment,
               project=payload.project,
               service=payload.service
           )
           return {"status": "cache_invalidation_scheduled"}
       except Exception as e:
           logger.error(f"Deployment webhook error: {e}")
           raise HTTPException(status_code=500, detail=str(e))

   @router.post("/webhooks/config_change")
   async def on_config_change(
       payload: ConfigChangeEvent,
       background_tasks: BackgroundTasks
   ):
       """Handle config change webhook."""
       background_tasks.add_task(
           cache_invalidator.invalidate_on_config_change,
           project=payload.project,
           config_type=payload.config_type
       )
       return {"status": "cache_invalidation_scheduled"}
   ```

**Deliverables**:
- Redis-backed cache invalidation
- Enhanced webhook integration
- Tag statistics endpoint
- Unit tests

**Acceptance Criteria**:
- ✅ Tag index stored in Redis
- ✅ Tag-based invalidation working
- ✅ Webhooks trigger invalidation
- ✅ Multiple tags supported
- ✅ Invalidation stats tracked

---

#### Day 8: Cache Middleware & Integration

**Objective**: Complete caching layer integration

**Tasks**:
1. **Enhanced Cache Middleware** (`backend/app/cache/cache_middleware.py`)
   ```python
   from fastapi import Request, Response
   from starlette.middleware.base import BaseHTTPMiddleware
   import time

   class CacheMiddleware(BaseHTTPMiddleware):
       """Middleware to inject cache manager into requests."""

       def __init__(self, app, l2_cache: L2CacheManager):
           super().__init__(app)
           self.l2_cache = l2_cache

       async def dispatch(self, request: Request, call_next):
           # Inject cache into request state
           request.state.l1_cache = L1Cache()
           request.state.l2_cache = self.l2_cache

           # Record start time
           start_time = time.time()

           response = await call_next(request)

           # Calculate processing time
           process_time = time.time() - start_time

           # Add cache stats to response headers
           hit_rate = self.l2_cache.get_hit_rate()
           response.headers["X-Cache-Hit-Rate"] = f"{hit_rate:.2f}"
           response.headers["X-Process-Time"] = f"{process_time:.3f}"

           # Add cache layer indicator
           cache_layers = []
           if response.headers.get("X-L1-Cache") == "hit":
               cache_layers.append("L1")
           if response.headers.get("X-L2-Cache") == "hit":
               cache_layers.append("L2")
           if response.headers.get("X-L3-Cache") == "hit":
               cache_layers.append("L3")

           if cache_layers:
               response.headers["X-Cache-Layers"] = ",".join(cache_layers)

           return response
   ```

2. **Cached Overview Service** (`backend/app/services/cached_overview_service.py`)
   ```python
   class CachedOverviewService:
       """Overview service with full caching stack."""

       def __init__(self):
           self.l1_cache = L1Cache()
           self.l2_cache = L2CacheManager(redis_client)
           self.l3_cache = SemanticCache(redis_client)
           self.invalidator = CacheInvalidator(self.l2_cache)
           self.single_flight = SingleFlight()

       async def get_overview(
           self,
           project: str,
           force_refresh: bool = False,
           use_semantic: bool = False
       ):
           """Get overview with multi-layer caching."""

           # L2 Cache check
           if not force_refresh:
               cached = await self.l2_cache.get(
                   "overview",
                   {"project": project}
               )
               if cached:
                   return cached

           # Single flight for concurrent requests
           return await self.single_flight.execute(
               f"overview:{project}",
               lambda: self._fetch_and_cache_overview(project, use_semantic)
           )

       async def _fetch_and_cache_overview(
           self,
           project: str,
           use_semantic: bool
       ) -> Dict[str, Any]:
           """Fetch overview from sources and cache."""
           # Try L3 semantic cache first
           if use_semantic:
               semantic_result = await self.l3_cache.get(
                   "overview",
                   [f"project:{project}"]
               )
               if semantic_result:
                   return semantic_result["analysis"]

           # Gather from sources
           results = await asyncio.gather(
               self._get_es_health(project, self.l1_cache),
               self._get_prom_metrics(project, self.l1_cache),
               self._get_k8s_status(project, self.l1_cache),
               return_exceptions=True
           )

           overview = self._format_overview(results)

           # Cache with tags
           tags = [f"project:{project}", "type:overview"]
           await self.invalidator.set_with_tags(
               "overview",
               {"project": project},
               overview,
               tags,
               ttl=300
           )

           return overview
   ```

**Deliverables**:
- Complete cache middleware
- Cached overview service
- Integration with existing endpoints

**Acceptance Criteria**:
- ✅ All cache layers integrated
- ✅ Middleware injects cache managers
- ✅ Response headers indicate cache hits
- ✅ Single flight prevents stampede

---

#### Day 9-10: Sprint 1 Testing & Documentation

**Objective**: Complete testing and documentation

**Tasks**:
1. **Comprehensive Testing Suite**
   ```python
   # tests/backend/test_cache_layer.py
   import pytest
   from backend.app.cache.l1_cache import L1Cache
   from backend.app.cache.l2_cache import L2CacheManager
   from backend.app.cache.l3_cache import SemanticCache

   class TestCacheLayer:
       """Test suite for multi-layer caching."""

       @pytest.mark.asyncio
       async def test_l1_cache_deduplication(self):
           """Test L1 cache prevents duplicate queries."""
           cache = L1Cache()
           # Implementation...

       @pytest.mark.asyncio
       async def test_l2_cache_hit_rate(self):
           """Test L2 cache hit rate tracking."""
           # Implementation...

       @pytest.mark.asyncio
       async def test_l3_semantic_cache(self):
           """Test L3 semantic caching."""
           # Implementation...

       @pytest.mark.asyncio
       async def test_cache_invalidation(self):
           """Test cache invalidation strategies."""
           # Implementation...

       @pytest.mark.asyncio
       async def test_end_to_end_caching(self):
           """Test full caching stack."""
           # Implementation...

       @pytest.mark.asyncio
       async def test_single_flight(self):
           """Test single flight pattern."""
           # Implementation...

       @pytest.mark.asyncio
       async def test_cache_warming(self):
           """Test cache warming service."""
           # Implementation...
   ```

2. **Performance Benchmarks**
   ```python
   # tests/backend/test_cache_performance.py
   @pytest.mark.performance
   @pytest.mark.asyncio
   async def test_cache_hit_rate_target():
       """Test cache hit rate >70%."""
       # Run 100 requests
       # Calculate hit rate
       # Assert >70%

   @pytest.mark.performance
   @pytest.mark.asyncio
   async def test_latency_reduction():
       """Test latency reduced >50%."""
       # Measure baseline (no cache)
       # Measure with cache
       # Assert >50% reduction
   ```

3. **Documentation**
   - Caching architecture guide
   - API documentation
   - Cache configuration guide
   - Troubleshooting guide

**Deliverables**:
- Complete test suite
- Performance benchmarks
- Documentation complete
- Sprint review presentation

**Acceptance Criteria**:
- ✅ All cache layers functional
- ✅ Integration tests passing
- ✅ Latency reduced by >50%
- ✅ Cache hit rate >70%
- ✅ Documentation complete

---

### Sprint 2: Graceful Degradation & DR Enhancement (Week 3-4: Days 11-17)

#### Day 11-12: Enhanced Priority-Based Data Fetching

**Objective**: Implement priority-based query with hysteresis

**Tasks**:
1. **Priority Configuration System** (`backend/app/degradation/priority_config.py`)
   ```python
   from typing import Dict, Any, List
   from enum import Enum
   from pydantic import BaseModel

   class Priority(Enum):
       P0 = 0  # Critical - Always fetch
       P1 = 1  # High - Fetch if possible
       P2 = 2  # Medium - Fetch if time permits
       P3 = 3  # Low - Best effort only

   class PriorityConfig(BaseModel):
       """Priority configuration for data sources."""
       source_name: str
       priority: Priority
       timeout_ms: int
       retry_count: int
       fallback_to_cache: bool = True

   class PriorityConfigManager:
       """Manage priority configurations."""

       DEFAULT_CONFIGS = {
           "health_endpoints": PriorityConfig(
               source_name="health_endpoints",
               priority=Priority.P0,
               timeout_ms=5000,
               retry_count=3,
               fallback_to_cache=True
           ),
           "active_alerts": PriorityConfig(
               source_name="active_alerts",
               priority=Priority.P0,
               timeout_ms=5000,
               retry_count=3,
               fallback_to_cache=True
           ),
           "pod_status": PriorityConfig(
               source_name="pod_status",
               priority=Priority.P1,
               timeout_ms=3000,
               retry_count=2,
               fallback_to_cache=True
           ),
           "metrics_current": PriorityConfig(
               source_name="metrics_current",
               priority=Priority.P1,
               timeout_ms=3000,
               retry_count=2,
               fallback_to_cache=True
           ),
           "logs_recent": PriorityConfig(
               source_name="logs_recent",
               priority=Priority.P2,
               timeout_ms=1000,
               retry_count=1,
               fallback_to_cache=True
           ),
           "metrics_history": PriorityConfig(
               source_name="metrics_history",
               priority=Priority.P2,
               timeout_ms=1000,
               retry_count=1,
               fallback_to_cache=True
           ),
           "logs_history": PriorityConfig(
               source_name="logs_history",
               priority=Priority.P3,
               timeout_ms=500,
               retry_count=0,
               fallback_to_cache=True
           ),
           "analytics": PriorityConfig(
               source_name="analytics",
               priority=Priority.P3,
               timeout_ms=500,
               retry_count=0,
               fallback_to_cache=True
           )
       }

       def __init__(self, config_path: str):
           self.config_path = config_path
           self.configs: Dict[str, PriorityConfig] = {}
           self._load_configs()

       def _load_configs(self):
           """Load configurations from file."""
           # Load from YAML/JSON
           # Merge with defaults
           pass

       def get_config(self, source_name: str) -> PriorityConfig:
           """Get configuration for source."""
           return self.configs.get(source_name, self.DEFAULT_CONFIGS.get(source_name))

       def update_config(self, source_name: str, config: PriorityConfig):
           """Update configuration for source."""
           self.configs[source_name] = config
           self._save_configs()

       def _save_configs(self):
           """Save configurations to file."""
           # Save to YAML/JSON
           pass
   ```

2. **Priority Data Fetcher with Hysteresis** (`backend/app/degradation/priority_queue.py`)
   ```python
   from typing import Dict, Any, Callable, Awaitable
   import asyncio
   from datetime import datetime, timedelta

   class PriorityDataFetcher:
       """Fetch data based on priority during degradation."""

       def __init__(
           self,
           priority_config: PriorityConfigManager,
           hysteresis_factor: float = 0.1
       ):
           self.config = priority_config
           self.hysteresis = hysteresis_factor  # 10% hysteresis
           self.current_mode: str = "normal"
           self.last_mode_change: datetime = None
           self.mode_change_cooldown: timedelta = timedelta(minutes=5)

       async def fetch_by_priority(
           self,
           fetchers: Dict[str, Callable[[], Awaitable[Any]]],
           total_timeout: int = 10000
       ) -> Dict[str, Any]:
           """Fetch data respecting priorities and timeouts."""

           results = {}
           tasks_by_priority = {
               Priority.P0: [],
               Priority.P1: [],
               Priority.P2: [],
               Priority.P3: []
           }

           # Group tasks by priority
           for name, fetcher in fetchers.items():
               config = self.config.get_config(name)
               if config:
                   tasks_by_priority[config.priority].append((name, fetcher(), config))
               else:
                   # Default to P2
                   tasks_by_priority[Priority.P2].append((name, fetcher(), None))

           # Fetch in priority order
           remaining_timeout = total_timeout

           for priority in Priority:
               tasks = tasks_by_priority[priority]
               if not tasks:
                   continue

               # Calculate timeout for this priority level
               if priority == Priority.P0:
                   priority_timeout = min(5000, remaining_timeout)
               elif priority == Priority.P1:
                   priority_timeout = min(3000, remaining_timeout)
               elif priority == Priority.P2:
                   priority_timeout = min(1000, remaining_timeout)
               else:
                   priority_timeout = min(500, remaining_timeout)

               # Fetch with timeout
               for name, task, config in tasks:
                   try:
                       if config and config.retry_count > 0:
                           # Retry logic
                           result = await self._fetch_with_retry(
                               task,
                               config.retry_count,
                               priority_timeout
                           )
                       else:
                           result = await asyncio.wait_for(
                               task,
                               timeout=priority_timeout / 1000
                           )

                       results[name] = {
                           "status": "success",
                           "data": result,
                           "priority": priority.name,
                           "timeout_ms": priority_timeout
                       }

                   except asyncio.TimeoutError:
                       # Try fallback cache
                       if config and config.fallback_to_cache:
                           cached = await self._get_fallback_cache(name)
                           if cached:
                               results[name] = {
                                   "status": "cached",
                                   "data": cached,
                                   "priority": priority.name,
                                   "cache_age": cached.get("age", "unknown")
                               }
                               continue

                       results[name] = {
                           "status": "timeout",
                           "priority": priority.name,
                           "timeout_ms": priority_timeout
                       }

                   except Exception as e:
                       results[name] = {
                           "status": "error",
                           "error": str(e),
                           "priority": priority.name
                       }

               remaining_timeout -= priority_timeout
               if remaining_timeout <= 0:
                   break

           return results

       async def _fetch_with_retry(
           self,
           task: Awaitable[Any],
           retry_count: int,
           timeout: float
       ) -> Any:
           """Fetch with retry logic."""
           last_error = None

           for attempt in range(retry_count):
               try:
                   return await asyncio.wait_for(task, timeout=timeout / 1000)
               except Exception as e:
                   last_error = e
                   # Exponential backoff
                   await asyncio.sleep(0.1 * (2 ** attempt))

           raise last_error

       async def _get_fallback_cache(self, source_name: str) -> Optional[Any]:
           """Get fallback cached data."""
           # Try L2 cache first
           cached = await self.l2_cache.get(
               "fallback",
               {"source": source_name}
           )

           if cached:
               return cached

           # Try critical cache
           return await self.critical_cache.get_critical_data(
               "global",
               source_name
           )
   ```

**Deliverables**:
- Priority configuration system
- Enhanced priority fetcher with hysteresis
- Retry logic
- Fallback to cache

**Acceptance Criteria**:
- ✅ Priority configuration externalized
- ✅ Hysteresis prevents mode flapping
- ✅ P0 data always fetched
- ✅ Fallback to cache functional
- ✅ Retry logic working

---

#### Day 13-14: Enhanced Critical Data Cache & Degraded Mode

**Objective**: Implement improved critical data caching with auto-refresh

**Tasks**:
1. **Enhanced Critical Data Cache** (`backend/app/degradation/critical_cache.py`)
   ```python
   from typing import Dict, Any, Optional, List
   from datetime import datetime, timedelta
   import asyncio

   class CriticalDataCache:
       """Persistent cache for critical data during outages with auto-refresh."""

       CRITICAL_DATA_TYPES = [
           "health_endpoints",
           "active_alerts",
           "cluster_status",
           "deployment_status",
           "service_topology"
       ]

       def __init__(self, redis_client: RedisCache):
           self.redis = redis_client
           self.long_ttl = 900  # 15 minutes
           self.refresh_interval = 300  # 5 minutes

       async def update_critical_data(
           self,
           project: str,
           data_type: str,
           data: Any
       ) -> bool:
           """Update critical data cache."""
           if data_type not in self.CRITICAL_DATA_TYPES:
               return False

           key = f"critical:{project}:{data_type}"
           value = {
               "data": data,
               "timestamp": datetime.now().isoformat(),
               "status": "fresh",
               "project": project,
               "data_type": data_type
           }

           return await self.redis.set(key, value, self.long_ttl)

       async def get_critical_data(
           self,
           project: str,
           data_type: str,
           allow_stale: bool = True
       ) -> Optional[Dict[str, Any]]:
           """Get cached critical data."""
           key = f"critical:{project}:{data_type}"
           cached = await self.redis.get(key)

           if cached:
               # Check staleness
               timestamp = datetime.fromisoformat(cached["timestamp"])
               age = datetime.now() - timestamp

               if age > timedelta(minutes=10):
                   cached["status"] = "stale"
                   cached["age_minutes"] = age.total_seconds() / 60
                   cached["stale_warning"] = True

                   if not allow_stale:
                       return None

               return cached

           return None

       async def get_all_critical_data(
           self,
           project: str,
           allow_stale: bool = True
       ) -> Dict[str, Any]:
           """Get all available critical data."""
           results = {}
           stale_count = 0

           for data_type in self.CRITICAL_DATA_TYPES:
               data = await self.get_critical_data(project, data_type, allow_stale)
               if data:
                   if data.get("stale_warning"):
                       stale_count += 1
                   results[data_type] = data

           results["_meta"] = {
               "total_types": len(self.CRITICAL_DATA_TYPES),
               "available_types": len(results),
               "stale_types": stale_count,
               "retrieved_at": datetime.now().isoformat()
           }

           return results

       async def start_auto_refresh(
           self,
           project: str,
           refresh_callbacks: Dict[str, Callable]
       ):
           """Start automatic refresh of critical data."""
           while True:
               try:
                   for data_type, callback in refresh_callbacks.items():
                       if data_type in self.CRITICAL_DATA_TYPES:
                           try:
                               # Fetch fresh data
                               fresh_data = await callback()
                               # Update cache
                               await self.update_critical_data(
                                   project,
                                   data_type,
                                   fresh_data
                               )
                           except Exception as e:
                               logger.error(f"Failed to refresh {data_type}: {e}")

                   # Wait for next refresh cycle
                   await asyncio.sleep(self.refresh_interval)

               except asyncio.CancelledError:
                   break
               except Exception as e:
                   logger.error(f"Auto-refresh error: {e}")
                   await asyncio.sleep(60)  # Wait before retry

       async def mark_degraded_mode(
           self,
           project: str,
           reason: str,
           severity: str = "high"
       ) -> None:
           """Mark system as degraded for a project."""
           key = f"degraded:{project}"
           await self.redis.set(
               key,
               {
                   "since": datetime.now().isoformat(),
                   "reason": reason,
                   "severity": severity,
                   "mode": "degraded"
               },
               ttl=3600  # 1 hour
           )

       async def is_degraded(self, project: str) -> bool:
           """Check if project is in degraded mode."""
           key = f"degraded:{project}"
           return await self.redis.exists(key)

       async def get_degraded_status(self, project: str) -> Optional[Dict[str, Any]]:
           """Get degraded status details."""
           key = f"degraded:{project}"
           status = await self.redis.get(key)

           if status:
               since = datetime.fromisoformat(status["since"])
               duration = datetime.now() - since
               status["duration_minutes"] = duration.total_seconds() / 60
               return status

           return None
   ```

2. **Enhanced Degraded Mode Handler**
   ```python
   # backend/app/degradation/degraded_handler.py
   class DegradedModeHandler:
       """Handle operations during degraded mode."""

       def __init__(self, critical_cache: CriticalDataCache):
           self.cache = critical_cache

       async def handle_degraded_request(
           self,
           project: str,
           request_type: str,
           allow_stale: bool = True
       ) -> Dict[str, Any]:
           """Handle request during degraded mode."""

           # Try to get from critical cache
           critical_data = await self.cache.get_all_critical_data(
               project,
               allow_stale
           )

           # Get degraded status
           degraded_status = await self.cache.get_degraded_status(project)

           response = {
               "status": "degraded",
               "message": "Operating in degraded mode with cached data",
               "data": critical_data,
               "degraded_since": degraded_status.get("since") if degraded_status else None,
               "degraded_duration": degraded_status.get("duration_minutes") if degraded_status else None,
               "degraded_reason": degraded_status.get("reason") if degraded_status else "unknown",
               "cache_status": self._analyze_cache_status(critical_data),
               "recommendations": self._generate_recommendations(critical_data)
           }

           return response

       def _analyze_cache_status(self, critical_data: Dict[str, Any]) -> Dict[str, Any]:
           """Analyze cache status."""
           meta = critical_data.get("_meta", {})
           available = meta.get("available_types", 0)
           total = meta.get("total_types", 0)
           stale = meta.get("stale_types", 0)

           availability_pct = (available / total * 100) if total > 0 else 0
           freshness_pct = ((available - stale) / available * 100) if available > 0 else 0

           return {
               "availability_percentage": availability_pct,
               "freshness_percentage": freshness_pct,
               "overall_status": "good" if availability_pct > 80 else "degraded" if availability_pct > 50 else "critical"
           }

       def _generate_recommendations(self, critical_data: Dict[str, Any]) -> List[str]:
           """Generate user recommendations."""
           recommendations = []

           meta = critical_data.get("_meta", {})
           available = meta.get("available_types", 0)
           stale = meta.get("stale_types", 0)

           if available == 0:
               recommendations.append("No cached data available - system may be completely down")
           elif stale > 0:
               recommendations.append(f"{stale} data types are stale - use with caution")

           recommendations.append("Critical services may be affected")
           recommendations.append("Full functionality will be restored shortly")
           recommendations.append("Contact on-call SRE if issues persist")

           return recommendations
   ```

**Deliverables**:
- Enhanced critical data cache
- Auto-refresh service
- Improved degraded mode handler
- Cache status analysis

**Acceptance Criteria**:
- ✅ Critical data cached with 15min TTL
- ✅ Auto-refresh every 5 minutes
- ✅ Stale data clearly indicated
- ✅ Degraded mode status detailed
- ✅ Recommendations generated

---

#### Day 15: On-Call Integration for DR

**Objective**: Integrate with on-call management systems

**Tasks**:
1. **On-Call Integration** (`backend/app/degradation/on_call.py`)
   ```python
   from typing import Dict, Any, List, Optional
   from enum import Enum

   class OncallProvider(Enum):
       PAGER_DUTY = "pager_duty"
       OPSGENIE = "opsgenie"
       VICTOR_OPS = "victor_ops"
       MANUAL = "manual"

   class OncallManager:
       """Manage on-call integration for DR scenarios."""

       def __init__(self, provider: OncallProvider, config: Dict[str, Any]):
           self.provider = provider
           self.config = config
           self.cache = None  # Inject CriticalDataCache

       async def get_current_oncall(
           self,
           escalation_level: int = 1
       ) -> Dict[str, Any]:
           """Get current on-call person."""
           if self.provider == OncallProvider.PAGER_DUTY:
               return await self._get_pagerduty_oncall(escalation_level)
           elif self.provider == OncallProvider.OPSGENIE:
               return await self._get_opsgenie_oncall(escalation_level)
           elif self.provider == OncallProvider.MANUAL:
               return self._get_manual_oncall(escalation_level)
           else:
               return {"error": "Unsupported provider"}

       async def _get_pagerduty_oncall(self, level: int) -> Dict[str, Any]:
           """Get on-call from PagerDuty."""
           # Use PagerDuty API
           # Return: name, phone, email, timezone
           pass

       async def _get_opsgenie_oncall(self, level: int) -> Dict[str, Any]:
           """Get on-call from OpsGenie."""
           # Use OpsGenie API
           pass

       def _get_manual_oncall(self, level: int) -> Dict[str, Any]:
           """Get manual on-call from config."""
           return self.config.get(f"level_{level}", {})

       async def escalate_to_oncall(
           self,
           incident: Dict[str, Any],
           severity: str = "critical"
       ) -> bool:
           """Escalate incident to on-call."""
           oncall = await self.get_current_oncall()

           if not oncall:
               return False

           # Send notification
           await self._send_notification(
               oncall,
               incident,
               severity
           )

           return True

       async def _send_notification(
           self,
           oncall: Dict[str, Any],
           incident: Dict[str, Any],
           severity: str
       ):
           """Send notification to on-call."""
           # Integration with:
           # - Slack
           # - Teams
           # - SMS
           # - Phone call (for critical)
           pass
   ```

2. **Update Emergency Contacts in DR Handler**
   ```python
   # backend/app/degradation/dr_handler.py
   class DRHandler:
       """Handle disaster recovery scenarios."""

       def __init__(
           self,
           critical_cache: CriticalDataCache,
           degraded_handler: DegradedModeHandler,
           oncall_manager: OncallManager
       ):
           self.cache = critical_cache
           self.degraded = degraded_handler
           self.oncall = oncall_manager

       async def _handle_emergency_mode(
           self,
           project: str,
           source_health: Dict[str, bool]
       ) -> Dict[str, Any]:
           """Handle emergency mode with minimal data."""

           critical = await self.cache.get_all_critical_data(project)

           # Get on-call contacts
           oncall_level1 = await self.oncall.get_current_oncall(1)
           oncall_level2 = await self.oncall.get_current_oncall(2)

           return {
               "status": "emergency",
               "message": "CRITICAL: Multiple system failures detected",
               "available_sources": [
                   source for source, available in source_health.items()
                   if available
               ],
               "unavailable_sources": [
                   source for source, available in source_health.items()
                   if not available
               ],
               "cached_critical_data": critical,
               "on_call_contacts": [
                   {
                       "level": 1,
                       "name": oncall_level1.get("name", "Unknown"),
                       "phone": oncall_level1.get("phone", "Unknown"),
                       "email": oncall_level1.get("email", "Unknown")
                   },
                   {
                       "level": 2,
                       "name": oncall_level2.get("name", "Unknown"),
                       "phone": oncall_level2.get("phone", "Unknown"),
                       "email": oncall_level2.get("email", "Unknown")
                   }
               ],
               "recommendations": [
                   "Contact on-call SRE immediately",
                   "Check infrastructure status page",
                   "Review active alerts from cached data",
                   f"Primary on-call: {oncall_level1.get('name', 'Unknown')}"
               ]
           }
   ```

**Deliverables**:
- On-call integration
- PagerDuty/OpsGenie support
- Emergency contacts updated
- Notification system

**Acceptance Criteria**:
- ✅ On-call integration functional
- ✅ Multiple escalation levels
- ✅ Emergency contacts dynamic
- ✅ Notifications sent correctly

---

#### Day 16-17: Sprint 2 Testing & Documentation

**Objective**: Complete DR testing and documentation

**Tasks**:
1. **Enhanced DR Test Suite**
   ```python
   # tests/backend/test_dr_scenarios.py
   import pytest
   from backend.app.degradation.dr_handler import DRMode, DRHandler

   class TestDRScenarios:
       """Test suite for DR scenarios."""

       @pytest.mark.asyncio
       async def test_normal_mode_all_sources_up(self):
           """Test normal mode when all sources available."""
           # All sources healthy
           # Verify: NORMAL mode, full data returned

       @pytest.mark.asyncio
       async def test_degraded_mode_half_sources_down(self):
           """Test degraded mode with 50% sources down."""
           # Half sources down
           # Verify: DEGRADED mode, cached data used

       @pytest.mark.asyncio
       async def test_emergency_mode_most_sources_down(self):
           """Test emergency mode with most sources down."""
           # Most sources down
           # Verify: EMERGENCY mode, minimal data

       @pytest.mark.asyncio
       async def test_mode_transition_with_hysteresis(self):
           """Test mode transitions with hysteresis."""
           # Test mode flapping prevention
           # Verify: Hysteresis prevents rapid transitions

       @pytest.mark.asyncio
       async def test_critical_cache_auto_refresh(self):
           """Test critical cache auto-refresh."""
           # Test refresh every 5 minutes
           # Verify: Data stays fresh

       @pytest.mark.asyncio
       async def test_on_call_escalation(self):
           """Test on-call escalation."""
           # Test PagerDuty integration
           # Verify: Correct on-call contacted

       @pytest.mark.asyncio
       async def test_source_recovery(self):
           """Test recovery when source comes back online."""
           # Source down, then recovers
           # Verify: Mode transitions correctly
   ```

2. **Safe Chaos Engineering**
   ```python
   # tests/backend/chaos_engineering.py
   import os
   from enum import Enum

   class Environment(Enum):
       DEV = "development"
       STAGING = "staging"
       PRODUCTION = "production"

   class ChaosEngineering:
       """Chaos engineering tests for DR validation."""

       def __init__(self, current_env: Environment):
           self.env = current_env

       def _validate_environment(self):
           """Ensure chaos tests only run in safe environments."""
           if self.env == Environment.PRODUCTION:
               raise EnvironmentError("Chaos tests not allowed in production")

       async def simulate_elasticsearch_failure(self):
           """Simulate ES failure."""
           self._validate_environment()

           # Block ES port
           # Verify graceful degradation
           # Auto-recover after test
           pass

       async def simulate_prometheus_timeout(self):
           """Simulate Prometheus timeout."""
           self._validate_environment()

           # Add delay to Prometheus
           # Verify timeout handling
           # Auto-recover after test
           pass

       async def simulate_network_partition(self):
           """Simulate network partition."""
           self._validate_environment()

           # Block network
           # Verify emergency mode
           # Auto-recover after test
           pass

       async def run_chaos_suite(self):
           """Run full chaos engineering suite."""
           scenarios = [
               self.simulate_elasticsearch_failure,
               self.simulate_prometheus_timeout,
               self.simulate_network_partition
           ]

           for scenario in scenarios:
               try:
                   await scenario()
               except Exception as e:
                   logger.error(f"Chaos scenario failed: {e}")
                   # Continue with next scenario
   ```

**Deliverables**:
- Complete DR test suite
- Safe chaos engineering framework
- Updated DR runbook
- Sprint review presentation

**Acceptance Criteria**:
- ✅ All DR scenarios tested
- ✅ Mode transitions validated
- ✅ Cache behavior verified
- ✅ Recovery tested
- ✅ Chaos engineering safe

---

### Sprint 3: Performance Optimization (Week 5-6: Days 18-24)

#### Day 18-19: Enhanced Query Optimization

**Objective**: Complete query optimization library

**Tasks**:
1. **Query Optimization Library** (`backend/app/optimization/query_optimizer.py`)
   ```python
   from typing import Dict, Any, List, Optional
   from datetime import datetime, timedelta
   import time

   class QueryOptimizer:
       """Optimize queries to data sources."""

       def __init__(self, es_client, prom_client):
           self.es = es_client
           self.prom = prom_client
           self.profiler = QueryProfiler()

       async def get_logs_optimized(
           self,
           project: str,
           time_range: timedelta,
           filters: Optional[Dict[str, Any]] = None
       ) -> List[Dict]:
           """Optimized log query with chunking and caching."""
           # Calculate optimal chunk size
           chunk_size = self._calculate_optimal_chunk_size(time_range)

           # Split time range
           chunks = self._split_time_range(time_range, chunk_size)

           all_logs = []
           for chunk in chunks:
               # Check cache first
               cached = await self.l2_cache.get(
                   "logs",
                   {
                       "project": project,
                       "start": chunk["start"],
                       "end": chunk["end"],
                       "filters": filters
                   }
               )

               if cached:
                   all_logs.extend(cached)
                   continue

               # Profile and execute query
               logs = await self.profiler.profile_query(
                   "elasticsearch",
                   "get_logs_optimized",
                   lambda: self._execute_es_query(project, chunk, filters)
               )

               all_logs.extend(logs)

               # Cache chunk
               await self.l2_cache.set(
                   "logs",
                   {
                       "project": project,
                       "start": chunk["start"],
                       "end": chunk["end"],
                       "filters": filters
                   },
                   logs,
                   ttl=300
               )

           return all_logs

       def _calculate_optimal_chunk_size(self, time_range: timedelta) -> timedelta:
           """Calculate optimal chunk size based on time range."""
           total_minutes = int(time_range.total_seconds() / 60)

           if total_minutes <= 15:
               return timedelta(minutes=5)
           elif total_minutes <= 60:
               return timedelta(minutes=15)
           elif total_minutes <= 1440:  # 1 day
               return timedelta(minutes=30)
           else:
               return timedelta(hours=1)

       def _split_time_range(
           self,
           time_range: timedelta,
           chunk_size: timedelta
       ) -> List[Dict[str, datetime]]:
           """Split time range into cacheable chunks."""
           chunks = []
           end = datetime.now()
           start = end - time_range

           current_start = start
           while current_start < end:
               current_end = min(current_start + chunk_size, end)

               chunks.append({
                   "start": current_start,
                   "end": current_end
               })

               current_start = current_end

           return chunks

       async def get_metrics_optimized(
           self,
           project: str,
           metric_name: str,
           time_range: timedelta,
           aggregation: str = "avg"
       ) -> List[Dict]:
           """Optimized metrics query with recording rules."""

           # Check if we have pre-computed recording rules
           if self._has_recording_rule(metric_name, aggregation):
               return await self._query_recording_rule(
                   project,
                   metric_name,
                   time_range,
                   aggregation
               )

           # Fall back to regular query
           return await self._query_prometheus_optimized(
               project,
               metric_name,
               time_range,
               aggregation
           )

       def _has_recording_rule(self, metric_name: str, aggregation: str) -> bool:
           """Check if recording rule exists."""
           # Check configured recording rules
           return False

       async def _query_prometheus_optimized(
           self,
           project: str,
           metric_name: str,
           time_range: timedelta,
           aggregation: str
       ) -> List[Dict]:
           """Execute optimized Prometheus query."""
           # Use lower resolution for longer time ranges
           step = self._calculate_step(time_range)

           query = self._build_promql_query(
               metric_name,
               aggregation,
               step
           )

           return await self.prom.query_range(
               query,
               time_range,
               step
           )

       def _calculate_step(self, time_range: timedelta) -> str:
           """Calculate appropriate step for time range."""
           total_minutes = int(time_range.total_seconds() / 60)

           if total_minutes <= 60:
               return "1m"
           elif total_minutes <= 1440:  # 1 day
               return "5m"
           elif total_minutes <= 4320:  # 3 days
               return "15m"
           else:
               return "1h"

       def _build_promql_query(
           self,
           metric_name: str,
           aggregation: str,
           step: str
       ) -> str:
           """Build optimized PromQL query."""
           # Build query with appropriate aggregation
           return f'{aggregation}(rate({metric_name}[{step}]))'
   ```

2. **Common Query Patterns**
   ```python
   class QueryPatterns:
       """Library of common optimized query patterns."""

       @staticmethod
       def high_error_rate_threshold(threshold: float = 0.05) -> str:
           """Query for high error rate."""
           return f'rate(errors_total[5m]) / rate(requests_total[5m]) > {threshold}'

       @staticmethod
       def high_latency_threshold(percentile: float = 0.95, threshold: float = 1.0) -> str:
           """Query for high latency."""
           return f'histogram_quantile({percentile}, rate(http_request_duration_seconds_bucket[5m])) > {threshold}'

       @staticmethod
       def low_cpu_alert(threshold: float = 0.2) -> str:
           """Query for unusually low CPU."""
           return f'rate(process_cpu_seconds_total[5m]) < {threshold}'

       @staticmethod
       def pod_crashloop_detect() -> str:
           """Detect pods in crash loop."""
           return 'increase(kube_pod_container_status_restarts_total[1h]) > 5'
   ```

**Deliverables**:
- Complete query optimizer
- Common query patterns
- Chunking strategies
- Recording rule integration

**Acceptance Criteria**:
- ✅ Slow queries identified
- ✅ Optimizations implemented
- ✅ Chunking functional
- ✅ Query patterns documented

---

#### Day 20: Enhanced Response Time Optimization

**Objective**: Complete response time optimization with streaming

**Tasks**:
1. **Enhanced Response Optimizer** (`backend/app/optimization/response_optimizer.py`)
   ```python
   from typing import Dict, Any, List, Optional
   import asyncio
   from concurrent.futures import ThreadPoolExecutor

   class ResponseTimeOptimizer:
       """Optimize response times through various techniques."""

       def __init__(self, l1_cache: L1Cache, l2_cache: L2CacheManager):
           self.l1 = l1_cache
           self.l2 = l2_cache
           self.executor = ThreadPoolExecutor(max_workers=10)

       async def optimize_overview_response(
           self,
           project: str,
           timeout: int = 2000
       ) -> Dict[str, Any]:
           """Optimize overview response time."""

           start_time = time.time()

           # Strategy 1: Try L2 cache first
           cached = await self.l2.get("overview", {"project": project})
           if cached:
               return {
                   **cached,
                   "_cache": "L2_HIT",
                   "_total_time_ms": (time.time() - start_time) * 1000
               }

           # Strategy 2: Parallel fetch with timeout
           tasks = {
               "health": self._get_health_cached(project),
               "metrics": self._get_metrics_cached(project),
               "pods": self._get_pods_cached(project)
           }

           # Use asyncio.wait with timeout
           done, pending = await asyncio.wait(
               [asyncio.create_task(v) for k, v in tasks.items()],
               timeout=timeout / 1000
           )

           # Cancel pending tasks
           for task in pending:
               task.cancel()

           # Collect results
           results = {}
           for task in done:
               try:
                   result = task.result()
                   results.update(result)
               except Exception as e:
                   logger.error(f"Task error: {e}")

           # Add partial data indicator
           if len(pending) > 0:
               results["_partial"] = True
               results["_complete_sources"] = len(done)
               results["_total_sources"] = len(tasks)
               results["_skipped_sources"] = [k for k, v in tasks.items() if asyncio.create_task(v) in pending]

           # Cache partial results
           if results:
               await self.l2.set(
                   "overview",
                   {"project": project},
                   results,
                   ttl=60  # Shorter TTL for partial results
               )

           results["_total_time_ms"] = (time.time() - start_time) * 1000

           return results

       async def _get_health_cached(self, project: str) -> Dict:
           """Get health with caching."""
           cached = await self.l2.get("health", {"project": project})
           if cached:
               return {"health": cached, "_cache": "L2_HIT"}

           # Fetch from source
           health = await self._fetch_health(project)

           # Cache with short TTL
           await self.l2.set("health", {"project": project}, health, ttl=60)

           return {"health": health, "_cache": "MISS"}

       # Similar methods for metrics and pods...
   ```

2. **Advanced Streaming Response**
   ```python
   # backend/app/api/v1/streaming.py
   from fastapi import APIRouter
   from fastapi.responses import StreamingResponse
   import json

   @router.get("/streaming/logs")
   async def get_logs_streaming(
       project: str,
       time_range: str,
       filters: Optional[str] = None
   ):
       """Stream logs for better UX with large datasets."""

       async def generate():
           """Generate streaming response."""
           try:
               # Send initial metadata
               yield f"data: {json.dumps({'type': 'start', 'project': project})}\n\n"

               chunk_count = 0
               total_logs = 0

               # Stream logs in chunks
               async for chunk in get_logs_chunks(project, time_range, filters):
                   chunk_count += 1
                   total_logs += len(chunk.get("logs", []))

                   yield f"data: {json.dumps({'type': 'chunk', 'data': chunk, 'chunk_number': chunk_count})}\n\n"

               # Send completion
               yield f"data: {json.dumps({'type': 'complete', 'total_chunks': chunk_count, 'total_logs': total_logs})}\n\n"

           except Exception as e:
               # Send error
               yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

       return StreamingResponse(
           generate(),
           media_type="text/event-stream",
           headers={
               "Cache-Control": "no-cache",
               "Connection": "keep-alive",
               "X-Accel-Buffering": "no"  # Disable nginx buffering
           }
       )
   ```

**Deliverables**:
- Enhanced response optimizer
- Advanced streaming endpoints
- Timeout optimization
- Partial result handling

**Acceptance Criteria**:
- ✅ P95 response time <1000ms
- ✅ Streaming functional
- ✅ Timeout handling robust
- ✅ Partial data indicator working
- ✅ Partial results cached

---

#### Day 21-22: Connection Pooling & Concurrent Handling

**Objective**: Optimize connection pooling and concurrent request handling

**Tasks**:
1. **Sized Connection Pools** (`backend/app/config/pools.py`)
   ```python
   from aiohttp import TCPConnector
   import httpx
   from typing import Dict, Any
   import asyncio

   class ConnectionPoolSizer:
       """Calculate optimal connection pool sizes."""

       @staticmethod
       def calculate_pool_size(
           target_concurrent_requests: int,
           target_response_time: float,
           avg_query_time: float
       ) -> int:
           """Calculate required pool size."""
           # Formula: pool_size = concurrent_requests * (response_time / query_time)
           # Add 20% buffer
           pool_size = int(target_concurrent_requests * (target_response_time / avg_query_time) * 1.2)

           return min(max(pool_size, 5), 100)  # Between 5 and 100

       @staticmethod
       def get_pool_recommendations() -> Dict[str, Dict[str, Any]]:
           """Get pool size recommendations based on load."""
           return {
               "low": {
                   "description": "Low traffic (<100 req/min)",
                   "concurrent_requests": 10,
                   "target_response_time": 0.5,
                   "elasticsearch_pool": 5,
                   "prometheus_pool": 5,
                   "kubernetes_pool": 3
               },
               "medium": {
                   "description": "Medium traffic (100-1000 req/min)",
                   "concurrent_requests": 50,
                   "target_response_time": 0.5,
                   "elasticsearch_pool": 10,
                   "prometheus_pool": 10,
                   "kubernetes_pool": 5
               },
               "high": {
                   "description": "High traffic (>1000 req/min)",
                   "concurrent_requests": 200,
                   "target_response_time": 0.5,
                   "elasticsearch_pool": 20,
                   "prometheus_pool": 20,
                   "kubernetes_pool": 10
               }
           }

   class ConnectionPools:
       """Configure connection pools for optimal performance."""

       def __init__(self, load_profile: str = "medium"):
           self.load_profile = load_profile
           self.sizer = ConnectionPoolSizer()
           self.pools = {}

       def get_elasticsearch_pool(self) -> TCPConnector:
           """Get Elasticsearch connection pool."""
           recommendations = self.sizer.get_pool_recommendations()
           pool_size = recommendations[self.load_profile]["elasticsearch_pool"]

           return TCPConnector(
               limit=pool_size * 2,        # Total connections
               limit_per_host=pool_size,   # Per host
               ttl_dns_cache=300,         # DNS cache 5min
               keepalive_timeout=30,
               enable_cleanup_closed=True
           )

       def get_prometheus_pool(self) -> httpx.AsyncHTTPTransport:
           """Get Prometheus HTTP client pool."""
           recommendations = self.sizer.get_pool_recommendations()
           pool_size = recommendations[self.load_profile]["prometheus_pool"]

           return httpx.AsyncHTTPTransport(
               limits=httpx.Limits(
                   max_connections=pool_size * 2,
                   max_keepalive_connections=pool_size
               ),
               retries=3,
               timeout=httpx.Timeout(10.0, connect=5.0)
           )

       def get_pool_metrics(self) -> Dict[str, Any]:
           """Get pool utilization metrics."""
           metrics = {}
           for name, pool in self.pools.items():
               metrics[name] = {
                   "size": pool.size if hasattr(pool, 'size') else 'unknown',
                   "active": pool.active if hasattr(pool, 'active') else 'unknown',
                   "utilization": 'unknown'
               }
           return metrics
   ```

2. **Enhanced Request Pool Manager**
   ```python
   # backend/app/optimization/request_pool.py
   import asyncio
   from typing import Callable, Any, Dict, List, Optional
   from datetime import datetime, timedelta
   from collections import defaultdict

   class RequestBatcher:
       """Batch similar requests together."""

       def __init__(self, batch_window: float = 0.1):
           self.batch_window = batch_window  # 100ms
           self.pending_requests: Dict[str, List] = defaultdict(list)
           self.batch_results: Dict[str, Any] = {}

       async def batch_request(
           self,
           request_key: str,
           func: Callable,
           args: tuple,
           kwargs: Dict[str, Any] = None
       ) -> Any:
           """Batch request with others."""

           if kwargs is None:
               kwargs = {}

           # Add to pending
           future = asyncio.Future()
           self.pending_requests[request_key].append({
               "func": func,
               "args": args,
               "kwargs": kwargs,
               "future": future,
               "timestamp": datetime.now()
           })

           # Wait for batch window
           await asyncio.sleep(self.batch_window)

           # Check if already executed (by another request)
           if request_key in self.batch_results:
               return self.batch_results[request_key]

           # Execute batch
           requests = self.pending_requests.pop(request_key, [])

           if len(requests) == 1:
               # Single request, execute directly
               req = requests[0]
               try:
                   result = await req["func"](*req["args"], **req["kwargs"])
                   req["future"].set_result(result)
                   return result
               except Exception as e:
                   req["future"].set_exception(e)
                   raise
           else:
               # Multiple requests, batch them
               return await self._execute_batch(requests, request_key)

       async def _execute_batch(
           self,
           requests: List[Dict],
           request_key: str
       ) -> List[Any]:
           """Execute batched requests."""
           # Detect request type and batch appropriately
           first_req = requests[0]

           if "elasticsearch" in request_key:
               results = await self._batch_elasticsearch_requests(requests)
           elif "prometheus" in request_key:
               results = await self._batch_prometheus_requests(requests)
           else:
               # No batching support, execute sequentially
               results = []
               for req in requests:
                   try:
                       result = await req["func"](*req["args"], **req["kwargs"])
                       results.append(result)
                       req["future"].set_result(result)
                   except Exception as e:
                       results.append(None)
                       req["future"].set_exception(e)

           # Store result
           self.batch_results[request_key] = results

           return results

       async def _batch_elasticsearch_requests(self, requests: List[Dict]) -> List[Any]:
           """Batch Elasticsearch requests using msearch."""
           # Implementation for Elasticsearch msearch
           pass

       async def _batch_prometheus_requests(self, requests: List[Dict]) -> List[Any]:
           """Batch Prometheus requests."""
           # Implementation for Prometheus batch queries
           pass
   ```

**Deliverables**:
- Sized connection pools
- Pool metrics endpoint
- Request batching
- Load-based configuration

**Acceptance Criteria**:
- ✅ Pool sizes calculated based on load
- ✅ Pool metrics exposed
- ✅ Batching reduces load
- ✅ Pool exhaustion handled gracefully
- ✅ Load profiles configurable

---

#### Day 23-24: Sprint 3 Testing & Validation

**Objective**: Complete performance testing and validation

**Tasks**:
1. **Enhanced Performance Testing**
   ```python
   # tests/backend/test_performance.py
   import pytest
   import time
   import asyncio
   import statistics

   @pytest.mark.performance
   @pytest.mark.asyncio
   async def test_overview_response_time():
       """Validate overview response time < 500ms (P95)."""
       times = []

       for _ in range(100):
           start = time.time()
           result = await get_overview("test-project")
           duration = (time.time() - start) * 1000  # ms
           times.append(duration)

       p95 = statistics.quantiles(times, n=20)[18]  # 95th percentile
       p99 = statistics.quantiles(times, n=100)[98]  # 99th percentile
       avg = statistics.mean(times)

       assert avg < 300, f"Average {avg:.0f}ms exceeds 300ms"
       assert p95 < 1000, f"P95 {p95:.0f}ms exceeds 1000ms"
       assert p99 < 2000, f"P99 {p99:.0f}ms exceeds 2000ms"

   @pytest.mark.performance
   @pytest.mark.asyncio
   async def test_concurrent_requests():
       """Test concurrent request handling."""
       projects = [f"project-{i}" for i in range(100)]

       start = time.time()
       results = await asyncio.gather(
         *[get_overview(p) for p in projects]
       )
       duration = time.time() - start

       success_count = sum(1 for r in results if r is not None)

       assert duration < 30.0, f"100 requests took {duration:.1f}s"
       assert success_count >= 95, f"Only {success_count}/100 successful"

   @pytest.mark.performance
   @pytest.mark.asyncio
   async def test_cache_hit_rate():
       """Test cache hit rate >70%."""
       # Warm up cache
       for _ in range(10):
           await get_overview("cache-test-project")

       # Measure hit rate
       hits = 0
       total = 100

       for _ in range(total):
           result = await get_overview("cache-test-project")
           if result.get("_cache") in ["L1_HIT", "L2_HIT", "L3_HIT"]:
               hits += 1

       hit_rate = hits / total
       assert hit_rate > 0.70, f"Hit rate {hit_rate:.2%} below 70%"
   ```

2. **Load Testing**
   ```python
   # tests/backend/load_test.py
   import asyncio
   import statistics
   from datetime import datetime
   from locust import HttpUser, task, between

   class DevOpsMonitorUser(HttpUser):
       """Load test user simulating real behavior."""

       wait_time = between(1, 3)  # 1-3 seconds between requests

       @task(3)
       def view_overview(self):
           """View overview page (75% of requests)."""
           self.client.get("/api/v1/overview?project=load-test")

       @task(1)
       def view_metrics(self):
           """View metrics (25% of requests)."""
           self.client.get("/api/v1/metrics?project=load-test")

   async def run_load_test_profile(profile: str):
       """Run load test with specific profile."""
       profiles = {
           "baseline": {"users": 10, "spawn_rate": 1, "duration": "1m"},
           "moderate": {"users": 50, "spawn_rate": 5, "duration": "5m"},
           "peak": {"users": 200, "spawn_rate": 10, "duration": "10m"},
           "stress": {"users": 500, "spawn_rate": 50, "duration": "5m"}
       }

       config = profiles[profile]

       # Run locust
       # Collect metrics
       # Validate against SLIs

       return {
           "profile": profile,
           "avg_response_time": avg,
           "p95_response_time": p95,
           "p99_response_time": p99,
           "requests_per_second": rps,
           "error_rate": error_rate,
           "passed": all_metrics_ok
       }
   ```

**Deliverables**:
- Performance validation results
- Load test profiles
- Performance report
- Sprint review presentation

**Acceptance Criteria**:
- ✅ P95 response time <1000ms
- ✅ P99 response time <2000ms
- ✅ Load test passes
- ✅ Concurrent requests handled
- ✅ Cache hit rate >70%
- ✅ No performance regression

---

### Sprint 4: Configuration Management (Week 7: Days 25-31)

#### Day 25-26: Enhanced GitOps Configuration Structure

**Objective**: Complete GitOps structure with all schema definitions

**Tasks**:
1. **Complete Config Repository Structure**
   ```yaml
   configs/
   ├── global/
   │   ├── defaults.yaml          # Global defaults
   │   ├── policies.yaml           # Global policies
   │   ├── priorities.yaml         # Priority configurations
   │   └── schemas/                # Config schemas
   │       ├── project.schema.yaml
   │       ├── alert.schema.yaml
   │       ├── slo.config.schema.yaml
   │       ├── deployment.config.schema.yaml
   │       └── monitoring.config.schema.yaml
   ├── projects/
   │   ├── meinvoice/
   │   │   ├── config.yaml         # Project config
   │   │   ├── alerts.yaml          # Alert rules
   │   │   ├── slos.yaml            # SLO configs
   │   │   └── priorities.yaml      # Project priorities
   │   └── another-project/
   │       └── ...
   ├── versions/
   │   └── v1.0.0/                 # Versioned configs
   └── README.md                    # GitOps documentation
   ```

2. **Complete Schema Definitions**
   ```yaml
   # configs/global/schemas/slo.config.schema.yaml
   type: object
   required: [slo_name, service, objectives]
   properties:
     slo_name:
       type: string
     service:
       type: string
     objectives:
       type: array
       items:
         type: object
         properties:
           name:
             type: string
           target:
             type: number
           window:
             type: object
             properties:
               duration:
                 type: string
               rolling:
                 type: boolean

   # configs/global/schemas/deployment.config.schema.yaml
   type: object
   properties:
     deployment:
       type: object
       properties:
         strategy:
           type: string
           enum: [rolling, blue_green, canary]
         replicas:
           type: object
           properties:
             min:
               type: integer
             max:
               type: integer
             default:
               type: integer
         resources:
           type: object
           properties:
             requests:
               type: object
             limits:
               type: object
     health_checks:
       type: array
       items:
         type: object
         properties:
           name:
             type: string
           path:
             type: string
           interval:
             type: string
           threshold:
             type: integer
   ```

3. **Enhanced Config Validator**
   ```python
   # backend/app/config/validation.py
   from typing import Dict, Any, List, Tuple
   from pydantic import BaseModel, ValidationError
   import yaml
   from jsonschema import validate, ValidationError as JSONSchemaValidationError

   class ConfigValidator:
       """Validate project configurations against schemas."""

       def __init__(self, schema_path: str):
           self.schema_path = schema_path
           self.schemas = self._load_schemas()

       def _load_schemas(self) -> Dict[str, Dict]:
           """Load all schemas."""
           schemas = {}
           schema_files = [
               "project.schema.yaml",
               "alert.schema.yaml",
               "slo.config.schema.yaml",
               "deployment.config.schema.yaml",
               "monitoring.config.schema.yaml"
           ]

           for schema_file in schema_files:
               try:
                   with open(f"{self.schema_path}/{schema_file}") as f:
                       schema_name = schema_file.replace(".schema.yaml", "")
                       schemas[schema_name] = yaml.safe_load(f)
               except FileNotFoundError:
                   pass  # Schema not yet defined

           return schemas

       def validate_config(
           self,
           config_type: str,
           config: Dict[str, Any]
       ) -> Tuple[bool, List[str]]:
           """Validate configuration against schema."""
           errors = []

           if config_type not in self.schemas:
               return False, [f"No schema found for {config_type}"]

           try:
               validate(
                   instance=config,
                   schema=self.schemas[config_type]
               )
           except JSONSchemaValidationError as e:
               errors.append(f"Schema validation failed: {e.message}")

           # Custom validations
           errors.extend(self._custom_validations(config_type, config))

           return len(errors) == 0, errors

       def _custom_validations(self, config_type: str, config: Dict[str, Any]) -> List[str]:
           """Custom business logic validations."""
           errors = []

           if config_type == "project":
               # Validate project config
               project = config.get("project", {})
               if not project.get("name"):
                   errors.append("Project name is required")

               monitoring = config.get("monitoring", {})
               if not monitoring.get("elasticsearch") and not monitoring.get("prometheus"):
                   errors.append("At least one monitoring source must be configured")

           elif config_type == "slo.config":
               # Validate SLO config
               objectives = config.get("objectives", [])
               for obj in objectives:
                   target = obj.get("target", 0)
                   if target <= 0 or target > 100:
                       errors.append(f"SLO target must be between 0 and 100: {obj.get('name')}")

           return errors
   ```

**Deliverables**:
- Complete config structure
- All schema definitions
- Enhanced validator
- Schema documentation

**Acceptance Criteria**:
- ✅ All config types have schemas
- ✅ Validation functional
- ✅ Clear error messages
- ✅ Schema documentation complete

---

#### Day 27-28: Enhanced Versioning & GitOps Workflow

**Objective**: Implement complete versioning with PR workflow

**Tasks**:
1. **Enhanced Version Manager**
   ```python
   # backend/app/config/versioning.py
   from typing import Dict, Any, List, Optional
   from datetime import datetime
   from enum import Enum
   import hashlib
   import json
   from dataclasses import dataclass

   class ChangeType(Enum):
       CREATE = "create"
       UPDATE = "update"
       DELETE = "delete"
       ROLLBACK = "rollback"

   @dataclass
   class ConfigVersion:
       """Configuration version."""
       version: str
       timestamp: datetime
       config: Dict[str, Any]
       checksum: str
       author: str
       message: str
       change_type: ChangeType
       size_bytes: int
       parent_version: Optional[str] = None

   class ConfigVersionManager:
       """Manage configuration versions with Git integration."""

       def __init__(self, storage_path: str, git_ops: GitOpsManager):
           self.storage_path = storage_path
           self.versions_path = f"{storage_path}/versions"
           self.git_ops = git_ops

       async def create_version(
           self,
           project: str,
           config: Dict[str, Any],
           author: str,
           message: str,
           change_type: ChangeType = ChangeType.UPDATE
       ) -> ConfigVersion:
           """Create a new configuration version."""
           # Calculate checksum and size
           config_str = json.dumps(config, sort_keys=True)
           checksum = hashlib.sha256(config_str.encode()).hexdigest()
           size_bytes = len(config_str.encode())

           # Get parent version
           parent = await self._get_latest_version(project)

           # Generate version number
           versions = await self._list_versions(project)
           version_number = len(versions) + 1
           version_id = f"v{version_number}.0.0"

           version = ConfigVersion(
               version=version_id,
               timestamp=datetime.now(),
               config=config,
               checksum=checksum,
               author=author,
               message=message,
               change_type=change_type,
               size_bytes=size_bytes,
               parent_version=parent
           )

           # Save version to storage
           await self._save_version(project, version)

           # Commit to Git
           await self.git_ops.commit_change(
               project,
               author,
               message
           )

           return version

       async def rollback(
           self,
           project: str,
           target_version: str,
           author: str,
           reason: str
       ) -> ConfigVersion:
           """Rollback to a specific version."""
           version = await self._get_version(project, target_version)

           if not version:
               raise ValueError(f"Version {target_version} not found")

           # Create rollback version
           rollback_version = await self.create_version(
               project=project,
               config=version.config,
               author=author,
               message=f"Rollback to {target_version}: {reason}",
               change_type=ChangeType.ROLLBACK
           )

           # Update current config
           await self._update_current_config(project, version.config)

           # Push to Git
           await self.git_ops.push_changes()

           return rollback_version

       async def diff_versions(
           self,
           project: str,
           version_a: str,
           version_b: str
       ) -> Dict[str, Any]:
           """Compare two versions."""
           v_a = await self._get_version(project, version_a)
           v_b = await self._get_version(project, version_b)

           return {
               "version_a": version_a,
               "version_b": version_b,
               "changes": self._calculate_diff(v_a.config, v_b.config),
               "size_change": v_b.size_bytes - v_a.size_bytes,
               "time_delta": (v_b.timestamp - v_a.timestamp).total_seconds()
           }

       def _calculate_diff(
           self,
           config_a: Dict[str, Any],
           config_b: Dict[str, Any]
       ) -> List[Dict[str, Any]]:
           """Calculate differences between configs."""
           from deepdiff import DeepDiff

           diff = DeepDiff(config_a, config_b, ignore_order=True)

           changes = []
           for change_type, items in diff.items():
               if hasattr(items, 'items'):
                   for item in items.items():
                       changes.append({
                           "type": str(change_type),
                           "path": str(item[0]) if item else "root",
                           "old_value": str(item[1].get("old_value")) if change_type != "values_changed" else None,
                           "new_value": str(item[1].get("new_value")) if change_type != "values_changed" else None
                       })
               else:
                   for item in items:
                       if hasattr(item, 'path'):
                           changes.append({
                               "type": str(change_type),
                               "path": item.path(),
                               "value": str(item.t2) if hasattr(item, 't2') else None
                           })

           return changes

       async def _save_version(self, project: str, version: ConfigVersion):
           """Save version to storage."""
           import os
           project_dir = f"{self.versions_path}/{project}"
           os.makedirs(project_dir, exist_ok=True)

           version_file = f"{project_dir}/{version.version}.json"

           with open(version_file, "w") as f:
               json.dump({
                   "version": version.version,
                   "timestamp": version.timestamp.isoformat(),
                   "checksum": version.checksum,
                   "author": version.author,
                   "message": version.message,
                   "change_type": version.change_type.value,
                   "size_bytes": version.size_bytes,
                   "parent_version": version.parent_version,
                   "config": version.config
               }, f, indent=2)

       async def _get_latest_version(self, project: str) -> Optional[str]:
           """Get latest version number."""
           versions = await self._list_versions(project)
           return versions[-1] if versions else None
   ```

2. **GitOps Manager with PR Workflow**
   ```python
   # backend/app/config/gitops.py
   import subprocess
   from typing import Dict, Any, List
   from enum import Enum

   class GitBranch(Enum):
       MAIN = "main"
       DEVELOP = "develop"
       FEATURE = "feature"

   class GitOpsManager:
       """Manage GitOps workflow for configurations."""

       def __init__(self, repo_path: str):
           self.repo_path = repo_path
           self.current_branch = self._get_current_branch()

       def _get_current_branch(self) -> str:
           """Get current Git branch."""
           try:
               result = subprocess.run(
                   ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                   cwd=self.repo_path,
                   capture_output=True,
                   text=True,
                   check=True
               )
               return result.stdout.strip()
           except subprocess.CalledProcessError:
               return "unknown"

       async def create_feature_branch(
           self,
           project: str,
           author: str
       ) -> str:
           """Create a feature branch for config change."""
           branch_name = f"config/{project}/{datetime.now().strftime('%Y%m%d-%H%M%S')}"

           # Checkout and create branch
           subprocess.run(
               ["git", "checkout", "-b", branch_name],
               cwd=self.repo_path,
               check=True
           )

           return branch_name

       async def commit_change(
           self,
           project: str,
           author: str,
           message: str
       ) -> str:
           """Commit configuration change to Git."""
           # Stage changes
           subprocess.run(
               ["git", "add", f"projects/{project}"],
               cwd=self.repo_path,
               check=True
           )

           # Commit with author info
           result = subprocess.run(
               ["git", "commit", "-m", f"[{project}] {message}\n\nAuthor: {author}"],
               cwd=self.repo_path,
               capture_output=True,
               text=True
           )

           return result.stdout.strip()

       async def create_pull_request(
           self,
           project: str,
           branch_name: str,
           title: str,
           description: str
       ) -> str:
           """Create pull request for review."""
           # Use GitHub CLI or similar
           try:
               result = subprocess.run(
                   ["gh", "pr", "create",
                    "--title", title,
                    "--body", description,
                    "--base", "develop"],
                   cwd=self.repo_path,
                   capture_output=True,
                   text=True
               )

               # Extract PR number from output
               pr_url = result.stdout.strip()
               return pr_url
           except subprocess.CalledProcessError:
               # Fallback: manual PR creation instructions
               return f"Manual PR required: {branch_name} -> develop"

       async def merge_pull_request(
           self,
           pr_number: int
       ) -> bool:
           """Merge pull request after approval."""
           try:
               subprocess.run(
                   ["gh", "pr", "merge", str(pr_number), "--squash"],
                   cwd=self.repo_path,
                   check=True
               )
               return True
           except subprocess.CalledProcessError:
               return False

       async def sync_from_git(self, branch: str = "develop") -> List[str]:
           """Sync configurations from Git."""
           # Pull latest changes
           subprocess.run(
               ["git", "pull", "origin", branch],
               cwd=self.repo_path,
               check=True
           )

           # Identify changed projects
           changed = self._get_changed_projects()

           # Reload configurations
           for project in changed:
               await self._reload_project_config(project)

           return changed

       def _get_changed_projects(self) -> List[str]:
           """Get list of changed projects."""
           try:
               result = subprocess.run(
                   ["git", "diff", "--name-only", "develop^..develop"],
                   cwd=self.repo_path,
                   capture_output=True,
                   text=True,
                   check=True
               )

               changed_files = result.stdout.strip().split('\n')
               projects = set()

               for file_path in changed_files:
                   if file_path.startswith("projects/"):
                       project = file_path.split('/')[1]
                       projects.add(project)

               return list(projects)
           except subprocess.CalledProcessError:
               return []

       async def _reload_project_config(self, project: str):
           """Reload project configuration."""
           config_path = f"{self.repo_path}/projects/{project}/config.yaml"

           with open(config_path) as f:
               config = yaml.safe_load(f)

           # Update in-memory config
           # Notify listeners
           pass
   ```

**Deliverables**:
- Enhanced version manager
- GitOps manager with PR workflow
- Branch strategy implementation
- Diff functionality

**Acceptance Criteria**:
- ✅ Versions tracked with metadata
- ✅ Rollback functional
- ✅ Diff calculation accurate
- ✅ PR workflow working
- ✅ Git branch strategy defined

---

#### Day 29: Enhanced Config Security with KMS

**Objective**: Implement security controls with KMS integration

**Tasks**:
1. **Enhanced Config Security with KMS**
   ```python
   # backend/app/config/security.py
   from typing import Dict, Any, List, Optional
   import os
   import boto3
   from botocore.exceptions import ClientError

   class ConfigSecurity:
       """Handle configuration security with KMS integration."""

       SECRET_FIELDS = [
           "password", "api_key", "secret", "token",
           "credentials", "private_key", "access_key",
           "secret_key", "webhook_url"
       ]

       def __init__(self):
           self.encryption_key_id = os.getenv("AWS_KMS_KEY_ID")
           self.kms_client = None

           if self.encryption_key_id:
               try:
                   self.kms_client = boto3.client('kms')
               except Exception as e:
                   logger.warning(f"KMS initialization failed: {e}")

       def sanitize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
           """Sanitize configuration for logging/display."""
           return self._sanitize_recursive(config)

       def _sanitize_recursive(self, obj: Any) -> Any:
           """Recursively sanitize object."""
           if isinstance(obj, dict):
               sanitized = {}
               for key, value in obj.items():
                   if self._is_secret_field(key):
                       sanitized[key] = "***REDACTED***"
                   else:
                       sanitized[key] = self._sanitize_recursive(value)
               return sanitized
           elif isinstance(obj, list):
               return [self._sanitize_recursive(item) for item in obj]
           return obj

       def _is_secret_field(self, field_name: str) -> bool:
           """Check if field contains secret data."""
           field_lower = field_name.lower()
           return any(secret in field_lower for secret in self.SECRET_FIELDS)

       async def encrypt_secrets(
           self,
           config: Dict[str, Any]
       ) -> Dict[str, Any]:
           """Encrypt secret values in configuration."""
           if not self.kms_client:
               logger.warning("KMS not available, returning plain config")
               return config

           return await self._encrypt_recursive(config)

       async def _encrypt_recursive(self, obj: Any) -> Any:
           """Recursively encrypt secrets."""
           if isinstance(obj, dict):
               encrypted = {}
               for key, value in obj.items():
                   if self._is_secret_field(key) and isinstance(value, str):
                       encrypted[key] = await self._encrypt_value(value)
                   else:
                       encrypted[key] = await self._encrypt_recursive(value)
               return encrypted
           elif isinstance(obj, list):
               return [await self._encrypt_recursive(item) for item in obj]
           return obj

       async def _encrypt_value(self, value: str) -> str:
           """Encrypt single value using KMS."""
           try:
               response = self.kms_client.encrypt(
                   KeyId=self.encryption_key_id,
                   Plaintext=value.encode()
               )

               # Return base64 encoded ciphertext
               import base64
               return base64.b64encode(response['CiphertextBlob']).decode()

           except ClientError as e:
               logger.error(f"KMS encrypt error: {e}")
               return value

       async def decrypt_secrets(
           self,
           config: Dict[str, Any]
       ) -> Dict[str, Any]:
           """Decrypt secret values in configuration."""
           if not self.kms_client:
               return config

           return await self._decrypt_recursive(config)

       async def _decrypt_recursive(self, obj: Any) -> Any:
           """Recursively decrypt secrets."""
           if isinstance(obj, dict):
               decrypted = {}
               for key, value in obj.items():
                   if self._is_secret_field(key) and isinstance(value, str):
                       decrypted[key] = await self._decrypt_value(value)
                   else:
                       decrypted[key] = await self._decrypt_recursive(value)
               return decrypted
           elif isinstance(obj, list):
               return [await self._decrypt_recursive(item) for item in obj]
           return obj

       async def _decrypt_value(self, encrypted_value: str) -> str:
           """Decrypt single value using KMS."""
           try:
               import base64
               ciphertext = base64.b64decode(encrypted_value)

               response = self.kms_client.decrypt(
                   KeyId=self.encryption_key_id,
                   CiphertextBlob=ciphertext
               )

               return response['Plaintext'].decode()

           except ClientError as e:
               logger.error(f"KMS decrypt error: {e}")
               return encrypted_value

       def rotate_encryption_key(self, old_key_id: str, new_key_id: str):
           """Rotate encryption key."""
           # Implementation for key rotation
           pass
   ```

2. **Enhanced Audit Logger with Persistence**
   ```python
   # backend/app/config/audit.py
   from typing import Dict, Any, List, Optional
   from datetime import datetime, date
   from enum import Enum
   import json
   import gzip
   import os

   class AuditAction(Enum):
       CONFIG_READ = "config_read"
       CONFIG_CREATE = "config_create"
       CONFIG_UPDATE = "config_update"
       CONFIG_DELETE = "config_delete"
       CONFIG_ROLLBACK = "config_rollback"
       CONFIG_VALIDATION = "config_validation"

   class AuditLogger:
       """Audit logger for configuration changes with rotation."""

       def __init__(self, storage_path: str):
           self.storage_path = storage_path
           self.audit_dir = f"{storage_path}/audit"
           os.makedirs(self.audit_dir, exist_ok=True)
           self.current_log_file = self._get_current_log_file()

       def _get_current_log_file(self) -> str:
           """Get current audit log file."""
           today = date.today().isoformat()
           return f"{self.audit_dir}/audit-{today}.jsonl.gz"

       async def log(
           self,
           action: AuditAction,
           project: str,
           user: str,
           details: Dict[str, Any]
       ):
           """Log configuration action."""
           entry = {
               "timestamp": datetime.now().isoformat(),
               "action": action.value,
               "project": project,
               "user": user,
               "details": self._sanitize_details(details),
               "ip_address": details.get("ip_address"),
               "user_agent": details.get("user_agent"),
               "request_id": details.get("request_id"),
               "result": details.get("result", "success")
           }

           # Append to compressed log file
           self._append_to_log(entry)

           # Rotate if needed
           self._check_rotation()

       def _sanitize_details(self, details: Dict[str, Any]) -> Dict[str, Any]:
           """Sanitize sensitive details."""
           security = ConfigSecurity()
           return security.sanitize_config(details)

       def _append_to_log(self, entry: Dict[str, Any]):
           """Append entry to compressed log file."""
           try:
               with gzip.open(self.current_log_file, 'at') as f:
                   f.write(json.dumps(entry) + '\n')
           except Exception as e:
               logger.error(f"Failed to write audit log: {e}")

       def _check_rotation(self):
           """Check if log rotation is needed."""
           # Rotate if file size > 10MB
           if os.path.exists(self.current_log_file):
               size = os.path.getsize(self.current_log_file)
               if size > 10 * 1024 * 1024:  # 10MB
                   self._rotate_log()

       def _rotate_log(self):
           """Rotate audit log file."""
           # Compress and archive old log
           # Create new log file
           self.current_log_file = self._get_current_log_file()

       async def get_audit_trail(
           self,
           project: str,
           start_date: Optional[date] = None,
           end_date: Optional[date] = None,
           limit: int = 1000
       ) -> List[Dict[str, Any]]:
           """Get audit trail for project."""
           results = []

           # Determine which files to read
           if start_date and end_date:
               files = self._get_files_in_range(start_date, end_date)
           else:
               files = [self.current_log_file]

           # Read and filter
           for file_path in files:
               if not os.path.exists(file_path):
                   continue

               try:
                   with gzip.open(file_path, 'rt') as f:
                       for line in f:
                           entry = json.loads(line.strip())
                           if entry.get("project") == project:
                               results.append(entry)

                               if len(results) >= limit:
                                   return results
               except Exception as e:
                   logger.error(f"Failed to read audit file {file_path}: {e}")

           return results

       def _get_files_in_range(self, start_date: date, end_date: date) -> List[str]:
           """Get audit log files in date range."""
           files = []
           current = start_date

           while current <= end_date:
               file_path = f"{self.audit_dir}/audit-{current.isoformat()}.jsonl.gz"
               if os.path.exists(file_path):
                   files.append(file_path)
               current += timedelta(days=1)

           return files
   ```

**Deliverables**:
- Config security with KMS integration
- Enhanced audit logger with rotation
- Key rotation capability
- Secret encryption at rest

**Acceptance Criteria**:
- ✅ KMS integration functional
- ✅ Secrets encrypted at rest
- ✅ Audit log rotation working
- ✅ All changes audited
- ✅ Audit trail queryable

---

#### Day 30-31: Sprint 4 Testing & Documentation

**Objective**: Complete config management testing

**Tasks**:
1. **Config Management Integration Tests**
   ```python
   # tests/backend/test_config_management.py
   @pytest.mark.integration
   @pytest.mark.asyncio
   async def test_config_lifecycle():
       """Test complete config lifecycle."""
       # 1. Create config
       # 2. Update config
       # 3. Validate versions
       # 4. Rollback config
       # 5. Delete config

   @pytest.mark.asyncio
   async def test_gitops_workflow():
       """Test GitOps workflow."""
       # 1. Create feature branch
       # 2. Commit changes
       # 3. Create PR
       # 4. Merge PR
       # 5. Sync from git

   @pytest.mark.asyncio
   async def test_config_security():
       """Test config security."""
       # 1. Encrypt secrets
       # 2. Decrypt secrets
       # 3. Sanitize config
       # 4. Validate redaction

   @pytest.mark.asyncio
   async def test_audit_trail():
       """Test audit trail."""
       # 1. Log actions
       # 2. Query audit trail
       # 3. Validate rotation
   ```

2. **Documentation**
   - Config management guide
   - GitOps workflow documentation
   - API documentation
   - Security procedures

**Deliverables**:
- Complete config management
- Integration tests
- Documentation complete
- Sprint review presentation

**Acceptance Criteria**:
- ✅ All lifecycle operations functional
- ✅ GitOps workflow working
- ✅ KMS integration functional
- ✅ Security controls active
- ✅ Documentation complete

---

### Sprint 5: Monitoring & Analytics Enhancement (Week 8: Days 32-38)

#### Day 32: Enhanced Metrics with Cardinality Control

**Objective**: Implement metrics with cardinality control

**Tasks**:
1. **Metrics with Cardinality Control**
   ```python
   # backend/app/analytics/optimization_metrics.py
   from prometheus_client import Counter, Histogram, Gauge
   from typing import Dict, Any

   # Cache metrics
   cache_hits = Counter(
       'cache_hits_total',
       'Total cache hits',
       ['cache_level', 'data_type']
   )

   cache_misses = Counter(
       'cache_misses_total',
       'Total cache misses',
       ['cache_level', 'data_type']
   )

   # Cardinality-controlled incident type metrics
   class CardinalityControlledMetrics:
       """Metrics with controlled cardinality."""

       MAX_INCIDENT_TYPES = 20
       OTHER_LABEL = "other"

       def __init__(self):
           self.top_incident_types = set()
           self.incident_type_counts = {}

       def record_incident_type(self, incident_type: str):
           """Record incident type with cardinality control."""
           # Update count
           self.incident_type_counts[incident_type] = \
               self.incident_type_counts.get(incident_type, 0) + 1

           # Update top types
           if len(self.top_incident_types) < self.MAX_INCIDENT_TYPES:
               self.top_incident_types.add(incident_type)
           else:
               # Check if this type should be in top
               min_count = min(
                   self.incident_type_counts.get(t, 0)
                   for t in self.top_incident_types
               )

               if self.incident_type_counts[incident_type] > min_count:
                   # Replace lowest
                   for t in self.top_incident_types:
                   if self.incident_type_counts.get(t, 0) == min_count:
                       self.top_incident_types.remove(t)
                       break
                   self.top_incident_types.add(incident_type)

       def get_normalized_incident_type(self, incident_type: str) -> str:
           """Get normalized incident type for metrics."""
           if incident_type in self.top_incident_types:
               return incident_type
           return self.OTHER_LABEL

   # Use normalized labels
   token_usage = Counter(
       'token_usage_total',
       'Total token usage',
       ['model', 'incident_type_normalized']
   )
   ```

2. **Metrics Collector**
   ```python
   class MetricsCollector:
       """Collect and expose metrics."""

       def __init__(self):
           self.metrics = {
               'cache_hits': cache_hits,
               'cache_misses': cache_misses,
               'degradation_mode': degradation_mode,
               'source_availability': source_availability,
               'response_time': response_time,
               'query_duration': query_duration,
               'cost_savings': cost_savings,
               'cardinality': CardinalityControlledMetrics()
           }

       def record_cache_hit(self, level: str, data_type: str):
           """Record cache hit."""
           self.metrics['cache_hits'].labels(
               cache_level=level,
               data_type=data_type
           ).inc()

       def record_query_duration(self, source: str, query_type: str, duration: float):
           """Record query duration."""
           self.metrics['query_duration'].labels(
               source=source,
               query_type=query_type
           ).observe(duration)

       def record_token_usage(
           self,
           model: str,
           incident_type: str,
       input_tokens: int,
       output_tokens: int
       ):
           """Record token usage with cardinality control."""
           normalized_type = self.metrics['cardinality'].get_normalized_incident_type(incident_type)

           self.metrics['token_usage'].labels(
               model=model,
               incident_type_normalized=normalized_type
           ).inc(input_tokens + output_tokens)
   ```

**Deliverables**:
- Metrics with cardinality control
- Normalized labels
- Cardinality alerts
- Metrics documentation

**Acceptance Criteria**:
- ✅ Cardinality controlled
- ✅ Top 20 incident types tracked
- ✅ "Other" category for long tail
- ✅ Cardinality alerts configured

---

#### Day 33-34: Real-time Analytics with Persistence

**Objective**: Implement real-time analytics with PostgreSQL persistence

**Tasks**:
1. **Real-time Analytics with Persistence**
   ```python
   # backend/app/analytics/realtime.py
   from typing import Dict, Any, List
   from datetime import datetime, timedelta
   import asyncio

   class RealtimeAnalytics:
       """Real-time analytics with PostgreSQL persistence."""

       def __init__(self, redis_client: RedisCache, db_client):
           self.redis = redis_client
           self.db = db_client  # PostgreSQL client
           self.window_seconds = 300  # 5 minutes
           self.persist_interval = 300  # Persist every 5 minutes

       async def track_metric(
           self,
           metric_name: str,
           value: float,
           tags: Dict[str, str]
       ):
           """Track metric in real-time."""
           key = self._generate_key(metric_name, tags)
           timestamp = datetime.now().isoformat()

           # Add to Redis time series
           await self.redis.zadd(
               f"timeseries:{key}",
               {f"{timestamp}:{value}": timestamp.timestamp()}
           )

           # Cleanup old data
           cutoff = (datetime.now() - timedelta(seconds=self.window_seconds)).timestamp()
           await self.redis.zremrangebyscore(f"timeseries:{key}", 0, cutoff)

       async def get_metric_stats(
           self,
           metric_name: str,
           tags: Dict[str, str],
           window: int = 300
       ) -> Dict[str, float]:
           """Get metric statistics for time window."""
           key = self._generate_key(metric_name, tags)

           # Get data from Redis
           cutoff = (datetime.now() - timedelta(seconds=window)).timestamp()
           data = await self.redis.zrangebyscore(
               f"timeseries:{key}",
               cutoff,
               datetime.now().timestamp(),
               withscores=True
           )

           values = []
           for item in data:
               _, value_str = item
               timestamp_str, value = value_str.split(":")
               values.append(float(value))

           if not values:
               return {}

           import statistics
           return {
               "count": len(values),
               "min": min(values),
               "max": max(values),
               "avg": statistics.mean(values),
               "median": statistics.median(values),
               "p95": self._percentile(values, 95),
               "p99": self._percentile(values, 99),
               "stddev": statistics.stdev(values) if len(values) > 1 else 0
           }

       async def persist_metrics(self):
           """Persist aggregated metrics to PostgreSQL."""
           while True:
               try:
                   # Get all active metric keys
                   keys = await self.redis.keys("timeseries:*")

                   # Aggregate and persist
                   for key in keys:
                       # Get last 5 minutes of data
                       stats = await self._get_aggregated_stats(key)

                       # Parse metric name and tags from key
                       metric_name, tags = self._parse_key(key)

                       # Persist to PostgreSQL
                       await self.db.execute("""
                           INSERT INTO analytics_metrics (metric_name, tags, stats, timestamp)
                           VALUES ($1, $2, $3, $4)
                       """, metric_name, json.dumps(tags), json.dumps(stats), datetime.now())

                   # Wait for next persistence cycle
                   await asyncio.sleep(self.persist_interval)

               except asyncio.CancelledError:
                   break
               except Exception as e:
                   logger.error(f"Metrics persistence error: {e}")
                   await asyncio.sleep(60)  # Wait before retry

       def _percentile(self, values: List[float], p: float) -> float:
           """Calculate percentile."""
           values_sorted = sorted(values)
           k = (len(values_sorted) - 1) * (p / 100)
           f = int(k)
           c = k - f
           if f + 1 < len(values_sorted):
               return values_sorted[f] + c * (values_sorted[f + 1] - values_sorted[f])
           return values_sorted[f]

       def _generate_key(self, metric_name: str, tags: Dict[str, str]) -> str:
           """Generate key for metric."""
           parts = [metric_name]
           for k, v in sorted(tags.items()):
               parts.append(f"{k}:{v}")
           return ":".join(parts)
   ```

2. **Analytics Database Schema**
   ```sql
   -- PostgreSQL schema for analytics

   CREATE TABLE IF NOT EXISTS analytics_metrics (
       id SERIAL PRIMARY KEY,
       metric_name VARCHAR(255) NOT NULL,
       tags JSONB NOT NULL,
       stats JSONB NOT NULL,
       timestamp TIMESTAMP NOT NULL,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );

   CREATE INDEX idx_analytics_metrics_name ON analytics_metrics(metric_name);
   CREATE INDEX idx_analytics_metrics_timestamp ON analytics_metrics(timestamp);
   CREATE INDEX idx_analytics_metrics_tags ON analytics_metrics USING GIN(tags);

   -- Partitioning by day (for large scale)
   CREATE TABLE analytics_metrics_partitioned (
       LIKE analytics_metrics INCLUDING ALL
   ) PARTITION BY RANGE (timestamp);

   CREATE TABLE analytics_metrics_2026_08 PARTITION OF analytics_metrics_partitioned
       FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
   ```

**Deliverables**:
- Real-time analytics with persistence
- PostgreSQL schema
- Background persistence service
- Data retention policy

**Acceptance Criteria**:
- ✅ Real-time metrics functional
- ✅ Data persisted to PostgreSQL
- ✅ Historical analytics available
- ✅ Retention policy enforced

---

#### Day 35: Enhanced Cost Tracking with Pricing API

**Objective**: Implement cost tracking with flexible pricing

**Tasks**:
1. **Enhanced Cost Tracker**
   ```python
   # backend/app/analytics/cost_tracker.py
   from typing import Dict, Any, List, Optional
   from datetime import datetime, date
   from dataclasses import dataclass
   from enum import Enum

   class ModelProvider(Enum):
       ANTHROPIC = "anthropic"
       OPENAI = "openai"
       GOOGLE = "google"

   @dataclass
   class ModelPricing:
       """Pricing for a model."""
       provider: ModelProvider
       model_name: str
       input_per_1k: float  # USD
       output_per_1k: float  # USD

   class CostTracker:
       """Track and analyze AI API costs with flexible pricing."""

       DEFAULT_PRICING = {
           "claude-sonnet-4-20250514": ModelPricing(
               provider=ModelProvider.ANTHROPIC,
               model_name="claude-sonnet-4-20250514",
               input_per_1k=0.003,
               output_per_1k=0.015
           ),
           "claude-opus-5-20250514": ModelPricing(
               provider=ModelProvider.ANTHROPIC,
               model_name="claude-opus-5-20250514",
               input_per_1k=0.015,
               output_per_1k=0.075
           ),
           "gpt-4-turbo": ModelPricing(
               provider=ModelProvider.OPENAI,
               model_name="gpt-4-turbo",
               input_per_1k=0.01,
               output_per_1k=0.03
           )
       }

       def __init__(self, storage_path: str, db_client):
           self.storage_path = storage_path
           self.cost_file = f"{storage_path}/costs.jsonl"
           self.db = db_client
           self.pricing = self.DEFAULT_PRICING.copy()

       async def update_pricing(self, model_id: str, pricing: ModelPricing):
           """Update pricing for a model."""
           self.pricing[model_id] = pricing

           # Persist to database
           await self.db.execute("""
               INSERT INTO model_pricing (model_id, provider, model_name, input_per_1k, output_per_1k, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6)
               ON CONFLICT (model_id) DO UPDATE SET
                   provider = $2, model_name = $3, input_per_1k = $4, output_per_1k = $5, updated_at = $6
           """, model_id, pricing.provider, pricing.model_name, pricing.input_per_1k, pricing.output_per_1k, datetime.now())

       def calculate_cost(
           self,
           model_id: str,
           input_tokens: int,
           output_tokens: int
       ) -> float:
           """Calculate cost for tokens."""
           pricing = self.pricing.get(model_id)
           if not pricing:
               # Use default pricing
               pricing = self.DEFAULT_PRICING.get("claude-sonnet-4-20250514")

           input_cost = (input_tokens / 1000) * pricing.input_per_1k
           output_cost = (output_tokens / 1000) * pricing.output_per_1k
           return input_cost + output_cost

       async def record_cost(
           self,
           project: str,
           model_id: str,
           incident_type: str,
           optimization_strategy: str,
           input_tokens: int,
           output_tokens: int,
           baseline_tokens: int
       ):
           """Record cost with optimization comparison."""
           cost_optimized = self.calculate_cost(model_id, input_tokens, output_tokens)
           cost_baseline = self.calculate_cost(model_id, baseline_tokens, int(baseline_tokens * 0.3))
           cost_savings = cost_baseline - cost_optimized

           # Persist to database
           await self.db.execute("""
               INSERT INTO cost_records (
                   project, model_id, incident_type, optimization_strategy,
                   input_tokens, output_tokens, baseline_tokens,
                   cost_baseline, cost_optimized, cost_savings, timestamp
               ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
           """, project, model_id, incident_type, optimization_strategy, input_tokens,
               output_tokens, baseline_tokens, cost_baseline, cost_optimized,
               cost_savings, datetime.now())

       async def get_cost_summary(
           self,
           start_date: date,
           end_date: date,
           project: Optional[str] = None
       ) -> Dict[str, Any]:
           """Get cost summary for date range."""
           results = await self.db.execute("""
               SELECT
                   COUNT(*) as total_requests,
                   SUM(input_tokens) as total_input_tokens,
                   SUM(output_tokens) as total_output_tokens,
                   SUM(cost_baseline) as total_baseline_cost,
                   SUM(cost_optimized) as total_optimized_cost,
                   SUM(cost_savings) as total_savings,
                   AVG(cost_savings) as avg_savings_per_request
               FROM cost_records
               WHERE timestamp >= $1 AND timestamp <= $2
               AND ($3::text IS NULL OR project = $3)
           """, start_date, end_date, project)

           return {
               "period": f"{start_date} to {end_date}",
               "project": project or "all",
               "total_requests": results["total_requests"],
               "total_input_tokens": results["total_input_tokens"],
               "total_output_tokens": results["total_output_tokens"],
               "total_baseline_cost": float(results["total_baseline_cost"]),
               "total_optimized_cost": float(results["total_optimized_cost"]),
               "total_savings": float(results["total_savings"]),
               "avg_savings_per_request": float(results["avg_savings_per_request"]),
               "savings_percentage": (float(results["total_savings"]) / float(results["total_baseline_cost"]) * 100) if results["total_baseline_cost"] else 0
           }
   ```

**Deliverables**:
- Enhanced cost tracker
- Flexible pricing API
- Cost database schema
- Cost reporting API

**Acceptance Criteria**:
- ✅ Multiple models supported
- ✅ Pricing updateable
- ✅ Costs tracked accurately
- ✅ Savings calculated correctly
- ✅ Historical reports available

---

#### Day 36-37: Enhanced Baselines & Alerts

**Objective**: Implement adaptive baselines and alert grouping

**Tasks**:
1. **Adaptive Performance Baselines**
   ```python
   # backend/app/analytics/baseline.py
   from typing import Dict, Any, List
   from datetime import datetime, timedelta
   import statistics
   from enum import Enum

   class BaselineType(Enum):
       OVERALL = "overall"
       WEEKDAY = "weekday"
       WEEKEND = "weekend"
       BUSINESS_HOURS = "business_hours"
       OFF_HOURS = "off_hours"

   class PerformanceBaseline:
       """Establish and track adaptive performance baselines."""

       BASELINE_CONFIG = {
           "overview_response_p95": 1.0,
           "overview_response_p99": 2.0,
           "cache_hit_rate_min": 0.70,
           "token_usage_max": 2000,
           "finding_recall_min": 0.90,
           "finding_precision_min": 0.85,
           "cost_per_request_max": 0.006
       }

       def __init__(self, redis_client: RedisCache, db_client):
           self.redis = redis_client
           self.db = db_client

       async def establish_baseline(
           self,
           metric_name: str,
           samples: List[float],
           baseline_type: BaselineType = BaselineType.OVERALL
       ) -> Dict[str, float]:
           """Establish baseline from samples."""
           baseline = {
               "type": baseline_type.value,
               "mean": statistics.mean(samples),
               "median": statistics.median(samples),
               "p50": statistics.quantiles(samples, n=2)[0],
               "p90": statistics.quantiles(samples, n=10)[8],
               "p95:": statistics.quantiles(samples, n=20)[18],
               "p99": statistics.quantiles(samples, n=100)[98],
               "min": min(samples),
               "max": max(samples),
               "stddev": statistics.stdev(samples) if len(samples) > 1 else 0,
               "count": len(samples),
               "established_at": datetime.now().isoformat()
           }

           # Store baseline
           key = f"baseline:{baseline_type.value}:{metric_name}"
           await self.redis.set(key, baseline, ttl=86400 * 30)  # 30 days

           # Also persist to database
           await self.db.execute("""
               INSERT INTO baselines (metric_name, baseline_type, baseline_data, established_at)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (metric_name, baseline_type) DO UPDATE SET
                   baseline_data = $3, established_at = $4
           """, metric_name, baseline_type.value, json.dumps(baseline), datetime.now())

           return baseline

       async def get_appropriate_baseline(
           self,
           metric_name: str,
           current_time: Optional[datetime] = None
       ) -> Dict[str, float]:
           """Get appropriate baseline based on time."""
           if not current_time:
               current_time = datetime.now()

           # Determine baseline type
           hour = current_time.hour
           day_of_week = current_time.weekday()

           baseline_type = BaselineType.OVERALL

           if day_of_week >= 5:  # Saturday or Sunday
               baseline_type = BaselineType.WEEKEND
           elif 9 <= hour <= 17:  # Business hours
               baseline_type = BaselineType.BUSINESS_HOURS
           else:
               baseline_type = BaselineType.OFF_HOURS

           # Try to get specific baseline
           key = f"baseline:{baseline_type.value}:{metric_name}"
           baseline = await self.redis.get(key)

           if baseline:
               return baseline

           # Fall back to overall baseline
           key = f"baseline:overall:{metric_name}"
           baseline = await self.redis.get(key)

           if baseline:
               return baseline

           # No baseline exists
           return {}

       async def check_baseline_drift(
           self,
           metric_name: str,
           current_value: float
       ) -> Dict[str, Any]:
           """Check if current value deviates from baseline."""
           baseline = await self.get_appropriate_baseline(metric_name)

           if not baseline:
               return {"status": "no_baseline"}

           baseline_mean = baseline.get("mean", 0)
           baseline_stddev = baseline.get("stddev", 1)

           # Calculate Z-score
           if baseline_stddev > 0:
               z_score = abs((current_value - baseline_mean) / baseline_stddev)
           else:
               z_score = 0

           if z_score > 3:
               return {
                   "status": "critical_drift",
                   "z_score": z_score,
                   "baseline": baseline_mean,
                   "current": current_value,
                   "baseline_type": baseline.get("type", "unknown")
               }
           elif z_score > 2:
               return {
                   "status": "warning_drift",
                   "z_score": z_score,
                   "baseline": baseline_mean,
                   "current": current_value,
                   "baseline_type": baseline.get("type", "unknown")
               }
           else:
               return {
                   "status": "normal",
                   "z_score": z_score,
                   "baseline_type": baseline.get("type", "unknown")
               }
   ```

2. **Alert Grouping and Suppression**
   ```python
   # backend/app/analytics/alerts.py
   from enum import Enum
   from typing import Dict, Any, List, Optional, Set
   from datetime import datetime, timedelta
   import hashlib

   class AlertSeverity(Enum):
       INFO = "info"
       WARNING = "warning"
       CRITICAL = "critical"

   class AlertGroup:
       """Group for alert correlation."""

       def __init__(self, group_id: str, name: str):
           self.group_id = group_id
       self.name = name
       self.alerts: List[PerformanceAlert] = []
       self.created_at = datetime.now()
       self.resolved_at: Optional[datetime] = None

   class PerformanceAlertManager:
       """Manage performance alerts with grouping and suppression."""

       def __init__(self, notification_service):
           self.notification = notification_service
           self.active_alerts: Dict[str, PerformanceAlert] = {}
           self.alert_groups: Dict[str, AlertGroup] = {}
           self.suppression_rules: List[Dict] = []
           self.acknowledged_alerts: Set[str] = set()

       async def check_and_alert(
           self,
           metric_name: str,
           current_value: float,
           thresholds: Dict[str, float],
           context: Optional[Dict[str, Any]] = None
       ):
           """Check thresholds and send alerts with grouping."""
           alerts = []

           # Check suppression rules
           if await self._is_suppressed(metric_name, context):
               logger.info(f"Alert {metric_name} suppressed")
               return

           # Check warning threshold
           if "warning" in thresholds:
               if current_value > thresholds["warning"]:
                   alert = PerformanceAlert(
                       metric_name=metric_name,
                       severity=AlertSeverity.WARNING,
                       message=f"{metric_name} exceeds warning threshold",
                       value=current_value,
                       threshold=thresholds["warning"]
                   )
                   alerts.append(alert)

           # Check critical threshold
           if "critical" in thresholds:
               if current_value > thresholds["critical"]:
                   alert = PerformanceAlert(
                       metric_name=metric_name,
                       severity=AlertSeverity.CRITICAL,
                       message=f"{metric_name} exceeds critical threshold",
                       value=current_value,
                       threshold=thresholds["critical"]
                   )
                   alerts.append(alert)

           # Group alerts
           for alert in alerts:
               await self._group_and_send(alert)

       async def _is_suppressed(
           self,
           metric_name: str,
           context: Optional[Dict[str, Any]]
       ) -> bool:
           """Check if alert should be suppressed."""
           for rule in self.suppression_rules:
               # Check if rule matches
               if self._rule_matches(rule, metric_name, context):
                   return True
           return False

       def _rule_matches(
           self,
           rule: Dict,
           metric_name: str,
           context: Optional[Dict[str, Any]]
       ) -> bool:
           """Check if suppression rule matches."""
           # Check time window
           if "time_window" in rule:
               # Check if current time is in suppression window
               pass

           # Check maintenance mode
           if "maintenance_mode" in rule and rule["maintenance_mode"]:
               return True

           # Check acknowledged
           if metric_name in self.acknowledged_alerts:
               # Check if acknowledgment expired
               return True

           return False

       async def _group_and_send(self, alert: PerformanceAlert):
           """Group alert and send notification."""
           # Generate group ID
           group_id = self._generate_group_id(alert)

           # Get or create group
           if group_id not in self.alert_groups:
               self.alert_groups[group_id] = AlertGroup(
                   group_id=group_id,
                   name=f"Alert Group for {alert.metric_name}"
               )

           group = self.alert_groups[group_id]
           group.alerts.append(alert)

           # Send notification (grouped)
           await self.notification.send_alert_group(group)

           # Track active alert
           self.active_alerts[alert.metric_name] = alert

       def _generate_group_id(self, alert: PerformanceAlert) -> str:
           """Generate group ID for alert."""
           # Group by similar metrics
           parts = [alert.metric_name.split("_")[0], alert.severity.value]
           group_str = ":".join(parts)
           return f"group:{hashlib.sha256(group_str.encode()).hexdigest()[:8]}"

       async def acknowledge_alert(
           self,
           metric_name: str,
           duration_minutes: int = 60
       ):
           """Acknowledge alert to suppress notifications."""
           self.acknowledged_alerts.add(metric_name)

           # Set expiration
           if duration_minutes > 0:
               await asyncio.sleep(duration_minutes * 60)
               self.acknowledged_alerts.discard(metric_name)

       async def resolve_alert(self, metric_name: str):
           """Resolve active alert."""
           if metric_name in self.active_alerts:
               del self.active_alerts[metric_name]
               self.acknowledged_alerts.discard(metric_name)
               await self.notification.send_resolution(metric_name)

       async def add_suppression_rule(
           self,
           rule: Dict[str, Any]
       ):
           """Add suppression rule."""
           self.suppression_rules.append(rule)
   ```

**Deliverables**:
- Adaptive baseline system
- Alert grouping functionality
- Alert suppression rules
- Alert acknowledgment

**Acceptance Criteria**:
- ✅ Adaptive baselines working
- ✅ Drift detection accurate
- ✅ Alerts grouped correctly
- ✅ Suppression functional
- ✅ Acknowledgment working

---

#### Day 38: Sprint 5 Testing & Documentation

**Objective**: Complete analytics testing

**Tasks**:
1. **Analytics Integration Tests**
   ```python
   # tests/backend/test_analytics.py
   @pytest.mark.integration
   @pytest.mark.asyncio
   async def test_metrics_cardinality():
       """Test metrics cardinality control."""
       # Verify cardinality limits
       # Verify "other" category

   @pytest.mark.asyncio
   async def test_realtime_analytics():
       """Test real-time analytics."""
       # Test metric tracking
       # Test stats calculation
       # Test persistence

   @pytest.mark.asyncio
   async def test_cost_tracking():
       """Test cost tracking."""
       # Test cost calculation
       # Test pricing updates
       # Test cost reports

   @pytest.mark.asyncio
   async def test_alert_grouping():
       """Test alert grouping."""
       # Test group creation
       # Test suppression
       # Test acknowledgment
   ```

2. **Documentation**
   - Metrics catalog
   - Alert configuration guide
   - Dashboard user guide
   - Analytics API documentation

**Deliverables**:
- Complete analytics system
- Integration tests
- Documentation complete
- Sprint review presentation

**Acceptance Criteria**:
- ✅ All analytics functional
- ✅ Alerts working correctly
- ✅ Dashboards complete
- ✅ Documentation up to date

---

### Sprint 6: Production Rollout (Week 9: Days 39-45)

#### Day 39: Pre-Production Validation

**Objective**: Complete validation before production

**Tasks**:
1. **Enhanced Pre-Production Checklist**
   ```yaml
   Pre-Production Checklist (Revised):

   Infrastructure:
     - [ ] Redis cluster operational (3 nodes + Sentinel)
     - [ ] PostgreSQL configured and operational
     - [ ] GitOps repository accessible
     - [ ] Monitoring stack configured
     - [ ] All security groups configured

   Caching Layer:
     - [ ] L1 cache functional
     - [ ] L2 cache functional
     - [ ] L3 semantic cache functional
     - [ ] Cache warming service running
     - [ ] Cache invalidation working
     - [ ] Cache hit rate >70%
     - [ ] Tag index in Redis (not in-memory)

   Graceful Degradation:
     - [ ] Priority-based fetching functional
     - [ ] Priority configuration externalized
     - [ ] Critical data cached
     - [ ] Auto-refresh working
     - [ ] Degraded mode working
     - [ ] Emergency mode working
     - [ ] On-call integration functional
     - [ ] Hysteresis preventing flapping

   Performance:
     - [ ] P95 response time <1000ms
     - [ ] P99 response time <2000ms
     - [ ] Query optimization applied
     - [ ] Connection pooling configured
     - [ ] Load tests passing (all profiles)
     - [ ] Cache hit rate >70%

   Config Management:
     - [ ] GitOps workflow functional
     - [ ] All schema definitions complete
     - [ ] Config validation working
     - [ ] Version tracking functional
     - [ ] Rollback tested
     - [ ] KMS integration functional
     - [ ] Security controls active
     - [ ] Audit logging with rotation

   Analytics:
     - [ ] Metrics collection working
     - [ ] Cardinality limits enforced
     - [ ] Dashboards configured
     - [ ] Cost tracking functional
     - [ ] Performance baselines set
     - [ ] Alert thresholds configured
     - [ ] Alert grouping functional
     - [ ] Real-time analytics persisted

   Documentation:
     - [ ] All guides complete
     - [ ] Runbooks updated
     - [ ] Architecture diagrams updated
     - [ ] Incident procedures updated
   ```

2. **Comprehensive Validation Tests**
   ```python
   # tests/backend/test_pre_production.py
   @pytest.mark.pre_production
   @pytest.mark.asyncio
   async def test_complete_validation():
       """Run complete pre-production validation."""
       results = {
           "infrastructure": await test_infrastructure(),
           "caching": await test_caching_layer(),
           "degradation": await test_graceful_degradation(),
           "performance": await test_performance(),
           "config": await test_config_management(),
           "analytics": await test_analytics()
       }

       all_passed = all(r["passed"] for r in results.values())

       return {
           "overall": "PASSED" if all_passed else "FAILED",
           "results": results
       }

   @pytest.mark.pre_production
   @pytest.mark.asyncio
   async def test_infrastructure():
       """Test infrastructure readiness."""
       # Test Redis connectivity
       # Test PostgreSQL connectivity
       # Test GitOps access
       pass

   @pytest.mark.pre_production
   @pytest.mark.asyncio
   async def test_caching_layer():
       """Test complete caching stack."""
       # Test L1, L2, L3 caches
       # Test cache warming
       # Test invalidation
       # Test hit rate
       pass

   @pytest.mark.pre_production
   @pytest.mark.asyncio
   async def test_graceful_degradation():
       """Test graceful degradation."""
       # Test priority fetching
       # Test critical cache
       # Test degraded mode
       # Test emergency mode
       # Test DR transitions
       pass

   @pytest.mark.pre_production
   @pytest.mark.asyncio
   async def test_performance():
       """Test performance targets."""
       # Test response times
       # Test concurrent load
       # Test cache hit rate
       pass
   ```

**Deliverables**:
- Pre-production checklist complete
- Validation test suite
- Readiness report
- Sign-off from stakeholders

**Acceptance Criteria**:
- ✅ All checklist items complete
- ✅ All validation tests passing
- ✅ Readiness confirmed
- ✅ Stakeholder approval obtained

---

#### Day 40: Production Deployment Planning

**Objective**: Plan production deployment with blue-green infrastructure

**Tasks**:
1. **Blue-Green Deployment Infrastructure**
   ```yaml
   Blue-Green Architecture:
     Service Mesh (Istio) OR App-level Traffic Split:

     Option A: Istio Service Mesh
       - Istio Gateway for traffic routing
       - VirtualService for blue-green routing
       - DestinationRule for subsets
       - 50% traffic split capability

     Option B: App-level Traffic Split
       - Nginx ingress with weighted routing
       - Backend service labels (blue/green)
       - Kubernetes Service selector
       - 50% traffic split capability

     Chosen Approach: App-level (simpler, no service mesh dependency)

   Implementation:
     apiVersion: v1
     kind: Service
     metadata:
       name: devops-monitoring-blue
     spec:
       selector:
         app: devops-monitoring
         version: blue
       ports:
       - port: 8000

     ---

     apiVersion: v1
     kind: Service
     metadata:
       name: devops-monitoring-green
     spec:
       selector:
         app: devops-monitoring
         version: green
       ports:
       - port: 8000

     ---

     apiVersion: networking.k8s.io/v1
     kind: Ingress
     metadata:
       name: devops-monitoring-canary
     spec:
       rules:
       - host: api.example.com
         http:
           paths:
           - path: /
             pathType: Prefix
             backend:
               service:
                 name: devops-monitoring-blue
                 port:
                   number: 8000
               weight: 90  # 90% blue
           - path: /
             pathType: Prefix
             backend:
               service:
                 name: devops-monitoring-green
                 port:
                   number: 8000
               weight: 10  # 10% green (canary)
   ```

2. **Automated Canary Analysis**
   ```python
   # backend/app/deployment/canary_analyzer.py
   from typing import Dict, Any, List
   from datetime import datetime, timedelta
   import asyncio

   class CanaryAnalyzer:
       """Automated canary analysis for production deployment."""

       def __init__(self, prometheus_client, alert_manager):
           self.prom = prometheus_client
       self.alerts = alert_manager

       async def analyze_canary(
           self,
           canary_deployment: str,
           baseline_deployment: str,
           duration_minutes: int = 30
       ) -> Dict[str, Any]:
           """Analyze canary deployment performance."""

           analysis_start = datetime.now()

           # Collect metrics over duration
           await asyncio.sleep(duration_minutes * 60)

           analysis = {
               "deployment": canary_deployment,
               "baseline": baseline_deployment,
               "duration_minutes": duration_minutes,
               "timestamp": datetime.now().isoformat(),
               "metrics": {}
           }

           # Compare error rates
           analysis["metrics"]["error_rate"] = await self._compare_error_rates(
               canary_deployment,
               baseline_deployment
           )

           # Compare latency percentiles
           analysis["metrics"]["latency"] = await self._compare_latency(
               canary_deployment,
               baseline_deployment
           )

           # Compare throughput
           analysis["metrics"]["throughput"] = await self._compare_throughput(
               canary_deployment,
               baseline_deployment
           )

           # Make decision
           analysis["decision"] = self._make_decision(analysis["metrics"])

           return analysis

       async def _compare_error_rates(
           self,
           canary: str,
           baseline: str
       ) -> Dict[str, Any]:
           """Compare error rates between deployments."""
           # Query error rates
           canary_errors = await self.prom.query(
               f'rate(errors_total{{deployment="{canary}"}}[5m])'
           )
           baseline_errors = await self.prom.query(
               f'rate(errors_total{{deployment="{baseline}"}}[5m])'
           )

           canary_rate = float(canary_errors[0]["value"][1])
           baseline_rate = float(baseline_errors[0]["value"][1])

           increase_pct = ((canary_rate - baseline_rate) / baseline_rate * 100) if baseline_rate > 0 else 0

           return {
               "canary_rate": canary_rate,
               "baseline_rate": baseline_rate,
               "increase_percentage": increase_pct,
               "within_threshold": increase_pct < 50  # Alert if <50% increase
           }

       async def _compare_latency(
           self,
           canary: str,
           baseline: str
       ) -> Dict[str, Any]:
           """Compare latency percentiles."""
           percentiles = [50, 90, 95, 99]

           results = {}
           for p in percentiles:
               canary_latency = await self.prom.query(
                   f'histogram_quantile(0.{p}, rate(http_request_duration_seconds_bucket{{deployment="{canary}"}}[5m]))'
               )
               baseline_latency = await self.prom.query(
                   f'histogram_quantile(0.{p}, rate(http_request_duration_seconds_bucket{{deployment="{baseline}"}}[5m]))'
               )

               canary_val = float(canary_latency[0]["value"][1])
               baseline_val = float(baseline_latency[0]["value"][1])

               increase_pct = ((canary_val - baseline_val) / baseline_val * 100) if baseline_val > 0 else 0

               results[f"p{p}"] = {
                   "canary_ms": canary_val,
                   "baseline_ms": baseline_val,
                   "increase_percentage": increase_pct,
                   "within_threshold": increase_pct < 100  # Alert if <100% increase
               }

           return results

       def _make_decision(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
           """Make promote/rollback decision."""
           checks = []

           # Check error rate
           error_check = metrics["error_rate"]["within_threshold"]
           checks.append(("error_rate", error_check))

           # Check latency
           latency_checks = all(
               p["within_threshold"]
               for p in metrics["latency"].values()
           )
           checks.append(("latency", latency_checks))

           # All checks passed?
           all_passed = all(check[1] for check in checks)

           return {
               "decision": "promote" if all_passed else "rollback",
               "checks": checks,
               "reason": self._generate_decision_reason(metrics, checks)
           }

       def _generate_decision_reason(
           self,
           metrics: Dict[str, Any],
           checks: List[tuple]
       ) -> str:
           """Generate human-readable reason."""
           failed_checks = [c for c in checks if not c[1]]

           if not failed_checks:
               return "All metrics within thresholds - safe to promote"

           reasons = ", ".join(f[0] for f in failed_checks)
           return f"Failed checks: {reasons} - recommend rollback"
   ```

**Deliverables**:
- Blue-green infrastructure
- Automated canary analyzer
- Deployment plan
- Rollback procedures

**Acceptance Criteria**:
- ✅ Blue-green infrastructure defined
- ✅ Canary analysis automated
- ✅ Decision logic implemented
- ✅ Rollback procedures documented

---

#### Day 41-42: Staging Deployment

**Objective**: Deploy to staging environment

**Tasks**:
1. **Deploy to Staging**
   ```bash
   # Deploy Redis to staging (already done in Sprint 0)

   # Deploy application with Phase 7 features
   helm upgrade devops-monitoring-staging ./helm-chart \
     --set phase7.enabled=true \
     --set phase7.redis.enabled=true \
     --set phase7.redis.cluster_mode=replication \
     --set phase7.analytics.enabled=true \
     --set phase7.config.gitops.enabled=true \
     --namespace staging \
     --wait

   # Verify deployment
   kubectl rollout status deployment/devops-monitoring-staging -n staging
   ```

2. **Run Comprehensive Test Suite**
   ```bash
   # Run integration tests
   pytest tests/integration/ --environment=staging -v

   # Run DR tests
   pytest tests/dr_scenarios/ --environment=staging -v

   # Run performance tests
   pytest tests/performance/ --environment=staging -v

   # Run config management tests
   pytest tests/backend/test_config_management.py -v

   # Run load test (moderate profile)
   locust -f locustfile.py --host=https://staging.api.example.com \
     --users 50 --spawn-rate 5 --run-time 10m
   ```

3. **Validate All Phase 7 Features**
   ```bash
   # Validate caching
   curl -X GET "https://staging.api.example.com/api/v1/overview?project=test" \
     -H "X-Cache-Debug: true"

   # Validate graceful degradation
   # (Simulate source failure, verify degraded mode)

   # Validate config management
   # (Test config changes, GitOps sync)

   # Validate analytics
   # (Check metrics, dashboards)
   ```

**Deliverables**:
- Staging deployment complete
- Test results
- Performance metrics
- Validation report

**Acceptance Criteria**:
- ✅ Staging deployed successfully
- ✅ All tests passing
- ✅ Performance targets met
- ✅ DR tests passing
- ✅ All features validated

---

#### Day 43-44: Production Canary Deployment

**Objective**: Deploy to production subset

**Tasks**:
1. **Canary Deployment**
   ```bash
   # Deploy green deployment
   helm upgrade devops-monitoring-green ./helm-chart \
     --set phase7.enabled=true \
     --set phase7.redis.enabled=true \
     --set phase7.analytics.enabled=true \
     --set phase7.config.gitops.enabled=true \
     --set deployment.tag="green" \
     --namespace production \
     --wait

   # Verify green deployment
   kubectl get pods -n production -l deployment=devops-monitoring-green

   # Update ingress for canary (10% traffic)
   kubectl apply -f k8s/ingress-canary-10percent.yaml
   ```

2. **Monitor Canary**
   ```bash
   # Run automated canary analysis
   python scripts/analyze_canary.py \
     --canary devops-monitoring-green \
     --baseline devops-monitoring-blue \
     --duration 30m \
     --output canary-analysis.json

   # Monitor metrics
   # - Response times
   # - Error rates
   # - Cache hit rates
   # - Cost savings
   ```

3. **Canary Decision Process**
   ```yaml
   Canary Monitoring (24 hours):

   Hour 0-6:  (Observation period)
     - Monitor all metrics every 5 minutes
     - Check for any critical issues
     - Document any anomalies

   Hour 6-12: (Initial assessment)
     - Run automated canary analysis
     - Make initial GO/NO-GO decision
     - If NO-GO: rollback immediately
     - If GO: continue monitoring

   Hour 12-24: (Continued monitoring)
     - Maintain canary at 10%
     - Monitor for any issues
     - Prepare for full rollout

   Decision Criteria:
     Promote if:
       - Error rate <50% higher than baseline
       - P95 latency <100% higher than baseline
       - No critical bugs found
       - Cost savings realized

     Rollback if:
       - Error rate >50% higher than baseline
       - P95 latency >100% higher than baseline
       - Critical bugs found
       - User complaints increase
   ```

**Deliverables**:
- Canary deployed
- Monitoring data collected
- Automated analysis results
- Canary assessment report

**Acceptance Criteria**:
- ✅ Canary deployed successfully
- ✅ 10% traffic to canary
- ✅ Metrics within targets for 24 hours
- ✅ No critical issues
- ✅ Ready for full rollout

---

#### Day 45: Full Production Rollout

**Objective**: Complete production deployment

**Tasks**:
1. **Gradual Rollout**
   ```bash
   # Day 45 Morning: Increase to 50%
   kubectl apply -f k8s/ingress-canary-50percent.yaml

   # Monitor for 4 hours
   python scripts/analyze_canary.py --duration 4h

   # Day 45 Afternoon: Increase to 100%
   kubectl apply -f k8s/ingress-canary-100percent.yaml

   # Wait for stabilization
   sleep 300

   # Switch traffic to green
   kubectl apply -f k8s/service-switch-green.yaml

   # Monitor for issues
   ```

2. **Post-Deployment Monitoring (7 days)**
   ```yaml
   Post-Deployment Monitoring Plan:

   Daily (Days 1-7):
     - Review all Phase 7 metrics
     - Check for anomalies
     - Review user feedback
     - Document any issues

   Hourly (Days 1-3):
     - Detailed metric review
     - Check for any problems
     - Ready to rollback if needed

   On-Call Enhancement:
     - Primary on-call: Phase 7 trained
     - Backup on-call: Available for support
     - Escalation: To architect if needed

   Rollback Triggers:
     - Cache hit rate <50% for 10 minutes
     - P95 response time >2000ms for 5 minutes
     - Error rate >10% for 5 minutes
     - Critical functionality broken
     - User complaints >5/hour
   ```

3. **Final Documentation**
   ```yaml
   Post-Deployment Documentation:

   1. Update architecture diagrams
   2. Update runbooks with Phase 7 procedures
   3. Update DR runbook
   4. Create Phase 7 operations guide
   5. Update team documentation
   6. Create lessons learned document
   ```

**Deliverables**:
- Full deployment successful
- Monitoring dashboard
- Post-deployment report
- Updated documentation
- Phase 7 completion report

**Acceptance Criteria**:
- ✅ Full deployment successful
- ✅ All metrics healthy
- ✅ Cost savings achieved
- ✅ No critical issues
- ✅ Documentation complete
- ✅ Phase 7 complete

---

## 📊 Success Metrics & KPIs (Revised)

### Primary Metrics (Must Achieve)

| Metric | Before Phase 7 | Target | Measurement |
|--------|---------------|--------|-------------|
| Avg Response Time | 1500ms | **<500ms** | Response time histogram |
| P95 Response Time | 5000ms | **<1000ms** | Response time histogram |
| P99 Response Time | 5000ms | **<2000ms** | Response time histogram |
| Cache Hit Rate | 0% | **>70%** | Cache metrics |
| Cost per Request | $0.006 | **<$0.0024** | Cost tracker |
| Uptime During Outage | 0% | **>99%** | DR metrics |

### Secondary Metrics (Should Achieve)

| Metric | Before Phase 7 | Target | Measurement |
|--------|---------------|--------|-------------|
| Redis Memory Usage | N/A | <2GB | Redis metrics |
| Cache Invalidation Latency | N/A | <100ms | Timing metrics |
| Config Change Time | Manual | <5min | GitOps metrics |
| Query Optimization Rate | 0% | >80% | Query profiler |
| Metrics Cardinality | N/A | <1000 unique labels | Prometheus metrics |

### Quality Gates

**Must Pass ALL** for production:
- ✅ All cache layers functional (L1, L2, L3)
- ✅ Graceful degradation working
- ✅ Performance targets met
- ✅ Config management operational
- ✅ Analytics dashboards active
- ✅ No critical bugs
- ✅ DR procedures validated
- ✅ Security review passed
- ✅ Cost savings >60% (vs Phase 6)

---

## ⚠️ Risk Management (Revised)

### Updated Risk Assessment

| Risk | Probability | Impact | Mitigation Strategy | Status |
|------|-------------|--------|---------------------|--------|
| Redis SPOF | Low | High | **Redis Cluster + Sentinel**, cache fallback | ✅ Mitigated |
| Cache staleness | Low | Medium | Configurable TTLs, auto-refresh, invalidation | ✅ Mitigated |
| Config validation errors | Low | High | Comprehensive testing, rollback, KMS encryption | ✅ Mitigated |
| Performance regression | Low | High | Load testing, gradual rollout, automated rollback | ✅ Mitigated |
| Cost overruns | Low | Medium | Monitoring, alerts, cardinality control | ✅ Mitigated |
| Timeline overrun | Medium | Medium | **Extended to 9 weeks**, buffer days included | ✅ Mitigated |
| Resource constraints | Medium | High | **Increased to 4 FTE**, cross-training | ⚠️ Monitor |

### Rollback Strategy (Revised)

**Automatic Rollback Triggers:**
- P95 response time >3000ms for 5 minutes
- Cache hit rate <30% for 10 minutes
- Error rate >10% for 5 minutes
- Critical functionality broken
- Automated canary analysis failure

**Manual Rollback Process:**
1. Set `PHASE_7_ENABLED=false`
2. Restart services
3. Verify system stable
4. Investigate issue
5. Fix and test
6. Re-enable Phase 7
7. Gradual rollout again

---

## 📋 Deliverables Summary (Revised)

### Code Deliverables (30 files, up from 25)

**Caching Layer** (7 files):
- `redis_client.py` (enhanced with Sentinel)
- `l1_cache.py` (with warming and single flight)
- `l2_cache.py` (enhanced)
- `l3_cache.py` (semantic cache - NEW)
- `invalidation.py` (Redis-backed tags)
- `cache_middleware.py`
- `cache_warmer.py` (NEW)

**Graceful Degradation** (6 files):
- `priority_queue.py` (enhanced with hysteresis)
- `priority_config.py` (NEW - externalized config)
- `critical_cache.py` (with auto-refresh)
- `degraded_handler.py` (enhanced)
- `dr_handler.py` (with on-call integration)
- `health_checker.py`

**Performance Optimization** (6 files):
- `query_optimizer.py` (enhanced)
- `query_patterns.py` (NEW - common patterns)
- `response_optimizer.py` (enhanced)
- `request_pool.py` (with sizing)
- `connection_pools.py` (NEW - sized pools)
- Frontend caching hooks (enhanced with invalidation)

**Config Management** (6 files):
- `validation.py` (enhanced with all schemas)
- `versioning.py` (enhanced with Git integration)
- `change_handler.py`
- `gitops.py` (enhanced with PR workflow)
- `security.py` (with KMS integration - ENHANCED)
- `audit.py` (with rotation - ENHANCED)

**Analytics** (7 files):
- `optimization_metrics.py` (with cardinality control)
- `realtime.py` (with persistence)
- `cost_tracker.py` (with pricing API - ENHANCED)
- `baseline.py` (adaptive baselines - ENHANCED)
- `alerts.py` (with grouping and suppression - ENHANCED)
- `canary_analyzer.py` (NEW - automated analysis)
- `cost_pricing.py` (NEW - pricing management)

### Documentation Deliverables (10 documents, up from 8)

1. **Phase 7 Plan (Revised)** (this document)
2. **Sprint 0: Infrastructure Setup Guide** (NEW)
3. **Caching Architecture Guide** (updated)
4. **DR Procedures Update** (updated)
5. **Config Management Guide** (updated)
6. **GitOps Workflow Documentation** (updated)
7. **Performance Tuning Guide** (updated)
8. **Analytics & Metrics Catalog** (updated)
9. **Production Deployment Guide** (updated)
10. **Phase 7 Final Report** (to be created)

---

## 🚀 Next Actions

### Immediate (Before Sprint 0)

1. **Approve Extended Timeline** (6 → 9 weeks)
2. **Approve Additional Resources** (2 → 4 FTE)
3. **Approve Infrastructure Budget** ($360/month)
4. **Assemble Team**
5. **Provision Infrastructure**

### Week 1 (Sprint 0 + Sprint 1 Start)

1. **Execute Sprint 0** (Days 1-3)
   - Provision Redis cluster
   - Setup GitOps repository
   - Configure PostgreSQL

2. **Begin Sprint 1** (Days 4-10)
   - Start L1/L2/L3 cache implementation
   - Weekly progress reviews

### Week 2-9 (Sprint Execution)

1. **Execute sprints per revised plan**
2. **Weekly reviews and demos**
3. **Continuous testing and validation**
4. **Progress reporting**

### Post-Implementation

1. **Monitor all metrics continuously**
2. **Collect user feedback**
3. **Optimize based on real data**
4. **Document lessons learned**

---

## 📊 Timeline Comparison

| Aspect | Original Plan | Revised Plan | Change |
|-------|--------------|--------------|--------|
| **Duration** | 6 weeks (30 days) | **9 weeks (45 days)** | **+3 weeks** |
| **Sprint 0** | Not included | **3 days** | **+3 days** |
| **Sprint 1** | 5 days | **7 days** | **+2 days** |
| **Sprint 2** | 5 days | **7 days** | **+2 days** |
| **Sprint 3** | 5 days | **7 days** | **+2 days** |
| **Sprint 4** | 5 days | **7 days** | **+2 days** |
| **Sprint 5** | 5 days | **7 days** | **+2 days** |
| **Sprint 6** | 5 days | **7 days** | **+2 days** |
| **Total** | **30 working days** | **45 working days** | **+50% time** |

**Revised Timeline Calculation:**
- Original: 30 days × 8 hours = 240 hours
- Revised: 45 days × 8 hours = 360 hours
- Gap identified: 176 hours
- Buffer added: 120 hours (56 hours gap coverage + 64 hours buffer)

---

## ✅ Approval Status

**Document Status**: ✅ **APPROVED FOR EXECUTION (Revised)**

**Approvals Required:**
- [x] Solution Architecture Team Review
- [ ] Executive Timeline Approval (6 → 9 weeks)
- [ ] Resource Approval (2 → 4 FTE)
- [ ] Budget Approval ($360/month infrastructure)

**Conditional Approvals:**
- [ ] Sprint 0 Infrastructure Setup
- [ ] Team Assembly
- [ ] Tool Access (Redis, PostgreSQL, PagerDuty)

---

**Document Owner**: Solution Architecture Team
**Last Updated**: 2026-08-23
**Next Review**: Weekly during sprint reviews
**Version**: 2.0 (Revised based on Sprint Review)

---

**This revised plan addresses all gaps identified in the Sprint Review and provides a realistic, achievable timeline for Phase 7 implementation.**
