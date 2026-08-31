"""Unit tests for RateLimitMiddleware (Phase 15 P2-14).

Covers the three ledger findings: trusted proxies not honored (one global
bucket behind an ingress), X-Real-IP accepted verbatim, and the unbounded
per-key window dict.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.rate_limit import MAX_TRACKED_CLIENTS, RateLimitMiddleware


def _mw(trusted_proxies=None, rpm=60, burst=20) -> RateLimitMiddleware:
    async def dummy_app(scope, receive, send):  # pragma: no cover
        pass

    return RateLimitMiddleware(
        dummy_app,
        requests_per_minute=rpm,
        burst=burst,
        trusted_proxies=trusted_proxies or [],
    )


def _request(client_ip="10.0.0.9", headers=None):
    return SimpleNamespace(
        client=SimpleNamespace(host=client_ip),
        headers={k.lower(): v for k, v in (headers or {}).items()},
    )


class TestClientIdentification:
    def test_no_trusted_proxies_ignores_forwarded_headers(self):
        mw = _mw()
        req = _request(headers={"x-forwarded-for": "1.2.3.4", "x-real-ip": "1.2.3.4"})
        assert mw._client_id(req) == "ip:10.0.0.9"

    def test_trusted_proxy_xff_takes_rightmost_untrusted(self):
        """Leftmost is attacker-controlled; the client is the first address
        from the right that is not itself a trusted proxy."""
        mw = _mw(trusted_proxies=["10.0.0.0/8"])
        req = _request(
            client_ip="10.0.0.1",
            headers={"x-forwarded-for": "spoofed-by-attacker, 1.2.3.4"},
        )
        assert mw._client_id(req) == "ip:1.2.3.4"

    def test_trusted_proxy_xff_single_entry(self):
        mw = _mw(trusted_proxies=["10.0.0.0/8"])
        req = _request(client_ip="10.0.0.1", headers={"x-forwarded-for": "9.9.9.9"})
        assert mw._client_id(req) == "ip:9.9.9.9"

    def test_trusted_chain_falls_back_to_direct_ip(self):
        mw = _mw(trusted_proxies=["10.0.0.0/8", "172.16.0.0/12"])
        req = _request(
            client_ip="10.0.0.1",
            headers={"x-forwarded-for": "172.16.5.5, 10.0.0.2"},
        )
        assert mw._client_id(req) == "ip:10.0.0.1"

    def test_malformed_xff_entry_falls_back_to_direct_ip(self):
        mw = _mw(trusted_proxies=["10.0.0.0/8"])
        req = _request(client_ip="10.0.0.1", headers={"x-forwarded-for": "not-an-ip"})
        assert mw._client_id(req) == "ip:10.0.0.1"

    def test_x_real_ip_accepted_only_valid_from_trusted(self):
        mw = _mw(trusted_proxies=["10.0.0.0/8"])
        req = _request(client_ip="10.0.0.1", headers={"x-real-ip": "8.8.8.8"})
        assert mw._client_id(req) == "ip:8.8.8.8"

    def test_x_real_ip_junk_rejected(self):
        """X-Real-IP is never trusted verbatim — junk must not become a key."""
        mw = _mw(trusted_proxies=["10.0.0.0/8"])
        req = _request(client_ip="10.0.0.1", headers={"x-real-ip": "junk;drop table"})
        assert mw._client_id(req) == "ip:10.0.0.1"

    def test_x_real_ip_ignored_without_trusted_proxy(self):
        mw = _mw()
        req = _request(headers={"x-real-ip": "8.8.8.8"})
        assert mw._client_id(req) == "ip:10.0.0.9"

    def test_untrusted_direct_ip_spoof_attempt_ignored(self):
        mw = _mw(trusted_proxies=["192.168.0.0/16"])
        req = _request(client_ip="10.0.0.1", headers={"x-forwarded-for": "1.2.3.4"})
        assert mw._client_id(req) == "ip:10.0.0.1"

    def test_missing_client_uses_unknown(self):
        req = SimpleNamespace(client=None, headers={})
        assert _mw()._client_id(req) == "ip:unknown"


class TestBoundedWindows:
    @pytest.mark.asyncio
    async def test_stale_keys_swept(self):
        mw = _mw()
        mw._last_sweep = 0.0
        with patch("app.rate_limit.time.time", side_effect=[1000.0, 1061.0]):
            await mw._is_limited_memory("ip:1.1.1.1")
            assert "ip:1.1.1.1" in mw._windows
            # One sweep interval later, the idle key is gone.
            await mw._is_limited_memory("ip:2.2.2.2")
        assert "ip:1.1.1.1" not in mw._windows
        assert "ip:2.2.2.2" in mw._windows

    @pytest.mark.asyncio
    async def test_window_dict_capped(self):
        mw = _mw()
        mw._last_sweep = 10_000.0  # keep the sweep off for this test
        with patch("app.rate_limit.time.time", return_value=10_000.0), \
             patch("app.rate_limit.MAX_TRACKED_CLIENTS", 50):
            for i in range(200):
                await mw._is_limited_memory(f"ip:10.0.{i}.1")
        assert len(mw._windows) <= 50

    def test_module_cap_is_bounded(self):
        assert MAX_TRACKED_CLIENTS == 10_000
