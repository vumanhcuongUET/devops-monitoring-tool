# ADR-004: Real-time Communication

**Status**: Accepted
**Date**: 2025-06-10
**Context**: DevOps AI Agentics 2026 Platform

## Context

A monitoring dashboard needs to show updates in near real-time. We need to decide on the communication mechanism between backend and frontend.

## Decision

### Primary: WebSocket with Fallback to REST Polling

We implement a **hybrid approach**:

1. **WebSocket** (`/ws/live`) for real-time updates
2. **REST polling** as automatic fallback when WebSocket disconnects
3. **Toast notifications** for alert events

### WebSocket Events

The WebSocket broadcasts these event types:

```javascript
// Overview update - when any system status changes
{
  "type": "overview_updated",
  "data": { /* overview state */ }
}

// Alert firing
{
  "type": "alert_fired",
  "data": { /* alert details */ }
}

// Alert resolved
{
  "type": "alert_resolved",
  "data": { /* alert details */ }
}
```

### Fallback Behavior

When WebSocket disconnects:
1. Detect disconnection in frontend
2. Automatically switch to REST polling at 10-second interval
3. Attempt WebSocket reconnection with exponential backoff
4. Return to WebSocket when connection restored

### Implementation Details

**Backend (FastAPI):**
```python
@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Wait for events from background tasks
            # Broadcast to connected clients
    except WebSocketDisconnect:
        # Client disconnected
```

**Frontend (React):**
- Custom hook: `frontend/src/hooks/useWebSocket.ts`
- Manages connection state and automatic reconnection
- Falls back to REST polling on disconnect

### Background Alert Engine

**Architecture:**
- Runs as `asyncio` background task in FastAPI lifespan
- Evaluates alert rules every 60 seconds (configurable)
- Dispatches notifications via multiple channels
- Pushes events to WebSocket clients

**Notification Channels:**
- Slack webhook
- Email (SMTP)
- Generic webhook
- WebSocket broadcast

## Rationale

### Why WebSocket + Fallback?

1. **Real-time**: WebSocket provides instant updates without polling overhead
2. **Resilient**: Fallback ensures dashboard works even if WebSocket fails
3. **Server-Driven**: Backend pushes updates when they happen
4. **Efficient**: No unnecessary polling when WebSocket is connected

### Why Not Pure WebSocket?

- Firewalls and proxies may block WebSocket
- Connection may drop and need recovery
- Simpler implementation for some consumers

### Why Not Pure Polling?

- 10-second interval means up to 10-second delay
- Unnecessary load on server when nothing is changing
- Poor user experience for time-sensitive alerts

## Consequences

### Positive
- Near real-time updates for critical alerts
- Resilient to connection issues
- Good user experience

### Negative
- More complex frontend logic
- Need to manage connection state
- Potential duplicate events during reconnect

## Related Decisions

- [ADR-001: Architecture Overview](./001-architecture-overview.md)
- [ADR-002: No Database Architecture](./002-no-database-architecture.md)
