"""Phase A chatops: Telegram webhook — secret token, chat allowlist,
approve/reject callbacks, read-only commands."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.settings import settings


def _make_client() -> TestClient:
    from app.approvals.telegram_webhook import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def telegram_env(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "tg-secret")
    monkeypatch.setattr(settings, "TELEGRAM_ALLOWED_CHAT_IDS", [42])
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    return settings


def _headers(token: str = "tg-secret") -> dict[str, str]:
    return {"X-Telegram-Bot-Api-Secret-Token": token}


def _callback(action_id: str = "act-1", verb: str = "approve", chat_id: int = 42) -> dict:
    return {
        "callback_query": {
            "data": f"{verb}:{action_id}",
            "from": {"id": 7, "username": "cuong"},
            "message": {"chat": {"id": chat_id}},
        }
    }


@pytest.fixture
def mock_notifier(monkeypatch):
    notifier = MagicMock()
    notifier.send_message = AsyncMock(return_value=True)
    notifier.send_approval_status = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "app.approvals.telegram_webhook.get_telegram_notifier", lambda: notifier
    )
    return notifier


class TestSecretToken:
    def test_missing_secret_config_fails_hard(self, monkeypatch, mock_notifier):
        monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "")
        client = _make_client()

        r = client.post("/approvals/webhook/telegram", headers=_headers(""), json={})

        assert r.status_code == 500
        assert "TELEGRAM_WEBHOOK_SECRET" in r.json()["detail"]

    def test_wrong_token_rejected(self, telegram_env, mock_notifier):
        client = _make_client()

        r = client.post("/approvals/webhook/telegram", headers=_headers("wrong"), json={})

        assert r.status_code == 401

    def test_missing_header_rejected(self, telegram_env, mock_notifier):
        client = _make_client()

        r = client.post("/approvals/webhook/telegram", json={})

        assert r.status_code == 401


class TestChatAllowlist:
    def test_empty_allowlist_denies_everyone(self, telegram_env, monkeypatch, mock_notifier):
        monkeypatch.setattr(settings, "TELEGRAM_ALLOWED_CHAT_IDS", [])
        client = _make_client()

        r = client.post(
            "/approvals/webhook/telegram", headers=_headers(), json=_callback()
        )

        assert r.status_code == 403

    def test_unlisted_chat_denied(self, telegram_env, mock_notifier):
        client = _make_client()

        r = client.post(
            "/approvals/webhook/telegram",
            headers=_headers(),
            json=_callback(chat_id=999),
        )

        assert r.status_code == 403


class TestCallbacks:
    @pytest.fixture
    def mock_engine(self, monkeypatch):
        engine = MagicMock()
        engine.approve_action = AsyncMock(
            return_value=MagicMock(status=MagicMock(value="approved"), id="act-1")
        )
        engine.reject_action = AsyncMock(
            return_value=MagicMock(status=MagicMock(value="rejected"), id="act-1")
        )
        engine.get_action = AsyncMock(return_value={"command": "kubectl get pods"})
        monkeypatch.setattr(
            "app.actions.engine.get_action_engine", lambda: engine
        )
        return engine

    @pytest.fixture
    def approval_gate(self, monkeypatch):
        """Phase B gate on: chat user 'cuong' maps to platform user 'alice'."""
        monkeypatch.setattr(settings, "CHATOPS_APPROVALS_ENABLED", True)
        monkeypatch.setattr(settings, "TELEGRAM_APPROVER_MAP", {"cuong": "alice"})
        monkeypatch.setattr("app.users.get_role", lambda username: "admin" if username == "alice" else None)

    def test_approve_callback_maps_to_platform_user(
        self, telegram_env, mock_notifier, mock_engine, approval_gate
    ):
        client = _make_client()

        r = client.post("/approvals/webhook/telegram", headers=_headers(), json=_callback())

        assert r.status_code == 200
        assert r.json() == {"ok": True}
        mock_engine.approve_action.assert_awaited_once()
        request = mock_engine.approve_action.await_args.kwargs["request"]
        # Attribution is the canonical platform username, not "telegram:cuong" —
        # the self-approval ban compares against created_by.
        assert request.approved_by == "alice"
        # auth_user drives per-user RBAC narrowing in the engine.
        assert mock_engine.approve_action.await_args.kwargs["auth_user"] == "alice"
        mock_notifier.send_approval_status.assert_awaited_once()

    def test_reject_callback(self, telegram_env, mock_notifier, mock_engine, approval_gate):
        client = _make_client()

        r = client.post(
            "/approvals/webhook/telegram",
            headers=_headers(),
            json=_callback(verb="reject"),
        )

        assert r.status_code == 200
        mock_engine.reject_action.assert_awaited_once()
        request = mock_engine.reject_action.await_args.kwargs["request"]
        assert request.rejected_by == "alice"
        assert mock_engine.reject_action.await_args.kwargs["auth_user"] == "alice"

    def test_approve_denied_when_gate_disabled(self, telegram_env, mock_notifier, mock_engine):
        """CHATOPS_APPROVALS_ENABLED defaults off — buttons refuse, engine untouched."""
        client = _make_client()

        r = client.post("/approvals/webhook/telegram", headers=_headers(), json=_callback())

        assert r.status_code == 200
        mock_engine.approve_action.assert_not_awaited()
        assert "⛔" in mock_notifier.send_message.await_args.args[1]

    def test_approve_denied_for_unmapped_sender(
        self, telegram_env, mock_notifier, mock_engine, monkeypatch
    ):
        monkeypatch.setattr(settings, "CHATOPS_APPROVALS_ENABLED", True)
        monkeypatch.setattr(settings, "TELEGRAM_APPROVER_MAP", {"someone-else": "alice"})
        client = _make_client()

        r = client.post("/approvals/webhook/telegram", headers=_headers(), json=_callback())

        assert r.status_code == 200
        mock_engine.approve_action.assert_not_awaited()

    def test_approve_denied_when_mapped_user_has_no_role(
        self, telegram_env, mock_notifier, mock_engine, monkeypatch
    ):
        monkeypatch.setattr(settings, "CHATOPS_APPROVALS_ENABLED", True)
        monkeypatch.setattr(settings, "TELEGRAM_APPROVER_MAP", {"cuong": "alice"})
        monkeypatch.setattr("app.users.get_role", lambda username: None)
        client = _make_client()

        r = client.post("/approvals/webhook/telegram", headers=_headers(), json=_callback())

        assert r.status_code == 200
        mock_engine.approve_action.assert_not_awaited()

    def test_engine_permission_denial_surfaced_to_chat(
        self, telegram_env, mock_notifier, mock_engine, approval_gate
    ):
        """Engine-side RBAC/self-approval denial → chat message, not a 500."""
        mock_engine.approve_action = AsyncMock(side_effect=PermissionError("lacks approve"))
        client = _make_client()

        r = client.post("/approvals/webhook/telegram", headers=_headers(), json=_callback())

        assert r.status_code == 200
        assert "Refused" in mock_notifier.send_message.await_args.args[1]

    def test_malformed_callback_data_rejected(self, telegram_env, mock_notifier, mock_engine):
        client = _make_client()
        payload = _callback()
        payload["callback_query"]["data"] = "nonsense-no-colon"

        r = client.post("/approvals/webhook/telegram", headers=_headers(), json=payload)

        assert r.status_code == 400

    def test_unknown_verb_rejected(self, telegram_env, mock_notifier, mock_engine):
        client = _make_client()

        r = client.post(
            "/approvals/webhook/telegram",
            headers=_headers(),
            json=_callback(verb="execute"),  # no execute verb exists — by design
        )

        assert r.status_code == 400
        mock_engine.approve_action.assert_not_awaited()


class TestCommands:
    async def test_status_command_answers_with_formatted_text(
        self, telegram_env, mock_notifier, monkeypatch
    ):
        from app.approvals.telegram_webhook import _handle_command

        monkeypatch.setattr(
            "app.approvals.telegram_webhook.collect_system_status",
            AsyncMock(return_value={"systems": {}, "active_alerts": 3}),
        )
        message = {"text": "/status", "chat": {"id": 42}}
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

        result = await _handle_command(request=request, message=message, notifier=mock_notifier)

        assert result == {"ok": True}
        text = mock_notifier.send_message.await_args.args[1]
        assert "Trạng thái hệ thống" in text
        assert "3" in text

    async def test_help_and_unknown_commands(self, telegram_env, mock_notifier):
        from app.approvals.telegram_webhook import _handle_command

        for text in ("/help", "/deploy", "xin chào"):
            mock_notifier.send_message.reset_mock()
            await _handle_command(
                request=None, message={"text": text, "chat": {"id": 42}},
                notifier=mock_notifier,
            )
            assert mock_notifier.send_message.await_count == 1


class TestNonMessageUpdates:
    def test_edits_acked_without_side_effects(self, telegram_env, mock_notifier):
        client = _make_client()

        r = client.post(
            "/approvals/webhook/telegram",
            headers=_headers(),
            json={"edited_message": {"text": "x", "chat": {"id": 42}}},
        )

        assert r.status_code == 200
        assert r.json() == {"ok": True}
        mock_notifier.send_message.assert_not_awaited()
