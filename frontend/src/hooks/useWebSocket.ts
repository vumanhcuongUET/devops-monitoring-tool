import { useEffect, useRef, useState, useCallback } from 'react';
import { WS_URL } from '../utils/constants';
import type { OverviewResponse } from '../types';
import toast from 'react-hot-toast';

export function useWebSocket() {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const isCleaningUpRef = useRef(false);

  const connect = useCallback(() => {
    // Prevent new connections during cleanup
    if (isCleaningUpRef.current) return;

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
      // Only reconnect if not cleaning up
      if (!isCleaningUpRef.current) {
        reconnectTimerRef.current = setTimeout(() => {
          if (!isCleaningUpRef.current) {
            connect();
          }
        }, 5000);
      }
    };

    ws.onerror = () => ws.close();
  }, []);

  useEffect(() => {
    connect();

    return () => {
      isCleaningUpRef.current = true;

      // Clear reconnect timer
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }

      // Close WebSocket
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { data, connected };
}
