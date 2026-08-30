"""Unit tests for H1 cross-pod WS fanout (Phase 12)."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from app.api.ws.fanout import CHANNEL, publish, subscribe_loop
from app.api.ws.live import ConnectionManager


@pytest.mark.asyncio
async def test_publish_disabled_returns_false(monkeypatch):
    monkeypatch.setattr("app.api.ws.fanout.fanout_enabled", lambda: False)
    assert await publish({"type": "x"}) is False


@pytest.mark.asyncio
async def test_publish_enabled_sends_to_channel(monkeypatch):
    monkeypatch.setattr("app.api.ws.fanout.fanout_enabled", lambda: True)
    client = AsyncMock()
    monkeypatch.setattr("app.redis_client.get_redis", lambda: client)

    assert await publish({"type": "alert", "n": 1}) is True
    args = client.publish.await_args.args
    assert args[0] == CHANNEL
    assert json.loads(args[1]) == {"type": "alert", "n": 1}


@pytest.mark.asyncio
async def test_publish_redis_down_returns_false(monkeypatch):
    monkeypatch.setattr("app.api.ws.fanout.fanout_enabled", lambda: True)
    client = AsyncMock()
    client.publish.side_effect = ConnectionError("redis down")
    monkeypatch.setattr("app.redis_client.get_redis", lambda: client)

    assert await publish({"type": "x"}) is False


class FakePubSub:
    def __init__(self, messages):
        self._messages = messages
        self.channel = None
        self.closed = False

    async def subscribe(self, channel):
        self.channel = channel

    async def listen(self):
        for m in self._messages:
            await asyncio.sleep(0)
            yield m
        await asyncio.sleep(3600)  # park until cancelled (cancellable)

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_subscribe_loop_delivers_messages_and_cleans_up(monkeypatch):
    pubsub = FakePubSub([
        {"type": "subscribe"},  # control message — must be skipped
        {"type": "message", "data": json.dumps({"type": "alert"})},
        {"type": "message", "data": json.dumps({"type": "slo"})},
    ])
    client = type("C", (), {"pubsub": lambda self: pubsub})()
    monkeypatch.setattr("app.redis_client.get_redis", lambda: client)

    delivered = []
    task = asyncio.create_task(subscribe_loop(delivered.append))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert delivered == [{"type": "alert"}, {"type": "slo"}]
    assert pubsub.channel == CHANNEL
    assert pubsub.closed is True


def _manager_with_ws():
    mgr = ConnectionManager()
    ws = type("WS", (), {"send_text": AsyncMock()})()
    mgr.active.append(ws)
    return mgr, ws


@pytest.mark.asyncio
async def test_broadcast_routes_through_redis_when_published(monkeypatch):
    mgr, ws = _manager_with_ws()
    pub = AsyncMock(return_value=True)
    monkeypatch.setattr("app.api.ws.fanout.publish", pub)

    await mgr.broadcast({"type": "alert"})

    pub.assert_awaited_once_with({"type": "alert"})
    ws.send_text.assert_not_awaited()  # subscriber delivers locally too


@pytest.mark.asyncio
async def test_broadcast_falls_back_to_local_when_not_published(monkeypatch):
    mgr, ws = _manager_with_ws()
    monkeypatch.setattr("app.api.ws.fanout.publish", AsyncMock(return_value=False))

    await mgr.broadcast({"type": "alert"})

    ws.send_text.assert_awaited_once()
    assert json.loads(ws.send_text.await_args.args[0]) == {"type": "alert"}
