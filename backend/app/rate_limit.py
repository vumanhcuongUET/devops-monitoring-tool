"""In-memory rate limiter middleware."""
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple sliding-window rate limiter per client IP."""

    def __init__(self, app, requests_per_minute: int = 60, burst: int = 20):
        super().__init__(app)
        self.rpm = requests_per_minute
        self.burst = burst
        self._windows: dict[str, list[float]] = defaultdict(list)

    def _client_id(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
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
