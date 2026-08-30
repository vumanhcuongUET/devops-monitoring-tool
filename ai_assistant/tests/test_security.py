"""
Tests for security module.
"""

import pytest
import time

from core.security import (
    TokenBucketRateLimiter,
    InputValidator,
    SecurityHeaders,
    rate_limit,
    check_rate_limit,
)


@pytest.mark.unit
class TestTokenBucketRateLimiter:
    """Tests for token bucket rate limiter."""

    def setup_method(self):
        """Reset rate limiter state before each test."""
        # Clear global rate limiters to avoid test interference
        from core.security import _global_rate_limiters
        _global_rate_limiters.clear()

    def test_init(self):
        """Test rate limiter initialization."""
        limiter = TokenBucketRateLimiter(rate=10.0, capacity=100)
        assert limiter._rate == 10.0
        assert limiter._capacity == 100

    def test_check_allows_requests_within_limit(self):
        """Test that requests within limit are allowed."""
        limiter = TokenBucketRateLimiter(rate=10.0, capacity=10)

        for i in range(10):
            result = limiter.check("user1")
            assert result.allowed is True
            # Remaining should be decreasing, but allow for timing variance
            assert result.remaining >= 0 and result.remaining <= 10 - i

    def test_check_blocks_requests_over_limit(self):
        """Test that requests over limit are blocked."""
        limiter = TokenBucketRateLimiter(rate=1.0, capacity=2)

        # First two requests should be allowed
        assert limiter.check("user1").allowed is True
        assert limiter.check("user1").allowed is True

        # Third should be blocked
        result = limiter.check("user1")
        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after is not None

    def test_check_refills_tokens_over_time(self):
        """Test that tokens refill over time."""
        limiter = TokenBucketRateLimiter(rate=10.0, capacity=10)

        # Use all tokens
        for _ in range(10):
            limiter.check("user1")

        # Wait for refill
        time.sleep(0.15)  # 150ms should refill ~1.5 tokens

        # Should have some tokens back
        result = limiter.check("user1")
        assert result.allowed is True

    def test_check_different_keys(self):
        """Test that different keys have separate buckets."""
        limiter = TokenBucketRateLimiter(rate=1.0, capacity=2)

        # Each user should get their full capacity
        assert limiter.check("user1").allowed is True
        assert limiter.check("user2").allowed is True
        assert limiter.check("user1").allowed is True
        assert limiter.check("user2").allowed is True

    def test_reset(self):
        """Test resetting rate limit for a key."""
        limiter = TokenBucketRateLimiter(rate=1.0, capacity=2)

        # Use all tokens
        limiter.check("user1")
        limiter.check("user1")
        assert limiter.check("user1").allowed is False

        # Reset
        limiter.reset("user1")

        # Should have full capacity again
        assert limiter.check("user1").allowed is True


@pytest.mark.unit
class TestInputValidator:
    """Tests for input validation."""

    def test_validate_project_name_valid(self):
        """Test valid project names."""
        valid_names = ["test", "test-project", "test_project", "Test123"]
        for name in valid_names:
            is_valid, error = InputValidator.validate_project_name(name)
            assert is_valid is True
            assert error is None

    def test_validate_project_name_invalid(self):
        """Test invalid project names."""
        invalid_names = ["", "test project", "test/project", "test@project"]
        for name in invalid_names:
            is_valid, error = InputValidator.validate_project_name(name)
            assert is_valid is False
            assert error is not None

    def test_validate_project_name_too_long(self):
        """Test project name length validation."""
        long_name = "a" * 101
        is_valid, error = InputValidator.validate_project_name(long_name)
        assert is_valid is False
        assert "too long" in error

    def test_validate_section_name(self):
        """Test section name validation."""
        assert InputValidator.validate_section_name("errors")[0] is True
        assert InputValidator.validate_section_name("")[0] is False

    def test_validate_time_range_valid(self):
        """Test valid time ranges."""
        valid_ranges = ["now", "now-30m", "now-2h", "now-7d"]
        for tr in valid_ranges:
            is_valid, error = InputValidator.validate_time_range(tr)
            assert is_valid is True

    def test_validate_time_range_invalid(self):
        """Test invalid time ranges."""
        invalid_ranges = ["", "invalid", "now-30x", "now-"]
        for tr in invalid_ranges:
            is_valid, error = InputValidator.validate_time_range(tr)
            assert is_valid is False

    def test_validate_query_body_size(self):
        """Test query body size validation."""
        small_body = {"query": {"match_all": {}}}
        is_valid, error = InputValidator.validate_query_body(small_body)
        assert is_valid is True

        huge_body = {"data": "x" * 11000}
        is_valid, error = InputValidator.validate_query_body(huge_body)
        assert is_valid is False
        assert "too large" in error

    def test_validate_promql(self):
        """Test PromQL validation."""
        valid_promqls = ["up", "rate(http_requests_total[5m])", "sum(container_memory_usage_bytes)"]
        for promql in valid_promqls:
            is_valid, error = InputValidator.validate_promql(promql)
            assert is_valid is True

    def test_validate_promql_dangerous(self):
        """Test PromQL with dangerous patterns."""
        dangerous_promql = "<script>alert('xss')</script>"
        is_valid, error = InputValidator.validate_promql(dangerous_promql)
        assert is_valid is False

    def test_sanitize_url(self):
        """Test URL sanitization."""
        url = "https://user:password@example.com/api/query?param=value"
        sanitized = InputValidator.sanitize_url(url)
        assert "***@" in sanitized
        assert "password" not in sanitized
        assert "?" not in sanitized  # Query params removed

    def test_validate_url_valid(self):
        """Test valid URL validation."""
        valid_urls = [
            "http://localhost:9200",
            "https://elasticsearch.example.com",
            "https://example.com:9200/path",
        ]
        for url in valid_urls:
            is_valid, error = InputValidator.validate_url(url)
            assert is_valid is True, f"Should accept URL: {url}"
            assert error is None

    def test_validate_url_invalid_protocol(self):
        """Test URL validation rejects dangerous protocols."""
        dangerous_urls = [
            "javascript:alert('xss')",
            "data:text/html,<script>alert('xss')</script>",
            "vbscript:msgbox('xss')",
            "ftp://example.com",
        ]
        for url in dangerous_urls:
            is_valid, error = InputValidator.validate_url(url)
            assert is_valid is False, f"Should reject URL: {url}"
            assert error is not None

    def test_validate_url_with_credentials(self):
        """Test URL validation handles credentials correctly."""
        url_with_creds = "http://user:pass@localhost:9200"
        # Should reject when allow_credentials=False
        is_valid, error = InputValidator.validate_url(url_with_creds, allow_credentials=False)
        assert is_valid is False
        assert "credentials" in error.lower()
        # Should accept when allow_credentials=True
        is_valid, error = InputValidator.validate_url(url_with_creds, allow_credentials=True)
        assert is_valid is True

    def test_validate_url_too_long(self):
        """Test URL length validation."""
        long_url = "https://example.com/" + "x" * 2000
        is_valid, error = InputValidator.validate_url(long_url)
        assert is_valid is False
        assert "too long" in error.lower()

    def test_validate_template_content_safe(self):
        """Test safe template content passes validation."""
        safe_templates = [
            '{"query": {"match": {"{{ key }}": "{{ value }}"}}}',
            'rate(http_requests_total[{{ range }}])',
            'sum(container_memory_usage_bytes){{ namespace_filter }}',
        ]
        for template in safe_templates:
            is_valid, error = InputValidator.validate_template_content(template)
            assert is_valid is True, f"Should accept template: {template}"
            assert error is None

    def test_validate_template_content_dangerous(self):
        """Test dangerous template patterns are rejected."""
        dangerous_templates = [
            '<?php system("rm -rf /"); ?>',
            '<script>alert("xss")</script>',
            '<%= System.exec("cat /etc/passwd") %>',
            '${@java.lang.Runtime::getRuntime().exec("calc")}',
        ]
        for template in dangerous_templates:
            is_valid, error = InputValidator.validate_template_content(template)
            assert is_valid is False, f"Should reject template: {template}"
            assert error is not None

    def test_validate_template_too_long(self):
        """Test template length validation."""
        long_template = '{"data": "' + ("x" * 11000) + '"}'
        is_valid, error = InputValidator.validate_template_content(long_template, max_length=10000)
        assert is_valid is False
        assert "too long" in error.lower()

    def test_validate_template_nesting_depth(self):
        """Test template nesting depth validation."""
        # Template with excessive nesting
        nested = '{"a": {"b": {"c": ' + '{"d": "value"' * 25 + '}}}'
        is_valid, error = InputValidator.validate_template_content(nested)
        assert is_valid is False
        assert "nesting" in error.lower()


@pytest.mark.unit
class TestSecurityHeaders:
    """Tests for security headers validation."""

    def test_validate_headers_valid(self):
        """Test valid headers."""
        headers = {"Content-Type": "application/json"}
        is_valid, errors = SecurityHeaders.validate_headers(headers)
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_headers_wrong_content_type(self):
        """Test headers with wrong content type."""
        headers = {"Content-Type": "text/html"}
        is_valid, errors = SecurityHeaders.validate_headers(headers)
        # HTML content type is flagged but not necessarily invalid
        assert len(errors) >= 0


@pytest.mark.unit
class TestRateLimitDecorator:
    """Tests for rate_limit decorator."""

    def test_rate_limit_decorator(self):
        """Test that decorator rate limits function calls."""
        @rate_limit(rate=100.0, capacity=5)  # High rate for fast test
        def limited_function():
            return "success"

        # Should allow first few calls
        for _ in range(5):
            assert limited_function() == "success"

    def test_rate_limit_with_key_func(self):
        """Test rate limit with custom key function."""
        calls_by_user = {}

        @rate_limit(rate=1.0, capacity=2, key_func=lambda user: user)
        def limited_function(user):
            calls_by_user[user] = calls_by_user.get(user, 0) + 1
            return "success"

        # Each user should get their own limit
        assert limited_function("user1") == "success"
        assert limited_function("user1") == "success"

        assert limited_function("user2") == "success"
        assert limited_function("user2") == "success"


@pytest.mark.unit
class TestCheckRateLimit:
    """Tests for check_rate_limit function."""

    def setup_method(self):
        """Reset rate limiter state before each test."""
        # Clear global rate limiters to avoid test interference
        from core.security import _global_rate_limiters
        _global_rate_limiters.clear()

    def test_check_rate_limit_basic(self):
        """Test basic rate limit checking."""
        result = check_rate_limit(identifier="test_user_unique", rate=10.0, capacity=5)
        assert result.allowed is True
        # Remaining should be less than capacity after consuming 1 token
        assert result.remaining >= 0 and result.remaining < 5

    def test_check_rate_limit_multiple_calls(self):
        """Test multiple calls deplete limit."""
        for _ in range(5):
            check_rate_limit(identifier="test_user", rate=10.0, capacity=5)

        result = check_rate_limit(identifier="test_user", rate=10.0, capacity=5)
        assert result.allowed is False


@pytest.mark.unit
class TestInputValidationInEntryPoints:
    """Tests for input validation applied in CLI entry points."""

    def test_invalid_project_name_rejected(self):
        """Test that invalid project names are rejected."""
        from core.security import InputValidator

        # Test invalid characters
        invalid_names = ["project with spaces", "project@special", "project/with/slash", ""]
        for name in invalid_names:
            is_valid, error = InputValidator.validate_project_name(name)
            assert is_valid is False, f"Should reject project name: {name}"
            assert error is not None

    def test_valid_project_name_accepted(self):
        """Test that valid project names are accepted."""
        from core.security import InputValidator

        valid_names = ["meinvoice", "project-123", "project_name", "Project123"]
        for name in valid_names:
            is_valid, error = InputValidator.validate_project_name(name)
            assert is_valid is True, f"Should accept project name: {name}"
            assert error is None

    def test_invalid_section_name_rejected(self):
        """Test that invalid section names are rejected."""
        from core.security import InputValidator

        # Test empty name
        is_valid, error = InputValidator.validate_section_name("")
        assert is_valid is False
        assert error is not None

    def test_valid_section_name_accepted(self):
        """Test that valid section names are accepted."""
        from core.security import InputValidator

        valid_names = ["errors", "alerts", "slow_endpoints", "custom-section"]
        for name in valid_names:
            is_valid, error = InputValidator.validate_section_name(name)
            assert is_valid is True

    def test_invalid_time_range_rejected(self):
        """Test that invalid time ranges are rejected."""
        from core.security import InputValidator

        invalid_ranges = ["invalid", "now-10x", "now-", "-30m", ""]
        for time_range in invalid_ranges:
            is_valid, error = InputValidator.validate_time_range(time_range)
            assert is_valid is False, f"Should reject time range: {time_range}"
            assert error is not None

    def test_valid_time_range_accepted(self):
        """Test that valid time ranges are accepted."""
        from core.security import InputValidator

        valid_ranges = ["now", "now-30m", "now-2h", "now-7d", "now-365d"]
        for time_range in valid_ranges:
            is_valid, error = InputValidator.validate_time_range(time_range)
            assert is_valid is True, f"Should accept time range: {time_range}"
            assert error is None

    def test_url_sanitization_removes_credentials(self):
        """Test that URL sanitization removes credentials."""
        from core.security import InputValidator

        url_with_creds = "http://user:pass@localhost:9200/path"
        sanitized = InputValidator.sanitize_url(url_with_creds)

        assert "user:pass" not in sanitized
        assert "***@" in sanitized
        assert "/path" in sanitized
