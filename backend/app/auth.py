import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone

from fastapi import Request, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPBearer

from app.config import settings


class APIKeyAuth:
    """Validates API key from X-API-Key header."""

    _scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

    async def __call__(self, request: Request, api_key: str = Security(_scheme)) -> str:
        if not settings.AUTH_ENABLED:
            return "anonymous"

        if api_key and _is_valid_api_key(api_key):
            return f"apikey:{api_key[:8]}"

        raise HTTPException(status_code=401, detail="Invalid API key")


class BearerAuth:
    """Validates JWT or HMAC-signed bearer tokens."""

    _scheme = HTTPBearer(auto_error=False)

    async def __call__(self, request: Request, credentials=Security(_scheme)) -> str:
        if not settings.AUTH_ENABLED:
            return "anonymous"

        if credentials and _is_valid_token(credentials.credentials):
            return f"bearer:{credentials.credentials[:8]}"

        raise HTTPException(status_code=401, detail="Invalid or expired token")


def _is_valid_api_key(key: str) -> bool:
    for stored in settings.API_KEYS:
        if hmac.compare_digest(key, stored):
            return True
    return False


def _is_valid_token(token: str) -> bool:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False
        payload_b64, ts_b64, sig_b64 = parts
        expected_sig = _sign(payload_b64, ts_b64)
        if not hmac.compare_digest(sig_b64, expected_sig):
            return False
        ts = int.from_bytes(_b64decode(ts_b64), "big")
        if time.time() - ts > settings.AUTH_TOKEN_TTL_SECONDS:
            return False
        return True
    except Exception:
        return False


def create_token(subject: str = "admin") -> str:
    import base64
    import json

    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": subject, "iat": int(time.time())}).encode()
    ).rstrip(b"=").decode()
    ts = base64.urlsafe_b64encode(
        int(time.time()).to_bytes(8, "big")
    ).rstrip(b"=").decode()
    sig = _sign(payload, ts)
    return f"{payload}.{ts}.{sig}"


def _sign(payload: str, ts: str) -> str:
    import base64

    msg = f"{payload}.{ts}".encode()
    mac = hmac.new(settings.AUTH_SECRET.encode(), msg, hashlib.sha256)
    return base64.urlsafe_b64encode(mac.digest()).rstrip(b"=").decode()


def _b64decode(s: str) -> bytes:
    import base64

    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


api_key_auth = APIKeyAuth()
bearer_auth = BearerAuth()
