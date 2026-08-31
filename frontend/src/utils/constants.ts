export const API_URL = import.meta.env.VITE_API_URL || '';
export const POLL_INTERVAL = 10000;
// Follow the page protocol: browsers block insecure ws:// on https pages
// (mixed content), which silently degraded live updates to polling.
export const WS_URL = import.meta.env.VITE_WS_URL ||
  `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/live`;
