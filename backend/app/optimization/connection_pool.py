"""
Connection Pool Manager - Phase 7 Sprint 3 Day 22

Purpose: Manage connection pools for optimal concurrent request handling

Features:
- HTTP connection pooling
- Database connection pooling
- Async connection management
- Pool statistics and monitoring
- Automatic pool resizing
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class PoolType(Enum):
    """Types of connection pools."""
    HTTP = "http"
    DATABASE = "database"
    REDIS = "redis"
    ELASTICSEARCH = "elasticsearch"


@dataclass
class PoolConfig:
    """Configuration for a connection pool."""
    pool_type: PoolType
    max_connections: int = 10
    min_connections: int = 2
    max_idle_time: int = 300  # seconds
    connection_timeout: int = 30  # seconds
    acquire_timeout: int = 10  # seconds
    health_check_interval: int = 60  # seconds
    enable_health_checks: bool = True

    class Config:
        use_enum_values = True


@dataclass
class PoolStats:
    """Statistics for a connection pool."""
    pool_name: str
    pool_type: str
    total_connections: int
    active_connections: int
    idle_connections: int
    waiting_requests: int
    failed_acquisitions: int = 0
    total_acquisitions: int = 0
    successful_acquisitions: int = 0
    avg_acquire_time_ms: float = 0
    last_health_check: Optional[str] = None
    is_healthy: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pool_name": self.pool_name,
            "pool_type": self.pool_type,
            "total_connections": self.total_connections,
            "active_connections": self.active_connections,
            "idle_connections": self.idle_connections,
            "waiting_requests": self.waiting_requests,
            "failed_acquisitions": self.failed_acquisitions,
            "total_acquisitions": self.total_acquisitions,
            "successful_acquisitions": self.successful_acquisitions,
            "avg_acquire_time_ms": self.avg_acquire_time_ms,
            "last_health_check": self.last_health_check,
            "is_healthy": self.is_healthy,
            "utilization_percent": (
                self.active_connections / self.total_connections * 100
                if self.total_connections > 0 else 0
            )
        }


class PooledConnection:
    """A pooled connection wrapper."""

    def __init__(
        self,
        connection: Any,
        pool: 'ConnectionPool',
        created_at: Optional[datetime] = None
    ):
        """Initialize pooled connection."""
        self.connection = connection
        self.pool = pool
        self.created_at = created_at or datetime.now()
        self.last_used = self.created_at
        self.is_active = True

    async def release(self):
        """Release connection back to pool."""
        self.is_active = False
        self.last_used = datetime.now()
        await self.pool._return_connection(self)


class ConnectionPool:
    """
    Manage a pool of connections.

    Features:
    - Connection reuse
    - Automatic cleanup
    - Health monitoring
    - Timeout handling
    """

    def __init__(
        self,
        name: str,
        config: PoolConfig,
        connection_factory: Optional[callable] = None
    ):
        """
        Initialize connection pool.

        Args:
            name: Pool name
            config: Pool configuration
            connection_factory: Factory function for new connections
        """
        self.name = name
        self.config = config
        self.connection_factory = connection_factory

        # Connection storage
        self.connections: List[PooledConnection] = []
        self.waiting_queue: asyncio.Queue = asyncio.Queue()

        # Statistics
        self.stats = {
            "total_acquisitions": 0,
            "successful_acquisitions": 0,
            "failed_acquisitions": 0,
            "total_acquire_time_ms": 0
        }

        # Health check task
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False

        # Lock for thread safety
        self._lock = asyncio.Lock()

    async def start(self):
        """Start the connection pool."""
        if not self._running:
            self._running = True

            # Initialize minimum connections
            await self._initialize_min_connections()

            # Start health check task
            if self.config.enable_health_checks:
                self._health_check_task = asyncio.create_task(
                    self._health_check_loop()
                )

            logger.info(f"Started connection pool: {self.name}")

    async def stop(self):
        """Stop the connection pool."""
        if self._running:
            self._running = False

            # Stop health check task
            if self._health_check_task:
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass

            # Close all connections
            await self._close_all_connections()

            logger.info(f"Stopped connection pool: {self.name}")

    async def acquire(self, timeout: Optional[float] = None) -> PooledConnection:
        """
        Acquire a connection from the pool.

        Args:
            timeout: Acquisition timeout in seconds

        Returns:
            PooledConnection

        Raises:
            asyncio.TimeoutError: If timeout expires
        """
        timeout = timeout or self.config.acquire_timeout
        start_time = datetime.now()

        async with self._lock:
            # Try to get idle connection
            idle_conn = self._get_idle_connection()
            if idle_conn:
                self.stats["total_acquisitions"] += 1
                self.stats["successful_acquisitions"] += 1
                acquire_time = (datetime.now() - start_time).total_seconds() * 1000
                self.stats["total_acquire_time_ms"] += acquire_time
                idle_conn.is_active = True
                return idle_conn

            # Check if we can create new connection
            if len(self.connections) < self.config.max_connections:
                new_conn = await self._create_connection()
                self.stats["total_acquisitions"] += 1
                self.stats["successful_acquisitions"] += 1
                return new_conn

        # Wait for connection to become available
        try:
            conn = await asyncio.wait_for(
                self.waiting_queue.get(),
                timeout=timeout
            )
            self.stats["total_acquisitions"] += 1
            self.stats["successful_acquisitions"] += 1
            acquire_time = (datetime.now() - start_time).total_seconds() * 1000
            self.stats["total_acquire_time_ms"] += acquire_time
            conn.is_active = True
            return conn

        except asyncio.TimeoutError:
            self.stats["total_acquisitions"] += 1
            self.stats["failed_acquisitions"] += 1
            logger.warning(f"Connection acquisition timeout: {self.name}")
            raise

    async def _return_connection(self, connection: PooledConnection):
        """Return a connection to the pool."""
        async with self._lock:
            if not self._running:
                # Pool is shutting down, close connection
                await self._close_connection(connection)
                return

            # Check if connection is too old
            age = (datetime.now() - connection.created_at).total_seconds()
            if age > self.config.max_idle_time:
                await self._close_connection(connection)
                return

            # Return connection to idle pool
            connection.is_active = False
            connection.last_used = datetime.now()

            # Notify waiting task if any
            if not self.waiting_queue.empty():
                try:
                    self.waiting_queue.put_nowait(connection)
                except asyncio.QueueFull:
                    logger.warning(f"Waiting queue full for {self.name}, connection not queued")

    def _get_idle_connection(self) -> Optional[PooledConnection]:
        """Get an idle connection from the pool."""
        # Collect unhealthy connections first to avoid modifying list during iteration
        unhealthy_connections = []
        idle_connection = None

        for conn in self.connections:
            if not conn.is_active:
                # Check if connection is healthy
                if self._is_connection_healthy(conn):
                    idle_connection = conn
                    break  # Found an idle connection, use it
                else:
                    unhealthy_connections.append(conn)

        # Remove unhealthy connections after iteration
        for conn in unhealthy_connections:
            if conn in self.connections:
                self.connections.remove(conn)

        return idle_connection

    async def _create_connection(self) -> PooledConnection:
        """Create a new connection."""
        if self.connection_factory:
            try:
                raw_conn = await self.connection_factory()
                conn = PooledConnection(raw_conn, self)
                self.connections.append(conn)
                logger.debug(f"Created new connection for {self.name}")
                return conn
            except Exception as e:
                logger.error(f"Failed to create connection: {e}")
                raise

        raise RuntimeError("No connection factory configured")

    async def _close_connection(self, connection: PooledConnection):
        """Close a connection."""
        try:
            if hasattr(connection.connection, 'close'):
                await connection.connection.close()
        except Exception as e:
            logger.warning(f"Error closing connection: {e}")

        if connection in self.connections:
            self.connections.remove(connection)

    async def _close_all_connections(self):
        """Close all connections in the pool."""
        for conn in self.connections.copy():
            await self._close_connection(conn)

    async def _initialize_min_connections(self):
        """Initialize minimum number of connections."""
        while len(self.connections) < self.config.min_connections:
            try:
                await self._create_connection()
            except Exception as e:
                logger.error(f"Failed to initialize connection: {e}")
                break

    def _is_connection_healthy(self, connection: PooledConnection) -> bool:
        """Check if a connection is healthy."""
        # Check if connection is too old
        age = (datetime.now() - connection.created_at).total_seconds()
        if age > self.config.max_idle_time:
            return False

        # Could add more health checks here
        return True

    async def _health_check_loop(self):
        """Background health check loop."""
        while self._running:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self._perform_health_checks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")

    async def _perform_health_checks(self):
        """Perform health checks on all connections."""
        async with self._lock:
            unhealthy = []

            for conn in self.connections:
                if not self._is_connection_healthy(conn):
                    unhealthy.append(conn)

            # Remove unhealthy connections
            for conn in unhealthy:
                await self._close_connection(conn)

            # Ensure minimum connections
            while len(self.connections) < self.config.min_connections:
                try:
                    await self._create_connection()
                except:
                    break

    def get_stats(self) -> PoolStats:
        """Get pool statistics."""
        active = sum(1 for c in self.connections if c.is_active)
        idle = len(self.connections) - active

        total_acq = self.stats["total_acquisitions"]
        avg_time = (
            self.stats["total_acquire_time_ms"] / total_acq
            if total_acq > 0 else 0
        )

        return PoolStats(
            pool_name=self.name,
            pool_type=self.config.pool_type.value,
            total_connections=len(self.connections),
            active_connections=active,
            idle_connections=idle,
            waiting_requests=self.waiting_queue.qsize(),
            failed_acquisitions=self.stats["failed_acquisitions"],
            total_acquisitions=self.stats["total_acquisitions"],
            successful_acquisitions=self.stats["successful_acquisitions"],
            avg_acquire_time_ms=avg_time
        )


class ConnectionPoolManager:
    """
    Manage multiple connection pools.

    Features:
    - Centralized pool management
    - Automatic pool creation
    - Pool statistics aggregation
    - Health monitoring
    """

    def __init__(self):
        """Initialize connection pool manager."""
        self.pools: Dict[str, ConnectionPool] = {}
        self._running = False
        self._lock = asyncio.Lock()  # Added lock for thread safety

    async def start(self):
        """Start all managed pools."""
        async with self._lock:
            self._running = True
            for pool in list(self.pools.values()):  # Use list() to avoid modification during iteration
                await pool.start()
        logger.info("Started all connection pools")

    async def stop(self):
        """Stop all managed pools."""
        async with self._lock:
            self._running = False
            for pool in list(self.pools.values()):  # Use list() to avoid modification during iteration
                await pool.stop()
        logger.info("Stopped all connection pools")

    def create_pool(
        self,
        name: str,
        config: PoolConfig,
        connection_factory: Optional[callable] = None
    ) -> ConnectionPool:
        """
        Create a new connection pool.

        Args:
            name: Pool name
            config: Pool configuration
            connection_factory: Factory function for new connections

        Returns:
            ConnectionPool instance
        """
        if name in self.pools:
            raise ValueError(f"Pool {name} already exists")

        pool = ConnectionPool(name, config, connection_factory)

        async def _create_and_start():
            async with self._lock:
                self.pools[name] = pool
                if self._running:
                    await pool.start()

        # Schedule the pool creation and start
        task = asyncio.create_task(_create_and_start())

        return pool

    def get_pool(self, name: str) -> Optional[ConnectionPool]:
        """Get a pool by name."""
        return self.pools.get(name)

    async def acquire_from_pool(
        self,
        pool_name: str,
        timeout: Optional[float] = None
    ) -> Optional[PooledConnection]:
        """Acquire a connection from a specific pool."""
        pool = self.get_pool(pool_name)
        if not pool:
            raise ValueError(f"Pool {pool_name} not found")

        return await pool.acquire(timeout)

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all pools."""
        # Get a snapshot of pools to avoid race conditions
        pools_snapshot = dict(self.pools)
        return {
            name: pool.get_stats().to_dict()
            for name, pool in pools_snapshot.items()
        }

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all pools."""
        results = {}
        # Get a snapshot of pools to avoid race conditions
        pools_snapshot = dict(self.pools)

        for name, pool in pools_snapshot.items():
            stats = pool.get_stats()
            results[name] = {
                "healthy": stats.is_healthy,
                "connections": stats.total_connections,
                "utilization": stats.to_dict()["utilization_percent"]
            }

        return {
            "total_pools": len(pools_snapshot),
            "healthy_pools": sum(1 for r in results.values() if r["healthy"]),
            "pools": results
        }

    def create_http_pool(
        self,
        name: str,
        max_connections: int = 100,
        limit_per_host: int = 10
    ) -> ConnectionPool:
        """Create an HTTP connection pool."""
        config = PoolConfig(
            pool_type=PoolType.HTTP,
            max_connections=max_connections,
            min_connections=2
        )
        return self.create_pool(name, config)

    def create_database_pool(
        self,
        name: str,
        max_connections: int = 20,
        min_connections: int = 2
    ) -> ConnectionPool:
        """Create a database connection pool."""
        config = PoolConfig(
            pool_type=PoolType.DATABASE,
            max_connections=max_connections,
            min_connections=min_connections
        )
        return self.create_pool(name, config)


class RateLimiter:
    """
    Rate limiter for concurrent request handling.

    Features:
    - Token bucket algorithm
    - Per-endpoint limiting
    - Adaptive rate limiting
    - Distributed coordination support
    """

    def __init__(
        self,
        default_rate: float = 100.0,  # requests per second
        burst: int = 10
    ):
        """
        Initialize rate limiter.

        Args:
            default_rate: Default rate limit (requests/second)
            burst: Burst capacity
        """
        self.default_rate = default_rate
        self.burst = burst

        # Per-endpoint rate limits
        self.endpoint_limits: Dict[str, Dict[str, float]] = {}

        # Token buckets
        self.buckets: Dict[str, float] = {}
        self._lock = asyncio.Lock()

        # Statistics
        self.stats = {
            "total_requests": 0,
            "allowed_requests": 0,
            "rejected_requests": 0,
            "endpoint_stats": {}
        }

    async def acquire(
        self,
        endpoint: str,
        tokens: int = 1
    ) -> bool:
        """
        Acquire tokens for a request.

        Args:
            endpoint: Endpoint identifier
            tokens: Number of tokens required

        Returns:
            True if request allowed, False otherwise
        """
        async with self._lock:
            self.stats["total_requests"] += 1

            # Get rate limit for endpoint
            endpoint_config = self.endpoint_limits.get(endpoint, {})
            rate = endpoint_config.get("rate", self.default_rate)
            burst = endpoint_config.get("burst", self.burst)  # Use endpoint-specific burst

            # Get or create token bucket
            if endpoint not in self.buckets:
                # Initialize with burst capacity
                self.buckets[endpoint] = burst

            bucket = self.buckets[endpoint]

            # Check if enough tokens
            if bucket >= tokens:
                bucket -= tokens
                self.stats["allowed_requests"] += 1
                self._update_endpoint_stats(endpoint, True)
                return True
            else:
                self.stats["rejected_requests"] += 1
                self._update_endpoint_stats(endpoint, False)
                return False

    async def replenish(self, endpoint: str):
        """Replenish tokens for an endpoint."""
        async with self._lock:
            rate = self.endpoint_limits.get(endpoint, {}).get("rate", self.default_rate)

            if endpoint not in self.buckets:
                self.buckets[endpoint] = 0

            # Add tokens (max burst capacity)
            self.buckets[endpoint] = min(
                self.buckets[endpoint] + rate,
                self.burst
            )

    async def set_endpoint_limit(
        self,
        endpoint: str,
        rate: float,
        burst: Optional[int] = None
    ):
        """Set rate limit for an endpoint."""
        async with self._lock:
            self.endpoint_limits[endpoint] = {
                "rate": rate,
                "burst": burst or self.burst
            }

    async def start_background_replenish(self, interval: float = 1.0):
        """Start background token replenishment."""
        while True:
            try:
                await asyncio.sleep(interval)

                # Get a snapshot of endpoints to replenish to avoid holding lock during iteration
                endpoints_to_replenish = []

                async with self._lock:
                    # Replenish all endpoints with custom limits
                    for endpoint in self.endpoint_limits:
                        endpoints_to_replenish.append(endpoint)

                    # Also add unknown endpoints
                    for endpoint in self.buckets:
                        if endpoint not in self.endpoint_limits:
                            endpoints_to_replenish.append(endpoint)

                # Replenish outside the lock to avoid deadlock
                for endpoint in endpoints_to_replenish:
                    await self.replenish(endpoint)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in replenish loop: {e}")

    def _update_endpoint_stats(self, endpoint: str, allowed: bool):
        """Update statistics for an endpoint."""
        if endpoint not in self.stats["endpoint_stats"]:
            self.stats["endpoint_stats"][endpoint] = {
                "total": 0,
                "allowed": 0,
                "rejected": 0
            }

        stats = self.stats["endpoint_stats"][endpoint]
        stats["total"] += 1
        if allowed:
            stats["allowed"] += 1
        else:
            stats["rejected"] += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        return {
            "total_requests": self.stats["total_requests"],
            "allowed_requests": self.stats["allowed_requests"],
            "rejected_requests": self.stats["rejected_requests"],
            "rejection_rate": (
                self.stats["rejected_requests"] / self.stats["total_requests"]
                if self.stats["total_requests"] > 0 else 0
            ),
            "endpoint_stats": self.stats["endpoint_stats"],
            "active_buckets": len(self.buckets)
        }
