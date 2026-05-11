"""SSRF protection — block requests to internal/reserved IP ranges."""
import ipaddress
import re
from urllib.parse import urlparse

import httpx

from app.config import settings

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

        for family, _, _, _, sockaddr in addr_info:
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
    """Sanitize Elasticsearch query string to prevent injection."""
    if len(query) > 1000:
        raise ValueError("Query string too long (max 1000)")
    if _ES_QUERY_RE.search(query):
        # Allow quotes and braces in simple queries but escape backslashes
        query = query.replace("\\", "\\\\")
    return query
