"""
Optimization API Endpoints - Phase 7 Sprint 3

Purpose: Expose optimization features via REST API

Endpoints:
- GET /api/v1/optimization/profiler/stats - Get query profiler statistics
- GET /api/v1/optimization/profiler/recent - Get recent query profiles
- DELETE /api/v1/optimization/profiler/reset - Reset profiler statistics
- GET /api/v1/optimization/pools/stats - Get connection pool statistics
- GET /api/v1/optimization/pools/health - Get connection pool health
- GET /api/v1/optimization/patterns/list - List available query patterns
- POST /api/v1/optimization/patterns/get - Get a specific query pattern
- GET /api/v1/optimization/rate-limiter/stats - Get rate limiter statistics
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from app.optimization import (
    QueryOptimizer,
    QueryPatternLibrary,
    ConnectionPoolManager,
    RateLimiter
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/optimization", tags=["optimization"])

# Global instances (injected at startup)
query_optimizer: Optional[QueryOptimizer] = None
pool_manager: Optional[ConnectionPoolManager] = None
rate_limiter: Optional[RateLimiter] = None


def set_optimization_instances(
    q_optimizer: QueryOptimizer,
    p_manager: ConnectionPoolManager,
    r_limiter: RateLimiter
):
    """Inject optimization instances at startup."""
    global query_optimizer, pool_manager, rate_limiter
    query_optimizer = q_optimizer
    pool_manager = p_manager
    rate_limiter = r_limiter


# Pydantic Models

class ProfilerStatsResponse(BaseModel):
    """Response model for profiler statistics."""
    total_queries: int
    cache_hits: int
    total_time_ms: float
    total_results: int
    avg_time_ms: float
    avg_results: float
    cache_hit_rate: float


class QueryProfileResponse(BaseModel):
    """Response model for a query profile."""
    query_type: str
    source: str
    function_name: str
    execution_time_ms: float
    result_count: int
    cache_hit: bool
    chunk_count: int
    timestamp: str


class PoolStatsResponse(BaseModel):
    """Response model for pool statistics."""
    pool_name: str
    pool_type: str
    total_connections: int
    active_connections: int
    idle_connections: int
    waiting_requests: int
    utilization_percent: float
    avg_acquire_time_ms: float


class PoolHealthResponse(BaseModel):
    """Response model for pool health."""
    total_pools: int
    healthy_pools: int
    pools: Dict[str, Dict[str, Any]]


class PatternListResponse(BaseModel):
    """Response model for pattern list."""
    patterns: Dict[str, List[str]]
    total_patterns: int


class PatternGetRequest(BaseModel):
    """Request model for getting a pattern."""
    category: str = Field(..., description="Pattern category (error, performance, resource, etc.)")
    pattern_name: str = Field(..., description="Pattern name")
    kwargs: Dict[str, Any] = Field(default={}, description="Pattern arguments")


class RateLimiterStatsResponse(BaseModel):
    """Response model for rate limiter statistics."""
    total_requests: int
    allowed_requests: int
    rejected_requests: int
    rejection_rate: float
    endpoint_stats: Dict[str, Dict[str, int]]
    active_buckets: int


# Endpoints

@router.get("/profiler/stats", response_model=ProfilerStatsResponse)
async def get_profiler_stats():
    """
    Get query profiler statistics.

    Returns aggregated statistics about query performance including
    execution times, cache hit rates, and result counts.
    """
    if not query_optimizer:
        raise HTTPException(status_code=503, detail="Query optimizer not initialized")

    stats = query_optimizer.get_profiler_stats()

    return ProfilerStatsResponse(
        total_queries=stats.get("total_queries", 0),
        cache_hits=stats.get("cache_hits", 0),
        total_time_ms=stats.get("total_time_ms", 0),
        total_results=stats.get("total_results", 0),
        avg_time_ms=stats.get("avg_time_ms", 0),
        avg_results=stats.get("avg_results", 0),
        cache_hit_rate=stats.get("cache_hit_rate", 0)
    )


@router.get("/profiler/recent", response_model=List[QueryProfileResponse])
async def get_recent_profiles(
    limit: int = Query(10, ge=1, le=100, description="Number of recent profiles to return")
):
    """
    Get recent query profiles.

    Returns the most recent query executions with detailed
    performance information.
    """
    if not query_optimizer:
        raise HTTPException(status_code=503, detail="Query optimizer not initialized")

    profiles = query_optimizer.profiler.get_recent_profiles(limit)

    return [
        QueryProfileResponse(
            query_type=p["query_type"],
            source=p["source"],
            function_name=p["function_name"],
            execution_time_ms=p["execution_time_ms"],
            result_count=p["result_count"],
            cache_hit=p["cache_hit"],
            chunk_count=p.get("chunk_count", 1),
            timestamp=p["timestamp"]
        )
        for p in profiles
    ]


@router.delete("/profiler/reset")
async def reset_profiler():
    """
    Reset profiler statistics.

    Clears all accumulated profiler statistics.
    """
    if not query_optimizer:
        raise HTTPException(status_code=503, detail="Query optimizer not initialized")

    query_optimizer.reset_profiler()

    return {
        "status": "reset",
        "message": "Profiler statistics reset successfully",
        "timestamp": datetime.now().isoformat()
    }


@router.get("/pools/stats", response_model=Dict[str, PoolStatsResponse])
async def get_pool_stats():
    """
    Get connection pool statistics.

    Returns statistics for all connection pools including
    utilization, active connections, and acquire times.
    """
    if not pool_manager:
        raise HTTPException(status_code=503, detail="Pool manager not initialized")

    all_stats = pool_manager.get_all_stats()

    return {
        name: PoolStatsResponse(
            pool_name=stats["pool_name"],
            pool_type=stats["pool_type"],
            total_connections=stats["total_connections"],
            active_connections=stats["active_connections"],
            idle_connections=stats["idle_connections"],
            waiting_requests=stats["waiting_requests"],
            utilization_percent=stats["utilization_percent"],
            avg_acquire_time_ms=stats["avg_acquire_time_ms"]
        )
        for name, stats in all_stats.items()
    }


@router.get("/pools/health", response_model=PoolHealthResponse)
async def get_pool_health():
    """
    Get connection pool health status.

    Returns health information for all managed connection pools.
    """
    if not pool_manager:
        raise HTTPException(status_code=503, detail="Pool manager not initialized")

    health = await pool_manager.health_check()

    return PoolHealthResponse(
        total_pools=health["total_pools"],
        healthy_pools=health["healthy_pools"],
        pools=health["pools"]
    )


@router.get("/patterns/list", response_model=PatternListResponse)
async def list_patterns(
    category: Optional[str] = Query(None, description="Filter by category")
):
    """
    List available query patterns.

    Returns a list of all available query patterns organized by category.
    """
    patterns = QueryPatternLibrary.list_patterns(category)

    total = sum(len(v) for v in patterns.values()) if patterns else 0

    return PatternListResponse(
        patterns=patterns,
        total_patterns=total
    )


@router.post("/patterns/get")
async def get_pattern(request: PatternGetRequest):
    """
    Get a specific query pattern.

    Returns the requested query pattern with applied parameters.
    """
    try:
        pattern = QueryPatternLibrary.get_pattern(
            request.category,
            request.pattern_name,
            **request.kwargs
        )

        return {
            "category": request.category,
            "pattern_name": request.pattern_name,
            "pattern": pattern,
            "timestamp": datetime.now().isoformat()
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting pattern: {str(e)}")


@router.get("/rate-limiter/stats", response_model=RateLimiterStatsResponse)
async def get_rate_limiter_stats():
    """
    Get rate limiter statistics.

    Returns statistics about rate limiting including request counts
    and rejection rates.
    """
    if not rate_limiter:
        raise HTTPException(status_code=503, detail="Rate limiter not initialized")

    stats = rate_limiter.get_stats()

    return RateLimiterStatsResponse(
        total_requests=stats["total_requests"],
        allowed_requests=stats["allowed_requests"],
        rejected_requests=stats["rejected_requests"],
        rejection_rate=stats["rejection_rate"],
        endpoint_stats=stats["endpoint_stats"],
        active_buckets=stats["active_buckets"]
    )


@router.post("/rate-limiter/limit")
async def set_rate_limit(
    endpoint: str = Query(..., description="Endpoint to set limit for"),
    rate: float = Query(..., ge=0.1, description="Rate limit (requests per second)"),
    burst: Optional[int] = Query(None, ge=1, description="Burst capacity")
):
    """
    Set rate limit for an endpoint.

    Configures rate limiting parameters for a specific endpoint.
    """
    if not rate_limiter:
        raise HTTPException(status_code=503, detail="Rate limiter not initialized")

    await rate_limiter.set_endpoint_limit(endpoint, rate, burst)

    return {
        "status": "configured",
        "endpoint": endpoint,
        "rate": rate,
        "burst": burst or rate_limiter.burst,
        "timestamp": datetime.now().isoformat()
    }


@router.get("/health")
async def optimization_health():
    """
    Get optimization module health status.

    Returns health status of all optimization components.
    """
    components = {
        "query_optimizer": query_optimizer is not None,
        "pool_manager": pool_manager is not None,
        "rate_limiter": rate_limiter is not None
    }

    all_healthy = all(components.values())

    return {
        "status": "healthy" if all_healthy else "degraded",
        "components": components,
        "timestamp": datetime.now().isoformat()
    }
