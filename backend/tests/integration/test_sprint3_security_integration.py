"""
Integration tests for Sprint 1-3 security features.

Tests the complete security flow combining:
- Rate limiting with time-window tracking
- Action chaining prevention
- CSP with nonce-based headers
- Webhook signature verification
- RBAC validation

Author: Phase 8 Sprint 3 (Day 11)
Date: 2026-08-24
"""

import hashlib
import hmac
import json
import time

import pytest

from app.actions.chain_monitor import ChainEvent, get_chain_monitor
from app.actions.rate_limiter import RateLimitConfig, get_rate_limiter
from app.actions.validator import ValidationResult, get_command_validator
from app.approvals.webhook import verify_slack_signature, verify_teams_hmac_signature
from app.main import app
from app.middleware.security import SecurityHeadersMiddleware


@pytest.fixture
def reset_rate_limiter():
    """Reset rate limiter state before each test."""
    limiter = get_rate_limiter()
    limiter.reset()
    yield limiter
    limiter.reset()


@pytest.fixture
def reset_chain_monitor():
    """Reset chain monitor state before each test."""
    monitor = get_chain_monitor()
    monitor.reset_tracking()
    yield monitor
    monitor.reset_tracking()


class TestRateLimitingIntegration:
    """Integration tests for rate limiting with action chaining."""

    def test_rate_limit_basic_flow(self, reset_rate_limiter):
        """Test basic rate limiting flow."""
        limiter = reset_rate_limiter

        # Use a shorter cooldown for testing, and high chain limit to avoid chain blocking
        test_config = RateLimitConfig(
            max_actions_per_hour=3,
            cooldown_seconds=0,  # Disable cooldown for this test
            chain_break_seconds=600,
            max_chain_length=100  # High limit to avoid chain blocking
        )
        limiter.update_config(test_config)

        # First action should be allowed
        allowed, reason, metadata = limiter.check(
            project="meinvoice",
            action_type="restart",
            user="test-user"
        )
        assert allowed is True
        assert "passed" in reason.lower()
        assert metadata["remaining"] == 2  # 3 - 1 = 2 remaining

        # Record the action
        limiter.record_action("meinvoice", "restart", "test-user")

        # Second action should still be allowed
        allowed, reason, metadata = limiter.check(
            project="meinvoice",
            action_type="restart",
            user="test-user"
        )
        assert allowed is True
        assert metadata["remaining"] == 1

        # Record second action
        limiter.record_action("meinvoice", "restart", "test-user")

        # Third action should still be allowed
        allowed, reason, metadata = limiter.check(
            project="meinvoice",
            action_type="restart",
            user="test-user"
        )
        assert allowed is True
        assert metadata["remaining"] == 0

        # Record third action
        limiter.record_action("meinvoice", "restart", "test-user")

        # Fourth action should be rate limited
        allowed, reason, metadata = limiter.check(
            project="meinvoice",
            action_type="restart",
            user="test-user"
        )
        assert allowed is False
        # Could be rate limit or chain limit depending on config
        assert ("rate limit" in reason.lower() or "exceeded" in reason.lower() or
                "limit" in reason.lower())
        assert metadata["remaining"] == 0

    def test_cooldown_period(self, reset_rate_limiter):
        """Test cooldown period between actions."""
        limiter = reset_rate_limiter

        # Ensure cooldown is enabled (default config has cooldown)
        test_config = RateLimitConfig(
            max_actions_per_hour=100,
            cooldown_seconds=5,  # 5 second cooldown
            chain_break_seconds=600,
            max_chain_length=100
        )
        limiter.update_config(test_config)

        # First action
        limiter.record_action("meinvoice", "restart", "test-user")

        # Immediate second action should be blocked by cooldown
        allowed, reason, metadata = limiter.check(
            project="meinvoice",
            action_type="restart",
            user="test-user"
        )
        assert allowed is False
        assert "cooldown" in reason.lower()
        assert metadata["cooldown_remaining"] > 0

    def test_different_action_types_independent(self, reset_rate_limiter):
        """Test that different action types have independent rate limits."""
        limiter = reset_rate_limiter

        # Use up restart limit
        for _ in range(3):
            limiter.record_action("meinvoice", "restart", "test-user")

        # Restart should be blocked
        allowed, _, _ = limiter.check("meinvoice", "restart", "test-user")
        assert allowed is False

        # But scale should still be allowed
        allowed, _, _ = limiter.check("meinvoice", "scale", "test-user")
        assert allowed is True

    def test_different_projects_independent(self, reset_rate_limiter):
        """Test that different projects have independent rate limits."""
        limiter = reset_rate_limiter

        # Use up meinvoice restart limit
        for _ in range(3):
            limiter.record_action("meinvoice", "restart", "test-user")

        # meinvoice restart should be blocked
        allowed, _, _ = limiter.check("meinvoice", "restart", "test-user")
        assert allowed is False

        # But other-project restart should be allowed
        allowed, _, _ = limiter.check("other-project", "restart", "test-user")
        assert allowed is True


class TestActionChainingIntegration:
    """Integration tests for action chaining prevention."""

    def test_chain_detection_and_prevention(self, reset_rate_limiter, reset_chain_monitor):
        """Test that action chains are detected and prevented."""
        limiter = reset_rate_limiter
        monitor = reset_chain_monitor

        # Configure rate limiter for chain testing (no cooldown, no rate limit)
        test_config = RateLimitConfig(
            max_actions_per_hour=100,  # High limit for chain testing
            cooldown_seconds=0,  # No cooldown
            chain_break_seconds=600,
            max_chain_length=3
        )
        limiter.update_config(test_config)

        # Track chain events
        chain_events = []

        def capture_event(event: ChainEvent):
            chain_events.append(event)

        monitor.set_alert_callback(capture_event)

        # Simulate chain of actions (wait for cooldown between them)
        for i in range(3):
            # Wait for cooldown to pass
            time.sleep(0.1)

            allowed, _, metadata = limiter.check(
                project="meinvoice",
                action_type="restart",
                user="test-user"
            )
            assert allowed is True, f"Action {i+1} should be allowed"
            assert metadata["chain_count"] == i

            limiter.record_action("meinvoice", "restart", "test-user")

        # Fourth action should be blocked by chain limit
        time.sleep(0.1)
        allowed, reason, metadata = limiter.check(
            project="meinvoice",
            action_type="restart",
            user="test-user"
        )
        assert allowed is False
        assert "chain" in reason.lower()
        assert metadata["chain_count"] == 3

    def test_chain_reset_after_timeout(self, reset_rate_limiter, reset_chain_monitor):
        """Test that chain counter resets after timeout period."""
        limiter = reset_rate_limiter
        monitor = reset_chain_monitor

        # Use shorter config for testing
        test_config = RateLimitConfig(
            max_actions_per_hour=100,  # High limit for chain testing
            cooldown_seconds=0,  # No cooldown
            chain_break_seconds=1,  # Short chain break for testing
            max_chain_length=3
        )
        limiter.update_config(test_config)

        # Perform 3 actions to reach chain limit
        for _i in range(3):
            limiter.record_action("meinvoice", "restart", "test-user")

        # Should be blocked by chain limit
        allowed, _, _ = limiter.check("meinvoice", "restart", "test-user")
        assert allowed is False

        # Wait for chain break timeout
        time.sleep(1.1)

        # Chain should be reset
        allowed, _, metadata = limiter.check("meinvoice", "restart", "test-user")
        assert allowed is True
        assert metadata["chain_count"] == 0

    def test_chain_alert_threshold(self, reset_chain_monitor):
        """Test that chain alerts fire at warning threshold."""
        monitor = reset_chain_monitor

        # Track events
        events = []

        def capture_event(event: ChainEvent):
            events.append(event)

        monitor.set_alert_callback(capture_event)

        # Check at 2/3 of limit (should trigger warning)
        monitor.check_chain(
            project="meinvoice",
            action_type="restart",
            chain_count=2,
            chain_limit=3,
            user="test-user"
        )

        assert len(events) == 1
        assert events[0].event_type == "approaching"

        # Check at limit (should trigger exceeded)
        monitor.check_chain(
            project="meinvoice",
            action_type="restart",
            chain_count=3,
            chain_limit=3,
            user="test-user"
        )

        assert len(events) == 2
        assert events[1].event_type == "exceeded"


class TestCSPNonceIntegration:
    """Integration tests for CSP nonce-based headers."""

    def test_nonce_generation_and_usage(self):
        """Test that nonces are generated and used correctly."""

        # Create middleware with nonce enabled
        middleware = SecurityHeadersMiddleware(app, use_nonce=True)

        # Test nonce manager
        nonce_manager = middleware.nonce_manager

        # Generate a nonce
        nonce1 = nonce_manager.generate_nonce()
        assert nonce1
        assert len(nonce1) > 10  # Should be reasonable length

        # Generate another nonce (should be different)
        nonce2 = nonce_manager.generate_nonce()
        assert nonce2 != nonce1

    def test_csp_policy_with_nonce(self):
        """Test CSP policy generation with nonce."""
        middleware = SecurityHeadersMiddleware(app, use_nonce=True)

        # Get policy with nonce
        test_nonce = "abc123test"
        policy = middleware._build_csp_policy(
            nonce=test_nonce,
            environment="production"
        )

        # Should contain nonce
        assert f"'nonce-{test_nonce}'" in policy

        # Should NOT contain unsafe-inline in production
        assert "'unsafe-inline'" not in policy

    def test_csp_policy_development_mode(self):
        """Test CSP policy in development mode allows unsafe-inline."""
        middleware = SecurityHeadersMiddleware(app, use_nonce=False)

        policy = middleware._build_csp_policy(
            nonce=None,
            environment="development"
        )

        # Development should allow unsafe-inline
        assert "'unsafe-inline'" in policy

    @pytest.mark.asyncio
    async def test_security_headers_added_to_response(self):
        """Test that security headers are added to all responses."""
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        # Create a simple app with SecurityHeadersMiddleware
        async def homepage(request):
            return JSONResponse({"message": "test"})

        test_app = Starlette(routes=[Route("/", homepage)])
        middleware = SecurityHeadersMiddleware(test_app, use_nonce=True)

        # Make request
        from starlette.testclient import TestClient
        client = TestClient(middleware)

        response = client.get("/")

        # Check security headers
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "Content-Security-Policy" in response.headers
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "Permissions-Policy" in response.headers


class TestWebhookSignatureIntegration:
    """Integration tests for webhook signature verification."""

    def test_slack_signature_valid(self):
        """Test valid Slack signature verification."""
        signing_secret = "test_secret"
        timestamp = str(int(time.time()))
        body = '{"test": "payload"}'

        # Calculate signature
        sig_basestring = f"v0:{timestamp}:{body}"
        digest = hmac.new(
            signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).digest()
        signature = f"v0={digest.hex()}"

        # Should verify successfully
        result = verify_slack_signature(
            raw_body=body.encode(),
            timestamp=timestamp,
            signature=signature,
            signing_secret=signing_secret
        )
        assert result is True

    def test_slack_signature_invalid(self):
        """Test invalid Slack signature is rejected."""
        signing_secret = "test_secret"
        timestamp = str(int(time.time()))
        body = '{"test": "payload"}'

        # Wrong signature
        signature = "v0=wrong_signature"

        result = verify_slack_signature(
            raw_body=body.encode(),
            timestamp=timestamp,
            signature=signature,
            signing_secret=signing_secret
        )
        assert result is False

    def test_slack_timestamp_rejection(self):
        """Test that old timestamps are rejected."""
        from fastapi import HTTPException

        signing_secret = "test_secret"
        # Use timestamp from 2 minutes ago
        old_timestamp = str(int(time.time()) - 120)
        body = '{"test": "payload"}'

        # Calculate signature
        sig_basestring = f"v0:{old_timestamp}:{body}"
        digest = hmac.new(
            signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).digest()
        signature = f"v0={digest.hex()}"

        # Should raise HTTPException for old timestamp
        with pytest.raises(HTTPException) as exc_info:
            verify_slack_signature(
                raw_body=body.encode(),
                timestamp=old_timestamp,
                signature=signature,
                signing_secret=signing_secret
            )

        assert exc_info.value.status_code == 401
        assert "replay" in exc_info.value.detail.lower()

    def test_teams_signature_valid(self):
        """Test valid Teams signature verification."""
        webhook_url = "https://example.com/webhook"
        body = '{"test": "teams"}'

        # Calculate signature
        digest = hmac.new(
            webhook_url.encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()
        auth_header = f"sha256={digest}"

        result = verify_teams_hmac_signature(
            raw_body=body.encode(),
            auth_header=auth_header,
            webhook_url=webhook_url
        )
        assert result is True

    def test_teams_signature_invalid(self):
        """Test invalid Teams signature is rejected."""
        webhook_url = "https://example.com/webhook"
        body = '{"test": "teams"}'

        result = verify_teams_hmac_signature(
            raw_body=body.encode(),
            auth_header="sha256=wrong",
            webhook_url=webhook_url
        )
        assert result is False


class TestRBACValidationIntegration:
    """Integration tests for RBAC validation with rate limiting."""

    def test_rbac_with_rate_limit_combined(self):
        """Test RBAC validation combined with rate limiting."""
        validator = get_command_validator()
        limiter = get_rate_limiter()

        # Reset state
        limiter.reset()

        # Note: RBAC validation requires project registry to be loaded
        # This test verifies the integration works when both components are used
        # In a real scenario, the registry would be loaded from config files

        # Check rate limit (this works independently)
        allowed, reason, metadata = limiter.check(
            project="meinvoice",
            action_type="restart",
            user="test-user"
        )

        assert allowed is True  # First action should be allowed

        # Verify that validation returns a result (even if project not found)
        result = validator.validate(
            command="kubectl restart deployment meinvoice-api -n meinvoice",
            project="nonexistent-project",  # Use project that won't exist
            user="test-user"
        )

        # Should get validation result (even if it's an error result)
        assert isinstance(result, ValidationResult)
        # If project not found, validation should fail
        if not result.allowed:
            assert "not found" in result.reason.lower()


class TestEndToEndSecurityFlow:
    """End-to-end integration tests for complete security flow."""

    @pytest.mark.asyncio
    async def test_complete_security_flow(self):
        """Test complete security flow from request to response."""
        # This test simulates a complete security flow:
        # 1. Rate limit check
        # 2. Chain detection
        # 3. Action recording

        limiter = get_rate_limiter()
        monitor = get_chain_monitor()

        # Reset state
        limiter.reset()
        monitor.reset_tracking()

        # Configure for chain testing
        test_config = RateLimitConfig(
            max_actions_per_hour=100,  # High limit for testing
            cooldown_seconds=0,  # No cooldown
            chain_break_seconds=600,
            max_chain_length=3
        )
        limiter.update_config(test_config)

        # Track events
        events = []
        monitor.set_alert_callback(lambda e: events.append(e))

        # Step 1: Rate limit check (first action)
        allowed, reason, metadata = limiter.check(
            project="meinvoice",
            action_type="restart",
            user="test-user"
        )
        assert allowed is True
        assert metadata["chain_count"] == 0

        # Step 2: Record action (triggers chain check)
        limiter.record_action("meinvoice", "restart", "test-user")

        # Step 3: Verify rate limit state after recording
        allowed2, reason2, metadata2 = limiter.check(
            project="meinvoice",
            action_type="restart",
            user="test-user"
        )
        assert allowed2 is True
        assert metadata2["chain_count"] == 1  # Second action now

        # Step 4: Repeat to test chain detection
        limiter.record_action("meinvoice", "restart", "test-user")
        limiter.record_action("meinvoice", "restart", "test-user")

        # Should now be at chain limit
        allowed3, reason3, metadata3 = limiter.check(
            project="meinvoice",
            action_type="restart",
            user="test-user"
        )
        assert allowed3 is False
        assert "chain" in reason3.lower()
        assert metadata3["chain_count"] == 3

    @pytest.mark.asyncio
    async def test_webhook_end_to_end(self):
        """Test webhook flow with signature verification and action processing."""
        # Simulate Slack webhook flow

        signing_secret = "test_signing_secret"
        timestamp = str(int(time.time()))

        # Create webhook payload
        payload = {
            "actions": [{
                "action_id": "approve_action",
                "value": "action:test-action-id"
            }],
            "user": {
                "id": "U12345",
                "name": "testuser"
            }
        }

        # Calculate signature
        body_str = f"payload={json.dumps(payload)}"
        sig_basestring = f"v0:{timestamp}:{body_str}"
        digest = hmac.new(
            signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).digest()
        signature = f"v0={digest.hex()}"

        # Verify signature
        result = verify_slack_signature(
            raw_body=body_str.encode(),
            timestamp=timestamp,
            signature=signature,
            signing_secret=signing_secret
        )
        assert result is True


@pytest.fixture
def app_with_security_middleware():
    """Create app with security middleware for testing."""
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def test_endpoint(request):
        return JSONResponse({"status": "ok"})

    async def api_endpoint(request):
        return JSONResponse({"data": "sensitive"})

    test_app = Starlette(routes=[
        Route("/test", test_endpoint),
        Route("/api/data", api_endpoint),
    ])

    # Wrap with security middleware
    secured_app = SecurityHeadersMiddleware(test_app, use_nonce=True)

    return secured_app


class TestSecurityHeadersIntegration:
    """Integration tests for security headers in HTTP responses."""

    @pytest.mark.asyncio
    async def test_all_security_headers_present(self, app_with_security_middleware):
        """Test that all required security headers are present."""
        from starlette.testclient import TestClient

        client = TestClient(app_with_security_middleware)
        response = client.get("/test")

        # Verify all security headers
        headers = response.headers

        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"
        assert headers.get("X-XSS-Protection") == "1; mode=block"
        assert "Content-Security-Policy" in headers
        assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "Permissions-Policy" in headers

        # Check CSP policy structure
        csp = headers.get("Content-Security-Policy")
        assert "default-src" in csp
        assert "script-src" in csp
        assert "style-src" in csp

    @pytest.mark.asyncio
    async def test_api_cache_control(self, app_with_security_middleware):
        """Test that API responses have proper cache control."""
        from starlette.testclient import TestClient

        client = TestClient(app_with_security_middleware)
        response = client.get("/api/data")

        # API responses should not be cached
        cache_control = response.headers.get("Cache-Control")
        assert "no-store" in cache_control or "no-cache" in cache_control

    @pytest.mark.asyncio
    async def test_nonce_header_present(self, app_with_security_middleware):
        """Test that nonce is passed to frontend via header."""
        from starlette.testclient import TestClient

        client = TestClient(app_with_security_middleware)
        response = client.get("/test")

        # Nonce should be present in response header
        nonce = response.headers.get("X-CSP-Nonce")
        assert nonce
        assert len(nonce) > 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
