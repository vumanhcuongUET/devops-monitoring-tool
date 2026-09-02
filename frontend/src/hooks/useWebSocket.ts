import { useEffect, useRef, useState, useCallback } from 'react';
import { WS_URL } from '../utils/constants';
import { getTokenManager } from '../auth/tokenManager';
import type { OverviewResponse, AlertEvent } from '../types';
import toast from 'react-hot-toast';

type WsMessage = { type: string; data: unknown };
type MessageListener = (msg: WsMessage) => void;
type StateListener = (connected: boolean) => void;

// Single shared WebSocket for the whole app (overview, actions, alerts
// previously opened one connection each). Refcounted: opens on first
// subscriber, closes when the last one unmounts.
const messageListeners = new Set<MessageListener>();
const stateListeners = new Set<StateListener>();
let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let connected = false;
let reconnectDelay = 5000;

function notifyState(value: boolean) {
  connected = value;
  for (const listener of stateListeners) listener(value);
}

function dispatchMessage(msg: WsMessage) {
  // Phase 2: Action events
  if (msg.type === 'action_created') {
    toast(`New action created: ${(msg.data as { id: string }).id}`, { icon: '⚡', duration: 3000 });
  } else if (msg.type === 'action_approved') {
    toast(`Action ${(msg.data as { id: string }).id} approved`, { icon: '✅' });
  } else if (msg.type === 'action_rejected') {
    toast(`Action ${(msg.data as { id: string }).id} rejected`, { icon: '❌' });
  } else if (msg.type === 'action_executed') {
    toast(`Action ${(msg.data as { id: string }).id} executed successfully`, { icon: '🚀' });
  } else if (msg.type === 'action_failed') {
    toast(`Action ${(msg.data as { id: string }).id} execution failed`, { icon: '💥' });
  } else if (msg.type === 'bulk_actions_created') {
    toast(`${(msg.data as { count: number }).count} actions created from Triage Card`, { icon: '⚡' });
  }

  for (const listener of messageListeners) listener(msg);
}

function connect() {
  if (ws) return;
  // The backend requires an authenticated token on /ws/live (query param,
  // same HMAC token as HTTP); re-read it on every connect so a refreshed
  // token is picked up. Phase 15: previously the socket sent no token at
  // all, so any AUTH_ENABLED deployment got a 4403 loop.
  const token = getTokenManager().getAccessToken();
  const url = token ? `${WS_URL}?token=${encodeURIComponent(token)}` : WS_URL;
  ws = new WebSocket(url);

  ws.onopen = () => {
    reconnectDelay = 5000;
    notifyState(true);
  };
  ws.onmessage = (event) => {
    try {
      dispatchMessage(JSON.parse(event.data));
    } catch {
      // ignore malformed messages
    }
  };
  ws.onclose = (event) => {
    ws = null;
    notifyState(false);
    if (event.code === 4403) {
      // Auth rejected (missing/expired/revoked token): surface it like the
      // HTTP client does instead of hammering the server forever.
      window.dispatchEvent(new Event('auth-required'));
      return;
    }
    // Exponential backoff, capped at 60s
    reconnectTimer = setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 60000);
  };
  ws.onerror = () => ws?.close();
}

function disconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  const closing = ws;
  ws = null;
  if (closing) {
    closing.onclose = null;  // intentional close — don't schedule reconnect
    closing.close();
  }
  notifyState(false);
}

function subscribeMessages(listener: MessageListener): () => void {
  messageListeners.add(listener);
  if (!ws) connect();
  return () => {
    messageListeners.delete(listener);
    if (messageListeners.size === 0 && stateListeners.size === 0) disconnect();
  };
}

function subscribeState(listener: StateListener): () => void {
  stateListeners.add(listener);
  if (!ws) connect();
  listener(connected);
  return () => {
    stateListeners.delete(listener);
    if (messageListeners.size === 0 && stateListeners.size === 0) disconnect();
  };
}

/** Overview data stream (shared socket). */
export function useWebSocket() {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [connectedState, setConnectedState] = useState(false);

  useEffect(() => {
    const offMessages = subscribeMessages((msg) => {
      if (msg.type === 'overview_update' || msg.type === 'status_update') {
        setData(msg.data as OverviewResponse);
      }
    });
    const offState = subscribeState(setConnectedState);
    return () => {
      offMessages();
      offState();
    };
  }, []);

  return { data, connected: connectedState };
}

type AlertHandler = (event: AlertEvent) => void;

/** Alert events + toast notifications (shared socket). */
export function useAlertNotifications(onAlert?: AlertHandler) {
  const handlerRef = useRef(onAlert);
  const stableHandler = useCallback((msg: WsMessage) => {
    if (msg.type !== 'alert_fired' && msg.type !== 'alert_resolved') return;
    const alertEvent = msg.data as AlertEvent;
    const isFiring = msg.type === 'alert_fired';

    // Dark card + severity border: white-on-green/red toasts failed contrast
    // (~1.9:1 / ~3.8:1) exactly when urgency peaks.
    toast(`${isFiring ? '🔴' : '🟢'} ${alertEvent.rule_name}: ${alertEvent.message}`, {
      duration: isFiring ? 8000 : 4000,
      style: {
        background: 'var(--color-bg-card)',
        color: 'var(--color-text-primary)',
        border: `1px solid ${isFiring ? 'var(--color-down)' : 'var(--color-healthy)'}`,
      },
    });

    handlerRef.current?.(alertEvent);
  }, []);

  useEffect(() => {
    handlerRef.current = onAlert;
  }, [onAlert]);

  useEffect(() => subscribeMessages(stableHandler), [stableHandler]);
}
