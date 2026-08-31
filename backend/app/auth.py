import base64
import hashlib
import hmac
import json
import time

from app.settings import settings


def _is_valid_api_key(key: str) -> bool:
    for stored in settings.API_KEYS:
        if hmac.compare_digest(key, stored):
            return True
    return False


def decode_token(token: str) -> dict | None:
    """Return the token payload ({\"sub\", \"iat\"}) when valid, else None.

    Phase 13: the payload carries the authenticated identity. Callers that
    only need a yes/no keep using _is_valid_token.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64, ts_b64, sig_b64 = parts
        expected_sig = _sign(payload_b64, ts_b64)
        if not hmac.compare_digest(sig_b64, expected_sig):
            return None
        ts = int.from_bytes(_b64decode(ts_b64), "big")
        if time.time() - ts > settings.AUTH_TOKEN_TTL_SECONDS:
            return None
        payload = json.loads(_b64decode(payload_b64))
        if not isinstance(payload, dict):
            return None
        return payload
    except Exception:
        return None


def _is_valid_token(token: str) -> bool:
    return decode_token(token) is not None


def create_token(subject: str = "service") -> str:
    """Mint a signed token for `subject` — a real username (user identity,
    RBAC role applies) or the "service" sentinel (API-key-minted automation
    tokens, environment-keyed RBAC as before Phase 13)."""
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": subject, "iat": int(time.time())}).encode()
    ).rstrip(b"=").decode()
    ts = base64.urlsafe_b64encode(
        int(time.time()).to_bytes(8, "big")
    ).rstrip(b"=").decode()
    sig = _sign(payload, ts)
    return f"{payload}.{ts}.{sig}"


def _sign(payload: str, ts: str) -> str:
    msg = f"{payload}.{ts}".encode()
    mac = hmac.new(settings.AUTH_SECRET.encode(), msg, hashlib.sha256)
    return base64.urlsafe_b64encode(mac.digest()).rstrip(b"=").decode()


def _b64decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)



