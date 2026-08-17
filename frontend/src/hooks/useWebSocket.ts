import { useEffect, useRef, useState, useCallback } from 'react';
import { WS_URL } from '../utils/constants';
import type { OverviewResponse } from '../types';
import toast from 'react-hot-toast';

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

        // Handle overview updates
        if (msg.type === 'overview_update' || msg.type === 'status_update') {
          setData(msg.data);
        }

        // Handle Phase 2: Action events
        if (msg.type === 'action_created') {
          toast(`New action created: ${msg.data.id}`, {
            icon: '⚡',
            duration: 3000,
          });
        } else if (msg.type === 'action_approved') {
          toast(`Action ${msg.data.id} approved`, {
            icon: '✅',
          });
        } else if (msg.type === 'action_rejected') {
          toast(`Action ${msg.data.id} rejected`, {
            icon: '❌',
          });
        } else if (msg.type === 'action_executed') {
          toast(`Action ${msg.data.id} executed successfully`, {
            icon: '🚀',
          });
        } else if (msg.type === 'action_failed') {
          toast(`Action ${msg.data.id} execution failed`, {
            icon: '💥',
          });
        } else if (msg.type === 'bulk_actions_created') {
          toast(`${msg.data.count} actions created from Triage Card`, {
            icon: '⚡',
          });
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
