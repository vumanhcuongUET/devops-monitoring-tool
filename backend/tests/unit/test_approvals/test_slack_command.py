"""Phase A chatops: Slack `/devops` slash command — signature, ACK pattern,
SSRF-guarded response_url delivery."""

import hashlib
import hmac
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.settings import settings

SLACK_SIGNATURE_VERSION = "v0"


def _sign(body: str, timestamp: str, secret: str) -> str:
    base = f"{SLACK_SIGNATURE_VERSION}:{timestamp}:{body}"
    digest = hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest()
    return f"{SLACK_SIGNATURE_VERSION}={digest}"


def _form_body(text: str, response_url: str = "https://hooks.slack.com/T1/B2/xx") -> str:
    from urllib.parse import urlencode

    return urlencode({
        "command": "/devops",
        "text": text,
        "response_url": response_url,
        "user_name": "cuong",
    })


def _make_client() -> TestClient:
    from app.approvals.slack_command import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _headers(body: str, secret: str = "test-secret") -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": _sign(body, timestamp, secret),
    }


@pytest.fixture
def slack_env(monkeypatch):
    monkeypatch.setattr(settings, "SLACK_SIGNING_SECRET", "test-secret")
    return settings


@pytest.fixture
def mock_deliver(monkeypatch):
    deliver = AsyncMock(return_value=None)
    monkeypatch.setattr("app.approvals.slack_command._deliver", deliver)
    return deliver


class TestSignature:
    def test_missing_secret_config_fails_hard(self, monkeypatch, mock_deliver):
        monkeypatch.setattr(settings, "SLACK_SIGNING_SECRET", "")
        client = _make_client()
        body = _form_body("status")

        # Slack always sends the signature headers; without a configured
        # secret the handler must fail hard (500), not just 401.
        r = client.post(
            "/approvals/webhook/slack/command",
            content=body.encode(),
            headers=_headers(body),
        )

        assert r.status_code == 500
        assert "SLACK_SIGNING_SECRET" in r.json()["detail"]

    def test_bad_signature_rejected(self, slack_env, mock_deliver):
        client = _make_client()
        body = _form_body("status")

        r = client.post(
            "/approvals/webhook/slack/command",
            content=body.encode(),
            headers=_headers(body, secret="attacker-secret"),
        )

        assert r.status_code == 401
        mock_deliver.assert_not_awaited()


class TestAckPattern:
    def test_status_acks_immediately_and_schedules_background_task(
        self, slack_env, mock_deliver, monkeypatch
    ):
        status_mock = AsyncMock(return_value={"systems": {}, "active_alerts": 0})
        monkeypatch.setattr(
            "app.approvals.slack_command.collect_system_status", status_mock
        )
        client = _make_client()
        body = _form_body("status")

        r = client.post(
            "/approvals/webhook/slack/command",
            content=body.encode(),
            headers=_headers(body),
        )

        assert r.status_code == 200
        assert r.json()["response_type"] == "in_channel"
        assert "Đang kiểm tra" in r.json()["text"]

    def test_help_delivers_help_text_synchronously(
        self, slack_env, mock_deliver
    ):
        client = _make_client()
        body = _form_body("help")

        r = client.post(
            "/approvals/webhook/slack/command",
            content=body.encode(),
            headers=_headers(body),
        )

        assert r.status_code == 200
        mock_deliver.assert_awaited_once()
        assert "lệnh hỗ trợ" in mock_deliver.await_args.args[1]

    def test_unknown_subcommand_gets_help(self, slack_env, mock_deliver):
        client = _make_client()
        body = _form_body("deploy-prod-now")

        r = client.post(
            "/approvals/webhook/slack/command",
            content=body.encode(),
            headers=_headers(body),
        )

        assert r.status_code == 200
        assert "lệnh hỗ trợ" in mock_deliver.await_args.args[1]


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient used as an async context manager."""

    posted: list = []

    def __init__(self, capture: list):
        self._capture = capture

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *args, **kwargs):
        self._capture.append((args, kwargs))
        return MagicMock(status_code=200)


class TestDeliver:
    async def test_posts_to_response_url(self, monkeypatch):
        import app.approvals.slack_command as sc

        posted: list = []
        monkeypatch.setattr(
            sc.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(posted)
        )

        await sc._deliver("https://hooks.slack.com/T1/B2/xx", "kết quả")

        assert len(posted) == 1
        payload = posted[0][1]["json"]
        assert payload["text"] == "kết quả"

    async def test_internal_response_url_blocked(self, monkeypatch):
        import app.approvals.slack_command as sc

        posted: list = []
        monkeypatch.setattr(
            sc.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(posted)
        )

        await sc._deliver("http://169.254.169.254/latest/meta-data", "kết quả")

        assert posted == []  # SSRF guard — metadata IP never contacted
