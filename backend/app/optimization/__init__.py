"""
Optimization Module - Phase 7 Sprint 3

This module provides performance optimization capabilities:

- Query optimization with chunking and caching
- Response time optimization with streaming
- Concurrent request handling
- Connection pooling
- Performance profiling and monitoring

Components:
- QueryOptimizer: Optimize queries to ES, Prom, K8s
- QueryPatterns: Common optimized query patterns
- QueryProfiler: Profile and analyze query performance
- StreamingOptimizer: Optimize large responses with streaming
- ConnectionPoolManager: Manage connection pools
- ResponseOptimizer: Optimize API responses
- BatchProcessor: Process large datasets in batches
- VirtualScroller: Support virtual scrolling
- RateLimiter: Rate limiting for concurrent requests
"""

from .query_optimizer import (
    QueryOptimizer,
    QueryProfiler,
    QueryProfile,
    QueryType
)

from .query_patterns import (
    QueryPatterns,
    QueryPatternLibrary
)

from .streaming_optimizer import (
    StreamingOptimizer,
    StreamingChunk,
    ResponseOptimizer,
    VirtualScroller,
    BatchProcessor,
    CompressionType
)

from .connection_pool import (
    ConnectionPoolManager,
    ConnectionPool,
    PooledConnection,
    PoolConfig,
    PoolType,
    PoolStats,
    RateLimiter
)

__all__ = [
    # Query Optimization
    "QueryOptimizer",
    "QueryProfiler",
    "QueryProfile",
    "QueryType",
    # Query Patterns
    "QueryPatterns",
    "QueryPatternLibrary",
    # Streaming Optimization
    "StreamingOptimizer",
    "StreamingChunk",
    "ResponseOptimizer",
    "VirtualScroller",
    "BatchProcessor",
    "CompressionType",
    # Connection Pooling
    "ConnectionPoolManager",
    "ConnectionPool",
    "PooledConnection",
    "PoolConfig",
    "PoolType",
    "PoolStats",
    "RateLimiter",
]
