import { useEffect, useRef, useState, useCallback } from 'react';
import { WS_URL } from '../utils/constants';
import type { OverviewResponse } from '../types';

export function useWebSocket() {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const connectRef = useRef<() => void>(() => {});

  const connect = useCallback(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'overview_update' || msg.type === 'status_update') {
          setData(msg.data);
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      setConnected(false);
      reconnectTimer.current = setTimeout(() => connectRef.current(), 5000);
    };

    ws.onerror = () => ws.close();
  }, []);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    };
  }, [connect]);

  return { data, connected };
}
