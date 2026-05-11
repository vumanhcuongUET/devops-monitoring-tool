import { useEffect, useRef, useCallback } from 'react';
import { WS_URL } from '../utils/constants';
import type { AlertEvent } from '../types';
import toast from 'react-hot-toast';

type AlertHandler = (event: AlertEvent) => void;

const listeners = new Set<AlertHandler>();
let wsInstance: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

function connect() {
  if (wsInstance?.readyState === WebSocket.OPEN || wsInstance?.readyState === WebSocket.CONNECTING) {
    return;
  }

  const ws = new WebSocket(WS_URL);
  wsInstance = ws;

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'alert_fired' || msg.type === 'alert_resolved') {
        const alertEvent = msg.data as AlertEvent;
        const isFiring = msg.type === 'alert_fired';

        // Show toast notification
        const icon = isFiring ? '🔴' : '🟢';
        toast(`${icon} ${alertEvent.rule_name}: ${alertEvent.message}`, {
          duration: isFiring ? 8000 : 4000,
          style: {
            background: isFiring ? 'var(--color-down)' : 'var(--color-healthy)',
            color: '#fff',
          },
        });

        // Notify subscribers
        for (const handler of listeners) {
          handler(alertEvent);
        }
      }
    } catch {
      // ignore malformed messages
    }
  };

  ws.onclose = () => {
    reconnectTimer = setTimeout(connect, 5000);
  };

  ws.onerror = () => ws.close();
}

function disconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  wsInstance?.close();
  wsInstance = null;
}

export function useAlertNotifications(onAlert?: AlertHandler) {
  const handlerRef = useRef(onAlert);

  const stableHandler = useCallback((event: AlertEvent) => {
    handlerRef.current?.(event);
  }, []);

  useEffect(() => {
    handlerRef.current = onAlert;
  }, [onAlert]);

  useEffect(() => {
    if (onAlert) {
      listeners.add(stableHandler);
    }
    connect();

    return () => {
      if (onAlert) {
        listeners.delete(stableHandler);
      }
      // Only disconnect if no listeners remain
      if (listeners.size === 0) {
        disconnect();
      }
    };
  }, [onAlert, stableHandler]);
}
