import asyncio
import json
from urllib.parse import parse_qs
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.config import settings

router = APIRouter()

_ALLOWED_ORIGINS: set[str] = set()


def set_allowed_origins(origins: list[str]):
    global _ALLOWED_ORIGINS
    for o in origins:
        _ALLOWED_ORIGINS.add(o.rstrip("/"))
        # Also allow host-only form (strip scheme)
        if "://" in o:
            _ALLOWED_ORIGINS.add(o.split("://", 1)[1].rstrip("/"))


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> bool:
        origin = ws.headers.get("origin", "")
        if settings.AUTH_ENABLED and _ALLOWED_ORIGINS and origin not in _ALLOWED_ORIGINS:
            await ws.close(code=4403, reason="Origin not allowed")
            return False

        # Auth: check query param token or header
        if settings.AUTH_ENABLED:
            token = ws.query_params.get("token")
            if not token:
                auth = ws.headers.get("Authorization", "")
                if auth.startswith("Bearer "):
                    token = auth[7:]
            if token:
                from app.auth import _is_valid_token, _is_valid_api_key
                if not (_is_valid_token(token) or _is_valid_api_key(token)):
                    await ws.close(code=4403, reason="Unauthorized")
                    return False
            else:
                await ws.close(code=4403, reason="Missing auth token")
                return False

        await ws.accept()
        self.active.append(ws)
        return True

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        msg = json.dumps(data)
        for ws in self.active[:]:
            try:
                await ws.send_text(msg)
            except Exception:
                if ws in self.active:
                    self.active.remove(ws)


manager = ConnectionManager()
set_allowed_origins(settings.CORS_ORIGINS)


@router.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    connected = await manager.connect(ws)
    if not connected:
        return
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
