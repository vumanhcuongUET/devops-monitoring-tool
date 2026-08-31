"""Rate limiter middleware - supports both in-memory and Redis-based limiting."""
import ipaddress
import logging
import time
from collections import defaultdict

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

# Phase 15 P2-14: the per-key window dict used to grow without bound — every
# distinct client IP (including junk from a spoofed header behind a trusted
# proxy) allocated a list forever. Keys are swept when stale and the dict is
# hard-capped; overflow evicts the oldest key (rate-limiting degrades to a
# fresh window for that key, it is never bypassed).
MAX_TRACKED_CLIENTS = 10_000
_SWEEP_INTERVAL_SECONDS = 60
_WINDOW_SECONDS = 60


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
        trusted_proxies: list[str] | None = None,
        use_redis: bool = False,
    ):
        super().__init__(app)
        self.rpm = requests_per_minute
        self.burst = burst
        self.use_redis = use_redis
        # Phase 15 P2-14: wired from settings.RATE_LIMIT_TRUSTED_PROXIES.
        # Empty (the default) means trust nobody — X-Forwarded-For/X-Real-IP
        # are ignored and the direct connection IP is the bucket. Behind an
        # ingress/NAT this collapses everyone into one bucket until the
        # deployment sets the proxy CIDRs, which is fail-closed: trusting
        # headers without this list would let any client forge its bucket.
        self.trusted_proxies = trusted_proxies or []
        self._last_sweep = 0.0

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

        try:
            client_ip = ipaddress.ip_address(ip)
        except ValueError:
            return False
        for proxy_cidr in self.trusted_proxies:
            if client_ip in ipaddress.ip_network(proxy_cidr, strict=False):
                return True
        return False

    @staticmethod
    def _is_valid_ip(value: str) -> bool:
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False

    def _client_id(self, request: Request) -> str:
        """Extract client IP with proper proxy validation.

        Priority:
        1. X-Forwarded-For chain, walked right-to-left past trusted proxies
        2. X-Real-IP if it parses as an IP and the proxy is trusted
        3. Otherwise, the direct connection IP
        """
        direct_ip = request.client.host if request.client else ""

        forwarded = request.headers.get("x-forwarded-for", "").strip()
        if forwarded and self._is_trusted_proxy(direct_ip):
            # "client, proxy1, proxy2" — the leftmost entry is
            # attacker-controlled whenever the client could send the header
            # itself; only proxies we trust may have appended entries. Walk
            # from the right, skip proxies we trust, and the first address
            # that is not a trusted proxy is the client.
            client_ip = ""
            for candidate in reversed([p.strip() for p in forwarded.split(",")]):
                if not candidate:
                    continue
                if self._is_trusted_proxy(candidate):
                    continue
                if self._is_valid_ip(candidate):
                    client_ip = candidate
                break
            if client_ip:
                return f"ip:{client_ip}"
            # Chain was entirely trusted proxies (or malformed) — fall
            # through to the direct connection IP.
            return f"ip:{direct_ip}"

        # X-Real-IP (set by nginx `set_real_ip_from`) — accepted only from a
        # trusted proxy and only if it actually parses as an IP, never
        # verbatim.
        real_ip = request.headers.get("x-real-ip", "").strip()
        if real_ip and self._is_trusted_proxy(direct_ip) and self._is_valid_ip(real_ip):
            return f"ip:{real_ip}"

        if forwarded:
            logger.warning(
                f"Untrusted proxy {direct_ip} attempted X-Forwarded-For spoofing"
            )

        # Fall back to direct connection IP
        return f"ip:{direct_ip or 'unknown'}"

    async def _is_limited_redis(self, client_id: str) -> tuple[bool, dict | None]:
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

    def _sweep_and_bound(self, now: float) -> None:
        """Keep the per-key window dict bounded (Phase 15 P2-14)."""
        if now - self._last_sweep >= _SWEEP_INTERVAL_SECONDS:
            self._last_sweep = now
            stale = [
                key for key, window in self._windows.items()
                if not window or now - window[-1] >= _WINDOW_SECONDS
            ]
            for key in stale:
                del self._windows[key]
        while len(self._windows) >= MAX_TRACKED_CLIENTS:
            # Insertion-order dict: evict the oldest key. The evicted client
            # simply starts a fresh window — limiting is degraded, never
            # bypassed, and only under a flood of that many distinct IPs.
            del self._windows[next(iter(self._windows))]

    async def _is_limited_memory(self, client_id: str) -> tuple[bool, dict | None]:
        """Check in-memory rate limit with info dict.

        Returns:
            Tuple of (is_limited: bool, info: dict or None)
        """
        now = time.time()
        self._sweep_and_bound(now)
        window = self._windows[client_id]
        # Remove entries older than 60s
        self._windows[client_id] = [t for t in window if now - t < _WINDOW_SECONDS]
        window = self._windows[client_id]

        if len(window) >= self.rpm:
            return True, {
                "limit": self.rpm,
                "remaining": 0,
                "reset": int(now + _WINDOW_SECONDS),
                "retry_after": _WINDOW_SECONDS,
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
            "reset": int(now + _WINDOW_SECONDS),
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
