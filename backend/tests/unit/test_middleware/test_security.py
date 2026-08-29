"""Unit tests for Security Headers Middleware with CSP nonce support."""

import re

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

from app.middleware.security import (
    SecurityHeadersMiddleware,
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
    app.add_middleware(SecurityHeadersMiddleware, use_nonce=True)
    return TestClient(app)


@pytest.fixture
def client_without_nonce(test_app):
    """Create test client without nonce-based CSP."""
    app = test_app
    app.add_middleware(SecurityHeadersMiddleware, use_nonce=False)
    return TestClient(app)


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
