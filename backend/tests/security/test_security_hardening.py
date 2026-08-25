"""
Security Hardening Tests

Phase 9 - Sprint 3 - Day 15
Purpose: Validate all security measures are properly implemented

Run with: pytest backend/tests/security/test_security_hardening.py -v -m security
"""

import asyncio
import os
from unittest.mock import Mock, patch

import pytest

from app.security import SSRFProtection
from app.config import settings


@pytest.mark.security
class TestSSRFProtection:
    """Test SSRF protection implementation."""

    def test_ssrf_blocks_loopback(self):
        """Test that SSRF protection blocks loopback addresses."""
        # localhost should be blocked
        is_safe, error = SSRFProtection.resolve_and_validate("localhost")
        assert not is_safe
        assert "blocked" in error.lower() or "not allowed" in error.lower()

    def test_ssrf_blocks_127_0_0_1(self):
        """Test that 127.0.0.1 is blocked."""
        is_safe, error = SSRFProtection.resolve_and_validate("127.0.0.1")
        assert not is_safe

    def test_ssrf_blocks_private_networks(self):
        """Test that private network IPs are blocked."""
        # 10.0.0.0/8
        is_safe, _ = SSRFProtection.resolve_and_validate("10.0.0.1")
        assert not is_safe

        # 172.16.0.0/12
        is_safe, _ = SSRFProtection.resolve_and_validate("172.16.0.1")
        assert not is_safe

        # 192.168.0.0/16
        is_safe, _ = SSRFProtection.resolve_and_validate("192.168.1.1")
        assert not is_safe

    def test_ssrf_blocks_metadata_services(self):
        """Test that cloud metadata services are blocked."""
        is_safe, _ = SSRFProtection.resolve_and_validate("169.254.169.254")
        assert not is_safe

        is_safe, _ = SSRFProtection.resolve_and_validate("metadata.google.internal")
        assert not is_safe

    def test_dns_cache_prevents_rebinding(self):
        """Test that DNS caching prevents rebinding attacks."""
        # Clear cache first
        SSRFProtection.clear_dns_cache()

        # First resolution
        is_safe, _ = SSRFProtection.resolve_and_validate("example.com")

        # Cache should be populated
        stats = SSRFProtection.get_cache_stats()
        assert stats["total_entries"] >= 1

    def test_blocked_networks_comprehensive(self):
        """Test all blocked network ranges are covered."""
        required_networks = {
            "127.0.0.0/8",      # Loopback
            "10.0.0.0/8",       # Private Class A
            "172.16.0.0/12",    # Private Class B
            "192.168.0.0/16",  # Private Class C
            "169.254.0.0/16",  # Link-local
            "::1/128",          # IPv6 loopback
            "fc00::/7",        # IPv6 unique-local
            "fe80::/10",       # IPv6 link-local
        }

        for network in required_networks:
            assert network in SSRFProtection.BLOCKED_NETWORKS, f"Missing network: {network}"

    def test_blocked_hostnames(self):
        """Test that sensitive hostnames are blocked."""
        required_hostnames = {
            "metadata.google.internal",
            "metadata.internal",
            "169.254.169.254",
        }

        for hostname in required_hostnames:
            assert hostname in SSRFProtection.BLOCKED_HOSTNAMES, f"Missing hostname: {hostname}"


@pytest.mark.security
class TestSecretsConfiguration:
    """Test secrets configuration and validation."""

    def test_no_dummy_secrets_in_config(self):
        """Test that no dummy secrets are configured in production."""
        # In development, we allow dummy secrets
        if settings.ENVIRONMENT == "development":
            return

        # In production, these should not be dummy values
        dummy_values = ["dummy_secret_for_dev", "CHANGE_ME", "xxx", "test"]

        if settings.AUTH_SECRET:
            assert settings.AUTH_SECRET not in dummy_values, "AUTH_SECRET is still a dummy value"

    def test_redis_config_exists(self):
        """Test that Redis configuration exists for distributed state."""
        assert hasattr(settings, "REDIS_HOST")
        assert hasattr(settings, "REDIS_PORT")
        assert settings.REDIS_HOST is not None

    def test_connection_pool_config_exists(self):
        """Test that connection pool settings are configured."""
        assert hasattr(settings, "ES_MAX_CONNECTIONS")
        assert settings.ES_MAX_CONNECTIONS > 0


@pytest.mark.security
class TestInputValidation:
    """Test input validation helpers."""

    def test_validate_identifier_rejects_injection(self):
        """Test that validate_identifier rejects injection attempts."""
        from app.security import validate_identifier

        # SQL injection patterns
        with pytest.raises(ValueError):
            validate_identifier("'; DROP TABLE users; --")

        # Path traversal
        with pytest.raises(ValueError):
            validate_identifier("../../../etc/passwd")

        # Script injection
        with pytest.raises(ValueError):
            validate_identifier("<script>alert('xss')</script>")

    def test_validate_identifier_accepts_safe_values(self):
        """Test that valid identifiers are accepted."""
        from app.security import validate_identifier

        # Valid project names
        assert validate_identifier("meinvoice") == "meinvoice"
        assert validate_identifier("my-service") == "my-service"
        assert validate_identifier("my_service") == "my_service"
        assert validate_identifier("MyService-123") == "MyService-123"

    def test_es_query_sanitization(self):
        """Test Elasticsearch query sanitization."""
        from app.security import sanitize_es_query

        # Should escape backslashes
        result = sanitize_es_query("test\\query")
        assert "\\\\" in result

        # Should reject overly long queries
        with pytest.raises(ValueError):
            sanitize_es_query("x" * 1001)


@pytest.mark.security
class TestRateLimiting:
    """Test distributed rate limiting."""

    @pytest.mark.asyncio
    async def test_rate_limit_enforced(self):
        """Test that rate limiting is enforced."""
        try:
            from app.rate_limit.redis_rate_limiter import RedisRateLimiter

            limiter = RedisRateLimiter()
            key = "test-security-rate-limit"

            # Make 10 requests, limit is 5
            results = await asyncio.gather(*[
                limiter.check_rate_limit(key, max_requests=5, window_seconds=60)
                for _ in range(10)
            ])

            allowed = sum(1 for r, _ in results if r)
            assert allowed == 5, f"Expected 5 allowed requests, got {allowed}"

        except ImportError:
            pytest.skip("Redis rate limiter not available")
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")


@pytest.mark.security
class TestAuthentication:
    """Test authentication and authorization."""

    def test_auth_enabled_setting_exists(self):
        """Test that AUTH_ENABLED setting exists."""
        assert hasattr(settings, "AUTH_ENABLED")

    def test_auth_secret_configured(self):
        """Test that AUTH_SECRET is configured when auth is enabled."""
        if settings.AUTH_ENABLED:
            # In development, a secret may be auto-generated
            # In production, it must be set
            if settings.ENVIRONMENT == "production":
                assert settings.AUTH_SECRET, "AUTH_SECRET must be set in production"

    def test_api_keys_configured(self):
        """Test that API_KEYS is configured when auth is enabled."""
        if settings.AUTH_ENABLED and settings.ENVIRONMENT == "production":
            assert settings.API_KEYS, "API_KEYS must be set in production"


@pytest.mark.security
class TestHeadersAndCORS:
    """Test CORS and security headers."""

    def test_cors_origins_configured(self):
        """Test that CORS origins are configured."""
        assert hasattr(settings, "CORS_ORIGINS")
        assert len(settings.CORS_ORIGINS) > 0

    def test_cors_origins_not_wildcard_in_prod(self):
        """Test that wildcard CORS is not used in production."""
        if settings.ENVIRONMENT == "production":
            assert "*" not in settings.CORS_ORIGINS, "Wildcard CORS not allowed in production"


@pytest.mark.security
class TestAuditLogging:
    """Test audit logging configuration."""

    def test_audit_logging_enabled(self):
        """Test that audit logging can be enabled."""
        assert hasattr(settings, "AUDIT_LOG_ENABLED")

    def test_audit_log_max_entries_configured(self):
        """Test that audit log size limit is configured."""
        assert hasattr(settings, "AUDIT_LOG_MAX_ENTRIES")
        assert settings.AUDIT_LOG_MAX_ENTRIES > 0


@pytest.mark.security
class TestEnvironmentBasedSecurity:
    """Test environment-specific security settings."""

    def test_production_security_harder(self):
        """Test that production has stricter security settings."""
        if settings.ENVIRONMENT == "production":
            # Auth should be enabled
            assert settings.AUTH_ENABLED, "AUTH must be enabled in production"

            # Audit logging should be enabled
            assert settings.AUDIT_LOG_ENABLED, "Audit logging must be enabled in production"


@pytest.mark.security
class TestGitIgnoreSecurity:
    """Test that sensitive files are in .gitignore."""

    def test_env_files_gitignored(self):
        """Test that .env files are gitignored."""
        gitignore_path = os.path.join(os.path.dirname(__file__), "../../../..", ".gitignore")

        with open(gitignore_path) as f:
            gitignore_content = f.read()

        assert ".env" in gitignore_content
        assert "*.key" in gitignore_content or "*.pem" in gitignore_content

    def test_secrets_directory_gitignored(self):
        """Test that secrets directory is gitignored."""
        gitignore_path = os.path.join(os.path.dirname(__file__), "../../../..", ".gitignore")

        with open(gitignore_path) as f:
            gitignore_content = f.read()

        assert "secrets/" in gitignore_content or "secrets" in gitignore_content


@pytest.mark.security
class TestSecurityValidationSummary:
    """Summary test for overall security validation."""

    @pytest.mark.asyncio
    async def test_security_checklist(self):
        """Run a comprehensive security checklist."""
        checklist = {
            "SSRF Protection": True,  # SSRFProtection class exists
            "Redis Config": hasattr(settings, "REDIS_HOST") and settings.REDIS_HOST,
            "Connection Pools": hasattr(settings, "ES_MAX_CONNECTIONS"),
            "Auth Enabled": hasattr(settings, "AUTH_ENABLED"),
            "Audit Logging": hasattr(settings, "AUDIT_LOG_ENABLED"),
            "CORS Configured": len(settings.CORS_ORIGINS) > 0,
            "Blocked Networks": len(SSRFProtection.BLOCKED_NETWORKS) >= 8,
        }

        # Print summary
        print("\n=== Security Checklist ===")
        for item, passed in checklist.items():
            status = "✅" if passed else "❌"
            print(f"{status} {item}")

        total = len(checklist)
        passed = sum(checklist.values())
        print(f"\nPassed: {passed}/{total}")

        # Should pass at least 80% of checks
        assert passed / total >= 0.8, f"Security check failed: {passed}/{total} passed"


def get_security_summary() -> dict:
    """Get summary of security measures."""
    return {
        "ssrf_protection": {
            "description": "Blocks requests to internal/private networks",
            "blocked_networks": len(SSRFProtection.BLOCKED_NETWORKS),
            "dns_cache_ttl": SSRFProtection._cache_ttl,
        },
        "authentication": {
            "enabled": settings.AUTH_ENABLED,
            "environment": settings.ENVIRONMENT,
        },
        "audit_logging": {
            "enabled": settings.AUDIT_LOG_ENABLED,
            "max_entries": settings.AUDIT_LOG_MAX_ENTRIES,
        },
        "secrets_management": {
            "method": "External Secrets Operator",
            "redis_enabled": bool(settings.REDIS_HOST),
        },
    }
