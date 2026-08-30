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