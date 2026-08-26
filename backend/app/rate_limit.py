"""Rate limiter middleware - supports both in-memory and Redis-based limiting."""
import time
import logging
from collections import defaultdict
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Import Redis rate limiter when needed
try:
    from app.rate_limiting.redis_rate_limiter import create_redis_rate_limiter
    REDIS_RATE_LIMITER_AVAILABLE = True
except ImportError:
    REDIS_RATE_LIMITER_AVAILABLE = False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiter with support for in-memory and Redis backends.

    Security features:
    - Validates X-Forwarded-For against trusted proxy list
    - Falls back to direct connection IP if forwarded is untrusted
    - Prevents IP spoofing attacks
    - Supports distributed rate limiting via Redis

    Backend selection:
    - use_redis=False: In-memory (default, single pod)
    - use_redis=True: Redis-backed (distributed across multiple pods)
    """

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        burst: int = 20,
        trusted_proxies: Optional[list[str]] = None,
        use_redis: bool = False,
    ):
        super().__init__(app)
        self.rpm = requests_per_minute
        self.burst = burst
        self.use_redis = use_redis
        self.trusted_proxies = trusted_proxies or []

        if not use_redis:
            # In-memory backend
            self._windows: dict[str, list[float]] = defaultdict(list)
            self._redis_limiter = None
        else:
            # Redis backend
            try:
                if REDIS_RATE_LIMITER_AVAILABLE:
                    self._redis_limiter = create_redis_rate_limiter()
                    self._windows = None  # Not used in Redis mode
                else:
                    raise ImportError("Redis rate limiter not available")
            except ImportError:
                logger.warning("Redis not available, falling back to in-memory rate limiting")
                self.use_redis = False
                self._windows: dict[str, list[float]] = defaultdict(list)
                self._redis_limiter = None

    def _is_trusted_proxy(self, ip: str) -> bool:
        """Check if an IP is in the trusted proxy list."""
        if not self.trusted_proxies:
            return False

        import ipaddress
        try:
            client_ip = ipaddress.ip_address(ip)
            for proxy_cidr in self.trusted_proxies:
                if client_ip in ipaddress.ip_network(proxy_cidr, strict=False):
                    return True
        except ValueError:
            logger.warning(f"Invalid IP address: {ip}")
        return False

    def _client_id(self, request: Request) -> str:
        """Extract client IP with proper proxy validation.

        Priority:
        1. If X-Real-IP header exists and proxy is trusted, use it
        2. If X-Forwarded-For exists and proxy is trusted, use first IP
        3. Otherwise, use direct connection IP
        """
        # Try X-Real-IP first (set by nginx when using set_real_ip_from)
        real_ip = request.headers.get("x-real-ip", "").strip()
        if real_ip and self._is_trusted_proxy(
            request.client.host if request.client else ""
        ):
            return f"ip:{real_ip}"

        # Try X-Forwarded-For (only if from trusted proxy)
        forwarded = request.headers.get("x-forwarded-for", "").strip()
        if forwarded:
            # Check if the immediate connection is from a trusted proxy
            direct_ip = request.client.host if request.client else ""
            if self._is_trusted_proxy(direct_ip):
                # X-Forwarded-For format: "client, proxy1, proxy2"
                # Take the leftmost (original client) IP
                client_ip = forwarded.split(",")[0].strip()
                return f"ip:{client_ip}"
            else:
                # Untrusted proxy trying to spoof - ignore X-Forwarded-For
                logger.warning(
                    f"Untrusted proxy {direct_ip} attempted X-Forwarded-For spoofing"
                )

        # Fall back to direct connection IP
        direct_ip = request.client.host if request.client else "unknown"
        return f"ip:{direct_ip}"

    async def _is_limited_redis(self, client_id: str) -> tuple[bool, Optional[dict]]:
        """Check Redis-based rate limit.

        Returns:
            Tuple of (is_limited: bool, info: dict or None)
        """
        if not self._redis_limiter:
            return False, None

        # Check with Redis (sliding window)
        allowed, info = await self._redis_limiter.check_rate_limit(
            key=client_id,
            max_requests=self.rpm,
            window_seconds=60,
        )

        return not allowed, info

    def _is_limited(self, client_id: str) -> bool:
        """Check in-memory rate limit."""
        now = time.time()
        window = self._windows[client_id]
        # Remove entries older than 60s
        self._windows[client_id] = [t for t in window if now - t < 60]
        window = self._windows[client_id]

        if len(window) >= self.rpm:
            return True
        # Burst check: more than `burst` requests in last 2s
        recent = sum(1 for t in window if now - t < 2)
        if recent >= self.burst:
            return True

        window.append(now)
        return False

    async def _is_limited_memory(self, client_id: str) -> tuple[bool, Optional[dict]]:
        """Check in-memory rate limit with info dict.

        Returns:
            Tuple of (is_limited: bool, info: dict or None)
        """
        now = time.time()
        window = self._windows[client_id]
        # Remove entries older than 60s
        self._windows[client_id] = [t for t in window if now - t < 60]
        window = self._windows[client_id]

        if len(window) >= self.rpm:
            return True, {
                "limit": self.rpm,
                "remaining": 0,
                "reset": int(now + 60),
                "retry_after": 60,
            }

        # Burst check: more than `burst` requests in last 2s
        recent = sum(1 for t in window if now - t < 2)
        if recent >= self.burst:
            return True, {
                "limit": self.rpm,
                "remaining": 0,
                "reset": int(now + 2),
                "retry_after": 2,
            }

        window.append(now)
        remaining = self.rpm - len(window)
        return False, {
            "limit": self.rpm,
            "remaining": max(0, remaining - 1),
            "reset": int(now + 60),
            "retry_after": 0,
        }

    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting."""
        # Phase 10 Sprint 1 Day 2: Bug Fix - Add OAuth2 redirect endpoint
        # Skip rate limiting for health checks, docs, and OAuth2 redirect
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"]:
            return await call_next(request)

        client_id = self._client_id(request)

        if self.use_redis and self._redis_limiter:
            # Redis-based rate limiting
            is_limited, info = await self._is_limited_redis(client_id)

            if is_limited and info:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded", "retry_after": info["retry_after"]},
                    headers={
                        "Retry-After": str(info["retry_after"]),
                        "X-RateLimit-Limit": str(info["limit"]),
                        "X-RateLimit-Remaining": str(info["remaining"]),
                        "X-RateLimit-Reset": str(info["reset"]),
                    },
                )
            elif info:
                # Add rate limit headers to response
                response = await call_next(request)
                response.headers["X-RateLimit-Limit"] = str(info["limit"])
                response.headers["X-RateLimit-Remaining"] = str(max(0, info["remaining"]))
                response.headers["X-RateLimit-Reset"] = str(info["reset"])
                return response
        else:
            # In-memory rate limiting
            is_limited, info = await self._is_limited_memory(client_id)

            if is_limited and info:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                    headers={
                        "Retry-After": str(info["retry_after"]),
                        "X-RateLimit-Limit": str(info["limit"]),
                        "X-RateLimit-Remaining": str(info["remaining"]),
                        "X-RateLimit-Reset": str(info["reset"]),
                    },
                )
            elif info:
                # Add rate limit headers to response
                response = await call_next(request)
                response.headers["X-RateLimit-Limit"] = str(info["limit"])
                response.headers["X-RateLimit-Remaining"] = str(max(0, info["remaining"]))
                response.headers["X-RateLimit-Reset"] = str(info["reset"])
                return response

        return await call_next(request)
