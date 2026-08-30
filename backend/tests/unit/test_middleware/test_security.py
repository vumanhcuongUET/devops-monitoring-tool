"""Unit tests for Security Headers Middleware."""

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
def client(test_app):
    """Create test client with security headers middleware."""
    app = test_app
    app.add_middleware(SecurityHeadersMiddleware)
    return TestClient(app)


class TestCSPPolicies:
    """Test individual CSP directives."""

    def test_default_src_policy(self, client):
        """Test default-src directive."""
        response = client.get("/")
        csp = response.headers["Content-Security-Policy"]

        assert "default-src 'self'" in csp

    def test_connect_src_policy(self, client):
        """Test connect-src directive."""
        response = client.get("/")
        csp = response.headers["Content-Security-Policy"]

        assert "connect-src 'self'" in csp

    def test_img_src_policy(self, client):
        """Test img-src directive."""
        response = client.get("/")
        csp = response.headers["Content-Security-Policy"]

        assert "img-src" in csp
        assert "'self'" in csp
        assert "data:" in csp

    def test_frame_ancestors_policy(self, client):
        """Test frame-ancestors directive."""
        response = client.get("/")
        csp = response.headers["Content-Security-Policy"]

        assert "frame-ancestors 'none'" in csp

    def test_base_uri_policy(self, client):
        """Test base-uri directive."""
        response = client.get("/")
        csp = response.headers["Content-Security-Policy"]

        assert "base-uri 'self'" in csp

    def test_form_action_policy(self, client):
        """Test form-action directive."""
        response = client.get("/")
        csp = response.headers["Content-Security-Policy"]

        assert "form-action 'self'" in csp

    def test_upgrade_insecure_requests(self, client):
        """Test upgrade-insecure-requests directive."""
        response = client.get("/")
        csp = response.headers["Content-Security-Policy"]

        assert "upgrade-insecure-requests" in csp

    def test_production_csp_no_unsafe_inline(self, client):
        """Test production CSP has no unsafe-inline."""
        middleware = SecurityHeadersMiddleware(client.app)
        csp = middleware._build_csp_policy(environment="production")

        assert "default-src 'self'" in csp
        assert "script-src" in csp
        assert "'unsafe-inline'" not in csp

    def test_security_headers_added(self, client):
        """Test core security headers on every response."""
        response = client.get("/")

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_api_cache_control(self, client):
        """Test API responses get no-store cache control."""
        response = client.get("/api/test")

        assert "no-store" in response.headers["Cache-Control"]
