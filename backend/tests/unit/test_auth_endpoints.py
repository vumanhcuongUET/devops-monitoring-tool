"""Auth token endpoints: 15-min tokens + /auth/refresh sliding sessions."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import _is_valid_token, create_token
from app.settings import settings
from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_token_response_includes_ttl(client, monkeypatch):
    monkeypatch.setattr(settings, "API_KEYS", ["test-key-123"], raising=False)
    resp = await client.post("/api/v1/auth/token", headers={"X-API-Key": "test-key-123"})
    assert resp.status_code == 200
    body = resp.json()
    assert _is_valid_token(body["access_token"])
    assert body["expires_in"] == settings.AUTH_TOKEN_TTL_SECONDS == 900


async def test_refresh_with_valid_token(client):
    resp = await client.post(
        "/api/v1/auth/refresh", headers={"Authorization": f"Bearer {create_token()}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert _is_valid_token(body["access_token"])
    assert body["expires_in"] == 900


async def test_refresh_with_invalid_token_rejected(client):
    resp = await client.post("/api/v1/auth/refresh", headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


async def test_refresh_without_token_rejected(client):
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401
