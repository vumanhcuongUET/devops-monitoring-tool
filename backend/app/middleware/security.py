"""Security headers middleware for HTTP response hardening."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all HTTP responses.

    Headers added:
    - X-Content-Type-Options: nosniff - Prevent MIME type sniffing
    - X-Frame-Options: DENY - Prevent clickjacking
    - X-XSS-Protection: 1; mode=block - Enable XSS filter
    - Content-Security-Policy: Restrict resource loading
    - Strict-Transport-Security: Enforce HTTPS (only in production)
    - Referrer-Policy: Control referrer information leakage
    - Permissions-Policy: Restrict browser features
    """

    # CSP policy - hardened version without unsafe-eval
    # Note: unsafe-inline is retained for development; remove in production with nonce/hash
    CSP_POLICY = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "  # TODO: Remove 'unsafe-inline' - use nonce/hash based CSP
        "style-src 'self' 'unsafe-inline'; "     # Required for inline styles in development
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Apply security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = self.CSP_POLICY
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions-Policy (formerly Feature-Policy)
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "accelerometer=()"
        )

        # HSTS only for HTTPS connections (production)
        if request.url.scheme == "https":
            # 1 year max-age, include subdomains
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Cache control for API responses (prevent sensitive data caching)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"

        return response
