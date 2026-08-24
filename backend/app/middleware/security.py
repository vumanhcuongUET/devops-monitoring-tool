"""Security headers middleware for HTTP response hardening with nonce-based CSP."""

import secrets
import hashlib
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.datastructures import Headers


class CSPNonceManager:
    """Manage CSP nonces for inline script and style authorization."""

    def __init__(self):
        """Initialize the nonce manager."""
        self._request_nonce: dict[int, str] = {}

    def generate_nonce(self) -> str:
        """Generate a cryptographically secure random nonce.

        Returns:
            Base64-encoded random nonce
        """
        return secrets.token_urlsafe(16)

    def get_request_nonce(self, request: Request) -> str:
        """Get or create a nonce for the current request.

        Args:
            request: The current HTTP request

        Returns:
            The nonce for this request
        """
        # Use id(request) as a unique identifier per request
        request_id = id(request)

        if request_id not in self._request_nonce:
            self._request_nonce[request_id] = self.generate_nonce()

        return self._request_nonce[request_id]

    def cleanup_request(self, request: Request) -> None:
        """Clean up nonce for a completed request.

        Args:
            request: The completed request
        """
        request_id = id(request)
        self._request_nonce.pop(request_id, None)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all HTTP responses with nonce-based CSP.

    Headers added:
    - X-Content-Type-Options: nosniff - Prevent MIME type sniffing
    - X-Frame-Options: DENY - Prevent clickjacking
    - X-XSS-Protection: 1; mode=block - Enable XSS filter
    - Content-Security-Policy: Restrict resource loading with nonce support
    - Strict-Transport-Security: Enforce HTTPS (only in production)
    - Referrer-Policy: Control referrer information leakage
    - Permissions-Policy: Restrict browser features
    """

    # Script hashes for known inline scripts (for hash-based CSP)
    # These should be calculated from actual inline scripts in the application
    SCRIPT_HASHES = [
        # Add SHA-256 hashes of inline scripts here
        # Example: "sha256-abc123..."
    ]

    # Style hashes for known inline styles
    STYLE_HASHES = [
        # Add SHA-256 hashes of inline styles here
    ]

    def __init__(self, app, use_nonce: bool = True, use_hashes: bool = False):
        """Initialize the security middleware.

        Args:
            app: The ASGI application
            use_nonce: Enable nonce-based CSP (default: True)
            use_hashes: Enable hash-based CSP (default: False)
        """
        super().__init__(app)
        self.use_nonce = use_nonce
        self.use_hashes = use_hashes
        self.nonce_manager = CSPNonceManager() if use_nonce else None

    def _build_csp_policy(
        self,
        nonce: Optional[str] = None,
        environment: str = "production",
    ) -> str:
        """Build Content-Security-Policy header.

        Args:
            nonce: Optional nonce for inline scripts
            environment: Environment name (development/staging/production)

        Returns:
            CSP policy string
        """
        directives = [
            "default-src 'self'",
            "connect-src 'self'",
            "img-src 'self' data: https:",
            "font-src 'self' data:",
            "frame-ancestors 'none'",
        ]

        # Script source with nonce or hashes
        script_src = ["script-src 'self'"]

        if nonce:
            script_src.append(f"'nonce-{nonce}'")

        if self.use_hashes and self.SCRIPT_HASHES:
            script_src.extend(self.SCRIPT_HASHES)

        # In development, allow unsafe-inline for easier debugging
        if environment == "development" and not nonce:
            script_src.append("'unsafe-inline'")

        directives.append(" ".join(script_src))

        # Style source
        style_src = ["style-src 'self'"]

        if nonce:
            # Nonce can also be used for inline styles
            style_src.append(f"'nonce-{nonce}'")

        if self.use_hashes and self.STYLE_HASHES:
            style_src.extend(self.STYLE_HASHES)

        # In development, allow unsafe-inline for styles
        if environment == "development":
            style_src.append("'unsafe-inline'")

        directives.append(" ".join(style_src))

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
        # Get or create nonce for this request
        nonce = None
        if self.use_nonce and self.nonce_manager:
            nonce = self.nonce_manager.get_request_nonce(request)

        # Determine environment from request state or headers
        # State uses attribute access, not dict-like access
        environment = getattr(request.state, "environment", "production")
        if "x-environment" in request.headers:
            environment = request.headers["x-environment"]

        # Process the request
        response: Response = await call_next(request)

        # Build CSP policy with nonce
        csp_policy = self._build_csp_policy(nonce=nonce, environment=environment)

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

        # Pass nonce to frontend via response header for single-page apps
        # The frontend can read this header and use it for inline scripts
        if nonce:
            response.headers["X-CSP-Nonce"] = nonce

        # Clean up nonce after request is complete
        if self.use_nonce and self.nonce_manager:
            self.nonce_manager.cleanup_request(request)

        return response


def calculate_script_hash(script_content: str) -> str:
    """Calculate SHA-256 hash of a script for CSP hash-based whitelisting.

    Args:
        script_content: The JavaScript content to hash

    Returns:
        The SHA-256 hash in CSP format (sha256-...)
    """
    import base64

    # Remove leading/trailing whitespace and normalize
    normalized = script_content.strip()

    # Calculate SHA-256 hash
    hash_digest = hashlib.sha256(normalized.encode()).digest()

    # Encode to base64
    hash_b64 = base64.b64encode(hash_digest).decode()

    return f"sha256-{hash_b64}"


def calculate_style_hash(style_content: str) -> str:
    """Calculate SHA-256 hash of a style for CSP hash-based whitelisting.

    Args:
        style_content: The CSS content to hash

    Returns:
        The SHA-256 hash in CSP format (sha256-...)
    """
    import base64

    # Remove leading/trailing whitespace and normalize
    normalized = style_content.strip()

    # Calculate SHA-256 hash
    hash_digest = hashlib.sha256(normalized.encode()).digest()

    # Encode to base64
    hash_b64 = base64.b64encode(hash_digest).decode()

    return f"sha256-{hash_b64}"


# Helper function to add script hash to middleware configuration
def add_known_script_hash(script_content: str) -> str:
    """Add a known script hash to the CSP middleware configuration.

    Args:
        script_content: The JavaScript content to hash and add

    Returns:
        The hash that was added
    """
    hash_value = calculate_script_hash(script_content)
    SecurityHeadersMiddleware.SCRIPT_HASHES.append(hash_value)
    return hash_value


# Helper function to add style hash to middleware configuration
def add_known_style_hash(style_content: str) -> str:
    """Add a known style hash to the CSP middleware configuration.

    Args:
        style_content: The CSS content to hash and add

    Returns:
        The hash that was added
    """
    hash_value = calculate_style_hash(style_content)
    SecurityHeadersMiddleware.STYLE_HASHES.append(hash_value)
    return hash_value
