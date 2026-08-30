"""Local user store for per-user identity (Phase 13).

Single-operator tool growing multi-user support the lazy way: a JSON file
next to the other persistent state (alert rules, SLO configs), scrypt
password hashing from the stdlib, no new dependency and no mandatory
PostgreSQL. Roles are coarse on purpose: admin / operator / viewer.

Tokens carry the username in the `sub` claim; `get_role` returning None
(revoked/deleted user) invalidates outstanding tokens.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import secrets
import time
from pathlib import Path

logger = logging.getLogger(__name__)

USERS_FILE = Path("data/users.json")
VALID_ROLES = ("admin", "operator", "viewer")

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
        )
        return secrets.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _load_users() -> dict:
    if not USERS_FILE.exists():
        return {}
    try:
        return json.loads(USERS_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.error("User store unreadable (%s): %s", USERS_FILE, e)
        return {}


def _save_users(users: dict) -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, indent=2))
    os.chmod(USERS_FILE, 0o600)


def create_user(username: str, password: str, role: str = "operator") -> None:
    """Create or update a user. CLI bootstrap and tests only — never call
    from a request path."""
    if role not in VALID_ROLES:
        raise ValueError(f"role must be one of {VALID_ROLES}")
    if not username or not password:
        raise ValueError("username and password are required")
    users = _load_users()
    users[username] = {
        "password_hash": _hash_password(password),
        "role": role,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _save_users(users)
    logger.info("User %s saved with role %s", username, role)


def delete_user(username: str) -> bool:
    users = _load_users()
    if username not in users:
        return False
    del users[username]
    _save_users(users)
    return True


def list_users() -> dict[str, str]:
    """username -> role map (never exposes hashes)."""
    return {name: u.get("role", "viewer") for name, u in _load_users().items()}


def verify_login(username: str, password: str) -> str | None:
    """Return the user's role on valid credentials, else None.

    Constant-ish time on unknown users by hashing a throwaway password
    (keeps the timing shape of the failure path similar).
    """
    users = _load_users()
    entry = users.get(username)
    if entry is None:
        _hash_password(password)  # burn comparable time
        return None
    if not _verify_password(password, entry["password_hash"]):
        return None
    return entry.get("role", "viewer")


def get_role(username: str | None) -> str | None:
    """Current role for a token subject; None means unknown/revoked user."""
    if not username:
        return None
    return _load_users().get(username, {}).get("role")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage local users")
    sub = parser.add_subparsers(dest="command", required=True)
    p_create = sub.add_parser("create", help="Create or update a user")
    p_create.add_argument("username")
    p_create.add_argument("password")
    p_create.add_argument("--role", default="operator", choices=VALID_ROLES)
    p_del = sub.add_parser("delete", help="Delete a user")
    p_del.add_argument("username")
    p_list = sub.add_parser("list", help="List usernames and roles")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.command == "create":
        create_user(args.username, args.password, args.role)
        print(f"OK {args.username} ({args.role})")
    elif args.command == "delete":
        print("OK" if delete_user(args.username) else "NOT FOUND")
    else:
        for name, role in sorted(list_users().items()):
            print(f"{name}: {role}")
