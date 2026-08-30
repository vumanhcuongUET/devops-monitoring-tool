"""Security headers middleware for HTTP response hardening."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all HTTP responses.

    Headers added:
    - X-Content-Type-Options: nosniff - Prevent MIME type sniffing
    - X-Frame-Options: DENY - Prevent clickjacking
    - X-XSS-Protection: 1; mode=block - Enable XSS filter
    - Content-Security-Policy: Restrict resource loading
    - Strict-Transport-Security: Enforce HTTPS (only over https)
    - Referrer-Policy: Control referrer information leakage
    - Permissions-Policy: Restrict browser features
    """

    def __init__(self, app):
        """Initialize the security middleware.

        Args:
            app: The ASGI application
        """
        super().__init__(app)

    def _build_csp_policy(self, environment: str = "production") -> str:
        """Build Content-Security-Policy header.

        Args:
            environment: Environment name (development/staging/production)

        Returns:
            CSP policy string
        """
        directives = [
            "default-src 'self'",
            "connect-src 'self'",
            "img-src 'self' data: https:",
            "font-src 'self' data:",
        ]

        # In development, allow unsafe-inline for easier debugging
        if environment == "development":
            directives.append("script-src 'self' 'unsafe-inline'")
            directives.append("style-src 'self' 'unsafe-inline'")
        else:
            directives.append("script-src 'self'")
            directives.append("style-src 'self'")

        # Additional directives
        directives.extend([
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
            "upgrade-insecure-requests",
        ])

        return "; ".join(directives)

    async def dispatch(self, request: Request, call_next):
        """Process request and add security headers.

        Args:
            request: The incoming HTTP request
            call_next: The next middleware/handler in the chain

        Returns:
            HTTP response with security headers
        """
        # Environment comes from server config, never from client-controlled headers.
        environment = getattr(request.state, "environment", settings.ENVIRONMENT)

        response: Response = await call_next(request)

        # Build CSP policy
        csp_policy = self._build_csp_policy(environment=environment)

        # Apply security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = csp_policy
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
