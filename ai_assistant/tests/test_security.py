"""
Tests for security module.
"""

import pytest

from core.security import InputValidator


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
class TestInputValidationInEntryPoints:
    """Tests for input validation applied in CLI entry points."""

    def test_invalid_project_name_rejected(self):
        """Test that invalid project names are rejected."""
        # Test invalid characters
        invalid_names = ["project with spaces", "project@special", "project/with/slash", ""]
        for name in invalid_names:
            is_valid, error = InputValidator.validate_project_name(name)
            assert is_valid is False, f"Should reject project name: {name}"
            assert error is not None

    def test_valid_project_name_accepted(self):
        """Test that valid project names are accepted."""
        valid_names = ["meinvoice", "project-123", "project_name", "Project123"]
        for name in valid_names:
            is_valid, error = InputValidator.validate_project_name(name)
            assert is_valid is True, f"Should accept project name: {name}"
            assert error is None

    def test_invalid_section_name_rejected(self):
        """Test that invalid section names are rejected."""
        # Test empty name
        is_valid, error = InputValidator.validate_section_name("")
        assert is_valid is False
        assert error is not None

    def test_valid_section_name_accepted(self):
        """Test that valid section names are accepted."""
        valid_names = ["errors", "alerts", "slow_endpoints", "custom-section"]
        for name in valid_names:
            is_valid, error = InputValidator.validate_section_name(name)
            assert is_valid is True

    def test_invalid_time_range_rejected(self):
        """Test that invalid time ranges are rejected."""
        invalid_ranges = ["invalid", "now-10x", "now-", "-30m", ""]
        for time_range in invalid_ranges:
            is_valid, error = InputValidator.validate_time_range(time_range)
            assert is_valid is False, f"Should reject time range: {time_range}"
            assert error is not None

    def test_valid_time_range_accepted(self):
        """Test that valid time ranges are accepted."""
        valid_ranges = ["now", "now-30m", "now-2h", "now-7d", "now-365d"]
        for time_range in valid_ranges:
            is_valid, error = InputValidator.validate_time_range(time_range)
            assert is_valid is True, f"Should accept time range: {time_range}"
            assert error is None

    def test_url_sanitization_removes_credentials(self):
        """Test that URL sanitization removes credentials."""
        url_with_creds = "http://user:pass@localhost:9200/path"
        sanitized = InputValidator.sanitize_url(url_with_creds)

        assert "user:pass" not in sanitized
        assert "***@" in sanitized
        assert "/path" in sanitized
