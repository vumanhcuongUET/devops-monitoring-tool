"""Tests for AuthMiddleware webhook exemption (Phase 12 S3)."""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import AuthMiddleware


def _make_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.post("/api/v1/approvals/webhook/slack")
    def slack_stub():
        return {"ok": True}

    @app.get("/api/v1/overview")
    def overview_stub():
        return {"ok": True}

    return TestClient(app)


@patch("app.main.settings")
def test_webhook_path_skips_api_key_auth(mock_settings):
    mock_settings.AUTH_ENABLED = True
    client = _make_client()
    r = client.post("/api/v1/approvals/webhook/slack")
    assert r.status_code == 200


@patch("app.auth.settings")
@patch("app.main.settings")
def test_normal_route_requires_api_key(mock_settings, mock_auth_settings):
    mock_auth_settings.AUTH_ENABLED = True
    mock_auth_settings.API_KEYS = ["valid-key"]
    mock_settings.AUTH_ENABLED = True
    client = _make_client()
    r = client.get("/api/v1/overview")
    assert r.status_code == 401
    r = client.get("/api/v1/overview", headers={"X-API-Key": "valid-key"})
    assert r.status_code == 200


@patch("app.main.settings")
def test_health_still_public(mock_settings):
    mock_settings.AUTH_ENABLED = True
    client = _make_client()
    r = client.get("/health")
    assert r.status_code == 404  # not routed in stub app, but NOT 401


@patch("app.main.settings")
def test_auth_disabled_passes_all(mock_settings):
    mock_settings.AUTH_ENABLED = False
    client = _make_client()
    r = client.get("/api/v1/overview")
    assert r.status_code == 200

@patch("app.main.settings")
def test_unversioned_webhook_mount_also_exempt(mock_settings):
    """The approvals router is really mounted at /approvals/webhook/* (no
    /api/v1 prefix). Phase 12 manual smoke: only the versioned prefix was
    exempt, so a real Slack callback 401'd at the middleware — plain
    "Unauthorized" — before signature verification ever ran."""
    mock_settings.AUTH_ENABLED = True
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.post("/approvals/webhook/slack")
    def slack_stub():
        return {"ok": True}

    client = TestClient(app)
    r = client.post("/approvals/webhook/slack")
    assert r.status_code == 200


@patch("app.main.settings")
def test_revoked_token_rejected(mock_settings):
    """Phase 15: a token whose iat precedes the user's min_iat floor is
    rejected with 401 even though the signature is valid."""
    import time as time_module

    mock_settings.AUTH_ENABLED = True
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/whoami")
    def whoami():
        return {"ok": True}

    with patch("app.main.decode_token") as mock_decode, patch("app.main.get_role") as mock_role, \
         patch("app.main.get_min_iat", return_value=int(time_module.time()) + 100):
        mock_decode.return_value = {"sub": "alice", "iat": 1}
        mock_role.return_value = "admin"
        client = TestClient(app)
        r = client.get("/whoami", headers={"Authorization": "Bearer f.a.k.e"})

    assert r.status_code == 401
    assert r.json()["detail"] == "Token revoked"
