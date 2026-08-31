"""
Security Module - SSRF Protection and Input Validation

Phase 9 - Sprint 3 - Day 12
Enhanced with:
- DNS caching to prevent DNS rebinding attacks
- Comprehensive IP range blocking
- Request validation helpers
"""
import ipaddress
import re
import socket
import time
from urllib.parse import urlparse

import httpx

from app.config import settings

# =============================================================================
# Enhanced SSRF Protection with DNS Caching
# =============================================================================

class SSRFProtection:
    """
    Enhanced SSRF protection with DNS caching and rebinding prevention.

    Features:
    - DNS resolution caching with TTL (prevents DNS rebinding)
    - Comprehensive blocked network ranges
    - Hostname blocklist for cloud metadata services
    - IP-based validation after DNS resolution

    Usage:
        is_safe, error = SSRFProtection.resolve_and_validate("example.com")
        if not is_safe:
            raise ValueError(f"Invalid URL: {error}")
    """

    # DNS cache: hostname -> (ip_list, timestamp)
    _dns_cache: dict[str, tuple[list[str], float]] = {}
    _cache_ttl = 300  # 5 minutes TTL for DNS cache

    # Blocked networks (private, loopback, link-local)
    BLOCKED_NETWORKS: set[str] = {
        "127.0.0.0/8",      # Loopback
        "169.254.0.0/16",   # Link-local
        "10.0.0.0/8",       # Private Class A
        "172.16.0.0/12",     # Private Class B
        "192.168.0.0/16",   # Private Class C
        "0.0.0.0/8",        # Current network
        "100.64.0.0/10",    # Carrier-grade NAT
        "192.0.0.0/24",     # IETF Protocol Assignments
        "192.0.2.0/24",     # TEST-NET-1
        "198.18.0.0/15",    # Network interconnect device benchmark
        "203.0.113.0/24",   # TEST-NET-2
        "224.0.0.0/4",      # IP multicast
        "240.0.0.0/4",      # Reserved
        "255.255.255.255/32", # Broadcast
        "::1/128",           # IPv6 loopback
        "fc00::/7",         # IPv6 unique-local
        "fe80::/10",        # IPv6 link-local
        "ff00::/8",         # IPv6 multicast
    }

    # Blocked hostnames (cloud metadata services)
    BLOCKED_HOSTNAMES: set[str] = {
        "metadata.google.internal",
        "metadata.internal",
        "169.254.169.254",  # AWS/GCP/Azure metadata
    }

    @classmethod
    def resolve_and_validate(
        cls,
        hostname: str,
        port: int | None = None,
    ) -> tuple[bool, str]:
        """
        Resolve hostname and validate against SSRF rules.

        Args:
            hostname: The hostname to validate
            port: Optional port number (not used for blocking, just for context)

        Returns:
            Tuple of (is_safe, error_message)
            - is_safe: True if hostname is safe to access
            - error_message: Error description if not safe

        Example:
            >>> is_safe, error = SSRFProtection.resolve_and_validate("example.com")
            >>> if not is_safe:
            ...     raise ValueError(f"Invalid URL: {error}")
        """
        now = time.time()

        # Check hostname blocklist first
        if hostname.lower() in cls.BLOCKED_HOSTNAMES:
            return False, f"Hostname {hostname} is blocked (metadata service)"

        # Check DNS cache
        if hostname in cls._dns_cache:
            resolved_ips, cached_time = cls._dns_cache[hostname]
            if now - cached_time < cls._cache_ttl:
                # Cache is still valid, use cached IPs
                return cls._validate_ips(resolved_ips, hostname)
            else:
                # Cache expired, remove and resolve fresh
                del cls._dns_cache[hostname]

        # Resolve DNS
        resolved_ips = cls._resolve_dns(hostname)

        # Update cache
        cls._dns_cache[hostname] = (resolved_ips, now)

        # Validate resolved IPs
        return cls._validate_ips(resolved_ips, hostname)

    @classmethod
    def _resolve_dns(cls, hostname: str) -> list[str]:
        """
        Resolve hostname to IP addresses.

        Args:
            hostname: The hostname to resolve

        Returns:
            List of IP addresses (strings)

        Raises:
            ValueError: If DNS resolution fails
        """
        try:
            addr_info = socket.getaddrinfo(
                hostname,
                80,  # Port doesn't matter for resolution
                proto=socket.IPPROTO_TCP,
            )

            # Extract unique IPs
            ips = set()
            for info in addr_info:
                ip_str = info[4][0]
                ips.add(ip_str)

            return list(ips)

        except socket.gaierror as e:
            raise ValueError(f"DNS resolution failed for {hostname}: {e}") from e

    @classmethod
    def _validate_ips(cls, ips: list[str], hostname: str) -> tuple[bool, str]:
        """
        Validate resolved IP addresses against blocked networks.

        Args:
            ips: List of IP addresses to validate
            hostname: Original hostname (for error messages)

        Returns:
            Tuple of (is_safe, error_message)
        """
        if not ips:
            return False, f"No IPs resolved for {hostname}"

        for ip_str in ips:
            is_allowed = cls._is_ip_allowed(ip_str)
            if not is_allowed:
                return False, f"IP {ip_str} (from {hostname}) is not allowed (blocked network)"

        return True, ""

    @classmethod
    def _is_ip_allowed(cls, ip_str: str) -> bool:
        """
        Check if IP is allowed (not in blocked networks).

        Args:
            ip_str: IP address string

        Returns:
            True if IP is allowed, False if blocked
        """
        try:
            ip = ipaddress.ip_address(ip_str)

            for network_str in cls.BLOCKED_NETWORKS:
                network = ipaddress.ip_network(network_str, strict=False)
                if ip in network:
                    return False

            return True

        except ValueError:
            # Invalid IP address
            return False

    @classmethod
    def clear_dns_cache(cls) -> None:
        """Clear DNS cache (useful for testing or manual refresh)."""
        cls._dns_cache.clear()

    @classmethod
    def get_cache_stats(cls) -> dict[str, any]:
        """Get DNS cache statistics."""
        now = time.time()
        valid_entries = sum(
            1 for _, timestamp in cls._dns_cache.values()
            if now - timestamp < cls._cache_ttl
        )

        return {
            "total_entries": len(cls._dns_cache),
            "valid_entries": valid_entries,
            "cache_ttl": cls._cache_ttl,
        }


# =============================================================================
# Legacy Functions (for backward compatibility)
# =============================================================================

# Reserved CIDRs that should never be reached from user-controlled URLs
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),  # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]

_BLOCKED_HOSTNAMES = {"metadata.google.internal", "metadata.internal"}


def is_url_allowed(url: str) -> bool:
    """Check if a URL is safe to call (not internal/private)."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False

        if hostname.lower() in _BLOCKED_HOSTNAMES:
            return False

        # If allowed_webhook_hosts is configured, only allow those
        if settings.ALLOWED_WEBHOOK_HOSTS:
            allowed = any(hostname == h or hostname.endswith("." + h)
                         for h in settings.ALLOWED_WEBHOOK_HOSTS)
            if not allowed:
                return False

        # Resolve hostname and check against blocked networks
        import socket
        try:
            addr_info = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
        except socket.gaierror:
            return False

        for _family, _, _, _, sockaddr in addr_info:
            ip = ipaddress.ip_address(sockaddr[0])
            for network in _BLOCKED_NETWORKS:
                if ip in network:
                    return False
        return True
    except Exception:
        return False


async def safe_post(url: str, json: dict, timeout: int = 10) -> httpx.Response | None:
    """POST to URL only if it passes SSRF check."""
    if not is_url_allowed(url):
        return None
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(url, json=json)


# ── Input validation helpers ──────────────────────────────────────────

_SAFE_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9_\-.:*]+$")
_ES_QUERY_RE = re.compile(r"[\"\\{}[\]]")


def validate_identifier(value: str, field_name: str = "field") -> str:
    """Validate service names, config IDs, etc. Allow only safe chars."""
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    if len(value) > 256:
        raise ValueError(f"{field_name} too long (max 256)")
    if not _SAFE_IDENTIFIER_RE.match(value):
        raise ValueError(f"{field_name} contains invalid characters")
    return value


def sanitize_es_query(query: str) -> str:
    """Sanitize an Elasticsearch query_string user input.

    Phase 15 P2-11: beyond injection chars, two Lucene query_string
    constructs are DoS-shaped and now rejected:

    - Unquoted ``/`` starts a regex term (``/.*/``) — arbitrary automata over
      the term dictionary. Searching a literal path already requires quoting
      it in query_string syntax, so nothing legitimate is lost.
    - Leading wildcards (``*foo``, ``?foo``, ``field:*foo``) force full
      term-dictionary expansion. Trailing wildcards (``nginx-*``) stay
      allowed; a bare ``*`` (match-all, the endpoint default) stays allowed.
    """
    if len(query) > 1000:
        raise ValueError("Query string too long (max 1000)")
    if _ES_QUERY_RE.search(query):
        # Allow quotes and braces in simple queries but escape backslashes
        query = query.replace("\\", "\\\\")

    in_quote = False
    term_start = True
    escaped = False
    for ch in query:
        if escaped:
            escaped = False
            term_start = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_quote = not in_quote
            term_start = False
            continue
        if in_quote:
            term_start = False
            continue
        if ch == "/":
            raise ValueError(
                "Regex terms (unquoted '/') are not allowed; quote the text instead"
            )
        if ch.isspace() or ch in "():":
            term_start = True
            continue
        if ch in "[]{}^":
            term_start = False
            continue
        if ch in "+-":
            # NOT/PLUS operators — a wildcard after them is still leading.
            continue
        if term_start and ch in "*?":
            if query == "*":
                break  # bare match-all, the endpoint default
            raise ValueError("Leading wildcards are not allowed")
        term_start = False
    return query
