"""
Security utilities for AI Assistant.

Input validation for project/section names, time ranges, PromQL, URLs and
query templates. (The unused token-bucket rate limiter and HTTP header
checker were removed in Phase 15 P2-13 — nothing ever imported them.)
"""

import re
from typing import Any, Optional, Tuple


class InputValidator:
    """Validates input for security and safety."""

    # Dangerous patterns that could indicate injection attempts
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # XSS
        r'javascript:',  # JavaScript URI
        r'on\w+\s*=',  # Event handlers
        r'<\?php',  # PHP tags
        r'\$\{.*\}',  # Template injection
        r'\${.*}',  # Shell variable expansion
        r'vbscript:',  # VBScript URI
        r'data:',  # Data URI (potential XSS)
    ]

    # Max lengths for various inputs
    MAX_LENGTHS = {
        "project_name": 100,
        "section_name": 100,
        "time_range": 50,
        "index_pattern": 500,
        "query_body": 10000,  # 10KB max for query body
        "promql_query": 2000,
    }

    @classmethod
    def validate_project_name(cls, name: str) -> Tuple[bool, Optional[str]]:
        """
        Validate project name.

        Args:
            name: Project name to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not name:
            return False, "Project name cannot be empty"

        if len(name) > cls.MAX_LENGTHS["project_name"]:
            return False, f"Project name too long (max {cls.MAX_LENGTHS['project_name']} chars)"

        # Only allow alphanumeric, hyphens, underscores
        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            return False, "Project name can only contain letters, numbers, hyphens, and underscores"

        return True, None

    @classmethod
    def validate_section_name(cls, name: str) -> Tuple[bool, Optional[str]]:
        """Validate section name."""
        if not name:
            return False, "Section name cannot be empty"

        if len(name) > cls.MAX_LENGTHS["section_name"]:
            return False, f"Section name too long (max {cls.MAX_LENGTHS['section_name']} chars)"

        # Only allow alphanumeric, hyphens, underscores (same as project names)
        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            return False, "Section name can only contain letters, numbers, hyphens, and underscores"

        return True, None

    @classmethod
    def validate_time_range(cls, time_range: str) -> Tuple[bool, Optional[str]]:
        """Validate time range format."""
        if not time_range:
            return False, "Time range cannot be empty"

        if len(time_range) > cls.MAX_LENGTHS["time_range"]:
            return False, f"Time range too long (max {cls.MAX_LENGTHS['time_range']} chars)"

        # Validate format: now-<duration> or now
        if time_range != "now" and not re.match(r'^now-\d+[smhd]$', time_range):
            return False, "Invalid time range format (use: now or now-<number><s|m|h|d>)"

        return True, None

    @classmethod
    def validate_query_body(cls, body: Any) -> Tuple[bool, Optional[str]]:
        """Validate query body size and content."""
        if not isinstance(body, dict):
            return False, "Query body must be a dictionary"

        body_str = str(body)
        if len(body_str) > cls.MAX_LENGTHS["query_body"]:
            return False, f"Query body too large (max {cls.MAX_LENGTHS['query_body']} chars)"

        return True, None

    @classmethod
    def validate_promql(cls, promql: str) -> Tuple[bool, Optional[str]]:
        """Validate PromQL query."""
        if not promql:
            return False, "PromQL query cannot be empty"

        if len(promql) > cls.MAX_LENGTHS["promql_query"]:
            return False, f"PromQL query too long (max {cls.MAX_LENGTHS['promql_query']} chars)"

        # Check for dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, promql, re.IGNORECASE):
                return False, f"PromQL contains potentially dangerous pattern: {pattern}"

        return True, None

    @classmethod
    def sanitize_url(cls, url: str) -> str:
        """
        Sanitize URL for logging.

        Removes query parameters and fragments.
        """
        # Remove query parameters and fragment
        sanitized = re.sub(r'[?].*', '', url)
        # Remove potential credentials
        sanitized = re.sub(r'://[^@]*@', '://***@', sanitized)
        return sanitized

    @classmethod
    def validate_url(cls, url: str, allow_credentials: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Validate URL for safety.

        Args:
            url: URL to validate
            allow_credentials: Whether to allow embedded credentials

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not url:
            return False, "URL cannot be empty"

        # Max URL length
        if len(url) > 2000:
            return False, "URL too long (max 2000 chars)"

        # Check for dangerous patterns
        dangerous = [
            r'<script[^>]*>',  # XSS
            r'javascript:',  # JavaScript URI
            r'data:',  # Data URI (potential XSS)
            r'vbscript:',  # VBScript
        ]
        url_lower = url.lower()
        for pattern in dangerous:
            if re.search(pattern, url_lower):
                return False, f"URL contains dangerous pattern: {pattern}"

        # Only allow http/https protocols
        if not url_lower.startswith(('http://', 'https://')):
            return False, "URL must use http:// or https:// protocol"

        # Check for credentials if not allowed
        if not allow_credentials and '://' in url:
            # Extract host part
            after_proto = url.split('://', 1)[1] if '://' in url else ''
            if '@' in after_proto.split('/')[0]:
                return False, "URL must not contain embedded credentials"

        return True, None

    @classmethod
    def validate_template_content(cls, template: str, max_length: int = 10000) -> Tuple[bool, Optional[str]]:
        """
        Validate template content for safety.

        Args:
            template: Template string to validate
            max_length: Maximum allowed template length

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(template, str):
            return False, "Template must be a string"

        if len(template) > max_length:
            return False, f"Template too long (max {max_length} chars)"

        # Check for dangerous injection patterns
        injection_patterns = [
            (r'<\?php', 'PHP tags'),
            (r'<\s*script', 'Script tags'),
            (r'<\?\=', 'PHP short echo'),
            (r'<\s*%\s*@?', 'JSP tags'),
            (r'\$\{', 'Variable expression'),
            (r'`[^`]*`', 'Command substitution'),
            # HTML injection vectors the tag rules miss (review F3):
            # inline event handlers and embeddable tags.
            (r'\bon(error|load|click|mouseover|mouseout|focus|blur|submit|change|keydown|keyup|keypress|mouseenter|mouseleave|input)\s*=', 'HTML event handler'),
            (r'<\s*(img|iframe|svg|object|embed|body|form|input|link|meta)\b', 'Executable/embeddable HTML tag'),
            (r'javascript\s*:', 'javascript: URL'),
        ]

        for pattern, name in injection_patterns:
            if re.search(pattern, template, re.IGNORECASE):
                return False, f"Template contains potentially dangerous {name}"

        # Check for excessive nested brackets (potential DoS)
        depth = 0
        max_depth = 20
        for char in template:
            if char == '{':
                depth += 1
                if depth > max_depth:
                    return False, f"Template nesting too deep (max {max_depth})"
            elif char == '}':
                depth -= 1

        return True, None
