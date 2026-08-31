import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.settings import settings

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
                from app.auth import _is_valid_api_key, decode_token
                from app.users import get_role

                payload = decode_token(token)
                if payload is None:
                    api_key_ok = _is_valid_api_key(token)
                else:
                    # user tokens must reference a live user (revocation),
                    # "service" tokens are API-key-minted automation
                    sub = payload.get("sub", "service")
                    api_key_ok = sub == "service" or get_role(sub) is not None
                if not api_key_ok:
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
        """Broadcast to all clients on this pod, and (when WS_FANOUT_USE_REDIS
        is on) to clients on every other pod via Redis pub/sub.

        Redis-delivery succeeded → the local subscriber delivers here too;
        disabled or Redis down → pod-local delivery (today's behavior).
        """
        from app.api.ws.fanout import publish

        if await publish(data):
            return
        await self.broadcast_local(data)

    async def broadcast_local(self, data: dict):
        msg = json.dumps(data, default=str)  # model_dump() may carry datetimes
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
