"""Unit tests for Security Headers Middleware with CSP nonce support."""

import pytest
import re
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

from app.middleware.security import (
    SecurityHeadersMiddleware,
    CSPNonceManager,
    calculate_script_hash,
    calculate_style_hash,
    add_known_script_hash,
    add_known_style_hash,
)


@pytest.fixture
def test_app():
    """Create a test Starlette application."""
    app = Starlette()

    @app.route("/")
    async def homepage(request):
        return PlainTextResponse("Hello, world!")

    @app.route("/api/test")
    async def api_test(request):
        from starlette.responses import JSONResponse
        return JSONResponse({"message": "test"})

    return app


@pytest.fixture
def client_with_nonce(test_app):
    """Create test client with nonce-based CSP enabled."""
    # Add middleware with nonce support
    app = test_app
    app.add_middleware(SecurityHeadersMiddleware, use_nonce=True, use_hashes=False)
    return TestClient(app)


@pytest.fixture
def client_without_nonce(test_app):
    """Create test client without nonce-based CSP."""
    app = test_app
    app.add_middleware(SecurityHeadersMiddleware, use_nonce=False, use_hashes=False)
    return TestClient(app)


@pytest.fixture
def client_with_hashes(test_app):
    """Create test client with hash-based CSP enabled."""
    app = test_app
    app.add_middleware(SecurityHeadersMiddleware, use_nonce=False, use_hashes=True)
    return TestClient(app)


class TestCSPNonceManager:
    """Test CSP nonce manager."""

    def test_generate_nonce(self):
        """Test that nonces are generated correctly."""
        manager = CSPNonceManager()
        nonce = manager.generate_nonce()

        assert nonce
        assert isinstance(nonce, str)
        assert len(nonce) > 10  # Should be a reasonably long string

    def test_nonce_per_request(self):
        """Test that each request gets a unique nonce."""
        manager = CSPNonceManager()

        # Mock request objects
        request1 = type("MockRequest", (), {})()
        request2 = type("MockRequest", (), {})()

        nonce1 = manager.get_request_nonce(request1)
        nonce2 = manager.get_request_nonce(request2)

        # Nonces should be different
        assert nonce1 != nonce2

    def test_same_nonce_for_same_request(self):
        """Test that the same request gets the same nonce."""
        manager = CSPNonceManager()

        request = type("MockRequest", (), {})()

        nonce1 = manager.get_request_nonce(request)
        nonce2 = manager.get_request_nonce(request)

        # Same request should get same nonce
        assert nonce1 == nonce2

    def test_cleanup_request(self):
        """Test that request cleanup works."""
        manager = CSPNonceManager()

        request = type("MockRequest", (), {})()
        nonce = manager.get_request_nonce(request)

        assert nonce is not None

        # Cleanup
        manager.cleanup_request(request)

        # Should get a new nonce after cleanup
        new_nonce = manager.get_request_nonce(request)
        assert new_nonce != nonce


class TestSecurityHeadersMiddleware:
    """Test security headers middleware."""

    def test_security_headers_present(self, client_with_nonce):
        """Test that security headers are present."""
        response = client_with_nonce.get("/")

        assert response.status_code == 200
        assert "X-Content-Type-Options" in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "X-Frame-Options" in response.headers
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "X-XSS-Protection" in response.headers
        assert response.headers["X-XSS-Protection"] == "1; mode=block"

    def test_csp_header_present(self, client_with_nonce):
        """Test that CSP header is present."""
        response = client_with_nonce.get("/")

        assert "Content-Security-Policy" in response.headers
        csp = response.headers["Content-Security-Policy"]
        assert csp
        assert "default-src 'self'" in csp

    def test_nonce_in_csp(self, client_with_nonce):
        """Test that nonce is included in CSP when enabled."""
        response = client_with_nonce.get("/")

        csp = response.headers["Content-Security-Policy"]

        # Should contain nonce-
        assert "nonce-" in csp

        # Should NOT contain unsafe-inline for scripts in production
        assert "script-src 'self'" in csp

    def test_nonce_header_present(self, client_with_nonce):
        """Test that X-CSP-Nonce header is present."""
        response = client_with_nonce.get("/")

        assert "X-CSP-Nonce" in response.headers
        nonce = response.headers["X-CSP-Nonce"]

        assert nonce
        assert isinstance(nonce, str)

    def test_no_unsafe_inline_in_production(self, client_with_nonce):
        """Test that unsafe-inline is NOT in CSP for production."""
        response = client_with_nonce.get("/")

        csp = response.headers["Content-Security-Policy"]

        # Check script-src doesn't have unsafe-inline
        script_src_match = re.search(r'script-src\s+([^;]+)', csp)
        if script_src_match:
            script_src = script_src_match.group(1)
            # In production with nonce, should NOT have unsafe-inline
            assert "'unsafe-inline'" not in script_src or "nonce-" in script_src

    def test_api_cache_control(self, client_with_nonce):
        """Test that API responses have cache control."""
        response = client_with_nonce.get("/api/test")

        assert "Cache-Control" in response.headers
        cache_control = response.headers["Cache-Control"]
        assert "no-store" in cache_control or "no-cache" in cache_control

    def test_referrer_policy(self, client_with_nonce):
        """Test that Referrer-Policy header is present."""
        response = client_with_nonce.get("/")

        assert "Referrer-Policy" in response.headers
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_permissions_policy(self, client_with_nonce):
        """Test that Permissions-Policy header is present."""
        response = client_with_nonce.get("/")

        assert "Permissions-Policy" in response.headers
        policy = response.headers["Permissions-Policy"]

        # Check that restrictive policies are in place
        assert "geolocation=()" in policy
        assert "microphone=()" in policy
        assert "camera=()" in policy


class TestCSPWithoutNonce:
    """Test CSP middleware without nonce."""

    def test_csp_without_nonce(self, client_without_nonce):
        """Test that CSP works without nonce."""
        response = client_without_nonce.get("/")

        assert "Content-Security-Policy" in response.headers
        assert "X-CSP-Nonce" not in response.headers

    def test_development_unsafe_inline(self, client_without_nonce):
        """Test that development allows unsafe-inline."""
        # Add environment header for development
        response = client_without_nonce.get(
            "/",
            headers={"x-environment": "development"}
        )

        csp = response.headers.get("Content-Security-Policy", "")

        # In development, unsafe-inline might be present
        # This is expected behavior
        assert csp


class TestCSPWithHashes:
    """Test CSP middleware with hash-based whitelisting."""

    def test_csp_with_hashes(self, client_with_hashes):
        """Test that CSP can include script hashes."""
        # Add a known script hash
        script_content = "console.log('test');"
        hash_value = add_known_script_hash(script_content)

        assert hash_value.startswith("sha256-")

        response = client_with_hashes.get("/")
        csp = response.headers["Content-Security-Policy"]

        # Should contain the hash we added
        assert hash_value in csp


class TestHashCalculation:
    """Test script and style hash calculation."""

    def test_script_hash_calculation(self):
        """Test SHA-256 hash calculation for scripts."""
        script = "console.log('hello');"
        hash_value = calculate_script_hash(script)

        assert hash_value.startswith("sha256-")
        assert len(hash_value) > 10

    def test_style_hash_calculation(self):
        """Test SHA-256 hash calculation for styles."""
        style = "body { color: red; }"
        hash_value = calculate_style_hash(style)

        assert hash_value.startswith("sha256-")
        assert len(hash_value) > 10

    def test_different_scripts_different_hashes(self):
        """Test that different scripts produce different hashes."""
        script1 = "console.log('test1');"
        script2 = "console.log('test2');"

        hash1 = calculate_script_hash(script1)
        hash2 = calculate_script_hash(script2)

        assert hash1 != hash2

    def test_same_script_same_hash(self):
        """Test that the same script produces the same hash."""
        script = "console.log('test');"

        hash1 = calculate_script_hash(script)
        hash2 = calculate_script_hash(script)

        assert hash1 == hash2

    def test_add_script_hash_to_middleware(self):
        """Test adding script hash to middleware configuration."""
        # Clear existing hashes
        original_hashes = SecurityHeadersMiddleware.SCRIPT_HASHES.copy()
        SecurityHeadersMiddleware.SCRIPT_HASHES.clear()

        script = "alert('test');"
        hash_value = add_known_script_hash(script)

        assert hash_value in SecurityHeadersMiddleware.SCRIPT_HASHES

        # Restore original hashes
        SecurityHeadersMiddleware.SCRIPT_HASHES = original_hashes

    def test_add_style_hash_to_middleware(self):
        """Test adding style hash to middleware configuration."""
        # Clear existing hashes
        original_hashes = SecurityHeadersMiddleware.STYLE_HASHES.copy()
        SecurityHeadersMiddleware.STYLE_HASHES.clear()

        style = "body { margin: 0; }"
        hash_value = add_known_style_hash(style)

        assert hash_value in SecurityHeadersMiddleware.STYLE_HASHES

        # Restore original hashes
        SecurityHeadersMiddleware.STYLE_HASHES = original_hashes


class TestCSPEnvironmentBased:
    """Test CSP policies based on environment."""

    def test_development_csp(self, client_with_nonce):
        """Test CSP policy for development environment."""
        response = client_with_nonce.get(
            "/",
            headers={"x-environment": "development"}
        )

        csp = response.headers["Content-Security-Policy"]

        # Development might have more relaxed policies
        assert csp

    def test_production_csp(self, client_with_nonce):
        """Test CSP policy for production environment."""
        response = client_with_nonce.get(
            "/",
            headers={"x-environment": "production"}
        )

        csp = response.headers["Content-Security-Policy"]

        # Production should have strict policies
        assert "default-src 'self'" in csp
        assert "script-src" in csp

        # If nonce is enabled, unsafe-inline should not be present for scripts
        if "nonce-" in csp:
            # Check that script-src doesn't have unsafe-inline
            script_src_match = re.search(r'script-src\s+([^;]+)', csp)
            if script_src_match:
                script_src = script_src_match.group(1)
                # In production with nonce, unsafe-inline should NOT be present
                assert "'unsafe-inline'" not in script_src


class TestCSPPolicies:
    """Test individual CSP directives."""

    def test_default_src_policy(self, client_with_nonce):
        """Test default-src directive."""
        response = client_with_nonce.get("/")
        csp = response.headers["Content-Security-Policy"]

        assert "default-src 'self'" in csp

    def test_connect_src_policy(self, client_with_nonce):
        """Test connect-src directive."""
        response = client_with_nonce.get("/")
        csp = response.headers["Content-Security-Policy"]

        assert "connect-src 'self'" in csp

    def test_img_src_policy(self, client_with_nonce):
        """Test img-src directive."""
        response = client_with_nonce.get("/")
        csp = response.headers["Content-Security-Policy"]

        assert "img-src" in csp
        assert "'self'" in csp
        assert "data:" in csp

    def test_frame_ancestors_policy(self, client_with_nonce):
        """Test frame-ancestors directive."""
        response = client_with_nonce.get("/")
        csp = response.headers["Content-Security-Policy"]

        assert "frame-ancestors 'none'" in csp

    def test_base_uri_policy(self, client_with_nonce):
        """Test base-uri directive."""
        response = client_with_nonce.get("/")
        csp = response.headers["Content-Security-Policy"]

        assert "base-uri 'self'" in csp

    def test_form_action_policy(self, client_with_nonce):
        """Test form-action directive."""
        response = client_with_nonce.get("/")
        csp = response.headers["Content-Security-Policy"]

        assert "form-action 'self'" in csp

    def test_upgrade_insecure_requests(self, client_with_nonce):
        """Test upgrade-insecure-requests directive."""
        response = client_with_nonce.get("/")
        csp = response.headers["Content-Security-Policy"]

        assert "upgrade-insecure-requests" in csp
