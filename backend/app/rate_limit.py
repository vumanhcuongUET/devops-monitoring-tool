"""In-memory rate limiter middleware."""
import time
import logging
from collections import defaultdict
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple sliding-window rate limiter per client IP.

    Security features:
    - Validates X-Forwarded-For against trusted proxy list
    - Falls back to direct connection IP if forwarded is untrusted
    - Prevents IP spoofing attacks
    """

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        burst: int = 20,
        trusted_proxies: Optional[list[str]] = None
    ):
        super().__init__(app)
        self.rpm = requests_per_minute
        self.burst = burst
        self._windows: dict[str, list[float]] = defaultdict(list)
        # If None, no X-Forwarded-For is trusted (use direct IP only)
        # If ["10.0.0.0/8", "172.16.0.0/12"], only these CIDR ranges are trusted
        self.trusted_proxies = trusted_proxies or []

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
            return real_ip

        # Try X-Forwarded-For (only if from trusted proxy)
        forwarded = request.headers.get("x-forwarded-for", "").strip()
        if forwarded:
            # Check if the immediate connection is from a trusted proxy
            direct_ip = request.client.host if request.client else ""
            if self._is_trusted_proxy(direct_ip):
                # X-Forwarded-For format: "client, proxy1, proxy2"
                # Take the leftmost (original client) IP
                client_ip = forwarded.split(",")[0].strip()
                return client_ip
            else:
                # Untrusted proxy trying to spoof - ignore X-Forwarded-For
                logger.warning(
                    f"Untrusted proxy {direct_ip} attempted X-Forwarded-For spoofing"
                )

        # Fall back to direct connection IP
        return request.client.host if request.client else "unknown"

    def _is_limited(self, client_id: str) -> bool:
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

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path == "/health":
            return await call_next(request)

        client_id = self._client_id(request)
        if self._is_limited(client_id):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Try again later."},
                headers={"Retry-After": "60"},
            )
        return await call_next(request)
