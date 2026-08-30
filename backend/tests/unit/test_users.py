"""Phase 13 identity: user store, login, middleware propagation, RBAC roles."""


import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app


@pytest.fixture
def user_store(tmp_path, monkeypatch):
    """Isolated users.json per test."""
    f = tmp_path / "users.json"
    monkeypatch.setattr("app.users.USERS_FILE", f)
    return f


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _mkuser(name, password="pw", role="operator"):
    from app.users import create_user

    create_user(name, password, role)
    return name


# ---------- user store ----------


def test_create_verify_roundtrip(user_store):
    from app.users import create_user, verify_login

    create_user("alice", "pw", "admin")
    assert verify_login("alice", "pw") == "admin"
    assert verify_login("alice", "wrong") is None
    assert verify_login("nobody", "pw") is None


def test_role_validation(user_store):
    from app.users import create_user

    with pytest.raises(ValueError):
        create_user("x", "pw", "superuser")


def test_delete_revokes(user_store):
    from app.users import delete_user, get_role

    _mkuser("bob", role="viewer")
    assert get_role("bob") == "viewer"
    delete_user("bob")
    assert get_role("bob") is None


def test_scrypt_format(user_store):
    from app.users import _hash_password, _verify_password

    h = _hash_password("s3cret")
    assert h.startswith("scrypt$")
    assert _verify_password("s3cret", h)
    assert not _verify_password("other", h)


# ---------- login endpoint ----------


async def test_login_success_returns_user_token(client, user_store, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    _mkuser("carol", "pw", "operator")
    resp = await client.post("/api/v1/auth/login", json={"username": "carol", "password": "pw"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "operator"
    from app.auth import decode_token

    assert decode_token(body["access_token"])["sub"] == "carol"


async def test_login_wrong_password_401(client, user_store, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    _mkuser("carol", "pw")
    resp = await client.post("/api/v1/auth/login", json={"username": "carol", "password": "bad"})
    assert resp.status_code == 401


async def test_refresh_keeps_user_subject(client, user_store):
    from app.auth import decode_token
    from app.users import create_user

    create_user("erin", "pw", "viewer")
    resp = await client.post(
        "/api/v1/auth/refresh", headers={"Authorization": f"Bearer {_tok('erin')}"}
    )
    assert resp.status_code == 200
    assert decode_token(resp.json()["access_token"])["sub"] == "erin"


async def test_refresh_revoked_user_401(client, user_store):
    from app.users import create_user, delete_user

    create_user("frank", "pw")
    tok = _tok("frank")
    delete_user("frank")
    resp = await client.post("/api/v1/auth/refresh", headers={"Authorization": f"Bearer {tok}"})
    assert resp.status_code == 401


# ---------- middleware + attribution ----------


def _tok(name):
    from app.auth import create_token

    return create_token(name)


async def test_revoked_user_token_rejected_by_middleware(client, user_store, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    from app.users import create_user, delete_user

    create_user("grace", "pw")
    tok = _tok("grace")
    resp = await client.get("/api/v1/skills/", headers={"Authorization": f"Bearer {tok}"})
    first = resp.status_code
    delete_user("grace")
    resp = await client.get("/api/v1/skills/", headers={"Authorization": f"Bearer {tok}"})
    assert resp.status_code == 401
    assert first in (200, 403)  # live user reaches the route (403 possible per RBAC)


# ---------- RBAC role matrix ----------


def test_role_allows_matrix():
    from app.governance.ai_rbac import AIPermission, role_allows

    # admin: everything everywhere
    assert role_allows("admin", AIPermission.DELETE, "production")
    # operator: full in dev/staging, view+scale only in prod
    assert role_allows("operator", AIPermission.EXECUTE, "development")
    assert role_allows("operator", AIPermission.SCALE, "production")
    assert not role_allows("operator", AIPermission.DELETE, "production")
    # viewer: view-only
    assert role_allows("viewer", AIPermission.VIEW, "production")
    assert not role_allows("viewer", AIPermission.SCALE, "development")
    # unknown role denies
    assert not role_allows("superuser", AIPermission.VIEW, "development")


def test_permission_checker_narrows_by_role(user_store):
    from app.governance.permission_checker import AIPermissionChecker

    from app.users import create_user

    create_user("henrik", "pw", "viewer")
    checker = AIPermissionChecker(default_environment="production", enable_rate_limit=False)

    # viewer henrik cannot delete even in dev; unknown label (Slack) unaffected
    result = checker.check("delete", environment="development", user="henrik")
    assert not result.allowed
    assert "viewer" in result.reason

    # Slack-style attribution without local role: env baseline only
    result = checker.check("delete", environment="development", user="slack-dude")
    assert result.allowed  # dev baseline allows delete

    # service identity: unchanged behavior
    result = checker.check("delete", environment="development", user="service")
    assert result.allowed


async def test_login_malformed_json_400(client):
    resp = await client.post(
        "/api/v1/auth/login", content=b"{not-json", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 400


def test_store_cache_sees_external_writes(user_store):
    """mtime cache must invalidate when the file changes underneath."""
    from app.users import get_role, create_user

    import json as _json

    create_user("kim", "pw", "viewer")
    assert get_role("kim") == "viewer"

    data = _json.loads(user_store.read_text())
    data["kim"]["role"] = "admin"
    user_store.write_text(_json.dumps(data))

    assert get_role("kim") == "admin"
